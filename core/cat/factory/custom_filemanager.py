import uuid
from abc import ABC, abstractmethod
import os
from typing import List
import shutil

from cat.log import log


class BaseFileManager(ABC):
    """
    Base class for file storage managers. It defines the interface that all storage managers must implement. It is used
    to upload files and folders composing an installed plugin to a storage service.
    Method `upload_directory`, `download_file`, `download_directory`, `list_files`
    MUST be implemented by subclasses.
    """

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._excluded_dirs = ["__pycache__"]
        self._excluded_files = [".gitignore", ".DS_Store", ".gitkeep", ".git", ".dockerignore"]

    @abstractmethod
    def upload_file_to_storage(self, file_path: str, root_dir: str | None = None) -> str | None:
        """
        Upload a single file on the storage, within the directory specified by `self.storage_dir`.

        Args:
            file_path: The path of the file to upload
            root_dir: The local directory where the file is contained to consider as root for the definition of the
                relative path of the file to upload, If not specified, the `root_dir` will be considered as the parent
                directory of the file to upload

        Returns:
            The path of the file on the storage, None if the file has not been uploaded
        """
        pass

    @abstractmethod
    def download_file_from_storage(self, file_path: str, local_dir: str) -> str | None:
        """
        Download a single file from the storage to the `local_path`.

        Args:
            file_path: The path of the file to download, contained on the storage within the directory specified by
                `self.storage_dir`
            local_dir: The directory where the file will be downloaded locally

        Returns:
            The path of the file locally if the file has been downloaded, None otherwise
        """
        pass

    @abstractmethod
    def remove_file_from_storage(self, file_path: str) -> bool:
        """
        Remove a single file with `file_path` path from the `storage_dir` of the storage.

        Args:
            file_path: The name/path of the file to remove, contained on the storage within the directory specified by
                `self.storage_dir`

        Returns:
            True if the file has been removed, False otherwise
        """
        pass

    @abstractmethod
    def remove_storage(self) -> bool:
        """
        Remove the `self.storage_dir` directory from the storage.

        Returns:
            True if the storage has been removed, False otherwise
        """
        pass

    @abstractmethod
    def list_files(self, all_results: bool = True) -> List[str]:
        """
        List of all the files contained into the `self.storage_dir` on the storage.

        Args:
            all_results: If True, return all the files, otherwise return only the files that are not excluded by the
                rules identified within the `_excluded_dirs` and `_excluded_files` attributes

        Returns:
            List of the paths of the files on the storage
        """
        pass

    def upload_to_storage(self, local_dir: str) -> List[str]:
        """
        Upload a directory with all the contained files on the storage, within the directory specified by
        `self.storage_dir`.

        Args:
            local_dir: The path of the directory locally, containing the files to upload to the storage

        Returns:
            List of the paths of the files on the storage
        """

        return [
            self.upload_file_to_storage(os.path.join(root, file), root)
            for root, _, files in os.walk(local_dir)
            for file in files
        ]

    def download_from_storage(self, local_dir: str) -> List[str]:
        """
        Download the directory specified by `self.storage_dir` with all the contained files from the storage to
        `local_dir`.

        Args:
            local_dir: The path where the directory will be downloaded locally

        Returns:
            List of the paths of the files locally
        """

        files = self.list_files(False)
        return [self.download_file_from_storage(file_path, local_dir) for file_path in files]

    def transfer(self, file_manager_from: "BaseFileManager") -> bool:
        """
        Transfer files from the file manager specified in the `file_manager_from` to the current one.

        Args:
            file_manager_from: The file manager to transfer the files from
        """

        try:
            # create tmp directory
            tmp_folder_name = f"/tmp/{uuid.uuid1()}"
            os.mkdir(tmp_folder_name)

            # try to download the files from the old file manager to the `tmp_folder_name`
            file_manager_from.download_from_storage(tmp_folder_name)

            # now, try to upload the files to the new storage
            self.upload_to_storage(tmp_folder_name)

            # cleanup
            if os.path.exists(tmp_folder_name):
                shutil.rmtree(tmp_folder_name)
            file_manager_from.remove_storage()
            return True
        except Exception as e:
            log.error(f"Error while transferring files from the old file manager to the new one: {e}")
            return False

    def file_exists(self, file_path: str) -> bool:
        """
        Check if a file exists in the storage.

        Args:
            file_path: The path of the file to check

        Returns:
            True if the file exists, False otherwise
        """
        return file_path in self.list_files()

    def _build_destination_path_for_download(self, file_path: str, local_dir: str) -> str | None:
        rel_path = os.path.relpath(file_path, self.storage_dir)
        local_path = os.path.join(local_dir, rel_path)
        if any([ex_file in local_path for ex_file in self._excluded_files]):
            return None
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        return local_path

    def _build_destination_path_for_upload(self, file_path: str, root_dir: str | None = None) -> str | None:
        rel_path = os.path.relpath(file_path, root_dir or os.path.dirname(file_path))
        destination_path = os.path.join(self.storage_dir, rel_path)
        if any([ex_file in destination_path for ex_file in self._excluded_files]):
            return None
        return destination_path

    def _build_destination_path_for_removal(self, file_path: str) -> str:
        rel_path = os.path.relpath(file_path, self.storage_dir)
        return os.path.join(self.storage_dir, rel_path)

    def _filter_excluded(self, files: List[str]) -> List[str]:
        excluded_paths = self._excluded_dirs + self._excluded_files
        return [file for file in files if not any([ex in files for ex in excluded_paths])]


class LocalFileManager(BaseFileManager):
    def upload_file_to_storage(self, file_path: str, root_dir: str | None = None) -> str | None:
        destination_path = self._build_destination_path_for_upload(file_path, root_dir)
        if destination_path and file_path != destination_path:
            # move the file from file_path to destination_path
            shutil.move(file_path, destination_path)
        return destination_path

    def download_file_from_storage(self, file_path: str, local_dir: str) -> str | None:
        destination_path = self._build_destination_path_for_download(file_path, local_dir)
        if destination_path and file_path != destination_path:
            # move the file from origin_path to destination_path
            shutil.move(file_path, destination_path)
        return destination_path

    def remove_file_from_storage(self, file_path: str) -> bool:
        final_path = self._build_destination_path_for_removal(file_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                log.error(f"Error while removing file {final_path} from storage: {e}")
                return False
        return True

    def list_files(self, all_results: bool = True) -> List[str]:
        results = [
            os.path.join(root, file)
            for root, _, files in os.walk(self.storage_dir)
            for file in files
        ]
        return results if all_results else self._filter_excluded(results)

    def remove_storage(self) -> bool:
        if os.path.exists(self.storage_dir) and os.path.isdir(self.storage_dir):
            try:
                shutil.rmtree(self.storage_dir)
            except Exception as e:
                log.error(f"Error while removing storage: {e}")
                return False
        return True


class AWSFileManager(BaseFileManager):
    def __init__(self, bucket_name: str, aws_access_key: str, aws_secret_key: str, storage_dir: str):
        import boto3
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        self.bucket_name = bucket_name
        super().__init__(storage_dir)

    def upload_file_to_storage(self, file_path: str, root_dir: str | None = None) -> str | None:
        bucket_key = self._build_destination_path_for_upload(file_path, root_dir)
        if bucket_key:
            self.s3.upload_file(file_path, self.bucket_name, bucket_key)
            return os.path.join("s3://", self.bucket_name, bucket_key)
        return None

    def download_file_from_storage(self, file_path: str, local_dir: str) -> str | None:
        local_path = self._build_destination_path_for_download(file_path, local_dir)
        if local_path:
            self.s3.download_file(self.bucket_name, file_path, local_path)
        return local_path

    def remove_file_from_storage(self, file_path: str) -> bool:
        bucket_key = self._build_destination_path_for_removal(file_path)
        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=bucket_key)
            self.s3.delete_object(Bucket=self.bucket_name, Key=bucket_key)
            return True
        except Exception as e:
            log.error(f"Error while removing file {file_path} from storage: {e}")
            return False

    def list_files(self, all_results: bool = True) -> List[str]:
        files = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=self.storage_dir):
            if "Contents" in page:
                files.extend([obj["Key"] for obj in page["Contents"]])
        return files if all_results else self._filter_excluded(files)

    def remove_storage(self) -> bool:
        try:
            files_to_delete = self.list_files()
            if files_to_delete:
                objects_to_delete = [{'Key': key} for key in files_to_delete]
                self.s3.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={'Objects': objects_to_delete}
                )
            return True
        except Exception as e:
            log.error(f"Error while removing storage: {e}")
            return False


class AzureFileManager(BaseFileManager):
    def __init__(self, connection_string: str, container_name: str, storage_dir: str):
        from azure.storage.blob import BlobServiceClient
        self.blob_service = BlobServiceClient.from_connection_string(connection_string)
        self.container = self.blob_service.get_container_client(container_name)
        super().__init__(storage_dir)

    def upload_file_to_storage(self, file_path: str, root_dir: str | None = None) -> str | None:
        blob_key = self._build_destination_path_for_upload(file_path, root_dir)
        if blob_key:
            with open(file_path, "rb") as data:
                self.container.upload_blob(name=blob_key, data=data, overwrite=True)
            return os.path.join("azure://", self.container.container_name, blob_key)
        return None

    def download_file_from_storage(self, file_path: str, local_dir: str) -> str | None:
        local_path = self._build_destination_path_for_download(file_path, local_dir)
        if local_path:
            blob_client = self.container.get_blob_client(file_path)
            with open(local_path, "wb") as file:
                data = blob_client.download_blob()
                file.write(data.readall())
        return local_path

    def remove_file_from_storage(self, file_path: str) -> bool:
        blob_key = self._build_destination_path_for_removal(file_path)
        try:
            blob_client = self.container.get_blob_client(blob_key)
            if blob_client.exists():
                blob_client.delete_blob()
            return True
        except Exception as e:
            log.error(f"Error while removing file {file_path} from storage: {e}")
            return False

    def list_files(self, all_results: bool = True) -> List[str]:
        files = [blob.name for blob in self.container.list_blobs(name_starts_with=self.storage_dir)]
        return files if all_results else self._filter_excluded(files)

    def remove_storage(self) -> bool:
        try:
            for file_path in self.list_files():
                blob_client = self.container.get_blob_client(file_path)
                blob_client.delete_blob()
            return True
        except Exception as e:
            log.error(f"Error while removing storage: {e}")
            return False


class GoogleCloudFileManager(BaseFileManager):
    def __init__(self, bucket_name: str, credentials_path: str, storage_dir: str):
        from google.cloud import storage
        self.storage_client = storage.Client.from_service_account_json(credentials_path)
        self.bucket = self.storage_client.bucket(bucket_name)
        super().__init__(storage_dir)

    def upload_file_to_storage(self, file_path: str, root_dir: str | None = None) -> str | None:
        blob_key = self._build_destination_path_for_upload(file_path, root_dir)
        if blob_key:
            blob = self.bucket.blob(blob_key)
            blob.upload_from_filename(file_path)
            return os.path.join("gs://", self.bucket.name, blob_key)
        return None

    def download_file_from_storage(self, file_path: str, local_dir: str) -> str | None:
        local_path = self._build_destination_path_for_download(file_path, local_dir)
        if local_path:
            blob = self.bucket.blob(file_path)
            blob.download_to_filename(local_path)
        return local_path

    def remove_file_from_storage(self, file_path: str) -> bool:
        blob_key = self._build_destination_path_for_removal(file_path)
        try:
            blob = self.bucket.blob(blob_key)
            if blob.exists():
                blob.delete()
            return True
        except Exception as e:
            log.error(f"Error while removing file {file_path} from storage: {e}")
            return False

    def list_files(self, all_results: bool = True) -> List[str]:
        files = [blob.name for blob in self.bucket.list_blobs(prefix=self.storage_dir)]
        return files if all_results else self._filter_excluded(files)

    def remove_storage(self) -> bool:
        try:
            for file_path in self.list_files():
                blob = self.bucket.blob(file_path)
                blob.delete()
            return True
        except Exception as e:
            log.error(f"Error while removing storage: {e}")
            return False


class DigitalOceanFileManager(AWSFileManager):
    pass
