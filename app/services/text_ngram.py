"""字符 n-gram 向量化（对齐与消歧共用）。"""

from collections import Counter

import numpy as np


def build_ngram_vocab(texts: list[str], n: int = 2) -> dict[str, int]:
    vocab: dict[str, int] = {}
    for text in texts:
        text_lower = text.lower()
        for i in range(len(text_lower) - n + 1):
            gram = text_lower[i : i + n]
            if gram not in vocab:
                vocab[gram] = len(vocab)
    return vocab


def text_to_vector(text: str, vocab: dict[str, int], n: int = 2) -> np.ndarray:
    vec = np.zeros(len(vocab), dtype=np.float32)
    text_lower = text.lower()
    counts = Counter(text_lower[i : i + n] for i in range(len(text_lower) - n + 1))
    for gram, cnt in counts.items():
        if gram in vocab:
            vec[vocab[gram]] = cnt
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def encode_texts(texts: list[str], vocab: dict[str, int], n: int = 2) -> np.ndarray:
    return np.stack([text_to_vector(t, vocab, n) for t in texts])
