#!/usr/bin/env python3
"""Smoke tests for the unified workflow command."""

from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from style_workflow_cli import main
from test_style_reference_gate import interpretation
from test_style_review_workflow import asset
from style_test_pool import TestImagePool, TestPoolError
from test_style_dynamic_baseline import add_catalog_package, catalog


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

    def test_retire_template_registers_key_and_releases_consumed_test_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool_file = root / "pool.json"
            ledger = root / "ledger.json"
            registry = root / "已退役模板索引.json"
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
                    "--pool", str(pool_file),
                    "--ledger", str(ledger),
                ])

            self.assertEqual(result, 0)
            response = json.loads(output.getvalue())
            self.assertEqual(response["releasedAssetIds"], ["asset-a"])
            self.assertEqual(json.loads(registry.read_text(encoding="utf-8"))["items"][0]["templateKey"], "ink-outline")
            assignment = json.loads(ledger.read_text(encoding="utf-8"))["assignments"][0]
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


if __name__ == "__main__":
    unittest.main()
