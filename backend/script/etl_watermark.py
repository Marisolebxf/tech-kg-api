"""ETL 增量水位文件(方案 B,显式状态)。

水位 = 上次成功灌到的最大 update_time,存于 ``backend/script/.etl_watermark/<域>.txt``。
稳健性:
  - 只在整批成功后调用 :meth:`write` / :meth:`advance_if_higher` 前进水位;
  - 原子写(temp + os.replace);
  - 文件丢失/损坏/非法时间戳 → :meth:`read` 返回 None,调用方退化 full(只慢不丢)。

时间戳格式约定:MySQL DATETIME 串,如 ``2026-08-20 10:00:00``(零填充,词法比较即时间序)。
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_WATERMARK_DIR = Path(__file__).resolve().parent / ".etl_watermark"

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}$")


class Watermark:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @classmethod
    def for_domain(cls, domain: str) -> Watermark:
        _WATERMARK_DIR.mkdir(parents=True, exist_ok=True)
        return cls(_WATERMARK_DIR / f"{domain}.txt")

    def read(self) -> str | None:
        """返回水位时间戳;文件缺失/空/损坏/非法 → None(调用方退化 full)。"""
        if not self.path.exists():
            return None
        try:
            val = self.path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not val or not _TS_RE.match(val):
            return None
        return val

    def write(self, ts: str) -> None:
        """整批成功后调用,原子写入新水位。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(ts)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def advance_if_higher(self, ts: str) -> None:
        """仅在 ts 高于当前水位时前进;相等或更低不动(避免回退)。"""
        current = self.read()
        if current is not None and ts <= current:
            return
        self.write(ts)
