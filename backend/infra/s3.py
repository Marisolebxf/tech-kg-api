"""基于 boto3 的 S3 对象存储封装，兼容 MinIO 的 S3 协议。"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any, BinaryIO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class StoredObject:
    bucket: str
    object_key: str
    etag: str | None


class S3Storage:
    """只使用标准 S3 API 的脚本对象存储。"""

    def __init__(
        self,
        *,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str | None = None,
        bucket: str | None = None,
        secure: bool | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url or os.getenv(
            "SCHEMA_S3_ENDPOINT_URL", "http://127.0.0.1:9020"
        )
        self.access_key = access_key or os.getenv("SCHEMA_S3_ACCESS_KEY", "rustfsadmin")
        self.secret_key = secret_key or os.getenv("SCHEMA_S3_SECRET_KEY", "rustfsadmin")
        self.region = region or os.getenv("SCHEMA_S3_REGION", "us-east-1")
        self.bucket = bucket or os.getenv("SCHEMA_S3_BUCKET", "tech-kg-schema-scripts")
        self.secure = (
            secure
            if secure is not None
            else os.getenv("SCHEMA_S3_SECURE", "false").lower() == "true"
        )
        self._client: Any | None = None
        self._bucket_ready = False
        self._lock = threading.RLock()

    @property
    def client(self) -> Any:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = boto3.client(
                        "s3",
                        endpoint_url=self.endpoint_url,
                        aws_access_key_id=self.access_key,
                        aws_secret_access_key=self.secret_key,
                        region_name=self.region,
                        use_ssl=self.secure,
                        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
                    )
        return self._client

    def ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        with self._lock:
            if self._bucket_ready:
                return
            try:
                self.client.head_bucket(Bucket=self.bucket)
            except ClientError as exc:
                error_code = str(exc.response.get("Error", {}).get("Code", ""))
                if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                    raise
                params: dict[str, Any] = {"Bucket": self.bucket}
                if self.region != "us-east-1":
                    params["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
                self.client.create_bucket(**params)
            self._bucket_ready = True

    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> StoredObject:
        self.ensure_bucket()
        response = self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )
        etag = response.get("ETag")
        return StoredObject(
            bucket=self.bucket,
            object_key=object_key,
            etag=etag.strip('"') if isinstance(etag, str) else None,
        )

    def get_object(self, bucket: str, object_key: str) -> BinaryIO:
        response = self.client.get_object(Bucket=bucket, Key=object_key)
        return response["Body"]

    def delete_object(self, bucket: str, object_key: str) -> None:
        self.client.delete_object(Bucket=bucket, Key=object_key)


_storage: S3Storage | None = None
_storage_lock = threading.Lock()


def get_schema_s3_storage() -> S3Storage:
    global _storage
    if _storage is None:
        with _storage_lock:
            if _storage is None:
                _storage = S3Storage()
    return _storage
