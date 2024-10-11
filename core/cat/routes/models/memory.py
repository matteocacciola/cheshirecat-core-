from typing import Dict, List
from pydantic import BaseModel


class MemoryPointBase(BaseModel):
    content: str
    metadata: Dict = {}

# TODOV2: annotate all endpoints and align internal usage (no qdrant PointStruct, no langchain Document)
class MemoryPoint(MemoryPointBase):
    id: str
    vector: List[float]
