import uuid
from abc import ABC, abstractmethod
import os
from typing import List
import shutil

from cat.log import log
from cat import utils


class BaseFileManager(ABC):
    """
    Base class for file storage managers. It defines the interface that all storage managers must implement. It is used
    to upload files and folders to a storage service.
    """

    def __init__(self):
        self._excluded_dirs = ["__pycache__"]
        self._excluded_files = [".gitignore", ".DS_Store", ".gitkeep", ".git", ".dockerignore"]
        self._root_dir = utils.get_file_manager_root_storage_path()

    def upload_file_to_storage_and_remove(self, file_path: str, remote_root_dir: str):
        """
        Upload a single file on the storage, within the directory specified by `remote_root_dir`, and then remove it
        from the local file system.

        Args:
            file_path: The path of the file to upload
            remote_root_dir: The directory on the storage where the file will be uploaded

        Returns:
            The path of the file on the storage, None if the file has not been uploaded
        """

        try:
            self.upload_file_to_storage(file_path, remote_root_dir)
        except Exception as e:
            log.error(f"Error while uploading file {file_path}: {e}")

        try:
            self.remove_file_from_storage(file_path)
        except Exception as e:
            log.error(f"Error while removing file {file_path}: {e}")

    def upload_file_to_storage(self, file_path: str, remote_root_dir: str | None = None) -> str | None:
        """
        Upload a single file on the storage, within the directory specified by `remote_root_dir`.

        Args:
            file_path: The path of the file to upload
            remote_root_dir: The directory on the storage where the file will be uploaded

        Returns:
            The path of the file on the storage, None if the file has not been uploaded
        """

        remote_root_dir = os.path.join(self._root_dir, remote_root_dir) if remote_root_dir else self._root_dir
        destination_path = os.path.join(remote_root_dir, os.path.basename(file_path))
        if any([ex_file in destination_path for ex_file in self._excluded_files]):
            return None

        return self._upload_file_to_storage(file_path, destination_path)

    @abstractmethod
    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        pass

    def download_file_from_storage(self, file_path: str, local_dir: str) -> str | None:
        """
        Download a single file from the storage to the `local_dir`.

        Args:
            file_path: The path of the file to download
            local_dir: The directory where the file will be downloaded locally

        Returns:
            The path of the file locally if the file has been downloaded, None otherwise
        """

        local_dir = os.path.join(self._root_dir, local_dir)

        local_path = os.path.join(local_dir, os.path.basename(file_path))
        if any([ex_file in local_path for ex_file in self._excluded_files]):
            return None
        os.makedirs(local_dir, exist_ok=True)

        return self._download_file_from_storage(file_path, local_path)

    @abstractmethod
    def _download_file_from_storage(self, file_path: str, local_path: str) -> str:
        pass

    def remove_file_from_storage(self, file_path: str) -> bool:
        """
        Remove a single file with `file_path` path from the storage.

        Args:
            file_path: The name/path of the file to remove, contained on the storage

        Returns:
            True if the file has been removed, False otherwise
        """

        file_path = os.path.join(self._root_dir, file_path)
        return self._remove_file_from_storage(file_path)

    @abstractmethod
    def _remove_file_from_storage(self, file_path: str) -> bool:
        pass

    def remove_folder_from_storage(self, remote_root_dir: str | None = None) -> bool:
        """
        Remove the entire `remote_root_dir` directory from the storage. If not specified, the entire storage will be
        removed.

        Returns:
            True if the storage has been removed, False otherwise
        """

        remote_root_dir = os.path.join(self._root_dir, remote_root_dir) if remote_root_dir else self._root_dir
        return self._remove_folder_from_storage(remote_root_dir)

    @abstractmethod
    def _remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        pass

    def list_files(self, remote_root_dir: str | None = None, all_results: bool = True) -> List[str]:
        """
        List of all the files contained into the `remote_root_dir` on the storage.

        Args:
            remote_root_dir: The directory on the storage where the files are contained
            all_results: If True, return all the files, otherwise return only the files that are not excluded by the
                rules identified within the `_excluded_dirs` and `_excluded_files` attributes

        Returns:
            List of the paths of the files on the storage
        """

        remote_root_dir = os.path.join(self._root_dir, remote_root_dir) if remote_root_dir else self._root_dir
        files = self._list_files(remote_root_dir)
        return files if all_results else self._filter_excluded(files)

    @abstractmethod
    def _list_files(self, remote_root_dir: str) -> List[str]:
        pass

    def upload_folder_to_storage(self, local_dir: str, remote_root_dir: str | None = None) -> List[str]:
        """
        Upload a directory with all the contained files on the storage, within the directory specified by
        `remote_root_dir`.

        Args:
            local_dir: The path of the directory locally, containing the files to upload to the storage
            remote_root_dir: The directory on the storage where the files will be uploaded

        Returns:
            List of the paths of the files on the storage
        """

        local_dir = os.path.join(self._root_dir, local_dir)

        return [
            self.upload_file_to_storage(os.path.join(root, file), remote_root_dir)
            for root, _, files in os.walk(local_dir)
            for file in files
        ]

    def download_folder_from_storage(self, local_dir: str, remote_root_dir: str | None = None) -> List[str]:
        """
        Download the directory specified by `remote_root_dir` with all the contained files from the storage to
        `local_dir`.

        Args:
            local_dir: The path where the directory will be downloaded locally
            remote_root_dir: The directory on the storage where the files are contained

        Returns:
            List of the paths of the files locally
        """

        files = self.list_files(remote_root_dir, False)
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
            file_manager_from.download_folder_from_storage(tmp_folder_name)

            # now, try to upload the files to the new storage
            self.upload_folder_to_storage(tmp_folder_name)

            # cleanup
            if os.path.exists(tmp_folder_name):
                shutil.rmtree(tmp_folder_name)
            file_manager_from.remove_folder_from_storage()
            return True
        except Exception as e:
            log.error(f"Error while transferring files from the old file manager to the new one: {e}")
            return False

    def file_exists(self, filename: str, remote_root_dir: str) -> bool:
        """
        Check if a file exists in the storage.

        Args:
            filename: The name of the file to check
            remote_root_dir: The directory on the storage where the file should be contained

        Returns:
            True if the file exists, False otherwise
        """
        return filename in self.list_files(remote_root_dir)

    def _filter_excluded(self, files: List[str]) -> List[str]:
        excluded_paths = self._excluded_dirs + self._excluded_files
        return [file for file in files if not any([ex in files for ex in excluded_paths])]


class LocalFileManager(BaseFileManager):
    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        if file_path != destination_path:
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            # move the file from file_path to destination_path
            shutil.move(file_path, destination_path)
        return destination_path

    def _download_file_from_storage(self, file_path: str, local_path: str) -> str:
        if file_path != local_path:
            # move the file from origin_path to local_path
            shutil.move(file_path, local_path)
        return local_path

    def _remove_file_from_storage(self, file_path: str) -> bool:
        if os.path.exists(file_path) and os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                log.error(f"Error while removing file {file_path} from storage: {e}")
                return False
        return True

    def _remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        if os.path.exists(remote_root_dir) and os.path.isdir(remote_root_dir):
            try:
                shutil.rmtree(remote_root_dir)
            except Exception as e:
                log.error(f"Error while removing storage: {e}")
                return False
        return True

    def _list_files(self, remote_root_dir: str) -> List[str]:
        return [
            os.path.join(root, file)
            for root, _, files in os.walk(remote_root_dir)
            for file in files
        ]


class AWSFileManager(BaseFileManager):
    def __init__(self, bucket_name: str, aws_access_key: str, aws_secret_key: str):
        import boto3
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        self.bucket_name = bucket_name
        super().__init__()

    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        self.s3.upload_file(file_path, self.bucket_name, destination_path)
        return os.path.join("s3://", self.bucket_name, destination_path)

    def _download_file_from_storage(self, file_path: str, local_path: str) -> str:
        self.s3.download_file(self.bucket_name, file_path, local_path)
        return local_path

    def _remove_file_from_storage(self, file_path: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=file_path)
            self.s3.delete_object(Bucket=self.bucket_name, Key=file_path)
            return True
        except Exception as e:
            log.error(f"Error while removing file {file_path} from storage: {e}")
            return False

    def _remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        try:
            files_to_delete = self.list_files(remote_root_dir)
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

    def _list_files(self, remote_root_dir: str) -> List[str]:
        files = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=remote_root_dir):
            if "Contents" in page:
                files.extend([obj["Key"] for obj in page["Contents"]])
        return files


class AzureFileManager(BaseFileManager):
    def __init__(self, connection_string: str, container_name: str):
        from azure.storage.blob import BlobServiceClient
        self.blob_service = BlobServiceClient.from_connection_string(connection_string)
        self.container = self.blob_service.get_container_client(container_name)
        super().__init__()

    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        with open(file_path, "rb") as data:
            self.container.upload_blob(name=destination_path, data=data, overwrite=True)
        return os.path.join("azure://", self.container.container_name, destination_path)

    def _download_file_from_storage(self, file_path: str, local_path: str) -> str:
        blob_client = self.container.get_blob_client(file_path)
        with open(local_path, "wb") as file:
            data = blob_client.download_blob()
            file.write(data.readall())
        return local_path

    def _remove_file_from_storage(self, file_path: str) -> bool:
        try:
            blob_client = self.container.get_blob_client(file_path)
            if blob_client.exists():
                blob_client.delete_blob()
            return True
        except Exception as e:
            log.error(f"Error while removing file {file_path} from storage: {e}")
            return False

    def _remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        try:
            for file_path in self.list_files(remote_root_dir):
                blob_client = self.container.get_blob_client(file_path)
                blob_client.delete_blob()
            return True
        except Exception as e:
            log.error(f"Error while removing storage: {e}")
            return False

    def _list_files(self, remote_root_dir: str) -> List[str]:
        return [blob.name for blob in self.container.list_blobs(name_starts_with=remote_root_dir)]


class GoogleCloudFileManager(BaseFileManager):
    def __init__(self, bucket_name: str, credentials_path: str):
        from google.cloud import storage
        self.storage_client = storage.Client.from_service_account_json(credentials_path)
        self.bucket = self.storage_client.bucket(bucket_name)
        super().__init__()

    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        blob = self.bucket.blob(destination_path)
        blob.upload_from_filename(file_path)
        return os.path.join("gs://", self.bucket.name, destination_path)

    def _download_file_from_storage(self, file_path: str, local_path: str) -> str:
        blob = self.bucket.blob(file_path)
        blob.download_to_filename(local_path)
        return local_path

    def _remove_file_from_storage(self, file_path: str) -> bool:
        try:
            blob = self.bucket.blob(file_path)
            if blob.exists():
                blob.delete()
            return True
        except Exception as e:
            log.error(f"Error while removing file {file_path} from storage: {e}")
            return False

    def _remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        try:
            for file_path in self.list_files(remote_root_dir):
                blob = self.bucket.blob(file_path)
                blob.delete()
            return True
        except Exception as e:
            log.error(f"Error while removing storage: {e}")
            return False

    def _list_files(self, remote_root_dir: str) -> List[str]:
        return [blob.name for blob in self.bucket.list_blobs(prefix=remote_root_dir)]


class DigitalOceanFileManager(AWSFileManager):
    pass
