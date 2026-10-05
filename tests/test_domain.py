"""The example's own domain: Pages' custom domain and host-core's origin name the same host."""

from __future__ import annotations

import json

from conftest import ROOT

DOMAIN = "notebook.typedstandards.org"
ORIGIN = f"https://{DOMAIN}"


def test_cname_names_the_example_domain() -> None:
    assert (ROOT / "docs" / "CNAME").read_text(encoding="utf-8").strip() == DOMAIN


def test_host_origin_is_the_example_domain() -> None:
    assert json.loads((ROOT / "host.json").read_text(encoding="utf-8"))["origin"] == ORIGIN


def test_served_files_name_the_origin() -> None:
    index = json.loads((ROOT / "docs" / "records.json").read_text(encoding="utf-8"))
    assert index["host"] == f"{ORIGIN}/"
    assert index["trustRegistryUrl"] == f"{ORIGIN}/.well-known/typed-publisher.json"
    for record in index["records"]:
        bundle = json.loads((ROOT / "docs" / record["bundle"]).read_text(encoding="utf-8"))
        assert bundle["trustRegistryUrl"] == index["trustRegistryUrl"], record["name"]
