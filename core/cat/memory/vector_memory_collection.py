import asyncio
import os
import uuid
from typing import Any, List, Dict, Tuple, Final
import aiofiles
import httpx
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
    PayloadSchemaType,
)

from cat.db.vector_database import get_vector_db
from cat.env import get_env
from cat.log import log
from cat.memory.utils import (
    ContentType,
    DocumentRecall,
    MultimodalContent,
    VectorMemoryConfig,
    VectorEmbedderSize,
    to_document_recall,
)


class VectorMemoryCollection:
    def __init__(self, agent_id: str, collection_name: str, vector_memory_config: VectorMemoryConfig):
        self.snapshot_info = None

        self.agent_id: Final[str] = agent_id

        # Set attributes (metadata on the embedder are useful because it may change at runtime)
        self.collection_name: Final[str] = collection_name
        self.embedder_name: Final[str] = vector_memory_config.embedder_name
        self.embedder_sizes: Final[VectorEmbedderSize] = vector_memory_config.embedder_size

        # connects to Qdrant and creates self.client attribute
        self.client: Final = get_vector_db()

        # Check if memory collection exists also in vectorDB, otherwise create it
        self._create_db_collection_if_not_exists()

        # Check db collection vector sizes are same as embedder sizes
        self._check_embedding_sizes()

        log.debug(f"Agent {self.agent_id}, Collection {self.collection_name}:")
        log.debug(self.client.get_collection(self.collection_name))

    def _check_embedding_sizes(self):
        collection_info = self.client.get_collection(self.collection_name)

        # Check if the collection exists and has the correct vector configurations
        # Single vector configuration (legacy)
        if (
                hasattr(collection_info.config.params, "vectors")
                and collection_info.config.params.vectors.size != self.embedder_sizes.text
        ):
            self._recreate_collection()
            return

        # Multiple vector configurations
        vectors_config = collection_info.config.params.vectors_config
        needs_update = False

        text_lbl = str(ContentType.TEXT)
        image_lbl = str(ContentType.IMAGE)
        audio_lbl = str(ContentType.AUDIO)

        if text_lbl in vectors_config and vectors_config[text_lbl].size != self.embedder_sizes.text:
            needs_update = True
        if self.embedder_sizes.image and (
                image_lbl not in vectors_config or vectors_config[image_lbl].size != self.embedder_sizes.image
        ):
            needs_update = True
        if self.embedder_sizes.audio and (
                audio_lbl not in vectors_config or
                vectors_config[audio_lbl].size != self.embedder_sizes.audio
        ):
            needs_update = True

        if needs_update:
            self._recreate_collection()

    def _recreate_collection(self):
        """Recreate the collection with updated vector configurations"""
        log.warning(f"Collection {self.collection_name} has different embedder sizes. Recreating...")

        if get_env("CCAT_SAVE_MEMORY_SNAPSHOTS") == "true":
            asyncio.get_event_loop().run_until_complete(self._save_dump())

        self.client.delete_collection(self.collection_name)
        self._create_collection()

    def _create_db_collection_if_not_exists(self):
        # is collection present in DB?
        collections_response = self.client.get_collections()
        if any(c.name == self.collection_name for c in collections_response.collections):
            # collection exists. Do nothing
            log.info(
                f"Collection \"{self.collection_name}\" already present in vector store"
            )
            return

        self._create_collection()

    # create collection
    def _create_collection(self):
        log.warning(f"Creating collection {self.collection_name} ...")

        # Create vector config for each modality
        vectors_config = {
            str(ContentType.TEXT): VectorParams(size=self.embedder_sizes.text, distance=Distance.COSINE)
        }

        if self.embedder_sizes.image:
            vectors_config[str(ContentType.IMAGE)] = VectorParams(
                size=self.embedder_sizes.image, distance=Distance.COSINE
            )

        if self.embedder_sizes.audio:
            vectors_config[str(ContentType.AUDIO)] = VectorParams(
                size=self.embedder_sizes.audio, distance=Distance.COSINE
            )

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=vectors_config,
            optimizers_config=OptimizersConfigDiff(memmap_threshold=20000, indexing_threshold=20000),
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

        # if the client is remote, create an index on the tenant_id field
        if self.db_is_remote():
            self.create_payload_index("tenant_id", PayloadSchemaType.KEYWORD)

    def _tenant_field_condition(self) -> FieldCondition:
        return FieldCondition(key="tenant_id", match=MatchValue(value=self.agent_id))

    # adapted from https://github.com/langchain-ai/langchain/blob/bfc12a4a7644cfc4d832cc4023086a7a5374f46a/libs/langchain/langchain/vectorstores/qdrant.py#L1941
    # see also https://github.com/langchain-ai/langchain/blob/bfc12a4a7644cfc4d832cc4023086a7a5374f46a/libs/langchain/langchain/vectorstores/qdrant.py#L1965
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

    def create_payload_index(self, field_name: str, field_type: PayloadSchemaType):
        """
        Create a new index on a field of the payload for an existing collection.

        Args:
            field_name: Name of the field on which to create the index
            field_type: Type of the index (es. PayloadSchemaType.KEYWORD)
        """
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=field_type
            )
        except Exception as e:
            log.error(f"Agent id {self.agent_id}. Error when creating a schema index: {e}")

    def get_payload_indexes(self) -> Dict:
        """
        Retrieve the indexes configured on the collection.

        Returns:
            Dictionary with the configuration of the indexes
        """
        collection_info = self.client.get_collection(self.collection_name)
        return collection_info.payload_schema

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
            scroll_filter=Filter(must=[self._tenant_field_condition(), HasIdCondition(has_id=points)]),
            limit=len(points),
            with_payload=True,
            with_vectors=True,
        )

        points_found, _ = results
        return points_found

    def add_point(
        self,
        content: MultimodalContent,
        vectors: Dict[ContentType, List[float]],
        metadata: Dict = None,
        id: str | None = None,
        **kwargs,
    ) -> PointStruct | None:
        """
        Add a multimodal point to the vectorstore.

        Args:
            content: MultimodalContent object containing text, image and/or audio data
            vectors: Dictionary mapping modality to its vector representation
            metadata: Optional metadata dictionary
            id: Optional unique identifier

        Returns:
            PointStruct: The stored point
        """

        point = PointStruct(
            id=id or uuid.uuid4().hex,
            payload={
                "page_content": content.model_dump(),
                "metadata": metadata,
                "tenant_id": self.agent_id,
            },
            vector={str(k): v for k, v in vectors.items()}  # Using named vectors
        )

        update_status = self.client.upsert(collection_name=self.collection_name, points=[point], **kwargs)

        if update_status.status == "completed":
            # returning stored point
            return point

        return None

    # add points in collection
    def add_points(self, ids: List, payloads: List[Payload], vectors: List[Dict[str, List[float]]]) -> UpdateResult:
        """
        Upsert memories in batch mode
        Args:
            ids: the ids of the points
            payloads: the payloads of the points
            vectors: the vectors of the points

        Returns:
            the response of the upsert operation
        """

        payloads = [{**p, **{"tenant_id": self.agent_id}} for p in payloads]
        points = Batch(ids=ids, payloads=payloads, vectors=vectors)

        return self.client.upsert(collection_name=self.collection_name, points=points)

    def delete_points_by_metadata_filter(self, metadata: Dict | None = None) -> UpdateResult:
        conditions = [self._tenant_field_condition()]
        if metadata:
            conditions.extend([
            condition for key, value in metadata.items() for condition in self._build_condition(key, value)
        ])

        res = self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(must=conditions),
        )
        return res

    # delete point in collection
    def delete_points(self, points_ids: List) -> UpdateResult:
        return self.client.delete(collection_name=self.collection_name, points_selector=points_ids)

    # retrieve similar memories from embedding
    def recall_memories_from_embedding(
        self,
        query_vectors: Dict[ContentType, List[float]],
        metadata: Dict | None = None,
        k: int | None = 5,
        threshold: float | None =None
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
            query_vectors: Dictionary mapping modality to query vector
            metadata: Optional metadata filter
            k: Number of results to return
            threshold: Optional similarity threshold

        Returns:
            List: List of DocumentRecall.
        """

        conditions = [self._tenant_field_condition()]
        if metadata:
            conditions.extend([
                condition for key, value in metadata.items() for condition in self._build_condition(key, value)
            ])

        memories = self.client.search(
            collection_name=self.collection_name,
            query_vector={str(k): v for k, v in query_vectors.items()},  # Using named vectors for search
            query_filter=Filter(must=conditions),
            with_payload=True,
            with_vectors=True,
            limit=k,
            score_threshold=threshold,
            search_params=SearchParams(
                quantization=QuantizationSearchParams(
                    ignore=False,
                    rescore=True,
                    oversampling=2.0,
                )
            ),
        )

        # convert Qdrant points to a structure containing langchain.Document and its information
        return [to_document_recall(m) for m in memories]

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
        memories = [to_document_recall(p) for p in all_points]

        return memories

    # retrieve all the points in the collection
    def get_all_points(self, limit: int = 10000, offset: str | None = None) -> Tuple[List[Record], int | str | None]:
        """
        Retrieve all the points in the collection with an optional offset and limit.

        Args:
            limit: The maximum number of points to retrieve.
            offset: The offset from which to start retrieving points.

        Returns:
            Tuple: A tuple containing the list of points and the next offset.
        """

        # retrieving the points
        return self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(must=[self._tenant_field_condition()]),
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
        return self.client.count(
            collection_name=self.collection_name,
            count_filter=Filter(must=[self._tenant_field_condition()]),
        ).count

    def destroy_all_points(self) -> bool:
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(must=[self._tenant_field_condition()]),
            )
            return True
        except Exception as e:
            log.error(f"Error deleting collection {self.collection_name}, agent {self.agent_id}: {e}")
            return False
