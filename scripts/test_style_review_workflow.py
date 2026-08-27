#!/usr/bin/env python3
"""Contract tests for the approval-gated three-phase workflow."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from style_atomic import atomic_write_json
from style_review_workflow import (
    ReviewWorkflowError,
    compile_reference,
    finalize_approved,
    record_review_decision,
    route_workflow,
)
from style_dynamic_baseline import DynamicBaselineCatalog
from style_effect_contract import BOUNDARY_MODES
from style_retirement import register_retirement
from test_style_reference_gate import interpretation, visual_gate
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
        return {
            "provider": "fixture",
            "sourceAssetId": source["assetId"],
            "submittedPromptSha256": hashlib.sha256(
                template_data["promptTemplate"].encode("utf-8")
            ).hexdigest(),
            "sourceSha256": source["sha256"],
            "inputImageCount": 1,
            "approvedAfterUsedAsInput": False,
        }


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


class GuardedBaseline:
    def __init__(self, sink) -> None:
        self.sink = sink

    @contextmanager
    def approval_guard(self, template_key: str):
        yield

    def __call__(self, event: dict) -> dict:
        return self.sink(event)


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
        self.experience_events: list[dict] = []
        self.baseline_events: list[dict] = []
        self.guarded_baseline = GuardedBaseline(self.baseline_sink)

    def experience_sink(self, event: dict) -> dict:
        self.experience_events.append(event)
        return {"eventId": f"event-{len(self.experience_events)}"}

    def baseline_sink(self, event: dict) -> dict:
        self.baseline_events.append(event)
        return {
            "catalog": (self.root / "dynamic-baseline.json").as_posix(),
            "catalogDigest": "c" * 64,
            "activeRevision": event["decision"]["revision"],
            "baselineCount": len(self.baseline_events),
            "idempotent": False,
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def effect_contract(template_key: str) -> dict:
        return {
            "artifactType": "effect_reproduction_contract",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": template_key,
            "authorityMode": "after-first",
            "boundaryDecisions": [
                {
                    "dimension": dimension,
                    "mode": next(iter(sorted(modes))),
                    "evidence": f"fixture After evidence for {dimension}",
                    "promptDirective": "用户上传图",
                }
                for dimension, modes in BOUNDARY_MODES.items()
            ],
            "templateConstants": [],
            "unresolvedConflicts": [],
        }

    @staticmethod
    def compiler(reference: Path) -> dict:
        data = template()
        evidence = analysis()
        evidence["templateKey"] = data["key"]
        semantics = interpretation()
        semantics["templateKey"] = data["key"]
        semantics["sourceImages"][0]["sha256"] = hashlib.sha256(reference.read_bytes()).hexdigest()
        return {
            "template": data,
            "analysis": evidence,
            "referenceInterpretation": semantics,
            "effectContract": ApprovalGatedWorkflowTests.effect_contract(data["key"]),
        }

    @staticmethod
    def visual_checker(output: Path, template_data: dict, interpretation_data: dict, attempt: int) -> dict:
        result = visual_gate()
        result["templateKey"] = template_data["key"]
        return result

    def create_review(
        self,
        *,
        delivery: str = "delivery-1",
        revision: int = 1,
        key: str | None = None,
    ) -> dict:
        compiler = self.compiler
        if key is not None:
            def compiler(reference: Path) -> dict:
                compiled = self.compiler(reference)
                compiled["template"]["key"] = key
                compiled["template"]["title"] = "线程样式甲" if key.endswith("a") else "线程样式乙"
                compiled["template"]["metadata"]["sourceRef"]["producerKey"] = key
                compiled["analysis"]["templateKey"] = key
                compiled["referenceInterpretation"]["templateKey"] = key
                compiled["effectContract"]["templateKey"] = key
                return compiled
        return compile_reference(
            self.reference,
            compiler,
            self.pool,
            self.generator,
            run_root=self.root / "runs",
            delivery_set_id=delivery,
            ledger_file=self.ledger,
            revision=revision,
            reference_visual_checker=self.visual_checker,
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
        manifest = json.loads((review_root / "artifact-manifest.json").read_text(encoding="utf-8"))
        assignment_record = next(item for item in manifest["artifacts"] if item["artifactType"] == "test_image_assignment")
        self.assertEqual(manifest["schemaVersion"], "6.0.0")
        self.assertEqual(assignment_record["schemaVersion"], "2.0.0")
        generation = json.loads(
            (review_root / "internal" / "cover-generation-receipt.json").read_text()
        )
        self.assertEqual(generation["schemaVersion"], "2.0.0")
        self.assertEqual(
            generation["provider"]["sourceLocalPath"],
            self.pool.asset(result["assetId"])["localPath"],
        )
        effect = json.loads(
            (review_root / "internal" / "effect-reproduction-contract.json").read_text()
        )
        self.assertEqual(effect["evidenceBinding"]["promptSha256"], generation["submittedPromptSha256"])

    def test_phase_one_rejects_generator_prompt_substitution(self) -> None:
        class SubstitutingGenerator(Generator):
            def __call__(self, source: dict, template_data: dict, output: Path) -> dict:
                receipt = super().__call__(source, template_data, output)
                receipt["submittedPromptSha256"] = "0" * 64
                return receipt

        with self.assertRaisesRegex(ReviewWorkflowError, "cover_generation_prompt_mismatch"):
            compile_reference(
                self.reference,
                self.compiler,
                self.pool,
                SubstitutingGenerator(),
                run_root=self.root / "runs",
                delivery_set_id="prompt-substitution",
                ledger_file=self.ledger,
                reference_visual_checker=self.visual_checker,
            )

    def test_phase_one_requires_effect_reproduction_contract(self) -> None:
        def compiler_without_effect(reference: Path) -> dict:
            compiled = self.compiler(reference)
            compiled.pop("effectContract")
            return compiled

        with self.assertRaisesRegex(ReviewWorkflowError, "effect_reproduction_contract_required"):
            compile_reference(
                self.reference,
                compiler_without_effect,
                self.pool,
                self.generator,
                run_root=self.root / "runs",
                delivery_set_id="missing-effect-contract",
                ledger_file=self.ledger,
                reference_visual_checker=self.visual_checker,
            )

    def test_pending_requires_explicit_human_release(self) -> None:
        review = self.create_review()
        result = record_review_decision(
            Path(review["reviewRoot"]),
            "pending",
            "还需要比较另一版",
            self.pool,
            self.ledger,
            experience_sink=self.experience_sink,
            baseline_sink=self.guarded_baseline,
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
            experience_sink=self.experience_sink,
            baseline_sink=self.baseline_sink,
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
            experience_sink=self.experience_sink,
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
            experience_sink=self.experience_sink,
            baseline_sink=self.guarded_baseline,
        )
        self.assertEqual(decision["status"], "approved")
        self.assertEqual(self.pool.capacity("delivery-2"), 1)
        self.assertTrue((Path(review["reviewRoot"]) / "internal" / "experience-deposit-receipt.json").is_file())
        self.assertTrue((Path(review["reviewRoot"]) / "internal" / "dynamic-baseline-registration-receipt.json").is_file())

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
        delivery_file = (self.root / "runs" / "delivery" / f"{template()['key']}.json").resolve()
        self.assertEqual(final["delivery"], delivery_file.as_posix())
        self.assertEqual(
            json.loads(delivery_file.read_text(encoding="utf-8")),
            json.loads((final_root / "package" / "style-template.json").read_text(encoding="utf-8")),
        )
        delivery_manifest = json.loads(
            (delivery_file.parent / "artifact-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(delivery_manifest["stage"], "handoff")
        self.assertEqual(delivery_manifest["artifacts"][0]["path"], delivery_file.name)
        delivery_file.unlink()
        again = finalize_approved(
            Path(review["reviewRoot"]),
            self.root / "runs",
            oss,
            assets_domain="assets.example.com",
        )
        self.assertTrue(again["idempotent"])
        self.assertEqual(again["delivery"], delivery_file.as_posix())
        self.assertTrue(delivery_file.is_file())
        self.assertEqual(oss.calls, 1)

    def test_finalization_upgrades_existing_awaiting_formal_revision_and_reconciles_catalog(self) -> None:
        review = self.create_review(delivery="delivery-pending", key="pending-style")
        review_root = Path(review["reviewRoot"])
        record_review_decision(
            review_root,
            "pass",
            "人工验收通过",
            self.pool,
            self.ledger,
            experience_sink=self.experience_sink,
            baseline_sink=self.guarded_baseline,
        )
        run_root = self.root / "formal"
        pending_root = run_root / "pending-style/1"
        (pending_root / "package").mkdir(parents=True)
        shutil.copy2(review_root / "review-package/style-template.json", pending_root / "package/style-template.json")
        shutil.copy2(review_root / "review-package/cover.png", pending_root / "package/cover.png")
        shutil.copytree(review_root / "internal", pending_root / "internal")
        write_json(pending_root / "artifact-manifest.json", {
            "artifactType": "style_template_catalog_entry",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "status": "approved",
            "stage": "dynamic-human-pass",
            "templateKey": "pending-style",
            "revision": 1,
        })
        local_template = json.loads((pending_root / "package/style-template.json").read_text(encoding="utf-8"))
        catalog = {
            "artifactType": "style_template_delivery_catalog",
            "schemaVersion": "2.0.0",
            "producer": "style-template-analyzer",
            "templateCount": 1,
            "effectImageCount": 1,
            "ossStatusCounts": {"finalized": 0, "awaiting-finalization": 1},
            "items": [{
                "id": "pending-style-r1",
                "key": "pending-style",
                "title": local_template["title"],
                "revision": 1,
                "verdict": "pass",
                "ossStatus": "awaiting-finalization",
                "template": "pending-style/1/package/style-template.json",
                "effectImage": "pending-style/1/package/cover.png",
                "templateSha256": hashlib.sha256((pending_root / "package/style-template.json").read_bytes()).hexdigest(),
                "effectSha256": hashlib.sha256((pending_root / "package/cover.png").read_bytes()).hexdigest(),
                "cover": "cover.png",
            }],
        }
        write_json(run_root / "统一通过模板索引.json", catalog)
        write_json(run_root / "已通过模板清单.json", catalog)

        result = finalize_approved(
            review_root,
            run_root,
            Oss(),
            assets_domain="assets.example.com",
        )

        self.assertFalse(result["idempotent"])
        finalized = json.loads((pending_root / "package/style-template.json").read_text(encoding="utf-8"))
        self.assertTrue(finalized["cover"].startswith("https://assets.example.com/"))
        self.assertTrue((pending_root / "internal/oss-finalization-receipt.json").is_file())
        updated = json.loads((run_root / "统一通过模板索引.json").read_text(encoding="utf-8"))
        self.assertEqual(updated["items"][0]["ossStatus"], "finalized")
        self.assertEqual(updated["ossStatusCounts"], {"finalized": 1, "awaiting-finalization": 0})
        self.assertEqual(
            updated,
            json.loads((run_root / "已通过模板清单.json").read_text(encoding="utf-8")),
        )

    def test_concurrent_finalization_keeps_every_delivery_manifest_entry(self) -> None:
        reviews = [
            self.create_review(delivery="delivery-concurrent", key="thread-style-a"),
            self.create_review(delivery="delivery-concurrent", key="thread-style-b"),
        ]
        for review in reviews:
            record_review_decision(
                Path(review["reviewRoot"]),
                "pass",
                "人工验收通过",
                self.pool,
                self.ledger,
                experience_sink=self.experience_sink,
                baseline_sink=self.guarded_baseline,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda review: finalize_approved(
                    Path(review["reviewRoot"]),
                    self.root / "runs",
                    Oss(),
                    assets_domain="assets.example.com",
                ),
                reviews,
            ))

        self.assertEqual({Path(result["delivery"]).name for result in results}, {
            "thread-style-a.json",
            "thread-style-b.json",
        })
        manifest = json.loads(
            (self.root / "runs" / "delivery" / "artifact-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            {item["path"] for item in manifest["artifacts"]},
            {"thread-style-a.json", "thread-style-b.json"},
        )

    def test_delivery_manifest_failure_rolls_back_new_delivery(self) -> None:
        from unittest.mock import patch

        review = self.create_review(delivery="delivery-rollback", key="rollback-style")
        record_review_decision(
            Path(review["reviewRoot"]),
            "pass",
            "人工验收通过",
            self.pool,
            self.ledger,
            experience_sink=self.experience_sink,
            baseline_sink=self.guarded_baseline,
        )
        delivery_root = self.root / "runs" / "delivery"
        original_atomic_write = atomic_write_json
        failed = False

        def fail_manifest_once(path: Path, value: object) -> None:
            nonlocal failed
            if path.name == "artifact-manifest.json" and not failed:
                failed = True
                raise OSError("manifest write failed")
            original_atomic_write(path, value)

        with patch("style_review_workflow.atomic_write_json", side_effect=fail_manifest_once):
            with self.assertRaisesRegex(OSError, "manifest write failed"):
                finalize_approved(
                    Path(review["reviewRoot"]),
                    self.root / "runs",
                    Oss(),
                    assets_domain="assets.example.com",
                )

        self.assertFalse((delivery_root / "rollback-style.json").exists())
        self.assertFalse((delivery_root / "artifact-manifest.json").exists())

    def test_retired_template_is_rejected_before_pass_mutates_review_or_ledger(self) -> None:
        review = self.create_review()
        baseline_root = self.root / "baseline"
        baseline_root.mkdir()
        catalog_file = baseline_root / "统一通过模板索引.json"
        write_json(catalog_file, {
            "artifactType": "style_template_delivery_catalog",
            "schemaVersion": "2.0.0",
            "producer": "style-template-analyzer",
            "items": [],
        })
        register_retirement(
            baseline_root / "已退役模板索引.json",
            template()["key"],
            "人工决定退役",
        )

        with self.assertRaisesRegex(
            ReviewWorkflowError,
            "dynamic_baseline_registration_failed: dynamic_baseline_template_retired",
        ):
            record_review_decision(
                Path(review["reviewRoot"]),
                "pass",
                "人工验收通过",
                self.pool,
                self.ledger,
                experience_sink=self.experience_sink,
                baseline_sink=DynamicBaselineCatalog(catalog_file),
            )

        assignment = json.loads(self.ledger.read_text(encoding="utf-8"))["assignments"][0]
        self.assertEqual(assignment["status"], "awaiting_approval")
        self.assertFalse(
            (Path(review["reviewRoot"]) / "internal" / "approval-decision-receipt.json").exists()
        )
        self.assertEqual(self.experience_events, [])

    def test_pass_requires_an_authoritative_template_lifecycle_guard(self) -> None:
        review = self.create_review()

        with self.assertRaisesRegex(
            ReviewWorkflowError,
            "dynamic_baseline_guard_required",
        ):
            record_review_decision(
                Path(review["reviewRoot"]),
                "pass",
                "人工验收通过",
                self.pool,
                self.ledger,
                experience_sink=self.experience_sink,
                baseline_sink=self.baseline_sink,
            )

        assignment = json.loads(self.ledger.read_text(encoding="utf-8"))["assignments"][0]
        self.assertEqual(assignment["status"], "awaiting_approval")
        self.assertEqual(self.experience_events, [])

    def test_experience_deposit_failure_blocks_completion_and_can_retry(self) -> None:
        review = self.create_review()

        def broken_sink(event: dict) -> None:
            raise RuntimeError("offline")

        with self.assertRaisesRegex(ReviewWorkflowError, "experience_deposit_failed"):
            record_review_decision(
                Path(review["reviewRoot"]),
                "pass",
                "人工验收通过",
                self.pool,
                self.ledger,
                experience_sink=broken_sink,
                baseline_sink=self.guarded_baseline,
            )
        with self.assertRaisesRegex(ReviewWorkflowError, "experience_deposit_required"):
            finalize_approved(
                Path(review["reviewRoot"]),
                self.root / "runs",
                Oss(),
                assets_domain="assets.example.com",
            )
        retried = record_review_decision(
            Path(review["reviewRoot"]),
            "pass",
            "人工验收通过",
            self.pool,
            self.ledger,
            experience_sink=self.experience_sink,
            baseline_sink=self.guarded_baseline,
        )
        self.assertTrue(retried["idempotent"])
        self.assertTrue((Path(review["reviewRoot"]) / "internal" / "experience-deposit-receipt.json").is_file())

    def test_dynamic_baseline_failure_blocks_finalization_and_can_retry(self) -> None:
        review = self.create_review()

        def broken_baseline(event: dict) -> dict:
            raise RuntimeError("catalog offline")
        guarded_broken_baseline = GuardedBaseline(broken_baseline)

        with self.assertRaisesRegex(ReviewWorkflowError, "dynamic_baseline_registration_failed"):
            record_review_decision(
                Path(review["reviewRoot"]),
                "pass",
                "人工验收通过",
                self.pool,
                self.ledger,
                experience_sink=self.experience_sink,
                baseline_sink=guarded_broken_baseline,
            )
        with self.assertRaisesRegex(ReviewWorkflowError, "dynamic_baseline_registration_required"):
            finalize_approved(
                Path(review["reviewRoot"]),
                self.root / "runs",
                Oss(),
                assets_domain="assets.example.com",
            )
        retried = record_review_decision(
            Path(review["reviewRoot"]),
            "pass",
            "人工验收通过",
            self.pool,
            self.ledger,
            experience_sink=self.experience_sink,
            baseline_sink=self.guarded_baseline,
        )
        self.assertTrue(retried["idempotent"])
        self.assertTrue((Path(review["reviewRoot"]) / "internal" / "dynamic-baseline-registration-receipt.json").is_file())

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
                reference_visual_checker=self.visual_checker,
            )
        ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
        self.assertEqual(ledger["assignments"][0]["status"], "released")
        self.assertEqual(ledger["assignments"][0]["decision"]["verdict"], "system_failure")
        retried = self.create_review()
        self.assertEqual(retried["status"], "awaiting_approval")

    def test_reference_semantics_failure_happens_before_asset_reservation(self) -> None:
        def ambiguous(reference: Path) -> dict:
            result = self.compiler(reference)
            result["referenceInterpretation"]["ambiguities"] = ["无法判断标题是否属于风格"]
            return result

        with self.assertRaisesRegex(ReviewWorkflowError, "reference_interpretation_failed"):
            compile_reference(
                self.reference,
                ambiguous,
                self.pool,
                self.generator,
                run_root=self.root / "runs",
                delivery_set_id="delivery-1",
                ledger_file=self.ledger,
                reference_visual_checker=self.visual_checker,
            )
        self.assertFalse(self.ledger.exists())

    def test_independent_visual_gate_blocks_review_package_and_releases_asset(self) -> None:
        def self_review(output: Path, template_data: dict, interpretation_data: dict, attempt: int) -> dict:
            result = self.visual_checker(output, template_data, interpretation_data, attempt)
            result["reviewer"] = interpretation_data["producer"]
            return result

        with self.assertRaisesRegex(ReviewWorkflowError, "reference_visual_gate_invalid"):
            compile_reference(
                self.reference,
                self.compiler,
                self.pool,
                self.generator,
                run_root=self.root / "runs",
                delivery_set_id="delivery-1",
                ledger_file=self.ledger,
                reference_visual_checker=self_review,
            )
        ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
        self.assertEqual(ledger["assignments"][0]["status"], "released")

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
            experience_sink=self.experience_sink,
            baseline_sink=self.guarded_baseline,
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
