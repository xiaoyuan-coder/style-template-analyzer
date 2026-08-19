#!/usr/bin/env python3
"""Contract tests for the approval-gated three-phase workflow."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from style_review_workflow import (
    ReviewWorkflowError,
    compile_reference,
    finalize_approved,
    record_review_decision,
    route_workflow,
)
from style_test_pool import TestImagePool, TestPoolError, normalize_asset
from test_validate_style_analysis import analysis
from test_validate_style_template import template
from validate_style_package import validate_package


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def asset(root: Path, asset_id: str, color: tuple[int, int, int], perceptual_hash: str) -> dict:
    source = root / f"{asset_id}.jpg"
    Image.new("RGB", (640, 512), color).save(source, format="JPEG")
    return normalize_asset({
        "assetId": asset_id,
        "sourceAdapter": "fixture",
        "sourcePageUrl": f"https://example.test/{asset_id}",
        "imageUrl": f"https://example.test/{asset_id}.jpg",
        "author": "Fixture Author",
        "license": "CC0",
        "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
        "rightsStatus": "verified",
        "collectedAt": "2026-08-19T00:00:00Z",
        "mime": "image/jpeg",
        "width": 640,
        "height": 512,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "perceptualHash": perceptual_hash,
        "photographic": True,
        "photographicEvidence": "fixture photograph",
        "riskLabels": [],
        "category": "object",
        "localPath": source.as_posix(),
    })


class Generator:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, source: dict, template_data: dict, output: Path) -> dict:
        self.calls += 1
        Image.new("RGB", (32, 32), (120, 80, 40)).save(output, format="PNG")
        return {"provider": "fixture", "sourceAssetId": source["assetId"]}


class Oss:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def __call__(self, source: Path, output: Path) -> dict:
        self.calls += 1
        if self.fail:
            raise RuntimeError("fixture failure")
        data = json.loads((source / "style-template.json").read_text(encoding="utf-8"))
        data["cover"] = "https://assets.example.com/style/templates/123e4567-e89b-42d3-a456-426614174000.png"
        write_json(output, data)
        return {"provider": "fixture-oss", "object": "same-content-hash"}


class ApprovalGatedWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.pool = TestImagePool([
            asset(self.root, "asset-a", (20, 40, 60), "0" * 16),
            asset(self.root, "asset-b", (80, 100, 120), "f" * 16),
        ])
        self.ledger = self.root / "ledger.json"
        self.reference = self.root / "reference.jpg"
        self.reference.write_bytes(b"fixture")
        self.generator = Generator()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def compiler(reference: Path) -> dict:
        data = template()
        evidence = analysis()
        evidence["templateKey"] = data["key"]
        return {"template": data, "analysis": evidence}

    def create_review(self, *, delivery: str = "delivery-1", revision: int = 1) -> dict:
        return compile_reference(
            self.reference,
            self.compiler,
            self.pool,
            self.generator,
            run_root=self.root / "runs",
            delivery_set_id=delivery,
            ledger_file=self.ledger,
            revision=revision,
        )

    def test_phase_one_creates_review_package_without_oss_and_holds_asset(self) -> None:
        result = self.create_review()
        review_root = Path(result["reviewRoot"])
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertEqual(
            sorted(path.name for path in (review_root / "review-package").iterdir()),
            ["cover.png", "style-template.json"],
        )
        assignment = json.loads((review_root / "internal" / "test-image-assignment.json").read_text())
        self.assertEqual(assignment["status"], "awaiting_approval")
        self.assertEqual(self.pool.capacity("another-delivery"), 1)
        errors, _ = validate_package(review_root, "review-package", "local", "", "")
        self.assertEqual(errors, [])

    def test_pending_requires_explicit_human_release(self) -> None:
        review = self.create_review()
        result = record_review_decision(
            Path(review["reviewRoot"]),
            "pending",
            "还需要比较另一版",
            self.pool,
            self.ledger,
        )
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertEqual(self.pool.capacity("another-delivery"), 1)
        with self.assertRaisesRegex(TestPoolError, "explicit_human_release_required"):
            self.pool.release_persisted(
                "delivery-1",
                template()["key"],
                1,
                self.ledger,
                verdict="system_failure",
                authority="system",
                reason="timeout",
            )
        released = record_review_decision(
            Path(review["reviewRoot"]),
            "manual_release",
            "人工确认本轮先释放测试图",
            self.pool,
            self.ledger,
        )
        self.assertEqual(released["status"], "released")
        self.assertEqual(self.pool.capacity("another-delivery"), 2)

    def test_reject_releases_asset_for_another_delivery(self) -> None:
        review = self.create_review()
        result = record_review_decision(
            Path(review["reviewRoot"]),
            "reject",
            "效果未达到验收标准",
            self.pool,
            self.ledger,
        )
        self.assertEqual(result["status"], "released")
        self.assertEqual(self.pool.capacity("delivery-2"), 2)
        reserved = self.pool.reserve_persisted("delivery-2", "second-template", 1, self.ledger)
        self.assertEqual(reserved["assetId"], review["assetId"])

    def test_pass_consumes_globally_and_finalization_is_recoverable(self) -> None:
        review = self.create_review()
        decision = record_review_decision(
            Path(review["reviewRoot"]),
            "pass",
            "人工验收通过",
            self.pool,
            self.ledger,
        )
        self.assertEqual(decision["status"], "approved")
        self.assertEqual(self.pool.capacity("delivery-2"), 1)

        failing = Oss(fail=True)
        with self.assertRaisesRegex(ReviewWorkflowError, "oss_finalization_failed"):
            finalize_approved(
                Path(review["reviewRoot"]),
                self.root / "runs",
                failing,
                assets_domain="assets.example.com",
            )
        ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
        self.assertEqual(ledger["assignments"][0]["status"], "consumed")

        oss = Oss()
        final = finalize_approved(
            Path(review["reviewRoot"]),
            self.root / "runs",
            oss,
            assets_domain="assets.example.com",
        )
        self.assertEqual(final["status"], "completed")
        final_root = Path(final["revisionRoot"])
        errors, _ = validate_package(final_root, "final-package", "remote", "assets.example.com", "")
        self.assertEqual(errors, [])
        again = finalize_approved(
            Path(review["reviewRoot"]),
            self.root / "runs",
            oss,
            assets_domain="assets.example.com",
        )
        self.assertTrue(again["idempotent"])
        self.assertEqual(oss.calls, 1)

    def test_experience_deposit_failure_does_not_block_main_flow(self) -> None:
        review = self.create_review()

        def broken_sink(event: dict) -> None:
            raise RuntimeError("offline")

        result = record_review_decision(
            Path(review["reviewRoot"]),
            "pass",
            "人工验收通过",
            self.pool,
            self.ledger,
            experience_sink=broken_sink,
        )
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["warnings"], ["experience_deposit_failed: offline"])

    def test_technical_failure_releases_before_review_and_same_revision_can_retry(self) -> None:
        class FailingGenerator:
            def __call__(self, source: dict, template_data: dict, output: Path) -> dict:
                raise RuntimeError("offline")

        with self.assertRaisesRegex(ReviewWorkflowError, "cover_generation_failed"):
            compile_reference(
                self.reference,
                self.compiler,
                self.pool,
                FailingGenerator(),
                run_root=self.root / "runs",
                delivery_set_id="delivery-1",
                ledger_file=self.ledger,
            )
        ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
        self.assertEqual(ledger["assignments"][0]["status"], "released")
        self.assertEqual(ledger["assignments"][0]["decision"]["verdict"], "system_failure")
        retried = self.create_review()
        self.assertEqual(retried["status"], "awaiting_approval")

    def test_router_can_enter_finalization_immediately_after_pass(self) -> None:
        review = self.create_review()
        oss = Oss()
        result = route_workflow(
            "compile-reference",
            "review-decision",
            review_root=Path(review["reviewRoot"]),
            verdict="pass",
            reason="人工验收通过",
            pool=self.pool,
            ledger_file=self.ledger,
            finalize_on_pass={
                "run_root": self.root / "runs",
                "oss_adapter": oss,
                "assets_domain": "assets.example.com",
            },
        )
        self.assertEqual(result["finalization"]["status"], "completed")
        self.assertEqual(oss.calls, 1)


if __name__ == "__main__":
    unittest.main()
