"""抽取载荷 S3 中转 store 单测：gzip 往返 / key 确定性 / 清理与 lifecycle。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from types import SimpleNamespace

import pytest

from service import extract_payload_store as store


class FakeBody(BytesIO):
    def close(self) -> None:  # noqa: D102
        pass


class FakeS3:
    """内存版 S3Storage：记录上传、按 mtime 过期模拟 list。"""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.mtimes: dict[str, datetime] = {}
        self.lifecycle_rules: list[dict] = []

    @property
    def bucket(self) -> str:
        return "b"

    def put_bytes(self, key: str, data: bytes, content_type: str) -> SimpleNamespace:
        self.objects[key] = data
        self.mtimes[key] = datetime.now(UTC)
        return SimpleNamespace(bucket=self.bucket, object_key=key, etag=None)

    def get_object(self, bucket: str, key: str) -> FakeBody:
        return FakeBody(self.objects[key])

    def delete_object(self, bucket: str, key: str) -> None:
        self.objects.pop(key, None)
        self.mtimes.pop(key, None)

    def list_objects(self, prefix: str) -> list:
        return [
            SimpleNamespace(object_key=k, size=len(v), last_modified=self.mtimes[k])
            for k, v in self.objects.items()
            if k.startswith(prefix)
        ]

    def get_lifecycle_rules(self) -> list[dict]:
        return [dict(r) for r in self.lifecycle_rules]

    def put_lifecycle_rules(self, rules: list[dict]) -> None:
        self.lifecycle_rules = [dict(r) for r in rules]


@pytest.fixture
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    fake = FakeS3()
    monkeypatch.setattr("infra.s3.get_schema_s3_storage", lambda: fake)
    return fake


class TestPutGetRoundtrip:
    def test_gzip_roundtrip(self, fake_s3: FakeS3):
        data = store.dumps_payload(
            {"rows": [{"id": f"r{i}", "blob": "甲乙丙丁" * 200} for i in range(3)]}
        )
        key = store.put_extract_payload("source:bind-1", 3, "rows-00", data)
        assert key.endswith(".json.gz")
        # 存的确实是 gzip（重复文本压缩后明显小于原文）
        assert fake_s3.objects[key][:2] == b"\x1f\x8b"
        assert len(fake_s3.objects[key]) < len(data)
        assert store.get_extract_payload(key) == data

    def test_gzip_off_raw_roundtrip(self, fake_s3: FakeS3, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SCHEMA_EXTRACT_PAYLOAD_GZIP", "false")
        data = store.dumps_payload([1, 2, 3])
        key = store.put_extract_payload("s", 0, "rows-00", data)
        assert fake_s3.objects[key] == data
        assert store.get_extract_payload(key) == data

    def test_json_helpers(self, fake_s3: FakeS3):
        value = {"entities": [{"id": "x", "props": {"名称": "甲"}}], "stats": {"n": 2}}
        key = store.put_extract_payload_json("s", 0, "out-00", value)
        assert store.load_extract_payload_json(key) == value


class TestKeyDerivation:
    def test_key_layout_and_determinism(self):
        kwargs = {"workflow_id": "wf-1", "run_id": "run-1"}
        k1 = store.extract_payload_key("source:bind-1", 2, "rows-01", **kwargs)
        k2 = store.extract_payload_key("source:bind-1", 2, "rows-01", **kwargs)
        assert k1 == k2
        assert k1 == "runs/wf-1/run-1/payloads/source:bind-1/0002/rows-01.json.gz"

    def test_same_context_same_key(self):
        # 无 activity 上下文时 local- 兜底：同一次调用的上下文内 key 稳定由调用方保证；
        # 显式传参时两次派生必然一致（activity 重试幂等的基础）
        a = store.extract_payload_key("s", 0, "out-00", workflow_id="w", run_id="r")
        b = store.extract_payload_key("s", 0, "out-00", workflow_id="w", run_id="r")
        assert a == b

    def test_different_chunk_different_key(self):
        kwargs = {"workflow_id": "w", "run_id": "r"}
        assert store.extract_payload_key("s", 0, "out-00", **kwargs) != store.extract_payload_key(
            "s", 0, "out-01", **kwargs
        )


class TestCleanup:
    def test_cleanup_deletes_only_expired(self, fake_s3: FakeS3, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SCHEMA_EXTRACT_PAYLOAD_RETENTION_DAYS", "7")
        old_key = store.put_extract_payload_json("s", 0, "rows-00", [{"id": 1}])
        new_key = store.put_extract_payload_json("s", 0, "rows-01", [{"id": 2}])
        fake_s3.mtimes[old_key] = datetime.now(UTC) - timedelta(days=8)
        result = store.cleanup_run_artifacts()
        assert result["deleted"] == 1
        assert old_key not in fake_s3.objects
        assert new_key in fake_s3.objects

    def test_lifecycle_rule_upserted_not_duplicated(
        self, fake_s3: FakeS3, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("SCHEMA_EXTRACT_PAYLOAD_RETENTION_DAYS", "3")
        fake_s3.lifecycle_rules = [
            {"ID": "other-rule", "Filter": {"Prefix": "other/"}, "Status": "Enabled"}
        ]
        store.cleanup_run_artifacts()
        store.cleanup_run_artifacts()  # 第二次不重复
        ours = [r for r in fake_s3.lifecycle_rules if r["ID"] == store.LIFECYCLE_RULE_ID]
        others = [r for r in fake_s3.lifecycle_rules if r["ID"] == "other-rule"]
        assert len(ours) == 1 and len(others) == 1
        assert ours[0]["Filter"] == {"Prefix": "runs/"}
        assert ours[0]["Expiration"] == {"Days": 3}


class TestEnvKnobs:
    def test_flag_default_off(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SCHEMA_EXTRACT_PAYLOAD_S3_ENABLED", raising=False)
        assert store.payload_s3_enabled() is False

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("", 8 * 1024 * 1024), ("1048576", 1048576), ("not-a-number", 8 * 1024 * 1024)],
    )
    def test_max_bytes_tolerates_bad_values(self, monkeypatch, raw, expected):
        monkeypatch.setenv("SCHEMA_EXTRACT_PAYLOAD_MAX_BYTES", raw)
        assert store.payload_max_bytes() == expected
