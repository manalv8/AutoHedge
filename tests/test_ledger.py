from autohedge.ledger import (
    append_recommendations,
    read_recommendations,
)
from tests.helpers import make_rec


def test_roundtrip(tmp_path):
    path = tmp_path / "sub" / "ledger.jsonl"
    append_recommendations(path, [make_rec(id="a")])
    append_recommendations(path, [make_rec(id="b")])
    assert [r.id for r in read_recommendations(path)] == ["a", "b"]


def test_missing_file_is_empty(tmp_path):
    assert read_recommendations(tmp_path / "none.jsonl") == []


def test_corrupt_line_is_skipped(tmp_path):
    path = tmp_path / "l.jsonl"
    append_recommendations(path, [make_rec(id="a")])
    with path.open("a") as f:
        f.write("{not json\n")
    append_recommendations(path, [make_rec(id="b")])
    assert [r.id for r in read_recommendations(path)] == ["a", "b"]
