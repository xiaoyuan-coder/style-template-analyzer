#!/usr/bin/env python3
"""Smoke tests for the unified workflow command."""

from __future__ import annotations

import json
import io
import hashlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from style_workflow_cli import main
from test_style_reference_gate import interpretation
from test_style_review_workflow import asset
from style_test_pool import TestImagePool, TestPoolError
from test_style_dynamic_baseline import add_catalog_package, catalog
from style_retirement import retire_template_transaction


class WorkflowCliTests(unittest.TestCase):
    def test_validate_reference_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "reference-interpretation.json"
            source.write_text(json.dumps(interpretation()), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate-reference", str(source), "--template-key", "ink-outline"]), 0)

    def test_audit_experience_fails_when_snapshot_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["audit-experience", directory]), 1)

    def test_reserve_test_image_command_persists_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool_file = root / "pool.json"
            ledger = root / "ledger.json"
            TestImagePool([asset(root, "asset-a", (20, 40, 60), "0" * 16)]).save(pool_file, ledger)
            with redirect_stdout(io.StringIO()):
                result = main([
                    "reserve-test-image",
                    "--pool", str(pool_file),
                    "--ledger", str(ledger),
                    "--delivery-set", "delivery-1",
                    "--template-key", "ink-outline",
                ])
            self.assertEqual(result, 0)
            data = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(data["assignments"][0]["status"], "reserved")

    def test_audit_dynamic_baseline_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = add_catalog_package(root, "ink-outline", "墨线重绘", 1)
            catalog_file = catalog(root, [item])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["audit-baseline", str(catalog_file)]), 0)

    def test_status_and_delivery_diagnostic_use_the_unified_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            formal = root / "formal"
            package = formal / "fixture-style/2/package"
            package.mkdir(parents=True)
            before = root / "before.jpg"
            before.write_bytes(b"before")
            template = {"key": "fixture-style", "title": "示例", "cover": "https://assets.example.com/style/templates/a.png"}
            template_file = package / "style-template.json"
            template_file.write_text(json.dumps(template, ensure_ascii=False), encoding="utf-8")
            cover_file = package / "cover.png"
            cover_file.write_bytes(b"cover")
            catalog_file = formal / "统一通过模板索引.json"
            catalog_file.write_text(json.dumps({
                "artifactType": "style_template_delivery_catalog",
                "schemaVersion": "2.0.0",
                "producer": "style-template-analyzer",
                "templateCount": 1,
                "effectImageCount": 1,
                "ossStatusCounts": {"finalized": 1, "awaiting-finalization": 0},
                "items": [{
                    "key": "fixture-style",
                    "revision": 2,
                    "ossStatus": "finalized",
                    "template": "fixture-style/2/package/style-template.json",
                    "effectImage": "fixture-style/2/package/cover.png",
                    "approvedBefore": before.as_posix(),
                    "templateSha256": hashlib.sha256(template_file.read_bytes()).hexdigest(),
                    "effectSha256": hashlib.sha256(cover_file.read_bytes()).hexdigest(),
                }],
            }), encoding="utf-8")
            delivery = root / "delivery/fixture-style.json"
            delivery.parent.mkdir()
            delivery.write_text(json.dumps(template, ensure_ascii=False), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main([
                    "status", "--catalog", str(catalog_file),
                    "--data-root", str(root), "--delivery-root", str(delivery.parent),
                ]), 0)
            self.assertEqual(json.loads(output.getvalue())["snapshot"]["counts"]["delivered"], 1)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([
                    "diagnose-delivery", str(delivery), "--catalog", str(catalog_file), "--data-root", str(root),
                ]), 0)

    def test_retire_template_registers_key_and_releases_consumed_test_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool_file = root / "pool.json"
            ledger = root / "ledger.json"
            registry = root / "已退役模板索引.json"
            catalog_file = catalog(
                root,
                [add_catalog_package(root, "ink-outline", "墨线重绘", 1)],
            )
            catalog_data = json.loads(catalog_file.read_text(encoding="utf-8"))
            catalog_data["approvalProvenanceCounts"] = {
                "legacy-delivery-confirmed": 0,
                "legacy-batch-human-pass": 0,
                "v5-human-pass": 1,
            }
            catalog_data["ossStatusCounts"] = {
                "finalized": 1,
                "awaiting-finalization": 0,
            }
            catalog_file.write_text(json.dumps(catalog_data), encoding="utf-8")
            pool = TestImagePool([asset(root, "asset-a", (20, 40, 60), "0" * 16)])
            pool.save(pool_file, ledger)
            pool.reserve_persisted("delivery-1", "ink-outline", 1, ledger)
            pool.mark_awaiting_approval_persisted("delivery-1", "ink-outline", 1, ledger)
            pool.consume_persisted(
                "delivery-1",
                "ink-outline",
                1,
                ledger,
                cover_sha256="a" * 64,
                prompt_sha256="b" * 64,
                reason="人工通过",
            )

            output = io.StringIO()
            with redirect_stdout(output):
                result = main([
                    "retire-template",
                    "--template-key", "ink-outline",
                    "--reason", "人工决定退役",
                    "--registry", str(registry),
                    "--catalog", str(catalog_file),
                    "--pool", str(pool_file),
                    "--ledger", str(ledger),
                ])

            self.assertEqual(result, 0)
            response = json.loads(output.getvalue())
            self.assertEqual(response["releasedAssetIds"], ["asset-a"])
            self.assertEqual(response["removedCatalogEntries"], 1)
            self.assertEqual(json.loads(registry.read_text(encoding="utf-8"))["items"][0]["templateKey"], "ink-outline")
            active_catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
            self.assertEqual(active_catalog["items"], [])
            self.assertEqual(active_catalog["templateCount"], 0)
            self.assertEqual(active_catalog["approvalProvenanceCounts"], {
                "legacy-delivery-confirmed": 0,
                "legacy-batch-human-pass": 0,
                "v5-human-pass": 0,
            })
            self.assertEqual(active_catalog["ossStatusCounts"], {
                "finalized": 0,
                "awaiting-finalization": 0,
            })
            assignment = json.loads(ledger.read_text(encoding="utf-8"))["assignments"][0]
            self.assertEqual(
                json.loads(ledger.read_text(encoding="utf-8"))["schemaVersion"],
                "4.0.0",
            )
            self.assertEqual(assignment["schemaVersion"], "3.0.0")
            self.assertEqual(assignment["status"], "released")
            self.assertEqual(assignment["decision"]["verdict"], "template_retired")
            self.assertEqual(assignment["previousDecision"]["verdict"], "pass")
            updated_pool = TestImagePool.load(pool_file, ledger)
            with self.assertRaisesRegex(TestPoolError, "test_pool_insufficient"):
                updated_pool.reserve_persisted("delivery-1", "paper-cutout", 1, ledger)
            reused = updated_pool.reserve_persisted(
                "delivery-2", "paper-cutout", 1, ledger
            )
            self.assertEqual(reused["assetId"], "asset-a")

    def test_retire_template_rejects_non_adjacent_registry_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_root = root / "catalog"
            catalog_root.mkdir()
            catalog_file = catalog(
                catalog_root,
                [add_catalog_package(catalog_root, "ink-outline", "墨线重绘", 1)],
            )
            registry = root / "elsewhere" / "已退役模板索引.json"
            pool_file = root / "pool.json"
            ledger = root / "ledger.json"
            TestImagePool([asset(root, "asset-a", (20, 40, 60), "0" * 16)]).save(pool_file, ledger)
            before_catalog = catalog_file.read_bytes()
            before_ledger = ledger.read_bytes()

            with redirect_stderr(io.StringIO()):
                result = main([
                    "retire-template",
                    "--template-key", "ink-outline",
                    "--reason", "人工决定退役",
                    "--registry", str(registry),
                    "--catalog", str(catalog_file),
                    "--pool", str(pool_file),
                    "--ledger", str(ledger),
                ])

            self.assertEqual(result, 1)
            self.assertFalse(registry.exists())
            self.assertEqual(catalog_file.read_bytes(), before_catalog)
            self.assertEqual(ledger.read_bytes(), before_ledger)

    def test_retirement_rolls_back_registry_and_catalog_when_ledger_release_fails(self) -> None:
        class FailingPool:
            def retire_template_persisted(self, *args: object, **kwargs: object) -> list[dict]:
                raise TestPoolError("ledger_release_failed")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "已退役模板索引.json"
            catalog_file = catalog(
                root,
                [add_catalog_package(root, "ink-outline", "墨线重绘", 1)],
            )
            before_catalog = catalog_file.read_bytes()

            with self.assertRaisesRegex(TestPoolError, "ledger_release_failed"):
                retire_template_transaction(
                    FailingPool(),
                    root / "ledger.json",
                    registry,
                    catalog_file,
                    "ink-outline",
                    "人工决定退役",
                )

            self.assertFalse(registry.exists())
            self.assertEqual(
                json.loads(catalog_file.read_text(encoding="utf-8")),
                json.loads(before_catalog),
            )

    def test_retire_template_invalid_catalog_does_not_register_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "已退役模板索引.json"
            catalog_file = root / "统一通过模板索引.json"
            catalog_file.write_text("{}", encoding="utf-8")
            pool_file = root / "pool.json"
            ledger = root / "ledger.json"
            TestImagePool([asset(root, "asset-a", (20, 40, 60), "0" * 16)]).save(pool_file, ledger)

            with redirect_stderr(io.StringIO()):
                result = main([
                    "retire-template",
                    "--template-key", "ink-outline",
                    "--reason", "人工决定退役",
                    "--registry", str(registry),
                    "--catalog", str(catalog_file),
                    "--pool", str(pool_file),
                    "--ledger", str(ledger),
                ])

            self.assertEqual(result, 1)
            self.assertFalse(registry.exists())


if __name__ == "__main__":
    unittest.main()
