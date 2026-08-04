"""专利实体索引的文本处理和可扩展 BM25 编码器。"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def normalize_text(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def tokens(text: str) -> list[str]:
    units = TOKEN_RE.findall(normalize_text(text))
    result = [u for u in units if not (len(u) == 1 and u.isascii())]
    chinese = "".join(u for u in units if "\u4e00" <= u <= "\u9fff")
    result.extend(chinese[i : i + 2] for i in range(max(0, len(chinese) - 1)))
    return result


def bucket(token: str, dimensions: int) -> int:
    return (
        int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big") % dimensions
    )


@dataclass
class HashedBM25:
    """固定内存的近似 BM25，适合亿级语料。"""

    dimensions: int = 262_144
    k1: float = 1.5
    b: float = 0.75

    def __post_init__(self) -> None:
        self.document_count, self.total_length = 0, 0
        self.document_frequency = [0] * self.dimensions

    def observe(self, text: str) -> None:
        terms = tokens(text)
        self.document_count += 1
        self.total_length += len(terms)
        for index in {bucket(t, self.dimensions) for t in terms}:
            self.document_frequency[index] += 1

    def encode(self, text: str) -> dict[int, float]:
        counts = Counter(bucket(t, self.dimensions) for t in tokens(text))
        if not counts or not self.document_count:
            return {}
        avg, length, result = (
            max(1.0, self.total_length / self.document_count),
            sum(counts.values()),
            {},
        )
        for index, frequency in counts.items():
            df = self.document_frequency[index]
            idf = math.log(1.0 + (self.document_count - df + 0.5) / (df + 0.5))
            den = frequency + self.k1 * (1 - self.b + self.b * length / avg)
            result[index] = idf * frequency * (self.k1 + 1) / den
        return result

    def to_dict(self) -> dict:
        return {
            "dimensions": self.dimensions,
            "k1": self.k1,
            "b": self.b,
            "document_count": self.document_count,
            "total_length": self.total_length,
            "document_frequency": self.document_frequency,
        }

    @classmethod
    def from_dict(cls, value: dict) -> HashedBM25:
        obj = cls(value["dimensions"], value["k1"], value["b"])
        obj.document_count = value["document_count"]
        obj.total_length = value["total_length"]
        obj.document_frequency = value["document_frequency"]
        return obj


def compose_search_text(properties: dict[str, object], fields: Iterable[str]) -> str:
    return " ".join(str(properties.get(f) or "") for f in fields).strip()


def truncate_utf8(text: str, max_bytes: int) -> str:
    """按Milvus VARCHAR的UTF-8字节限制安全截断，不产生半个字符。"""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    return raw[:max_bytes].decode("utf-8", errors="ignore")
