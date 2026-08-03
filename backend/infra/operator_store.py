"""通过 S3 兼容协议持久化用户算子 bundle。"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class OperatorStoreError(RuntimeError):
    """对象存储访问失败。"""


class S3OperatorStore:
    """S3 兼容对象存储；可连接 RustFS、AWS S3 或其他兼容实现。"""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "operators",
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region: str = "us-east-1",
        client: Any | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.region = region
        self._client = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def _key(self, name: str) -> str:
        filename = f"{name}.json"
        return f"{self.prefix}/{filename}" if self.prefix else filename

    def ensure_ready(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                raise OperatorStoreError(f"检查算子 bucket 失败: {exc}") from exc
        except BotoCoreError as exc:
            raise OperatorStoreError(f"连接算子对象存储失败: {exc}") from exc

        arguments: dict[str, Any] = {"Bucket": self.bucket}
        if self.region != "us-east-1":
            arguments["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
        try:
            self._client.create_bucket(**arguments)
        except (BotoCoreError, ClientError) as exc:
            raise OperatorStoreError(f"创建算子 bucket 失败: {exc}") from exc

    def exists(self, name: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=self._key(name))
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise OperatorStoreError(f"检查算子对象失败: {exc}") from exc
        except BotoCoreError as exc:
            raise OperatorStoreError(f"检查算子对象失败: {exc}") from exc

    def put(self, name: str, bundle: dict[str, Any]) -> None:
        body = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode()
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=self._key(name),
                Body=body,
                ContentType="application/json; charset=utf-8",
            )
        except (BotoCoreError, ClientError) as exc:
            raise OperatorStoreError(f"保存算子对象失败: {exc}") from exc

    def delete(self, name: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=self._key(name))
        except (BotoCoreError, ClientError) as exc:
            raise OperatorStoreError(f"删除算子对象失败: {exc}") from exc

    def list_bundles(self) -> list[dict[str, Any]]:
        prefix = f"{self.prefix}/" if self.prefix else ""
        bundles: list[dict[str, Any]] = []
        continuation_token: str | None = None
        try:
            while True:
                arguments: dict[str, Any] = {"Bucket": self.bucket, "Prefix": prefix}
                if continuation_token:
                    arguments["ContinuationToken"] = continuation_token
                response = self._client.list_objects_v2(**arguments)
                for item in response.get("Contents", []):
                    key = str(item.get("Key", ""))
                    if not key.endswith(".json"):
                        continue
                    stored = self._client.get_object(Bucket=self.bucket, Key=key)
                    value = json.loads(stored["Body"].read().decode("utf-8"))
                    if not isinstance(value, dict):
                        raise OperatorStoreError(f"算子对象格式错误: {key}")
                    bundles.append(value)
                if not response.get("IsTruncated"):
                    break
                continuation_token = response.get("NextContinuationToken")
        except OperatorStoreError:
            raise
        except (BotoCoreError, ClientError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OperatorStoreError(f"读取算子对象失败: {exc}") from exc
        return bundles


def create_operator_store_from_env() -> S3OperatorStore | None:
    """未配置 bucket 时使用纯本地模式，方便测试和本机开发。"""
    bucket = os.getenv("OPERATOR_S3_BUCKET", "").strip()
    if not bucket:
        return None
    return S3OperatorStore(
        bucket=bucket,
        prefix=os.getenv("OPERATOR_S3_PREFIX", "operators"),
        endpoint_url=os.getenv("OPERATOR_S3_ENDPOINT_URL") or None,
        access_key_id=os.getenv("OPERATOR_S3_ACCESS_KEY_ID") or None,
        secret_access_key=os.getenv("OPERATOR_S3_SECRET_ACCESS_KEY") or None,
        region=os.getenv("OPERATOR_S3_REGION", "us-east-1"),
    )
