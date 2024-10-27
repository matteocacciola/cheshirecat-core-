from abc import ABC, abstractmethod
import os
from typing import List


class BaseUploader(ABC):
    """
    Base class for cloud uploaders. It defines the interface that all cloud uploaders must implement. It is used to
    upload files and folders composing an installed plugin to a cloud storage service.
    Method `upload_directory`, `download_file`, `download_directory`, `list_files`
    MUST be implemented by subclasses.
    """

    @abstractmethod
    def upload_file(self, file_path: str, destination_path: str) -> str:
        """Upload a single file on the cloud"""
        pass

    @abstractmethod
    def download_file(self, cloud_path: str, local_path: str) -> str:
        """Download a single file from the cload to the local_path"""
        pass

    @abstractmethod
    def download_directory(self, cloud_dir: str, local_dir: str):
        """Download a directory with all the contained files from the cloud to local_dir"""
        pass

    @abstractmethod
    def list_files(self, cloud_dir: str) -> List[str]:
        """Lista tutti i file in una directory del cloud"""
        pass

    def upload_directory(self, local_dir: str, destination_dir: str) -> List[str]:
        """Upload a directory with all the contained files on the cloud"""
        uploaded_files = []
        for root, _, files in os.walk(local_dir):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, local_dir)
                destination_path = os.path.join(destination_dir, relative_path)
                uploaded_files.append(self.upload_file(local_path, destination_path))
        return uploaded_files


class LocalUploader(BaseUploader):
    def __init__(self):
        import shutil
        self.move = shutil.move
        pass

    def upload_file(self, file_path: str, destination_path: str) -> str:
        if file_path == destination_path:
            return destination_path

        # move the file from file_path to destination_path
        self.move(file_path, destination_path)
        return destination_path

    def download_file(self, cloud_path: str, local_path: str) -> str:
        if cloud_path == local_path:
            return local_path

        # move the file from cloud_path to local_path
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.move(cloud_path, local_path)
        return local_path

    def download_directory(self, cloud_dir: str, local_dir: str):
        """Upload a directory with all the contained files on the cloud"""
        downloaded_files = []
        for root, _, files in os.walk(cloud_dir):
            for file in files:
                cloud_path = os.path.join(root, file)
                relative_path = os.path.relpath(cloud_path, local_dir)
                local_path = os.path.join(local_dir, relative_path)
                downloaded_files.append(self.download_file(cloud_path, local_path))
        return downloaded_files

    def list_files(self, cloud_dir: str) -> List[str]:
        return [os.path.join(root, file) for root, _, files in os.walk(cloud_dir) for file in files]


class AWSUploader(BaseUploader):
    def __init__(self, bucket_name: str, aws_access_key: str, aws_secret_key: str):
        import boto3
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        self.bucket_name = bucket_name

    def upload_file(self, file_path: str, destination_path: str) -> str:
        self.s3.upload_file(file_path, self.bucket_name, destination_path)
        return f"s3://{self.bucket_name}/{destination_path}"

    def download_file(self, cloud_path: str, local_path: str) -> str:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        self.s3.download_file(self.bucket_name, cloud_path, local_path)
        return local_path

    def download_directory(self, cloud_dir: str, local_dir: str) -> List[str]:
        downloaded_files = []
        cloud_files = self.list_files(cloud_dir)

        for cloud_path in cloud_files:
            relative_path = os.path.relpath(cloud_path, cloud_dir)
            local_path = os.path.join(local_dir, relative_path)
            downloaded_files.append(self.download_file(cloud_path, local_path))

        return downloaded_files

    def list_files(self, cloud_dir: str) -> List[str]:
        files = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=cloud_dir):
            if "Contents" in page:
                files.extend([obj["Key"] for obj in page["Contents"]])
        return files


class AzureUploader(BaseUploader):
    def __init__(self, connection_string: str, container_name: str):
        from azure.storage.blob import BlobServiceClient
        self.blob_service = BlobServiceClient.from_connection_string(connection_string)
        self.container = self.blob_service.get_container_client(container_name)

    def upload_file(self, file_path: str, destination_path: str) -> str:
        with open(file_path, "rb") as data:
            self.container.upload_blob(name=destination_path, data=data, overwrite=True)
        return f"azure://{self.container.container_name}/{destination_path}"

    def download_file(self, cloud_path: str, local_path: str) -> str:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob_client = self.container.get_blob_client(cloud_path)
        with open(local_path, "wb") as file:
            data = blob_client.download_blob()
            file.write(data.readall())
        return local_path

    def download_directory(self, cloud_dir: str, local_dir: str) -> List[str]:
        downloaded_files = []
        cloud_files = self.list_files(cloud_dir)

        for cloud_path in cloud_files:
            relative_path = os.path.relpath(cloud_path, cloud_dir)
            local_path = os.path.join(local_dir, relative_path)
            downloaded_files.append(self.download_file(cloud_path, local_path))

        return downloaded_files

    def list_files(self, cloud_dir: str) -> List[str]:
        return [blob.name for blob in self.container.list_blobs(name_starts_with=cloud_dir)]


class GoogleCloudUploader(BaseUploader):
    def __init__(self, bucket_name: str, credentials_path: str):
        from google.cloud import storage
        self.storage_client = storage.Client.from_service_account_json(credentials_path)
        self.bucket = self.storage_client.bucket(bucket_name)

    def upload_file(self, file_path: str, destination_path: str) -> str:
        blob = self.bucket.blob(destination_path)
        blob.upload_from_filename(file_path)
        return f"gs://{self.bucket.name}/{destination_path}"

    def download_file(self, cloud_path: str, local_path: str) -> str:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob = self.bucket.blob(cloud_path)
        blob.download_to_filename(local_path)
        return local_path

    def download_directory(self, cloud_dir: str, local_dir: str) -> List[str]:
        downloaded_files = []
        cloud_files = self.list_files(cloud_dir)

        for cloud_path in cloud_files:
            relative_path = os.path.relpath(cloud_path, cloud_dir)
            local_path = os.path.join(local_dir, relative_path)
            downloaded_files.append(self.download_file(cloud_path, local_path))

        return downloaded_files

    def list_files(self, cloud_dir: str) -> List[str]:
        return [blob.name for blob in self.bucket.list_blobs(prefix=cloud_dir)]
