import os
import uuid
from typing import Any, List, Iterable, Dict, Tuple
import requests
from qdrant_client import QdrantClient
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

from cat.log import log
from cat.env import get_env


class VectorMemoryCollection:
    def __init__(
        self,
        agent_id: str,
        client: QdrantClient,
        collection_name: str,
        embedder_name: str,
        embedder_size: int,
    ):
        self.snapshot_info = None

        self.__agent_id = agent_id

        # Set attributes (metadata on the embedder are useful because it may change at runtime)
        self.client = client
        self.collection_name = collection_name
        self.embedder_name = embedder_name
        self.embedder_size = embedder_size

        # Check if memory collection exists also in vectorDB, otherwise create it
        self.create_db_collection_if_not_exists()

        # Check db collection vector size is same as embedder size
        self.check_embedding_size()

        # log collection info
        log.debug(f"Agent {self.__agent_id}, Collection {self.collection_name}:")
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
            self.save_dump()

        self.wipe()
        log.warning(f"Collection \"{self.collection_name}\" deleted")
        self.create_collection()

    def create_db_collection_if_not_exists(self):
        # is collection present in DB?
        collections_response = self.client.get_collections()
        for c in collections_response.collections:
            if c.name == self.collection_name:
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
        return Filter(must=[FieldCondition(key="group_id", match=MatchValue(value=self.__agent_id))])

    def _qdrant_combine_filter_with_tenant(self, other_filter: Filter | None = None):
        combined_filter = self._qdrant_build_tenant_filter()

        if other_filter:
            combined_filter = Filter(must=[*combined_filter.must, *other_filter.must])

        return combined_filter

    # adapted from https://github.com/langchain-ai/langchain/blob/bfc12a4a7644cfc4d832cc4023086a7a5374f46a/libs/langchain/langchain/vectorstores/qdrant.py#L1941
    def _build_condition(self, key: str, value: Any) -> List[FieldCondition]:
        out = []

        if isinstance(value, Dict):
            for _key, value in value.items():
                out.extend(self._build_condition(f"{key}.{_key}", value))
        elif isinstance(value, List):
            for _value in value:
                out.extend(self._build_condition(f"{key}[]" if isinstance(_value, Dict) else f"{key}", _value))
        else:
            out.append(
                FieldCondition(
                    key=f"metadata.{key}",
                    match=MatchValue(value=value),
                )
            )

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
        **kwargs: Any,
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
                "group_id": self.__agent_id,
            },
            vector=vector,
        )

        update_status = self.client.upsert(collection_name=self.collection_name, points=[point], **kwargs)

        if update_status.status == "completed":
            # returning stored point
            return point # TODOV2 return internal MemoryPoint

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

        payloads = [p | {"group_id": self.__agent_id} for p in payloads]
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
    ) -> List:
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
        langchain_documents_from_points = []
        for m in memories:
            langchain_documents_from_points.append(
                (
                    Document(
                        page_content=m.payload.get("page_content"),
                        metadata=m.payload.get("metadata") or {},
                    ),
                    m.score,
                    m.vector,
                    m.id,
                )
            )

        # we'll move out of langchain conventions soon and have our own cat Document
        # for doc, score, vector in langchain_documents_from_points:
        #    doc.lc_kwargs = None

        return langchain_documents_from_points

    # retrieve all the points in the collection
    def get_all_points(
        self, limit: int = 10000, offset: str | None = None
    ) -> Tuple[List[Record], int | str | None | Any]:
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
    def save_dump(self, folder="dormouse/"):
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
        response = requests.get(snapshot_url_in)
        open(snapshot_url_out, "wb").write(response.content)

        new_name = os.path.join(folder, alias.replace("/", "-") + ".snapshot")
        os.rename(snapshot_url_out, new_name)

        for s in self.client.list_snapshots(self.collection_name):
            self.client.delete_snapshot(collection_name=self.collection_name, snapshot_name=s.name)
        log.warning(f"Dump \"{new_name}\" completed")

    def get_vectors_count(self) -> int:
        tenant_filter = self._qdrant_build_tenant_filter()

        return self.client.count(collection_name=self.collection_name, count_filter=tenant_filter).count

    def wipe(self) -> bool:
        tenant_filter = self._qdrant_build_tenant_filter()

        try:
            self.client.delete(collection_name=self.collection_name, points_selector=tenant_filter)
            return True
        except Exception as e:
            log.error(f"Error deleting collection {self.collection_name}: {e}")
            return False
