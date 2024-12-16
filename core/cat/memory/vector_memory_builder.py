import os
from typing import Final
import aiofiles
import httpx
from qdrant_client.qdrant_remote import QdrantRemote
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    CreateAliasOperation,
    CreateAlias,
    OptimizersConfigDiff,
    PayloadSchemaType,
)

from cat.db.vector_database import get_vector_db
from cat.env import get_env
from cat.log import log
from cat.memory.utils import VectorMemoryCollectionTypes
from cat.utils import singleton


@singleton
class VectorMemoryBuilder:
    def __init__(self):
        self.__snapshot_info = None

        # connects to Qdrant and creates self.__client attribute
        self.__client: Final = get_vector_db()

    def build(self):
        for collection_name in VectorMemoryCollectionTypes:
            # is collection present in DB?
            collections_response = self.__client.get_collections()
            if any(c.name == str(collection_name) for c in collections_response.collections):
                # collection exists. Do nothing
                log.info(
                    f"Collection \"{collection_name}\" already present in vector store"
                )
                continue

            self.__create_collection(str(collection_name))

    # create collection
    def __create_collection(self, collection_name: str):
        """
        Create a new collection in the vector database.

        Args:
            collection_name: Name of the collection to create
        """

        log.warning(f"Creating collection \"{collection_name}\" ...")
        self.__client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=self.lizard.embedder_size.text, distance=Distance.COSINE
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

        self.__client.update_collection_aliases(
            change_aliases_operations=[
                CreateAliasOperation(
                    create_alias=CreateAlias(
                        collection_name=collection_name,
                        alias_name=self.lizard.embedder_name + "_" +collection_name,
                    )
                )
            ]
        )

        # if the client is remote, create an index on the tenant_id field
        if self.__db_is_remote():
            self.__create_payload_index("tenant_id", PayloadSchemaType.KEYWORD, collection_name)

    def __db_is_remote(self):
        return isinstance(self.__client._client, QdrantRemote)

    def __create_payload_index(self, field_name: str, field_type: PayloadSchemaType, collection_name: str):
        """
        Create a new index on a field of the payload for an existing collection.

        Args:
            field_name: Name of the field on which to create the index
            field_type: Type of the index (es. PayloadSchemaType.KEYWORD)
            collection_name: Name of the collection on which to create the index
        """
        try:
            self.__client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_type
            )
        except Exception as e:
            log.error(f"Error when creating a schema index: {e}")

    async def rebuild(self):
        for collection_name in VectorMemoryCollectionTypes:
            await self.__check_embedding_size(str(collection_name))

    async def __check_embedding_size(self, collection_name: str):
        # having the same size does not necessarily imply being the same embedder
        # having vectors with the same size but from different embedder in the same vector space is wrong
        same_size = (
            self.__client.get_collection(collection_name).config.params.vectors.size
            == self.lizard.embedder_size
        )
        local_alias = self.lizard.embedder_name + "_" + collection_name
        db_aliases = self.__client.get_collection_aliases(collection_name).aliases

        if same_size and local_alias == db_aliases[0].alias_name:
            log.debug(f"Collection \"{collection_name}\" has the same embedder")
            return

        log.warning(f"Collection \"{collection_name}\" has different embedder")
        # Memory snapshot saving can be turned off in the .env file with:
        # SAVE_MEMORY_SNAPSHOTS=false
        if get_env("CCAT_SAVE_MEMORY_SNAPSHOTS") == "true":
            # dump collection on disk before deleting
            await self.__save_dump(collection_name)

        self.__client.delete_collection(collection_name)
        log.warning(f"Collection \"{collection_name}\" deleted")
        self.__create_collection(collection_name)

    # dump collection on disk before deleting
    async def __save_dump(self, collection_name: str, folder="dormouse/"):
        # only do snapshotting if using remote Qdrant
        if not self.__db_is_remote():
            return

        host = self.__client._client._host
        port = self.__client._client._port

        if os.path.isdir(folder):
            log.info(f"Directory dormouse exists")
        else:
            log.warning(f"Directory dormouse does NOT exists, creating it.")
            os.mkdir(folder)

        snapshot_info = self.__client.create_snapshot(collection_name=collection_name)
        snapshot_url_in = (
            "http://"
            + str(host)
            + ":"
            + str(port)
            + "/collections/"
            + collection_name
            + "/snapshots/"
            + self.__snapshot_info.name
        )
        snapshot_url_out = os.path.join(folder, snapshot_info.name)
        # rename snapshots for an easier restore in the future
        alias = self.__client.get_collection_aliases(collection_name).aliases[0].alias_name

        async with httpx.AsyncClient() as client:
            response = await client.get(snapshot_url_in)
            async with aiofiles.open(snapshot_url_out, "wb") as f:
                await f.write(response.content)  # Write the content asynchronously

        new_name = os.path.join(folder, alias.replace("/", "-") + ".snapshot")
        os.rename(snapshot_url_out, new_name)

        for s in self.__client.list_snapshots(collection_name):
            self.__client.delete_snapshot(collection_name=collection_name, snapshot_name=s.name)
        log.warning(f"Dump \"{new_name}\" completed")

    @property
    def lizard(self) -> "BillTheLizard":
        from cat.looking_glass.bill_the_lizard import BillTheLizard
        return BillTheLizard()