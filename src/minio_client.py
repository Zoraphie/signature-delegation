import logging
from dataclasses import dataclass

import aioboto3

@dataclass
class MinioAuthenticator:
    username: str
    password: str
    host: str
    port: int

class AsyncMinioClient:
    def __init__(self, authenticator: MinioAuthenticator, secure: bool = True, logger: logging.Logger = logging.getLogger()):
        if secure:
            prefix = "https://"
        else:
            prefix = "http://"
        self.url = f"{prefix}{authenticator.host}:{authenticator.port}"
        self.authenticator = authenticator
        self.logger = logger
        self.default_bucket = None

    def set_default_bucket(self, bucket_name: str):
        self.default_bucket = bucket_name

    def resolve_bucket_name(self, bucket_name: str | None) -> str:
        if bucket_name is None:
            if self.default_bucket is None:
                raise ValueError("Default bucket was not properly initialized")
            return self.default_bucket
        return bucket_name

    async def _get_client(self):
        session = aioboto3.Session()
        return session.client(
            "s3",
            endpoint_url=self.url,
            aws_access_key_id=self.authenticator.username,
            aws_secret_access_key=self.authenticator.password,
            region_name="us-east-1"
        )

    async def create_bucket(self, bucket_name: str | None = None):
        """Create a bucket if non existant"""
        bucket_name = self.resolve_bucket_name(bucket_name)
        async with await self._get_client() as client:
            exists = await client.list_buckets()
            if bucket_name not in [b['Name'] for b in exists.get('Buckets', [])]:
                await client.create_bucket(Bucket=bucket_name)
                self.logger.info("Bucket %s was created", bucket_name)
            else:
                self.logger.info("Bucket %s already exists", bucket_name)

    async def upload_file(self, object_name: str, file_path: str, bucket_name: str | None = None):
        """Upload a file from path to the specified bucket"""
        bucket_name = self.resolve_bucket_name(bucket_name)
        async with await self._get_client() as client:
            await client.upload_file(file_path, bucket_name, object_name)
            self.logger.info("File %s was upload as %s in %s", file_path, object_name, bucket_name)

    async def upload_file_from_bytes(self, object_name: str, file_data: bytes, bucket_name: str | None = None):
        """Upload a file from bytes to the specified bucket"""
        bucket_name = self.resolve_bucket_name(bucket_name)
        async with await self._get_client() as client:
            await client.put_object(
                Bucket=bucket_name,
                Key=object_name,
                Body=file_data,
                ContentLength=len(file_data)
            )

    async def download_file(self, object_name: str, file_path: str, bucket_name: str | None = None):
        """Download a file from the specified bucket"""
        bucket_name = self.resolve_bucket_name(bucket_name)
        async with await self._get_client() as client:
            await client.download_file(bucket_name, object_name, file_path)
            self.logger.info("File %s downloaded into %s", object_name, file_path)

    async def list_objects(self, bucket_name: str | None = None) -> list[dict]:
        """Returns all the objects within a bucket"""
        bucket_name = self.resolve_bucket_name(bucket_name)
        async with await self._get_client() as client:
            response = await client.list_objects_v2(Bucket=bucket_name)
            objects = response.get('Contents', [])
            result = []
            for obj in objects:
                result.append({
                    "object_name": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat()
                })
            return result

    async def delete_object(self, object_name: str, bucket_name: str | None = None):
        """Delete a file from a bucket"""
        bucket_name = self.resolve_bucket_name(bucket_name)
        async with await self._get_client() as client:
            await client.delete_object(Bucket=bucket_name, Key=object_name)
            self.logger.info("File %s was deleted from the bucket %s", object_name, bucket_name)
