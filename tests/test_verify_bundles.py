"""scripts/verify_bundles.py: typedstandards.verify over every bundle docs/records.json lists."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import verify_bundles
from conftest import ROOT


def run(docs: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    code = verify_bundles.main(["--docs", str(docs)])
    return code, capsys.readouterr().out.splitlines()


def test_every_served_bundle_reads_ok(capsys: pytest.CaptureFixture[str]) -> None:
    code, lines = run(ROOT / "docs", capsys)
    index = json.loads((ROOT / "docs" / "records.json").read_text(encoding="utf-8"))
    ok = [line for line in lines if line.startswith("ok ")]
    assert code == 0
    assert len(ok) == len(index["records"])
    for record, line in zip(index["records"], ok, strict=True):
        assert line.split()[1:] == [record["status"], record["name"], record["bundle"]]


def test_a_bundle_altered_by_one_byte_fails_and_is_named(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = repo / "docs" / "bundles" / "first-note.bundle.json"
    before = path.read_bytes()
    assert before.count(b"throwaway key") == 1
    path.write_bytes(before.replace(b"throwaway key", b"throwawaz key"))
    after = path.read_bytes()
    assert len(after) == len(before) and sum(a != b for a, b in zip(before, after, strict=True)) == 1

    code, lines = run(repo / "docs", capsys)
    assert code != 0
    failed = [line for line in lines if line.startswith("FAILED ")]
    assert len(failed) == 1 and "first-note" in failed[0] and "bundles/first-note.bundle.json" in failed[0]
    assert not [line for line in lines if line.startswith("ok ")]


def test_an_index_with_no_records_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    index_path = repo / "docs" / "records.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["records"] = []
    index_path.write_text(json.dumps(index), encoding="utf-8")
    code, _ = run(repo / "docs", capsys)
    assert code != 0
