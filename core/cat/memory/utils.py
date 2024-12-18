import json
from typing import Dict, List

from pydantic import BaseModel, Field
from qdrant_client.http.models import Record, ScoredPoint
from langchain.docstore.document import Document

from cat.utils import Enum as BaseEnum, BaseModelDict


class VectorMemoryCollectionTypes(BaseEnum):
    EPISODIC = "episodic"
    DECLARATIVE = "declarative"
    PROCEDURAL = "procedural"


class VectorEmbedderSize(BaseModel):
    text: int
    image: int | None = None
    audio: int | None = None


class DocumentRecall(BaseModelDict):
    """
    Langchain `Document` retrieved from the episodic memory, with the similarity score, the list of embeddings and the
    id of the memory.
    """

    document: Document
    score: float | None = None
    vector: List[float] = Field(default_factory=list)
    id: str | None = None


def to_document_recall(m: Record | ScoredPoint) -> DocumentRecall:
    """
    Convert a Qdrant point to a DocumentRecall object

    Args:
        m: The Qdrant point

    Returns:
        DocumentRecall: The converted DocumentRecall object
    """

    document = DocumentRecall(document=Document(**m.payload), vector=m.vector, id=m.id)

    if isinstance(m, ScoredPoint):
        document.score = m.score

    return document
