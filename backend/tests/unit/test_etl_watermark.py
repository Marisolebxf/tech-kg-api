from script.etl_watermark import Watermark


def test_read_missing_returns_none(tmp_path):
    wm = Watermark(tmp_path / "scholar.txt")
    assert wm.read() is None


def test_write_then_read_roundtrip(tmp_path):
    wm = Watermark(tmp_path / "scholar.txt")
    wm.write("2026-08-20 10:00:00")
    assert wm.read() == "2026-08-20 10:00:00"


def test_write_is_atomic(tmp_path):
    wm = Watermark(tmp_path / "scholar.txt")
    wm.write("2026-08-20 10:00:00")
    # 只有一个最终文件,无 .tmp 残留
    assert list(tmp_path.glob("*.tmp")) == []


def test_advance_only_when_higher(tmp_path):
    wm = Watermark(tmp_path / "scholar.txt")
    wm.write("2026-08-20 10:00:00")
    # 较低水位不应回退
    wm.advance_if_higher("2026-08-19 00:00:00")
    assert wm.read() == "2026-08-20 10:00:00"
    # 较高水位前进
    wm.advance_if_higher("2026-08-21 00:00:00")
    assert wm.read() == "2026-08-21 00:00:00"


def test_corrupt_file_returns_none(tmp_path):
    f = tmp_path / "scholar.txt"
    f.write_text("garbage{}{")
    # 损坏/非法时间戳 → read() 返回 None,调用方退化 full(只慢不丢)
    assert Watermark(f).read() is None


def test_empty_file_returns_none(tmp_path):
    f = tmp_path / "scholar.txt"
    f.write_text("")
    assert Watermark(f).read() is None
