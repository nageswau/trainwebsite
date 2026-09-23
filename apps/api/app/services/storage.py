import uuid
from pathlib import Path

import boto3

from app.core.config import settings


class StorageService:
    def __init__(self):
        self.bucket = settings.aws_s3_bucket
        self.local_dir = Path(settings.local_upload_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)

    def presign_upload(self, filename: str, content_type: str) -> dict:
        safe_name = Path(filename).name.replace(" ", "-")[:180] or "upload.bin"
        key = f"uploads/{uuid.uuid4().hex}-{safe_name}"
        if self.bucket:
            s3 = boto3.client("s3", region_name=settings.aws_region)
            url = s3.generate_presigned_url("put_object", Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type}, ExpiresIn=900)
            return {"provider": "s3", "key": key, "upload_url": url, "expires_in": 900}
        return {"provider": "local", "key": key, "upload_url": "/api/v1/files/local-upload", "expires_in": 900}

    def presign_download(self, key: str) -> str:
        if not self.bucket:
            return f"/local-files/{key.lstrip('/')}"
        return boto3.client("s3", region_name=settings.aws_region).generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=900)

    def write_bytes(self, key: str, data: bytes, content_type: str) -> None:
        if self.bucket:
            boto3.client("s3", region_name=settings.aws_region).put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256")
            return
        destination = self.local_dir / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    def _local_path(self, key: str) -> Path:
        """Resolve a key under the storage root. Keys are server-generated, but a read or delete still checks
        the resolved target is strictly below the root (ENH-025 spec §5)."""
        root = self.local_dir.resolve()
        path = (self.local_dir / key).resolve()
        if root not in path.parents:
            raise ValueError("storage key resolves outside the upload root")
        return path

    def read_bytes(self, key: str) -> bytes:
        if self.bucket:
            return boto3.client("s3", region_name=settings.aws_region).get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return self._local_path(key).read_bytes()

    def delete(self, key: str) -> None:
        if self.bucket:
            boto3.client("s3", region_name=settings.aws_region).delete_object(Bucket=self.bucket, Key=key)
            return
        self._local_path(key).unlink(missing_ok=True)


storage = StorageService()
