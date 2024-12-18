import os
import tempfile
import time
import json
import mimetypes
import httpx
from typing import List, Dict, Tuple
from urllib.parse import urlparse
from urllib.error import HTTPError
from starlette.datastructures import UploadFile
from langchain.docstore.document import Document
from langchain_community.document_loaders.parsers.generic import MimeTypeBasedParser
from langchain.document_loaders.blob_loaders.schema import Blob

from cat.env import get_env
from cat.log import log
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.memory.utils import VectorMemoryCollectionTypes
from cat.utils import singleton


@singleton
class RabbitHole:
    """Manages content ingestion. I'm late... I'm late!"""

    def ingest_memory(self, ccat: CheshireCat, file: UploadFile):
        """Upload memories to the declarative memory from a JSON file.

        Args:
            ccat: CheshireCat
                Cheshire Cat instance.
            file: UploadFile
                File object sent via `rabbithole/memory` hook.

        Notes
        -----
        This method allows uploading a JSON file containing vector and text memories directly to the declarative memory.
        When doing this, please, make sure the embedder used to export the memories is the same as the one used
        when uploading.
        The method also performs a check on the dimensionality of the embeddings (i.e. length of each vector).
        """

        # Get file bytes
        file_bytes = file.file.read()

        # Load fyle byte in a dict
        memories = json.loads(file_bytes.decode("utf-8"))

        # Check the embedder used for the uploaded memories is the same the Cat is using now
        upload_embedder = memories["embedder"]
        cat_embedder = str(ccat.embedder.__class__.__name__)

        if upload_embedder != cat_embedder:
            raise Exception(
                f"Embedder mismatch: file embedder {upload_embedder} is different from {cat_embedder}"
            )

        # Get Declarative memories in file
        declarative_memories = memories["collections"][str(VectorMemoryCollectionTypes.DECLARATIVE)]

        # Store data to upload the memories in batch
        ids = [m["id"] for m in declarative_memories]
        payloads = [
            {"page_content": m["page_content"], "metadata": m["metadata"]}
            for m in declarative_memories
        ]
        vectors = [m["vector"] for m in declarative_memories]

        log.info(f"Agent id: {ccat.id}. Preparing to load {len(vectors)} vector memories")

        # Check embedding size is correct
        embedder_size = ccat.lizard.embedder_size.text
        len_mismatch = [len(v) == embedder_size for v in vectors]

        if not any(len_mismatch):
            raise Exception(
                f"Embedding size mismatch: vectors length should be {embedder_size}"
            )

        # Upsert memories in batch mode
        ccat.memory.vectors.declarative.add_points(ids, payloads, vectors)

    def ingest_file(
        self,
        stray: "StrayCat",
        file: str | UploadFile,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        metadata: Dict = None
    ):
        """Load a file in the Cat's declarative memory.

        The method splits and converts the file in Langchain `Document`. Then, it stores the `Document` in the Cat's
        memory.

        Args:
            stray: StrayCat
                Stray Cat instance.
            file: str, UploadFile
                The file can be a path passed as a string or an `UploadFile` object if the document is ingested using the
                `rabbithole` endpoint.
            chunk_size: int
                Number of tokens in each document chunk.
            chunk_overlap: int
                Number of overlapping tokens between consecutive chunks.
            metadata: Dict
                Metadata to be stored with each chunk.

        See Also:
            before_rabbithole_stores_documents

        Notes
        ----------
        Currently supported formats are `.txt`, `.pdf` and `.md`.
        You cn add custom ones or substitute the above via RabbitHole hooks.
        """

        # split file into a list of docs
        file_bytes, content_type, docs = self.file_to_docs(
            stray=stray, file=file, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        metadata = metadata or {}

        # store in memory
        filename = file if isinstance(file, str) else file.filename

        self.store_documents(stray=stray, docs=docs, source=filename, metadata=metadata)
        self.save_file(stray, file_bytes, content_type)

    def file_to_docs(
        self,
        stray: "StrayCat",
        file: str | UploadFile,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None
    ) -> Tuple[bytes, str | None, List[Document]]:
        """
        Load and convert files to Langchain `Document`.

        This method takes a file either from a Python script, from the `/rabbithole/` or `/rabbithole/web` endpoints.
        Hence, it loads it in memory and splits it in overlapped chunks of text.

        Args:
            stray: StrayCat
                Stray Cat instance.
            file: str, UploadFile
                The file can be either a string path if loaded programmatically, a FastAPI `UploadFile`
                if coming from the `/rabbithole/` endpoint or a URL if coming from the `/rabbithole/web` endpoint.
            chunk_size: int
                Number of tokens in each document chunk.
            chunk_overlap: int
                Number of overlapping tokens between consecutive chunks.

        Returns:
            (bytes, content_type, docs): Tuple[bytes, List[Document]]
                The file bytes, the content type and the list of Langchain `Document` of chunked text.

        Notes
        -----
        This method is used by both `/rabbithole/` and `/rabbithole/web` endpoints.
        Currently supported files are `.txt`, `.pdf`, `.md` and web pages.
        """

        file_bytes = None

        # Check type of incoming file.
        if isinstance(file, UploadFile):
            # Get mime type and source of UploadFile
            content_type = mimetypes.guess_type(file.filename)[0]
            source = file.filename

            # Get file bytes
            file_bytes = file.file.read()
        elif isinstance(file, str):
            # Check if string file is a string or url
            parsed_file = urlparse(file)
            is_url = all([parsed_file.scheme, parsed_file.netloc])

            if is_url:
                # Make a request with a fake browser name
                request = httpx.get(file, headers={"User-Agent": "Magic Browser"})

                # Define mime type and source of url
                content_type = request.headers["Content-Type"].split(";")[0]
                source = file

                try:
                    # Get binary content of url
                    file_bytes = request.content
                except HTTPError as e:
                    log.error(f"Agent id: {stray.agent_id}. Error: {e}")
            else:
                # Get mime type from file extension and source
                content_type = mimetypes.guess_type(file)[0]
                source = os.path.basename(file)

                # Get file bytes
                with open(file, "rb") as f:
                    file_bytes = f.read()
        else:
            raise ValueError(f"{type(file)} is not a valid type.")

        if not file_bytes:
            raise ValueError(f"Something went wrong with the file {source}")

        return file_bytes, content_type, self.string_to_docs(
            stray=stray,
            file_bytes=file_bytes,
            source=source,
            content_type=content_type,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

    def string_to_docs(
        self,
        stray: "StrayCat",
        file_bytes: bytes,
        source: str = None,
        content_type: str = "text/plain",
        chunk_size: int | None = None,
        chunk_overlap: int | None = None
    ) -> List[Document]:
        """Convert string to Langchain `Document`.

        Takes a string, converts it to langchain `Document`.
        Hence, loads it in memory and splits it in overlapped chunks of text.

        Args:
            stray: StrayCat
                Stray Cat instance.
            file_bytes: bytes
                The bytes to be converted.
            source: str
                Source filename.
            content_type:
                Mimetype of content.
            chunk_size: int
                Number of tokens in each document chunk.
            chunk_overlap: int
                Number of overlapping tokens between consecutive chunks.

        Returns:
            docs: List[Document]
                List of Langchain `Document` of chunked text.
        """

        # Load the bytes in the Blob schema
        blob = Blob(data=file_bytes, mimetype=content_type, source=source).from_data(
            data=file_bytes, mime_type=content_type, path=source
        )
        # Parser based on the mime type
        parser = MimeTypeBasedParser(handlers=stray.file_handlers)

        # Parse the text
        stray.send_ws_message(
            "I'm parsing the content. Big content could require some minutes..."
        )
        super_docs = parser.parse(blob)

        # Split
        stray.send_ws_message("Parsing completed. Now let's go with reading process...")
        docs = self.__split_text(stray=stray, text=super_docs, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        return docs

    def store_documents(
        self,
        stray: "StrayCat",
        docs: List[Document],
        source: str, # TODO V2: is this necessary?
        metadata: Dict = None
    ) -> None:
        """Add documents to the Cat's declarative memory.

        This method loops a list of Langchain `Document` and adds some metadata. Namely, the source filename and the
        timestamp of insertion. Once done, the method notifies the client via Websocket connection.

        Args:
            stray: StrayCat
                Stray Cat instance.
            docs: List[Document]
                List of Langchain `Document` to be inserted in the Cat's declarative memory.
            source: str
                Source name to be added as a metadata. It can be a file name or an URL.
            metadata: Dict
                Metadata to be stored with each chunk.

        See Also:
            before_rabbithole_insert_memory

        Notes
        -------
        At this point, it is possible to customize the Cat's behavior using the `before_rabbithole_insert_memory` hook
        to edit the memories before they are inserted in the vector database.
        """

        ccat = stray.cheshire_cat
        log.info(f"Agent id: {ccat.id}. Preparing to memorize {len(docs)} vectors")

        embedder = ccat.embedder
        memory = ccat.memory

        plugin_manager = stray.mad_hatter

        # hook the docs before they are stored in the vector memory
        docs = plugin_manager.execute_hook("before_rabbithole_stores_documents", docs, cat=stray)

        metadata = metadata or {}

        # classic embed
        time_last_notification = time.time()
        time_interval = 10  # a notification every 10 secs
        stored_points = []

        for d, doc in enumerate(docs):
            if time.time() - time_last_notification > time_interval:
                time_last_notification = time.time()
                perc_read = int(d / len(docs) * 100)
                read_message = f"Read {perc_read}% of {source}"
                stray.send_ws_message(read_message)

            # add default metadata
            doc.metadata["source"] = source
            doc.metadata["when"] = time.time()
            # add custom metadata (sent via endpoint)
            doc.metadata = {**doc.metadata, **{k: v for k, v in metadata.items()}}

            doc = plugin_manager.execute_hook(
                "before_rabbithole_insert_memory", doc, cat=stray
            )
            inserting_info = f"{d + 1}/{len(docs)}):    {doc.page_content}"
            if doc.page_content != "":
                doc_embedding = embedder.embed_documents([doc.page_content])
                stored_point = memory.vectors.declarative.add_point(
                    doc.page_content,
                    doc_embedding[0],
                    doc.metadata,
                )
                stored_points.append(stored_point)

                log.info(f"Agent id: {ccat.id}. Inserted into memory ({inserting_info})")
            else:
                log.info(f"Agent id: {ccat.id}. Skipped memory insertion of empty doc ({inserting_info})")

            # wait a little to avoid APIs rate limit errors
            time.sleep(0.05)

        # hook the points after they are stored in the vector memory
        plugin_manager.execute_hook(
            "after_rabbithole_stored_documents", source, stored_points, cat=stray
        )

        # notify client
        finished_reading_message = (
            f"Finished reading {source}, I made {len(docs)} thoughts on it."
        )

        stray.send_ws_message(finished_reading_message)

        log.warning(f"Agent id: {ccat.id}. Done uploading {source}")

    def __split_text(self, stray: "StrayCat", text: List[Document], chunk_size: int, chunk_overlap: int):
        """Split text in overlapped chunks.

        This method splits the incoming text in overlapped  chunks of text. Other two hooks are available to edit the
        text before and after the split step.

        Args:
            stray: StrayCat
                Stray Cat instance.
            text: List[Document]
                Content of the loaded file.
            chunk_size: int
                Number of tokens in each document chunk.
            chunk_overlap: int
                Number of overlapping tokens between consecutive chunks.

        Returns:
            docs: List[Document]
                List of split Langchain `Document`.

        See Also:
            before_rabbithole_splits_text
            after_rabbithole_splitted_text

        Notes
        -----
        The default behavior splits the text and executes the hooks, before and after the splitting, respectively.
        `before_rabbithole_splits_text` and `after_rabbithole_splitted_text` hooks return the original input without
        any modification.
        """

        plugin_manager = stray.mad_hatter
        text_splitter = stray.text_splitter

        # do something on the text before it is split
        text = plugin_manager.execute_hook("before_rabbithole_splits_text", text, cat=stray)

        # hooks decide the test splitter (see @property .text_splitter)
        # override chunk_size and chunk_overlap only if the request has that info
        if chunk_size:
            text_splitter._chunk_size = chunk_size
        if chunk_overlap:
            text_splitter._chunk_overlap = chunk_overlap

        log.info(f"Agent id: {stray.agent_id}. Chunk size: {chunk_size}, chunk overlap: {chunk_overlap}")
        # split text
        docs = text_splitter.split_documents(text)
        # remove short texts (page numbers, isolated words, etc.)
        # TODO: join each short chunk with previous one, instead of deleting them
        docs = list(filter(lambda d: len(d.page_content) > 10, docs))

        # do something on the text after it is split
        docs = plugin_manager.execute_hook(
            "after_rabbithole_splitted_text", docs, cat=stray
        )

        return docs

    def save_file(self, stray: "StrayCat", file_bytes: bytes, content_type: str):
        """
        Save file in the Rabbit Hole remote storage handled by the BillTheLizard's file manager.
        This method saves the file in the Rabbit Hole storage. The file is saved in a temporary folder and the path is
        stored in the remote storage handled by the BillTheLizard's file manager.

        Args:
            stray: StrayCat
                Stray Cat instance.
            file_bytes: bytes
                The file bytes to be saved.
            content_type: str
                The content type of the file.
        """

        if get_env("CCAT_RABBIT_HOLE_STORAGE_ENABLED") not in ("1", "true"):
            return

        # save file in a temporary folder
        extension = mimetypes.guess_extension(content_type)
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            temp_file.write(file_bytes)
            file_path = temp_file.name

            self.lizard.file_manager.upload_file_to_storage_and_remove(file_path, f"rabbit_hole/{stray.agent_id}")

    @property
    def lizard(self) -> "BillTheLizard":
        from cat.looking_glass.bill_the_lizard import BillTheLizard
        return BillTheLizard()
