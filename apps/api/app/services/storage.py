import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

import boto3
import jwt

from app.core.config import settings
from app.core.security import ALGORITHM

# nehn-003 (DEC-SCOPE-279 PS2): a local-mode download link lives as long as an S3 presigned URL.
DOWNLOAD_TTL_SECONDS = 900
DOWNLOAD_TOKEN_TYPE = "download"


class StorageService:
    def __init__(self):
        self.bucket = settings.aws_s3_bucket
        self.local_dir = Path(settings.local_upload_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)

    def _client(self):
        """nehn-003 PS1: one S3 client for every call, pointed at `S3_ENDPOINT_URL` when set (DigitalOcean Spaces, MinIO)."""
        return boto3.client("s3", region_name=settings.aws_region, endpoint_url=settings.s3_endpoint_url or None)

    def _put_args(self, content_type: str) -> dict:
        args = {"ContentType": content_type}
        if settings.s3_sse:  # PS1: configurable, since SSE is untested on Spaces
            args["ServerSideEncryption"] = settings.s3_sse
        return args

    def presign_upload(self, filename: str, content_type: str) -> dict:
        safe_name = Path(filename).name.replace(" ", "-")[:180] or "upload.bin"
        key = f"uploads/{uuid.uuid4().hex}-{safe_name}"
        if self.bucket:
            url = self._client().generate_presigned_url("put_object", Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type}, ExpiresIn=900)
            return {"provider": "s3", "key": key, "upload_url": url, "expires_in": 900}
        return {"provider": "local", "key": key, "upload_url": "/api/v1/files/local-upload", "expires_in": 900}

    def presign_download(self, key: str) -> str:
        """A short-lived link to one object. Locally it is a signed API route (PS2), never the public `/local-files` path."""
        key = key.lstrip("/")
        if not self.bucket:
            exp = datetime.now(UTC) + timedelta(seconds=DOWNLOAD_TTL_SECONDS)
            token = jwt.encode({"sub": key, "type": DOWNLOAD_TOKEN_TYPE, "exp": exp}, settings.secret_key, algorithm=ALGORITHM)
            return f"/api/v1/files/signed/{token}"
        return self._client().generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=DOWNLOAD_TTL_SECONDS)

    @staticmethod
    def signed_key(token: str) -> str | None:
        """The key a `presign_download` token was issued for, or None when it is forged, expired or not a download token."""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        except jwt.PyJWTError:
            return None
        return payload.get("sub") if payload.get("type") == DOWNLOAD_TOKEN_TYPE else None

    def write_bytes(self, key: str, data: bytes, content_type: str) -> None:
        if self.bucket:
            self._client().put_object(Bucket=self.bucket, Key=key, Body=data, **self._put_args(content_type))
            return
        destination = self.local_dir / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    def write_stream(self, key: str, stream: BinaryIO, content_type: str) -> None:
        """nehn-003 PS6: copy an upload in chunks (S3 multipart or a local file), never reading it whole into memory."""
        stream.seek(0)
        if self.bucket:
            self._client().upload_fileobj(stream, self.bucket, key, ExtraArgs=self._put_args(content_type))
            return
        destination = self.local_dir / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as out:
            shutil.copyfileobj(stream, out, 1024 * 1024)

    def _local_path(self, key: str) -> Path:
        """Resolve a key under the storage root. Keys are server-generated, but a read or delete still checks
        the resolved target is strictly below the root (ENH-025 spec §5)."""
        root = self.local_dir.resolve()
        path = (self.local_dir / key).resolve()
        if root not in path.parents:
            raise ValueError("storage key resolves outside the upload root")
        return path

    def local_file(self, key: str) -> Path | None:
        """The local file behind `key` for streaming, or None when it is missing or escapes the root."""
        try:
            path = self._local_path(key)
        except ValueError:
            return None
        return path if path.is_file() else None

    def read_bytes(self, key: str) -> bytes:
        if self.bucket:
            return self._client().get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return self._local_path(key).read_bytes()

    def delete(self, key: str) -> None:
        if self.bucket:
            self._client().delete_object(Bucket=self.bucket, Key=key)
            return
        self._local_path(key).unlink(missing_ok=True)


storage = StorageService()
