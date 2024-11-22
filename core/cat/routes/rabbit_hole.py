import mimetypes
import httpx
import json
from typing import Dict, List
from copy import deepcopy
from pydantic import BaseModel, Field, ConfigDict
from fastapi import Form, Depends, APIRouter, UploadFile, BackgroundTasks, Request

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.exceptions import CustomValidationException
from cat.log import log
from cat.looking_glass.bill_the_lizard import BillTheLizard
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.routes.routes_utils import format_upload_file

router = APIRouter()


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


class UploadSingleFileResponse(BaseModel):
    filename: str
    content_type: str
    info: str


class UploadUrlResponse(BaseModel):
    url: str
    info: str


class AllowedMimeTypesResponse(BaseModel):
    allowed: List[str]


# receive files via http endpoint
@router.post("/", response_model=UploadSingleFileResponse)
async def upload_file(
    request: Request,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    chunk_size: int | None = Form(
        default=None,
        description="Maximum length of each chunk after the document is split (in tokens)"
    ),
    chunk_overlap: int | None = Form(
        default=None,
        description="Chunk overlap (in tokens)"
    ),
    metadata: str = Form(
        default="{}",
        description="Metadata to be stored with each chunk (e.g. author, category, etc.). "
                    "Since we are passing this along side form data, must be a JSON string (use `json.dumps(metadata)`)."
    ),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.UPLOAD, AuthPermission.WRITE)),
) -> UploadSingleFileResponse:
    """Upload a file containing text (.txt, .md, .pdf, etc.). File content will be extracted and segmented into chunks.
    Chunks will be then vectorized and stored into documents memory.

    Note
    ----------
    `chunk_size`, `chunk_overlap` and `metadata` must be passed as form data.
    This is necessary because the HTTP protocol does not allow file uploads to be sent as JSON.

    Example
    ----------
    ```
    content_type = "application/pdf"
    file_name = "sample.pdf"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, content_type)}

        metadata = {
            "source": "sample.pdf",
            "title": "Test title",
            "author": "Test author",
            "year": 2020,
        }
        # upload file endpoint only accepts form-encoded data
        payload = {
            "chunk_size": 128,
            "metadata": json.dumps(metadata)
        }

        response = requests.post(
            "http://localhost:1865/rabbithole/",
            files=files,
            data=payload
        )
    ```
    """

    lizard: BillTheLizard = request.app.state.lizard
    ccat: CheshireCat = cats.cheshire_cat

    # Check the file format is supported
    admitted_types = ccat.file_handlers.keys()

    # Get file mime type
    content_type = mimetypes.guess_type(file.filename)[0]
    log.info(f"Uploaded {content_type} down the rabbit hole")

    # check if MIME type of uploaded file is supported
    if content_type not in admitted_types:
        CustomValidationException(
            f'MIME type {content_type} not supported. Admitted types: {" - ".join(admitted_types)}'
        )

    # upload file to long term memory, in the background
    uploaded_file = deepcopy(format_upload_file(file))
    background_tasks.add_task(
        # we deepcopy the file because FastAPI does not keep the file in memory after the response returns to the client
        # https://github.com/tiangolo/fastapi/discussions/10936
        lizard.rabbit_hole.ingest_file,
        cats.stray_cat,
        uploaded_file,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        metadata=json.loads(metadata)
    )

    # reply to client
    return UploadSingleFileResponse(
        filename=file.filename, content_type=file.content_type, info="File is being ingested asynchronously"
    )


# receive files via http endpoint
@router.post("/batch", response_model=Dict[str, UploadSingleFileResponse])
async def upload_files(
    request: Request,
    files: List[UploadFile],
    background_tasks: BackgroundTasks,
    chunk_size: int | None = Form(
        default=None,
        description="Maximum length of each chunk after the document is split (in tokens)"
    ),
    chunk_overlap: int | None = Form(
        default=None,
        description="Chunk overlap (in tokens)"
    ),
    metadata: str = Form(
        default="{}",
        description="Metadata to be stored where each key is the name of a file being uploaded, and the corresponding value is another dictionary containing metadata specific to that file. "
                    "Since we are passing this along side form data, metadata must be a JSON string (use `json.dumps(metadata)`)."
    ),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.UPLOAD, AuthPermission.WRITE)),
) -> Dict[str, UploadSingleFileResponse]:
    """Batch upload multiple files containing text (.txt, .md, .pdf, etc.). File content will be extracted and segmented into chunks.
    Chunks will be then vectorized and stored into documents memory.

    Note
    ----------
    `chunk_size`, `chunk_overlap` and `metadata` must be passed as form data.
    This is necessary because the HTTP protocol does not allow file uploads to be sent as JSON.

    Example
    ----------
    ```
    files = []
    files_to_upload = {"sample.pdf":"application/pdf","sample.txt":"application/txt"}

    for file_name in files_to_upload:
        content_type = files_to_upload[file_name]
        file_path = f"tests/mocks/{file_name}"
        files.append(  ("files", ((file_name, open(file_path, "rb"), content_type))) )


    metadata = {
        "sample.pdf":{
            "source": "sample.pdf",
            "title": "Test title",
            "author": "Test author",
            "year": 2020
        },
        "sample.txt":{
            "source": "sample.txt",
            "title": "Test title",
            "author": "Test author",
            "year": 2021
        }
    }

    # upload file endpoint only accepts form-encoded data
    payload = {
        "chunk_size": 128,
        "metadata": json.dumps(metadata)
    }

    response = requests.post(
        "http://localhost:1865/rabbithole/batch",
        files=files,
        data=payload
    )
    ```
    """

    response = {}
    metadata_dict = json.loads(metadata)

    for file in files:
        response[file.filename] = await upload_file(
            request,
            file,
            background_tasks,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            # if file.filename in dictionary pass the stringified metadata, otherwise pass empty dictionary-like string
            metadata=json.dumps(metadata_dict[file.filename]) if file.filename in metadata_dict else "{}",
            cats=cats
        )

    return response


@router.post("/web", response_model=UploadUrlResponse)
async def upload_url(
    request: Request,
    background_tasks: BackgroundTasks,
    upload_config: UploadURLConfig,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.UPLOAD, AuthPermission.WRITE)),
) -> UploadUrlResponse:
    """Upload an url. Website content will be extracted and segmented into chunks.
    Chunks will be then vectorized and stored into documents memory."""

    # check that URL is valid
    try:
        # Send a HEAD request to the specified URL
        async with httpx.AsyncClient() as client:
            response = await client.head(
                upload_config.url, headers={"User-Agent": "Magic Browser"}, follow_redirects=True
            )

        if response.status_code == 200:
            # upload file to long term memory, in the background
            background_tasks.add_task(
                request.app.state.lizard.rabbit_hole.ingest_file,
                cats.stray_cat,
                upload_config.url,
                **upload_config.model_dump(exclude={"url"})
            )
            return UploadUrlResponse(url=upload_config.url, info="URL is being ingested asynchronously")

        raise CustomValidationException(f"Invalid URL: {upload_config.url}")
    except httpx.RequestError as _e:
        raise CustomValidationException(f"Unable to reach the URL: {upload_config.url}")


@router.post("/memory", response_model=UploadSingleFileResponse)
async def upload_memory(
    request: Request,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.WRITE)),
) -> UploadSingleFileResponse:
    """Upload a memory json file to the cat memory"""

    # Get file mime type
    content_type = mimetypes.guess_type(file.filename)[0]
    log.info(f"Uploaded {content_type} down the rabbit hole")
    if content_type != "application/json":
        raise CustomValidationException(
            f'MIME type {content_type} not supported. Admitted types: "application/json"'
        )

    # Ingest memories in background and notify client
    background_tasks.add_task(
        request.app.state.lizard.rabbit_hole.ingest_memory,
        cats.cheshire_cat,
        deepcopy(file)
    )

    # reply to client
    return UploadSingleFileResponse(
        filename=file.filename, content_type=file.content_type, info="Memory is being ingested asynchronously",
    )


@router.get("/allowed-mimetypes", response_model=AllowedMimeTypesResponse)
async def get_allowed_mimetypes(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.UPLOAD, AuthPermission.WRITE)),
) -> AllowedMimeTypesResponse:
    """Retrieve the allowed mimetypes that can be ingested by the Rabbit Hole"""

    return AllowedMimeTypesResponse(allowed=list(cats.cheshire_cat.file_handlers.keys()))
