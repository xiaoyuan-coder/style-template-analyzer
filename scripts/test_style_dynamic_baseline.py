#!/usr/bin/env python3
"""Tests for human-pass-driven dynamic baselines."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from style_contracts import sha256_file
from style_dynamic_baseline import DynamicBaselineCatalog
from test_validate_style_template import template


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def catalog(root: Path, items: list[dict] | None = None) -> Path:
    value = {
        "artifactType": "style_template_delivery_catalog",
        "schemaVersion": "2.0.0",
        "producer": "style-template-analyzer",
        "generatedAt": "2026-08-20T00:00:00Z",
        "packageName": "已通过正式模板包",
        "status": "completed",
        "templateCount": len(items or []),
        "effectImageCount": len(items or []),
        "pathPolicy": "catalog-relative",
        "approvalProvenanceCounts": {},
        "ossStatusCounts": {},
        "items": items or [],
    }
    path = root / "统一通过模板索引.json"
    write_json(path, value)
    return path


def add_catalog_package(root: Path, key: str, title: str, revision: int) -> dict:
    package = root / key / str(revision) / "package"
    package.mkdir(parents=True)
    data = template()
    data["key"] = key
    data["title"] = title
    data["cover"] = "cover.png"
    write_json(package / "style-template.json", data)
    (package / "cover.png").write_bytes(PNG)
    return {
        "id": f"{key}-r{revision}",
        "key": key,
        "title": title,
        "revision": revision,
        "verdict": "pass",
        "approvalProvenance": "fixture",
        "ossStatus": "finalized",
        "template": f"{key}/{revision}/package/style-template.json",
        "effectImage": f"{key}/{revision}/package/cover.png",
        "templateSha256": sha256_file(package / "style-template.json"),
        "effectSha256": sha256_file(package / "cover.png"),
        "cover": "cover.png",
        "approvalEvidence": "fixture.json",
        "sourcePackage": "fixture",
    }


class DynamicBaselineTests(unittest.TestCase):
    def test_active_snapshot_uses_latest_passed_revision_per_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            items = [
                add_catalog_package(root, "ink-outline", "墨线重绘旧版", 1),
                add_catalog_package(root, "ink-outline", "墨线重绘", 2),
                add_catalog_package(root, "paper-cutout", "纸感贴画", 1),
            ]
            store = DynamicBaselineCatalog(catalog(root, items))
            snapshot, templates = store.load_active()
            self.assertEqual(snapshot["count"], 2)
            self.assertEqual({item["title"] for item in templates}, {"墨线重绘", "纸感贴画"})

    def test_human_pass_registers_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_file = catalog(root)
            review = root / "review-source"
            public = review / "review-package"
            internal = review / "internal"
            public.mkdir(parents=True)
            internal.mkdir()
            data = template()
            data["key"] = "ink-outline"
            data["title"] = "墨线重绘"
            data["cover"] = "cover.png"
            write_json(public / "style-template.json", data)
            (public / "cover.png").write_bytes(PNG)
            decision = {
                "templateKey": "ink-outline",
                "revision": 1,
                "verdict": "pass",
            }
            write_json(internal / "approval-decision-receipt.json", decision)
            store = DynamicBaselineCatalog(catalog_file)
            first = store({"reviewRoot": review.as_posix(), "decision": decision})
            second = store({"reviewRoot": review.as_posix(), "decision": decision})
            self.assertFalse(first["idempotent"])
            self.assertTrue(second["idempotent"])
            self.assertEqual(store.load_active()[0]["count"], 1)
            self.assertTrue((root / "ink-outline/1/package/style-template.json").is_file())


if __name__ == "__main__":
    unittest.main()
