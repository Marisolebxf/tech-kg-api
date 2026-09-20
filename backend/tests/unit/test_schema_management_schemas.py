"""Schema 管理请求模型的文本长度上限（与前端 utils/textInput.ts 规则对齐）。

前端 SCHEMA_ENTITY_NAME_RULE/SCHEMA_LABEL_RULE/PROP_NAME_RULE 上限 128、
SCHEMA_DESC_RULE 上限 4000；后端曾全局卡 64 导致合法输入被拒。
"""

import pytest
from pydantic import ValidationError

from biz.schemas.schema_management import (
    EntitySchemaCreate,
    RelationSchemaCreate,
    SchemaPropertyInput,
)


def _payload(**overrides):
    base = {
        "schema_key": "gadget",
        "name": "Gadget",
        "label": "部件",
        "description": "",
        "properties": [{"name": "id", "data_type": "string"}],
    }
    base.update(overrides)
    return base


def _relation_payload(**overrides):
    base = _payload(
        schema_key="uses_technology",
        name="USES_TECHNOLOGY",
        label="使用技术",
        source_schema_id="018f1a2b-0000-4000-8000-000000000001",
        target_schema_id="018f1a2b-0000-4000-8000-000000000002",
    )
    base.update(overrides)
    return base


class TestSchemaCreateTextLimits:
    def test_label_128_chars_accepted(self):
        entity = EntitySchemaCreate(**_payload(label="部" * 128))
        assert len(entity.label) == 128

    def test_label_129_chars_rejected(self):
        with pytest.raises(ValidationError):
            EntitySchemaCreate(**_payload(label="部" * 129))

    def test_label_65_chars_accepted(self):
        # 修复点：65 字中文名曾被 check_text 的全局 64 上限打回
        entity = EntitySchemaCreate(**_payload(label="部" * 65))
        assert len(entity.label) == 65

    def test_label_abnormal_chars_rejected(self):
        with pytest.raises(ValidationError, match="异常字符"):
            EntitySchemaCreate(**_payload(label="部件!"))

    def test_name_128_chars_accepted(self):
        entity = EntitySchemaCreate(**_payload(name="A" + "b" * 127))
        assert len(entity.name) == 128

    def test_name_129_chars_rejected(self):
        with pytest.raises(ValidationError):
            EntitySchemaCreate(**_payload(name="A" + "b" * 128))

    def test_description_4000_chars_accepted(self):
        entity = EntitySchemaCreate(**_payload(description="说" * 4000))
        assert len(entity.description) == 4000

    def test_description_4001_chars_rejected(self):
        with pytest.raises(ValidationError):
            EntitySchemaCreate(**_payload(description="说" * 4001))

    def test_description_abnormal_chars_rejected(self):
        with pytest.raises(ValidationError, match="异常字符"):
            EntitySchemaCreate(**_payload(description="说明含#"))

    def test_identity_key_still_capped_at_64(self):
        # identity_key 未放开，维持全局 64 上限
        with pytest.raises(ValidationError, match="64"):
            EntitySchemaCreate(**_payload(identity_key="k" * 65))


class TestRelationNameLimit:
    def test_relation_name_64_chars_accepted(self):
        relation = RelationSchemaCreate(**_relation_payload(name="U" + "S" * 63))
        assert len(relation.name) == 64

    def test_relation_name_65_chars_rejected(self):
        # 关系英文名（EDGE 类型名）单独收紧到 64，实体名维持 128
        with pytest.raises(ValidationError):
            RelationSchemaCreate(**_relation_payload(name="U" + "S" * 64))

    def test_entity_name_128_still_accepted(self):
        entity = EntitySchemaCreate(**_payload(name="A" + "b" * 127))
        assert len(entity.name) == 128


class TestSchemaPropertyInputLimits:
    def test_property_name_128_chars_accepted(self):
        prop = SchemaPropertyInput(name="p" * 128, data_type="string")
        assert len(prop.name) == 128

    def test_property_name_129_chars_rejected(self):
        with pytest.raises(ValidationError):
            SchemaPropertyInput(name="p" * 129, data_type="string")
