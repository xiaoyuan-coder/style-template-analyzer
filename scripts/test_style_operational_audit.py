#!/usr/bin/env python3
"""Regression tests for catalog status and workstation delivery diagnostics."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from style_operational_audit import diagnose_delivery, workflow_status_snapshot


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class OperationalAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog_root = self.root / "formal"
        self.delivery_root = self.root / "delivery"
        self.before = self.root / "evidence/before.jpg"
        self.before.parent.mkdir(parents=True)
        self.before.write_bytes(b"before")
        self.items: list[dict] = []

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def add_item(self, key: str, revision: int, cover: str, status: str, *, before: bool = True) -> dict:
        template_file = self.catalog_root / key / str(revision) / "package/style-template.json"
        effect_file = template_file.with_name("cover.png")
        template = {"key": key, "title": key, "cover": cover}
        write_json(template_file, template)
        effect_file.write_bytes(f"effect-{key}".encode())
        item = {
            "id": f"{key}-r{revision}",
            "key": key,
            "title": key,
            "revision": revision,
            "verdict": "pass",
            "ossStatus": status,
            "template": template_file.relative_to(self.catalog_root).as_posix(),
            "effectImage": effect_file.relative_to(self.catalog_root).as_posix(),
            "templateSha256": hashlib.sha256(template_file.read_bytes()).hexdigest(),
            "effectSha256": hashlib.sha256(effect_file.read_bytes()).hexdigest(),
            "cover": cover,
        }
        if before:
            item["approvedBefore"] = self.before.as_posix()
        self.items.append(item)
        return item

    def write_catalog(self) -> Path:
        catalog = {
            "artifactType": "style_template_delivery_catalog",
            "schemaVersion": "2.0.0",
            "producer": "style-template-analyzer",
            "templateCount": len(self.items),
            "effectImageCount": len(self.items),
            "ossStatusCounts": {
                "finalized": sum(item["ossStatus"] == "finalized" for item in self.items),
                "awaiting-finalization": sum(item["ossStatus"] == "awaiting-finalization" for item in self.items),
            },
            "items": self.items,
        }
        path = self.catalog_root / "统一通过模板索引.json"
        write_json(path, catalog)
        return path

    def test_status_uses_catalog_as_authority_and_reports_state_drift(self) -> None:
        first = self.add_item("final-style", 1, "https://assets.example.com/style/templates/a.png", "finalized")
        self.add_item("pending-style", 1, "cover.png", "awaiting-finalization")
        self.add_item("stale-style", 1, "https://assets.example.com/style/templates/c.png", "awaiting-finalization", before=False)
        write_json(self.delivery_root / "final-style.json", {
            "key": "final-style", "title": "final-style", "cover": first["cover"]
        })
        snapshot = workflow_status_snapshot(
            self.write_catalog(),
            data_root=self.root,
            delivery_root=self.delivery_root,
        )
        schema = json.loads(
            (Path(__file__).parents[1] / "contracts/workflow-status-snapshot.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(snapshot)
        self.assertEqual(snapshot["counts"]["templates"], 3)
        self.assertEqual(snapshot["counts"]["catalogFinalized"], 1)
        self.assertEqual(snapshot["counts"]["actualFinalized"], 2)
        self.assertEqual(snapshot["counts"]["awaitingFinalization"], 1)
        self.assertEqual(snapshot["counts"]["missingApprovedBefore"], 1)
        self.assertEqual(snapshot["counts"]["delivered"], 1)
        stale = next(item for item in snapshot["items"] if item["key"] == "stale-style")
        self.assertIn("CATALOG_OSS_STATUS_DRIFT", stale["issues"])
        self.assertIn("APPROVED_BEFORE_UNDISCOVERABLE", stale["issues"])

    def test_diagnose_delivery_identifies_old_workstation_json(self) -> None:
        active = self.add_item("versioned-style", 2, "https://assets.example.com/style/templates/new.png", "finalized")
        catalog_file = self.write_catalog()
        old_delivery = self.delivery_root / "versioned-style.json"
        write_json(old_delivery, {
            "key": "versioned-style",
            "title": "versioned-style",
            "cover": "https://assets.example.com/style/templates/old.png",
        })
        report = diagnose_delivery(old_delivery, catalog_file, data_root=self.root)
        self.assertEqual(report["activeRevision"], active["revision"])
        self.assertIn("DELIVERY_JSON_STALE", report["issues"])
        self.assertEqual(report["approvedBefore"], self.before.as_posix())


if __name__ == "__main__":
    unittest.main()
