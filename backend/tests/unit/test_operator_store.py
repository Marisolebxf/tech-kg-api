from __future__ import annotations

from io import BytesIO

from botocore.exceptions import ClientError

from infra.operator_store import S3OperatorStore


class FakeS3Client:
    def __init__(self, bucket_exists: bool = True) -> None:
        self.bucket_exists = bucket_exists
        self.objects: dict[str, bytes] = {}

    def head_bucket(self, *, Bucket):
        if not self.bucket_exists:
            raise ClientError({"Error": {"Code": "404", "Message": "missing"}}, "HeadBucket")

    def create_bucket(self, **kwargs):
        self.bucket_exists = True

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "missing"}}, "HeadObject")

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body

    def delete_object(self, *, Bucket, Key):
        self.objects.pop(Key, None)

    def list_objects_v2(self, *, Bucket, Prefix, ContinuationToken=None):
        keys = sorted(key for key in self.objects if key.startswith(Prefix))
        return {"Contents": [{"Key": key} for key in keys], "IsTruncated": False}

    def get_object(self, *, Bucket, Key):
        return {"Body": BytesIO(self.objects[Key])}


def test_s3_operator_store_uses_single_json_bundle_object():
    client = FakeS3Client(bucket_exists=False)
    store = S3OperatorStore(bucket="operators", prefix="user-code", client=client)
    bundle = {
        "manifest": {"name": "user.demo", "version": "1.0.0"},
        "source": "def operator(data, ctx):\n    return data\n",
    }

    store.ensure_ready()
    store.put("user.demo", bundle)

    assert client.bucket_exists is True
    assert set(client.objects) == {"user-code/user.demo.json"}
    assert store.exists("user.demo") is True
    assert store.list_bundles() == [bundle]

    store.delete("user.demo")
    assert store.exists("user.demo") is False
