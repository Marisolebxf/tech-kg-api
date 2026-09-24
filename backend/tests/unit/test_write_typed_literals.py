"""ngql_value_for_column 列类型双向适配的单测（write_records 写图格式化）。

背景：dev 空间等存量 Schema 的列不全是 string（Patent 有 int64/datetime/double，
Person 有 int64），脚本输出的值类型与之并不总一致（时间列常收到 "" 或 ISO 文本，
计数列可能收到字符串数字）——裸字面量与列类型不匹配会被 Nebula 以
"data type does not meet the requirements" 拒绝。
"""

from __future__ import annotations

from service.temporal_workflows import (
    ngql_datetime_literal,
    ngql_value_for_column,
)


class TestNumericColumns:
    def test_int_value_into_int_column(self):
        assert ngql_value_for_column(20210101, "int64", True) == "20210101"

    def test_numeric_string_into_int_column(self):
        assert ngql_value_for_column("20210101", "int64", True) == "20210101"

    def test_float_string_into_int_column_truncates(self):
        assert ngql_value_for_column("20210101.0", "int64", True) == "20210101"

    def test_empty_string_into_nullable_int_is_null(self):
        assert ngql_value_for_column("", "int64", True) == "NULL"

    def test_empty_string_into_not_null_int_is_zero(self):
        assert ngql_value_for_column("", "int64", False) == "0"

    def test_unparseable_string_into_nullable_int_is_null(self):
        assert ngql_value_for_column("n/a", "int64", True) == "NULL"

    def test_none_into_nullable_int_is_null(self):
        assert ngql_value_for_column(None, "int64", True) == "NULL"

    def test_float_value_into_double_column(self):
        assert ngql_value_for_column(0.85, "double", True) == "0.85"

    def test_double_fallback_not_null_is_zero_point_zero(self):
        assert ngql_value_for_column(None, "double", False) == "0.0"


class TestDatetimeColumns:
    def test_space_separated_text(self):
        assert (
            ngql_value_for_column("2024-05-01 12:34:56", "datetime", False)
            == 'datetime("2024-05-01 12:34:56")'
        )

    def test_iso_t_text(self):
        assert (
            ngql_value_for_column("2024-05-01T08:00:00", "datetime", True)
            == 'datetime("2024-05-01 08:00:00")'
        )

    def test_iso_with_zulu(self):
        assert (
            ngql_value_for_column("2024-05-01T08:00:00Z", "datetime", True)
            == 'datetime("2024-05-01 08:00:00")'
        )

    def test_date_only_fills_midnight(self):
        assert (
            ngql_value_for_column("2024-05-01", "datetime", True)
            == 'datetime("2024-05-01 00:00:00")'
        )

    def test_empty_into_not_null_is_epoch(self):
        assert ngql_value_for_column("", "datetime", False) == 'datetime("1970-01-01 00:00:00")'

    def test_empty_into_nullable_is_null(self):
        assert ngql_value_for_column("", "datetime", True) == "NULL"

    def test_date_column_literal(self):
        assert ngql_value_for_column("2024-05-01", "date", True) == 'date("2024-05-01")'

    def test_datetime_literal_helper_rejects_garbage(self):
        assert ngql_datetime_literal("not a date") is None


class TestStringAndBoolColumns:
    def test_int_value_into_string_column_becomes_quoted(self):
        assert ngql_value_for_column(42, "string", True) == '"42"'

    def test_float_value_into_string_column_becomes_quoted(self):
        assert ngql_value_for_column(1.0, "string", True) == '"1.0"'

    def test_string_value_into_string_column(self):
        assert ngql_value_for_column('带"引号"', "string", True) == '"带\\"引号\\""'

    def test_bool_value_into_string_column(self):
        assert ngql_value_for_column(True, "string", True) == '"True"'

    def test_none_into_nullable_string_is_null(self):
        assert ngql_value_for_column(None, "string", True) == "NULL"

    def test_none_into_not_null_string_is_empty_string(self):
        assert ngql_value_for_column(None, "string", False) == '""'

    def test_bool_column_literals(self):
        assert ngql_value_for_column(True, "bool", True) == "true"
        assert ngql_value_for_column("false", "bool", True) == "false"
        assert ngql_value_for_column(1, "bool", True) == "true"

    def test_unknown_column_type_defaults_to_string(self):
        assert ngql_value_for_column(7, "", True) == '"7"'
