from __future__ import annotations

from types import SimpleNamespace

from service.common import entity_extraction


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content

    def create(self, **_kwargs):
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def fake_client(content: str):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(content)))


def test_extract_accepts_json_markdown_fence(monkeypatch):
    content = '```json\n{"entities":[{"id":"E1","text":"清华大学","type":"Institution"}]}\n```'
    monkeypatch.setattr(entity_extraction, "get_client", lambda: (fake_client(content), "test"))

    assert entity_extraction.extract("任职于清华大学") == [
        {"id": "E1", "text": "清华大学", "type": "Institution"}
    ]


def test_extract_accepts_plain_json(monkeypatch):
    content = '{"entities":[{"id":"E1","text":"北京大学","type":"Institution"}]}'
    monkeypatch.setattr(entity_extraction, "get_client", lambda: (fake_client(content), "test"))

    assert entity_extraction.extract("毕业于北京大学")[0]["text"] == "北京大学"
