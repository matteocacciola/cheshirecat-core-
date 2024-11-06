import asyncio
import os
import uuid
from typing import Any, List, Iterable, Dict, Tuple
import aiofiles
import httpx
from pydantic import BaseModel
from qdrant_client.qdrant_remote import QdrantRemote
from qdrant_client.http.models import (
    Batch,
    PointStruct,
    Distance,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    SearchParams,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    QuantizationSearchParams,
    CreateAliasOperation,
    CreateAlias,
    OptimizersConfigDiff,
    Record,
    UpdateResult,
    HasIdCondition,
    Payload,
)
from langchain.docstore.document import Document

from cat.db.vector_database import get_vector_db
from cat.log import log
from cat.env import get_env
from cat.utils import Enum as BaseEnum, BaseModelDict


class VectoryMemoryCollectionTypes(BaseEnum):
    EPISODIC = "episodic"
    DECLARATIVE = "declarative"
    PROCEDURAL = "procedural"


class VectorEmbedderSize(BaseModel):
    text: int
    image: int | None = None
    audio: int | None = None


class VectorMemoryConfig(BaseModelDict):
    embedder_name: str
    embedder_size: VectorEmbedderSize


class DocumentRecall(BaseModelDict):
    """
    Langchain `Document` retrieved from the episodic memory, with the similarity score, the list of embeddings and the
    id of the memory.
    """

    document: Document
    score: float | None = None
    vector: List[float] = []
    id: str | None = None


class VectorMemoryCollection:
    def __init__(self, agent_id: str, collection_name: str, vector_memory_config: VectorMemoryConfig):
        self.snapshot_info = None

        self.agent_id = agent_id

        # Set attributes (metadata on the embedder are useful because it may change at runtime)
        self.collection_name = collection_name
        self.embedder_name = vector_memory_config.embedder_name
        self.embedder_size = vector_memory_config.embedder_size.text

        # connects to Qdrant and creates self.client attribute
        self.client = get_vector_db()

        # Check if memory collection exists also in vectorDB, otherwise create it
        self.create_db_collection_if_not_exists()

        # Check db collection vector size is same as embedder size
        self.check_embedding_size()

        # log collection info
        log.debug(f"Agent {self.agent_id}, Collection {self.collection_name}:")
        log.debug(self.client.get_collection(self.collection_name))

    def check_embedding_size(self):
        # having the same size does not necessarily imply being the same embedder
        # having vectors with the same size but from different embedder in the same vector space is wrong
        same_size = (
            self.client.get_collection(self.collection_name).config.params.vectors.size
            == self.embedder_size
        )
        alias = self.embedder_name + "_" + self.collection_name
        if (
            same_size and alias == self.client.get_collection_aliases(self.collection_name)
                .aliases[0]
                .alias_name
        ):
            log.debug(f"Collection \"{self.collection_name}\" has the same embedder")
            return

        log.warning(f"Collection \"{self.collection_name}\" has different embedder")
        # Memory snapshot saving can be turned off in the .env file with:
        # SAVE_MEMORY_SNAPSHOTS=false
        if get_env("CCAT_SAVE_MEMORY_SNAPSHOTS") == "true":
            # dump collection on disk before deleting
            asyncio.get_event_loop().run_until_complete(self.save_dump())

        self.client.delete_collection(self.collection_name)
        log.warning(f"Collection \"{self.collection_name}\" deleted")
        self.create_collection()

    def create_db_collection_if_not_exists(self):
        # is collection present in DB?
        collections_response = self.client.get_collections()
        if any(c.name == self.collection_name for c in collections_response.collections):
            # collection exists. Do nothing
            log.info(
                f"Collection \"{self.collection_name}\" already present in vector store"
            )
            return

        self.create_collection()

    # create collection
    def create_collection(self):
        log.warning(f"Creating collection \"{self.collection_name}\" ...")
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.embedder_size, distance=Distance.COSINE
            ),
            # hybrid mode: original vector on Disk, quantized vector in RAM
            optimizers_config=OptimizersConfigDiff(memmap_threshold=20000),
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8, quantile=0.95, always_ram=True
                )
            ),
            # shard_number=3,
        )

        self.client.update_collection_aliases(
            change_aliases_operations=[
                CreateAliasOperation(
                    create_alias=CreateAlias(
                        collection_name=self.collection_name,
                        alias_name=self.embedder_name + "_" + self.collection_name,
                    )
                )
            ]
        )

    # adapted from https://github.com/langchain-ai/langchain/blob/bfc12a4a7644cfc4d832cc4023086a7a5374f46a/libs/langchain/langchain/vectorstores/qdrant.py#L1965
    def _qdrant_filter_from_dict(self, dict_filter: Dict) -> Filter | None:
        if not dict_filter:
            return None

        return Filter(
            must=[condition for key, value in dict_filter.items() for condition in self._build_condition(key, value)]
        )

    def _qdrant_build_tenant_filter(self) -> Filter:
        return Filter(must=[FieldCondition(key="group_id", match=MatchValue(value=self.agent_id))])

    def _qdrant_combine_filter_with_tenant(self, other_filter: Filter | None = None):
        combined_filter = self._qdrant_build_tenant_filter()

        if other_filter:
            combined_filter = Filter(must=[*combined_filter.must, *other_filter.must])

        return combined_filter

    # adapted from https://github.com/langchain-ai/langchain/blob/bfc12a4a7644cfc4d832cc4023086a7a5374f46a/libs/langchain/langchain/vectorstores/qdrant.py#L1941
    def _build_condition(self, key: str, value: Any) -> List[FieldCondition]:
        out = []

        if isinstance(value, Dict):
            out.extend(self._build_condition(f"{key}.{k}", v) for k, v in value.items())
        elif isinstance(value, List):
            out.extend(
                self._build_condition(f"{key}[]" if isinstance(v, Dict) else f"{key}", v) for v in value
            )
        else:
            out.append(FieldCondition(key=f"metadata.{key}", match=MatchValue(value=value)))

        return out

    def retrieve_points(self, points: List) -> List[Record]:
        """
        Retrieve points from the collection by their ids

        Args:
            points: the ids of the points to retrieve

        Returns:
            the list of points
        """

        results = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=self._qdrant_combine_filter_with_tenant(Filter(must=[HasIdCondition(has_id=points)])),
            limit=len(points),
            with_payload=True,
            with_vectors=True,
        )

        points_found, _ = results
        return points_found

    def add_point(
        self,
        content: str,
        vector: Iterable,
        metadata: Dict = None,
        id: str | None = None,
        **kwargs,
    ) -> PointStruct | None:
        """Add a point (and its metadata) to the vectorstore.

        Args:
            content: original text.
            vector: Embedding vector.
            metadata: Optional metadata dictionary associated with the text.
            id:
                Optional id to associate with the point. Id has to be an uuid-like string.

        Returns:
            PointStruct: The stored point.
        """

        point = PointStruct(
            id=id or uuid.uuid4().hex,
            payload={
                "page_content": content,
                "metadata": metadata,
                "group_id": self.agent_id,
            },
            vector=vector,
        )

        update_status = self.client.upsert(collection_name=self.collection_name, points=[point], **kwargs)

        if update_status.status == "completed":
            # returning stored point
            return point

        return None

    # add points in collection
    def add_points(self, ids: List, payloads: List[Payload], vectors: List):
        """
        Upsert memories in batch mode
        Args:
            ids: the ids of the points
            payloads: the payloads of the points
            vectors: the vectors of the points

        Returns:
            the response of the upsert operation
        """

        payloads = [p | {"group_id": self.agent_id} for p in payloads]
        points = Batch(ids=ids, payloads=payloads, vectors=vectors)

        res = self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return res

    def delete_points_by_metadata_filter(self, metadata=None) -> UpdateResult:
        combined_filter = self._qdrant_combine_filter_with_tenant(self._qdrant_filter_from_dict(metadata))

        res = self.client.delete(
            collection_name=self.collection_name,
            points_selector=combined_filter,
        )
        return res

    # delete point in collection
    def delete_points(self, points_ids: List) -> UpdateResult:
        res = self.client.delete(
            collection_name=self.collection_name,
            points_selector=points_ids,
        )
        return res

    # retrieve similar memories from embedding
    def recall_memories_from_embedding(
        self, embedding, metadata: Dict | None = None, k: int | None = 5, threshold: float | None =None
    ) -> List[DocumentRecall]:
        """
        Retrieve memories from the collection based on an embedding vector. The memories are sorted by similarity to the
        embedding vector. The metadata filter is applied to the memories before retrieving them. The number of memories
        to retrieve is limited by the k parameter. The threshold parameter is used to filter out memories with a score
        below the threshold. The memories are returned as a list of tuples, where each tuple contains a Document, the
        similarity score, and the embedding vector of the memory. The Document contains the page content and metadata of
        the memory. The similarity score is a float between 0 and 1, where 1 is the highest similarity. The embedding
        vector is a list of floats. The list of tuples is sorted by similarity score in descending order. If the k
        parameter is None, all memories are retrieved. If the threshold parameter is None, no memories are filtered out.

        Args:
            embedding: Embedding vector.
            metadata: Dictionary containing metadata filter.
            k: Number of memories to retrieve.
            threshold: Similarity threshold.

        Returns:
            List: List of DocumentRecall.
        """
        combined_filter = self._qdrant_combine_filter_with_tenant(self._qdrant_filter_from_dict(metadata))

        # retrieve memories
        memories = self.client.search(
            collection_name=self.collection_name,
            query_vector=embedding,
            query_filter=combined_filter,
            with_payload=True,
            with_vectors=True,
            limit=k,
            score_threshold=threshold,
            search_params=SearchParams(
                quantization=QuantizationSearchParams(
                    ignore=False,
                    rescore=True,
                    oversampling=2.0,  # Available as of v1.3.0
                )
            ),
        )

        # convert Qdrant points to langchain.Document
        langchain_documents_from_points = [DocumentRecall(
            document=Document(page_content=m.payload.get("page_content"), metadata=m.payload.get("metadata") or {}),
            score=m.score,
            vector=m.vector,
            id=m.id,
        ) for m in memories]

        # we'll move out of langchain conventions soon and have our own cat Document
        # for doc, score, vector in langchain_documents_from_points:
        #    doc.lc_kwargs = None

        return langchain_documents_from_points

    def recall_all_memories(self) -> List[DocumentRecall]:
        """
        Retrieve the entire memories. It is similar to `recall_memories_from_embedding`, but without the embedding
        vector. Like `get_all_points`, it retrieves all the memories in the collection. The memories are returned in the
        same format as `recall_memories_from_embedding`.

        Returns:
            List: List of DocumentRecall, like `recall_memories_from_embedding`, but with the nulled 2nd element
            (the score).

        See Also:
            VectorMemoryCollection.recall_memories_from_embedding
            VectorMemoryCollection.get_all_points
        """
        all_points, _ = self.get_all_points()
        memories = [DocumentRecall(document=Document(**p.payload), vector=p.vector, id=p.id) for p in all_points]

        return memories

    # retrieve all the points in the collection
    def get_all_points(
        self, limit: int = 10000, offset: str | None = None
    ) -> Tuple[List[Record], int | str | None]:
        """Retrieve all the points in the collection with an optional offset and limit."""

        tenant_filter = self._qdrant_build_tenant_filter()

        # retrieving the points
        return self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=tenant_filter,
            with_vectors=True,
            offset=offset,  # Start from the given offset, or the beginning if None.
            limit=limit  # Limit the number of points retrieved to the specified limit.
        )

    def db_is_remote(self):
        return isinstance(self.client._client, QdrantRemote)

    # dump collection on disk before deleting
    async def save_dump(self, folder="dormouse/"):
        # only do snapshotting if using remote Qdrant
        if not self.db_is_remote():
            return

        host = self.client._client._host
        port = self.client._client._port

        if os.path.isdir(folder):
            log.info(f"Directory dormouse exists")
        else:
            log.warning(f"Directory dormouse does NOT exists, creating it.")
            os.mkdir(folder)

        self.snapshot_info = self.client.create_snapshot(collection_name=self.collection_name)
        snapshot_url_in = (
            "http://"
            + str(host)
            + ":"
            + str(port)
            + "/collections/"
            + self.collection_name
            + "/snapshots/"
            + self.snapshot_info.name
        )
        snapshot_url_out = os.path.join(folder, self.snapshot_info.name)
        # rename snapshots for an easier restore in the future
        alias = self.client.get_collection_aliases(self.collection_name).aliases[0].alias_name

        async with httpx.AsyncClient() as client:
            response = await client.get(snapshot_url_in)
            async with aiofiles.open(snapshot_url_out, "wb") as f:
                await f.write(response.content)  # Write the content asynchronously

        new_name = os.path.join(folder, alias.replace("/", "-") + ".snapshot")
        os.rename(snapshot_url_out, new_name)

        for s in self.client.list_snapshots(self.collection_name):
            self.client.delete_snapshot(collection_name=self.collection_name, snapshot_name=s.name)
        log.warning(f"Dump \"{new_name}\" completed")

    def get_vectors_count(self) -> int:
        tenant_filter = self._qdrant_build_tenant_filter()

        return self.client.count(collection_name=self.collection_name, count_filter=tenant_filter).count

    def destroy(self) -> bool:
        tenant_filter = self._qdrant_build_tenant_filter()

        try:
            self.client.delete(collection_name=self.collection_name, points_selector=tenant_filter)
            return True
        except Exception as e:
            log.error(f"Error deleting collection {self.collection_name}, agent {self.agent_id}: {e}")
            return False
