from typing import Dict

from pydantic import BaseModel, Field, ConfigDict


# This model can be used only for the upload_url endpoint,
# because in upload_file we need to pass the file and config as form data
class UploadURLConfig(BaseModel):
    url: str = Field(
        description="URL of the website to which you want to save the content"
    )
    chunk_size: int | None = Field(
        default=None,
        description="Maximum length of each chunk after the document is split (in tokens)"
    )
    chunk_overlap: int | None = Field(
        default=None,
        description="Chunk overlap (in tokens)"
    )
    metadata: Dict = Field(
        default={},
        description="Metadata to be stored with each chunk (e.g. author, category, etc.)"
    )
    model_config = ConfigDict(extra="forbid")
