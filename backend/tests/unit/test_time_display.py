"""utils.time_display 单元测试：UTC 出口转北京时间。"""

from datetime import datetime, timezone

from utils.time_display import utc_to_cst_str


def test_utc_naive_datetime_to_cst():
    assert utc_to_cst_str(datetime(2026, 10, 9, 14, 30, 5)) == "2026-10-09 22:30:05"


def test_utc_naive_string_space_sep():
    assert utc_to_cst_str("2026-10-09 14:30:05") == "2026-10-09 22:30:05"


def test_utc_iso_t_sep_with_micros():
    assert utc_to_cst_str("2026-10-09T14:30:05.123456") == "2026-10-09 22:30:05"


def test_aware_datetime_converts_by_own_tz():
    aware = datetime(2026, 10, 9, 14, 30, 5, tzinfo=timezone.utc)
    assert utc_to_cst_str(aware) == "2026-10-09 22:30:05"


def test_z_suffix_string():
    assert utc_to_cst_str("2026-10-09T14:30:05Z") == "2026-10-09 22:30:05"


def test_already_cst_offset_string():
    assert utc_to_cst_str("2026-10-09T22:30:05+08:00") == "2026-10-09 22:30:05"


def test_non_time_values_pass_through():
    assert utc_to_cst_str(None) is None
    assert utc_to_cst_str("") == ""
    assert utc_to_cst_str("2026-10-09") == "2026-10-09"  # 纯日期不动
    assert utc_to_cst_str("abc") == "abc"
    assert utc_to_cst_str(123) == 123
