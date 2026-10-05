"""Verify every bundle docs/records.json lists with typedstandards.verify, offline.

    uv run scripts/verify_bundles.py [--docs DIR]

It prints one line per bundle, `ok <status> <name> <bundle>` or `FAILED <name> <bundle>: <why>`,
then a total, and exits 0 only when every bundle reads ok: the CLI verifies it (exit 0) and its
lifecycle status equals the status the index states. It exits 1 when any bundle fails, and 2 when
the index cannot be read or lists no record. It holds no key and reads no secret: verify needs
none. `typedstandards.verify` drops a served bundle's top-level `trustRegistry` before the CLI
reads it (typedstandards#136) and changes nothing else.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import typedstandards

ROOT = Path(__file__).resolve().parent.parent


def _verify_one(docs: Path, record: dict[str, Any]) -> tuple[bool, str]:
    name, bundle = record.get("name"), record.get("bundle")
    if not isinstance(name, str) or not isinstance(bundle, str):
        return False, f"FAILED {name} {bundle}: the index record has no name or bundle path"
    if "://" in bundle:
        return False, f"FAILED {name} {bundle}: an absolute bundle URL is not served from this directory"
    path = docs / bundle
    try:
        result = typedstandards.verify(path)
    except typedstandards.VerificationError as err:
        failures = (err.document or {}).get("failures") or [err.stderr.strip()]
        return False, f"FAILED {name} {bundle}: " + "; ".join(str(f) for f in failures)
    except typedstandards.CliError as err:
        return False, f"FAILED {name} {bundle}: {err}"
    status = (result.get("lifecycle") or {}).get("status")
    if not result.get("ok"):
        return False, f"FAILED {name} {bundle}: " + "; ".join(str(f) for f in result.get("failures") or [])
    if status != record.get("status"):
        return False, f"FAILED {name} {bundle}: the bundle reads {status}, the index states {record.get('status')}"
    return True, f"ok    {status:<10} {name} {bundle}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--docs", type=Path, default=ROOT / "docs", help="the served directory (default: docs/)")
    args = parser.parse_args(argv)
    docs: Path = args.docs

    try:
        index = json.loads((docs / "records.json").read_text(encoding="utf-8"))
        records = index["records"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        print(f"verify_bundles: cannot read {docs / 'records.json'}: {err}")
        return 2
    if not isinstance(records, list) or not records:
        print(f"verify_bundles: {docs / 'records.json'} lists no record")
        return 2

    print(
        f"verify_bundles: records.json lists {len(records)} bundle(s); typedstandards {typedstandards.__version__}, "
        f"CLI {typedstandards.CLI_VERSION}, offline"
    )
    failed = 0
    for record in records:
        ok, line = _verify_one(docs, record if isinstance(record, dict) else {})
        failed += 0 if ok else 1
        print(line)
    print(f"bundles: {len(records)} listed, {len(records) - failed} ok, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
