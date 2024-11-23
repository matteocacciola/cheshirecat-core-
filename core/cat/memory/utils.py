import json
from typing import Dict, List

from pydantic import BaseModel, Field
from qdrant_client.http.models import Record, ScoredPoint
from langchain.docstore.document import Document

from cat.utils import Enum as BaseEnum, BaseModelDict


class ContentType(BaseEnum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"


class VectorMemoryCollectionTypes(BaseEnum):
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


class MultimodalContent(BaseModel):
    """Represents multimodal content with optional text, image and audio data"""
    text: str | None = None
    image_path: str | None = None
    audio_path: str | None = None
    content_type: ContentType = Field(default=ContentType.TEXT)


class DocumentRecall(BaseModelDict):
    """
    Langchain `Document` retrieved from the episodic memory, with the similarity score, the vectors for each modality
    and the id of the memory.
    """

    document: Document
    score: float | None = None
    vectors: Dict[ContentType, List[float]] = Field(default_factory=dict)  # Mapping of modality to vector
    id: str | None = None


def to_document_recall(m: Record | ScoredPoint) -> DocumentRecall:
    """
    Convert a Qdrant point to a DocumentRecall object

    Args:
        m: The Qdrant point

    Returns:
        DocumentRecall: The converted DocumentRecall object
    """

    document = DocumentRecall(
        document=Document(
            page_content=json.dumps(m.payload.get("page_content", {})),
            metadata=m.payload.get("metadata", {})
        ),
        vectors={ContentType(k): v for k, v in m.vector.items()},
        id=m.id,
    )

    if isinstance(m, ScoredPoint):
        document.score = m.score

    return document
