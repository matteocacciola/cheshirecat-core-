from typing import Dict, List, Any
from pydantic import BaseModel
from fastapi import Query, APIRouter, Depends
from qdrant_client.http.models import UpdateResult, Record

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.factory.embedder import EmbedderFactory
from cat.memory.vector_memory_collection import VectorMemoryCollectionTypes, DocumentRecall
from cat.routes.routes_utils import (
    MemoryPointBase,
    MemoryPoint,
    upsert_memory_point,
    verify_memory_point_existence,
    memory_collection_is_accessible,
    create_dict_parser,
)

router = APIRouter()


class RecallResponseQuery(BaseModel):
    text: str
    vector: List[float]


class RecallResponseVectors(BaseModel):
    embedder: str
    collections: Dict[str, List[Dict[str, Any]]]


class RecallResponse(BaseModel):
    query: RecallResponseQuery
    vectors: RecallResponseVectors


class GetPointsInCollectionResponse(BaseModel):
    points: List[Record]
    next_offset: int | str | None


class DeleteMemoryPointResponse(BaseModel):
    deleted: str


class DeleteMemoryPointsByMetadataResponse(BaseModel):
    deleted: UpdateResult


@router.get("/recall", response_model=RecallResponse)
async def recall_memory_points_from_text(
    text: str = Query(description="Find memories similar to this text."),
    k: int = Query(default=100, description="How many memories to return."),
    metadata: Dict[str, Any] = Depends(create_dict_parser(
        "metadata",
        description="Flat dictionary where each key-value pair represents a filter."
                    "The memory points returned will match the specified metadata criteria."
    )),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.READ)),
) -> RecallResponse:
    """
    Search k memories similar to given text with specified metadata criteria.

    Example
    ----------
    ```
    collection = "episodic"
    content = "MIAO!"
    metadata = {"custom_key": "custom_value"}
    req_json = {
        "content": content,
        "metadata": metadata,
    }
    # create a point
    res = requests.post(
        f"http://localhost:1865/memory/collections/{collection}/points", json=req_json
    )

    # recall with metadata
    req_json = {
        "text": "CAT",
        "metadata":{"custom_key":"custom_value"}
    }
    res = requests.post(
        f"http://localhost:1865/memory/recall", json=req_json
    )
    json = res.json()
    print(json)
    ```
    """

    def build_memory_dict(document_recall: DocumentRecall) -> Dict[str, Any]:
        memory_dict = dict(document_recall.document)
        memory_dict.pop("lc_kwargs", None)  # langchain stuff, not needed
        memory_dict["id"] = document_recall.id
        memory_dict["score"] = float(document_recall.score) if document_recall.score else None
        memory_dict["vector"] = document_recall.vector
        return memory_dict

    def get_memories(c: VectorMemoryCollectionTypes) -> List:
        # only episodic collection has users, and then a source
        if c == VectorMemoryCollectionTypes.EPISODIC:
            metadata["source"] = cats.stray_cat.user.id
        else:
            metadata.pop("source", None)
        return ccat.memory.vectors.collections[str(c)].recall_memories_from_embedding(
            query_embedding, k=k, metadata=metadata
        )

    ccat = cats.cheshire_cat

    # Embed the query to plot it in the Memory page
    query_embedding = ccat.embedder.embed_query(text)

    # Loop over collections and retrieve nearby memories
    recalled = {
        str(c): [build_memory_dict(document_recall) for document_recall in get_memories(c)]
        for c in VectorMemoryCollectionTypes
    }

    config_class = EmbedderFactory(ccat.plugin_manager).get_config_class_from_adapter(ccat.embedder.__class__)

    return RecallResponse(
        query=RecallResponseQuery(text=text, vector=query_embedding),
        vectors=RecallResponseVectors(
            embedder=config_class.__name__ if config_class else None,
            collections=recalled
        )
    )


@router.post("/collections/{collection_id}/points", response_model=MemoryPoint)
async def create_memory_point(
    collection_id: str,
    point: MemoryPointBase,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.WRITE)),
) -> MemoryPoint:
    """Create a point in memory"""

    memory_collection_is_accessible(collection_id)

    return upsert_memory_point(collection_id, point, cats)


@router.put("/collections/{collection_id}/points/{point_id}", response_model=MemoryPoint)
async def edit_memory_point(
    collection_id: str,
    point_id: str,
    point: MemoryPointBase,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.EDIT)),
) -> MemoryPoint:
    """Edit a point in memory

    Example
    ----------
    ```

    collection = "declarative"
    content = "MIAO!"
    metadata = {"custom_key": "custom_value"}
    req_json = {
        "content": content,
        "metadata": metadata,
    }
    # create a point
    res = requests.post(
        f"http://localhost:1865/memory/collections/{collection}/points", json=req_json
    )
    json = res.json()
    #get the id
    point_id = json["id"]
    # new point values
    content = "NEW MIAO!"
    metadata = {"custom_key": "new_custom_value"}
    req_json = {
        "content": content,
        "metadata": metadata,
    }
    # edit the point
    res = requests.put(
        f"http://localhost:1865/memory/collections/{collection}/points/{point_id}", json=req_json
    )
    json = res.json()
    print(json)
    ```
    """

    memory_collection_is_accessible(collection_id)
    verify_memory_point_existence(collection_id, point_id, cats.cheshire_cat.memory.vectors)

    return upsert_memory_point(collection_id, point, cats, point_id)


@router.delete("/collections/{collection_id}/points/{point_id}", response_model=DeleteMemoryPointResponse)
async def delete_memory_point(
    collection_id: str,
    point_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> DeleteMemoryPointResponse:
    """Delete a specific point in memory"""

    memory_collection_is_accessible(collection_id)

    vector_memory = cats.cheshire_cat.memory.vectors
    verify_memory_point_existence(collection_id, point_id, vector_memory)

    # delete point
    vector_memory.collections[collection_id].delete_points([point_id])

    return DeleteMemoryPointResponse(deleted=point_id)


@router.delete("/collections/{collection_id}/points", response_model=DeleteMemoryPointsByMetadataResponse)
async def delete_memory_points_by_metadata(
    collection_id: str,
    metadata: Dict = None,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> DeleteMemoryPointsByMetadataResponse:
    """Delete points in memory by filter"""

    memory_collection_is_accessible(collection_id)

    metadata = metadata or {}

    # delete points
    ret = cats.cheshire_cat.memory.vectors.collections[collection_id].delete_points_by_metadata_filter(metadata)

    return DeleteMemoryPointsByMetadataResponse(deleted=ret)


# GET all the points from a single collection
@router.get("/collections/{collection_id}/points", response_model=GetPointsInCollectionResponse)
async def get_points_in_collection(
    collection_id: str,
    limit: int = Query(
        default=100,
        description="How many points to return"
    ),
    offset: str = Query(
        default=None,
        description="If provided (or not empty string) - skip points with ids less than given `offset`"
    ),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> GetPointsInCollectionResponse:
    """Retrieve all the points from a single collection

    Example
    ----------
    ```
    collection = "declarative"
    res = requests.get(
        f"http://localhost:1865/memory/collections/{collection}/points",
    )
    json = res.json()
    points = json["points"]

    for point in points:
        payload = point["payload"]
        vector = point["vector"]
        print(payload)
        print(vector)
    ```

    Example using offset
    ----------
    ```
    # get all the points with limit 10
    limit = 10
    next_offset = ""
    collection = "declarative"

    while True:
        res = requests.get(
            f"http://localhost:1865/memory/collections/{collection}/points?limit={limit}&offset={next_offset}",
        )
        json = res.json()
        points = json["points"]
        next_offset = json["next_offset"]

        for point in points:
            payload = point["payload"]
            vector = point["vector"]
            print(payload)
            print(vector)

        if next_offset is None:
            break
    ```
    """

    memory_collection_is_accessible(collection_id)

    # if offset is empty string set to null
    if offset == "":
        offset = None

    memory_collection = cats.cheshire_cat.memory.vectors.collections[collection_id]
    points, next_offset = memory_collection.get_all_points(limit=limit, offset=offset)

    return GetPointsInCollectionResponse(points=points, next_offset=next_offset)
