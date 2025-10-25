import logging
from dataclasses import dataclass

from minio import Minio
from minio.error import S3Error

@dataclass
class MinioAuthenticator:
    username: str
    password: str
    host: str
    port: int

class MinioClient:
    def __init__(self, authenticator: MinioAuthenticator, secure: bool = True, logger: logging.Logger = logging.getLogger()):
        url = f"{authenticator.host}:{authenticator.port}"
        self.client = Minio(
            endpoint=url,
            access_key=authenticator.username,
            secret_key=authenticator.password,
            secure=secure
        )
        self.logger = logger

    def create_bucket(self, bucket_name: str):
        """Create a bucket if non existant"""
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                self.logger.info("Bucket %s was created", bucket_name)
            else:
                self.logger.info("Bucket %s already exists", bucket_name)
        except S3Error as err:
            self.logger.error("Error during the bucket creation: %s", err)

    def upload_file(self, bucket_name: str, object_name: str, file_path: str):
        """Upload a file to the specified bucket"""
        try:
            self.client.fput_object(bucket_name, object_name, file_path)
            self.logger.info("File %s was upload as %s in %s", file_path, object_name, bucket_name)
        except S3Error as err:
            self.logger.error("Error during the file upload: %s", err)

    def download_file(self, bucket_name: str, object_name: str, file_path: str):
        """Download a file from the specified bucket"""
        try:
            self.client.fget_object(bucket_name, object_name, file_path)
            self.logger.info("File %s downloaded into %s", object_name, file_path)
        except S3Error as err:
            self.logger.error("Error during the file download: %s", err)

    def get_objects(self, bucket_name: str) -> list:
        """Returns all the objects within a bucket"""
        try:
            objects = self.client.list_objects(bucket_name)
            return objects
        except S3Error as err:
            self.logger.error("Error during the file listing: %s", err)

    def delete_object(self, bucket_name: str, object_name: str):
        """Delete a file from a bucket"""
        try:
            self.client.remove_object(bucket_name, object_name)
            self.logger.info("File %s was deleted from the bucket %s", object_name, bucket_name)
        except S3Error as err:
            self.logger.error("Error during the file deletion: %s", err)
