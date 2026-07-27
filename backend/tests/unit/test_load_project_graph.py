from __future__ import annotations

from script.load_project_graph import parse_list, project_vid
from script.project_graph_utils import keyword_vid, org_vid, person_vid


def test_parse_list_json_and_csv():
    assert parse_list('["张伟", "李明"]') == ["张伟", "李明"]
    assert "清华大学" in parse_list("清华大学,北京大学")


def test_project_vid():
    assert project_vid("fake-zh-proj-001") == "project_fake-zh-proj-001"


def test_stub_vids_stable():
    assert person_vid("张伟") == person_vid(" 张伟 ")
    assert org_vid("清华大学") == org_vid("清华大学")
    assert keyword_vid("KG") == keyword_vid("kg")
