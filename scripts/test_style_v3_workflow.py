#!/usr/bin/env python3
"""End-to-end tests for v3 compile, produce, and independent advance stages."""

from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from unittest.mock import patch

from PIL import Image

from style_baseline import build_baseline_snapshot
from style_contracts import build_manifest
from style_test_pool import TestImagePool, TestPoolError, normalize_asset
from style_v3_workflow import (
    WorkflowError,
    advance_package,
    compile,
    compile_reference,
    produce,
    produce_from_baseline,
)
from test_validate_style_analysis import analysis
from test_validate_style_evaluation import evaluation
from test_validate_style_template import template
from validate_style_package import validate_package


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class FakeGenerator:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def __call__(self, asset: dict, template_data: dict, output: Path) -> dict:
        self.calls += 1
        if self.fail:
            raise RuntimeError("generator exploded")
        Image.new("RGB", (16, 16), (120, 80, 40)).save(output, format="PNG")
        return {"provider": "fake", "model": "fixture", "sourceAssetId": asset["assetId"]}


class FakeOssAdapter:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def __call__(self, source: Path, output: Path) -> dict:
        self.calls += 1
        if self.fail:
            raise RuntimeError("oss exploded")
        data = json.loads((source / "style-template.json").read_text(encoding="utf-8"))
        data["cover"] = "https://assets.example.com/style/templates/123e4567-e89b-42d3-a456-426614174000.png"
        write_json(output, data)
        return {"provider": "fake-oss", "uploaded": 1}


def pool_asset(asset_id: str, digest: str, perceptual_hash: str) -> dict:
    local_path = Path(tempfile.gettempdir()) / f"style-v3-workflow-{asset_id}.jpg"
    Image.new("RGB", (640, 512), (ord(digest[0]) % 255, 60, 90)).save(local_path, format="JPEG")
    return normalize_asset({
        "assetId": asset_id,
        "sourceAdapter": "fixture",
        "sourcePageUrl": f"https://example.test/{asset_id}",
        "imageUrl": f"https://example.test/{asset_id}.jpg",
        "author": "Fixture Author",
        "license": "CC0",
        "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
        "rightsStatus": "verified",
        "collectedAt": "2026-08-17T00:00:00Z",
        "mime": "image/jpeg",
        "width": 640,
        "height": 512,
        "sha256": hashlib.sha256(local_path.read_bytes()).hexdigest(),
        "perceptualHash": perceptual_hash,
        "photographic": True,
        "photographicEvidence": "测试 fixture 确认摄影图",
        "riskLabels": [],
        "category": "object",
        "localPath": local_path.as_posix(),
    })


def compile_inputs() -> tuple[dict, dict]:
    data = template()
    data["cover"] = "cover.png"
    evidence = analysis()
    evidence["templateKey"] = data["key"]
    return data, evidence


def make_fresh(data: dict) -> None:
    data["key"] = "fresh-paper-sculpture"
    data["title"] = "纸艺塑形"
    data["description"] = "把你的画面完整重绘为层叠剪纸、折痕阴影与纸张纤维组成的立体纸艺"
    data["promptTemplate"] = data["promptTemplate"].replace(
        "将全部目标画面完整重绘为高反射抛光铬材质：连续圆润曲面概括形体，宽阔高光与深色反射带塑造体积，柔和接触阴影稳定空间，所有区域使用同一非摄影成像。",
        "将全部目标画面完整重绘为层叠纸艺雕塑：以切割纸边、折痕、纤维纹理和分层投影塑造体积，使用哑光纸张综合色块统一全部区域。",
    )
    data["metadata"]["sourceRef"]["producerKey"] = data["key"]


class CompileWorkflowTests(unittest.TestCase):
    def test_compile_creates_atomic_two_file_package_and_internal_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            pool = TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)])
            generator = FakeGenerator()
            data, evidence = compile_inputs()
            result = compile_reference(
                reference, data, evidence, pool, generator,
                run_root=root / "runs", delivery_set_id="delivery-1", revision=1,
            )
            revision_root = Path(result["revisionRoot"])
            self.assertEqual(sorted(path.name for path in (revision_root / "package").iterdir()), ["cover.png", "style-template.json"])
            self.assertTrue((revision_root / "internal" / "test-image-assignment.json").is_file())
            self.assertTrue((revision_root / "artifact-manifest.json").is_file())
            errors, _ = validate_package(revision_root, "fast-package", "local", "", "")
            self.assertEqual(errors, [])

    def test_compile_failure_leaves_no_package_or_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            pool = TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)])
            data, evidence = compile_inputs()
            with self.assertRaisesRegex(WorkflowError, "cover_generation_failed"):
                compile_reference(
                    reference, data, evidence, pool, FakeGenerator(fail=True),
                    run_root=root / "runs", delivery_set_id="delivery-1", revision=1,
                )
            self.assertEqual(pool.assignments, [])
            self.assertFalse((root / "runs" / data["key"] / "1" / "package").exists())

    def test_invalid_template_is_rejected_before_generator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            data["title"] = "太短"
            generator = FakeGenerator()
            pool = TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)])
            with self.assertRaisesRegex(WorkflowError, "package_validation_failed"):
                compile_reference(
                    reference, data, evidence, pool, generator,
                    run_root=root / "runs", delivery_set_id="delivery-1",
                )
            self.assertEqual(generator.calls, 0)
            self.assertEqual(pool.assignments, [])

    def test_publish_failure_releases_persisted_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            ledger = root / "ledger.json"
            with patch("style_v3_workflow._publish_revision", side_effect=OSError("rename failed")):
                with self.assertRaisesRegex(OSError, "rename failed"):
                    compile_reference(
                        reference, data, evidence,
                        TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)]), FakeGenerator(),
                        run_root=root / "runs", delivery_set_id="delivery-1", ledger_file=ledger,
                    )
            ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(ledger_data["assignments"], [])

    def test_ledger_commit_failure_rolls_back_public_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            ledger = root / "ledger.json"
            pool = TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)])
            with patch.object(pool, "commit_persisted", side_effect=OSError("ledger failed")):
                with self.assertRaisesRegex(OSError, "ledger failed"):
                    compile_reference(
                        reference, data, evidence, pool, FakeGenerator(),
                        run_root=root / "runs", delivery_set_id="delivery-1", ledger_file=ledger,
                    )
            self.assertFalse((root / "runs" / data["key"] / "1").exists())
            self.assertEqual(json.loads(ledger.read_text(encoding="utf-8"))["assignments"], [])

    def test_restart_promotes_publishing_assignment_to_committed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            ledger = root / "ledger.json"
            asset = pool_asset("asset-a", "a" * 64, "0" * 16)
            kwargs = dict(run_root=root / "runs", delivery_set_id="delivery-1", ledger_file=ledger)
            compile_reference(reference, data, evidence, TestImagePool([asset]), FakeGenerator(), **kwargs)
            ledger_data = json.loads(ledger.read_text(encoding="utf-8"))
            ledger_data["assignments"][0]["status"] = "publishing"
            write_json(ledger, ledger_data)
            result = compile_reference(reference, data, evidence, TestImagePool([asset]), FakeGenerator(), **kwargs)
            self.assertTrue(result["idempotent"])
            self.assertEqual(json.loads(ledger.read_text(encoding="utf-8"))["assignments"][0]["status"], "committed")

    def test_same_identity_concurrent_calls_generate_once_and_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            asset = pool_asset("asset-a", "a" * 64, "0" * 16)
            ledger = root / "ledger.json"
            entered = Event()
            release = Event()
            counter_lock = Lock()
            calls = 0

            def blocking_generator(source: dict, template_data: dict, output: Path) -> dict:
                nonlocal calls
                with counter_lock:
                    calls += 1
                entered.set()
                if not release.wait(timeout=5):
                    raise RuntimeError("test timeout")
                Image.new("RGB", (16, 16), (5, 6, 7)).save(output, format="PNG")
                return {"provider": "fake", "sourceAssetId": source["assetId"]}

            def run_once() -> dict:
                return compile_reference(
                    reference, data, evidence, TestImagePool([asset]), blocking_generator,
                    run_root=root / "runs", delivery_set_id="delivery-1", ledger_file=ledger,
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(run_once)
                self.assertTrue(entered.wait(timeout=5))
                second = executor.submit(run_once)
                release.set()
                results = [first.result(timeout=5), second.result(timeout=5)]

            self.assertEqual(calls, 1)
            self.assertEqual({result["idempotent"] for result in results}, {False, True})
            self.assertEqual(json.loads(ledger.read_text(encoding="utf-8"))["assignments"][0]["status"], "committed")

    def test_assigned_asset_is_reverified_before_generator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            asset = pool_asset("asset-a", "a" * 64, "0" * 16)
            pool = TestImagePool([asset])
            Path(asset["localPath"]).unlink()
            generator = FakeGenerator()
            with self.assertRaisesRegex(TestPoolError, "test_asset_not_ready"):
                compile_reference(
                    reference, data, evidence, pool, generator,
                    run_root=root / "runs", delivery_set_id="delivery-1",
                )
            self.assertEqual(generator.calls, 0)

    def test_generator_receipt_must_match_assigned_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            def wrong_receipt(asset: dict, template_data: dict, output: Path) -> dict:
                Image.new("RGB", (16, 16), (1, 2, 3)).save(output, format="PNG")
                return {"provider": "fake", "sourceAssetId": "wrong"}
            with self.assertRaisesRegex(WorkflowError, "sourceAssetId mismatch"):
                compile_reference(
                    reference, data, evidence,
                    TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)]), wrong_receipt,
                    run_root=root / "runs", delivery_set_id="delivery-1",
                )

    def test_compile_retry_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            pool = TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)])
            generator = FakeGenerator()
            data, evidence = compile_inputs()
            kwargs = dict(run_root=root / "runs", delivery_set_id="delivery-1", revision=1)
            first = compile_reference(reference, data, evidence, pool, generator, **kwargs)
            second = compile_reference(reference, data, evidence, pool, generator, **kwargs)
            self.assertEqual(first["revisionRoot"], second["revisionRoot"])
            self.assertEqual(generator.calls, 1)
            self.assertEqual(len(pool.assignments), 1)

    def test_public_compile_calls_compiler_and_persists_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            called = []
            def compiler(source: Path) -> dict:
                called.append(source)
                return {"template": data, "analysis": evidence}
            result = compile(
                reference, compiler,
                TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)]), FakeGenerator(),
                run_root=root / "runs", delivery_set_id="delivery-1", ledger_file=root / "ledger.json",
                oss_adapter=FakeOssAdapter(), assets_domain="assets.example.com",
            )
            self.assertEqual(called, [reference])
            self.assertTrue(Path(result["revisionRoot"]).is_dir())
            ledger = json.loads((root / "ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["assignments"][0]["status"], "committed")
            final_template = json.loads((Path(result["package"]) / "style-template.json").read_text(encoding="utf-8"))
            self.assertTrue(final_template["cover"].startswith("https://assets.example.com/style/templates/"))
            errors, _ = validate_package(Path(result["revisionRoot"]), "final-package", "remote", "assets.example.com", "")
            self.assertEqual(errors, [])

    def test_public_compile_preview_stops_before_oss_and_has_no_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            result = compile(
                reference, lambda _: {"template": data, "analysis": evidence},
                TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)]), FakeGenerator(),
                run_root=root / "runs", delivery_set_id="delivery-1", ledger_file=root / "ledger.json",
                preview=True,
            )
            self.assertEqual(result["status"], "awaiting_oss")
            preview_root = Path(result["prepublishRoot"])
            self.assertFalse((root / "runs" / data["key"] / "1" / "package").exists())
            self.assertFalse((preview_root / "package").exists())
            errors, _ = validate_package(preview_root, "prepublish", "local", "", "")
            self.assertEqual(errors, [])

    def test_public_compile_oss_failure_leaves_no_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            ledger = root / "ledger.json"
            with self.assertRaisesRegex(WorkflowError, "oss_finalization_failed"):
                compile(
                    reference, lambda _: {"template": data, "analysis": evidence},
                    TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)]), FakeGenerator(),
                    run_root=root / "runs", delivery_set_id="delivery-1", ledger_file=ledger,
                    oss_adapter=FakeOssAdapter(fail=True), assets_domain="assets.example.com",
                )
            self.assertFalse((root / "runs" / data["key"] / "1" / "package").exists())
            self.assertEqual(json.loads(ledger.read_text(encoding="utf-8"))["assignments"], [])

    def test_lightweight_cover_check_retries_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            generator = FakeGenerator()
            decisions = []
            def checker(_cover: Path, _template: dict, attempt: int) -> dict:
                decisions.append(attempt)
                return {"verdict": "retry" if attempt == 1 else "pass", "reasons": ["fixture"]}
            result = compile(
                reference, lambda _: {"template": data, "analysis": evidence},
                TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)]), generator,
                run_root=root / "runs", delivery_set_id="delivery-1", ledger_file=root / "ledger.json",
                oss_adapter=FakeOssAdapter(), assets_domain="assets.example.com", cover_checker=checker,
            )
            self.assertEqual(generator.calls, 2)
            self.assertEqual(decisions, [1, 2])
            receipt = json.loads((Path(result["revisionRoot"]) / "internal" / "cover-check-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual([item["verdict"] for item in receipt["attempts"]], ["retry", "pass"])

    def test_final_package_can_advance_to_independent_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            data, evidence = compile_inputs()
            result = compile(
                reference, lambda _: {"template": data, "analysis": evidence},
                TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)]), FakeGenerator(),
                run_root=root / "runs", delivery_set_id="delivery-1", ledger_file=root / "ledger.json",
                oss_adapter=FakeOssAdapter(), assets_domain="assets.example.com",
            )
            def evaluator(_source: Path, output: Path) -> dict:
                write_json(output, evaluation(output.parent))
                return {"provider": "fake-evaluator"}
            advanced = advance_package(
                Path(result["package"]), "evaluation", evaluator, root / "evaluation",
                assets_domain="assets.example.com",
            )
            self.assertEqual(advanced["status"], "completed")
            self.assertTrue(Path(advanced["outputPath"]).is_file())

    def test_existing_revision_reconciles_assignment_into_fresh_pool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.jpg"
            reference.write_bytes(b"reference")
            asset = pool_asset("asset-a", "a" * 64, "0" * 16)
            data, evidence = compile_inputs()
            kwargs = dict(run_root=root / "runs", delivery_set_id="delivery-1", revision=1)
            compile_reference(reference, data, evidence, TestImagePool([asset]), FakeGenerator(), **kwargs)
            fresh_pool = TestImagePool([asset])
            generator = FakeGenerator()
            result = compile_reference(reference, data, evidence, fresh_pool, generator, **kwargs)
            self.assertTrue(result["idempotent"])
            self.assertEqual(generator.calls, 0)
            self.assertEqual(fresh_pool.assignments[0]["assetId"], "asset-a")


class ProduceWorkflowTests(unittest.TestCase):
    def baseline(self, root: Path) -> tuple[dict, Path]:
        baseline = root / "baseline"
        item = baseline / "existing"
        item.mkdir(parents=True)
        (item / "style.png").write_bytes(b"image")
        write_json(item / "style-template.json", template())
        return build_baseline_snapshot(baseline, approved_count=1), baseline

    def test_produce_rejects_duplicates_and_delivers_new_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, baseline = self.baseline(root)
            duplicate, duplicate_analysis = compile_inputs()
            fresh, fresh_analysis = compile_inputs()
            make_fresh(fresh)
            fresh_analysis["templateKey"] = fresh["key"]
            pool = TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)])
            results = produce_from_baseline(
                snapshot, baseline,
                [{"template": duplicate, "analysis": duplicate_analysis}, {"template": fresh, "analysis": fresh_analysis}],
                pool, FakeGenerator(), run_root=root / "runs", delivery_set_id="delivery-1",
            )
            self.assertEqual(results[0]["status"], "failed")
            self.assertEqual(results[0]["code"], "candidate_duplicate_key")
            self.assertEqual(results[1]["status"], "completed")
            revision_root = Path(results[1]["revisionRoot"])
            self.assertTrue(revision_root.joinpath("package", "cover.png").is_file())

            snapshot_file = revision_root / "internal" / "baseline-snapshot.json"
            invalid_snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
            invalid_snapshot["schemaVersion"] = "999.0.0"
            invalid_snapshot["producer"] = "wrong"
            invalid_snapshot["createdAt"] = None
            write_json(snapshot_file, invalid_snapshot)
            write_json(
                revision_root / "artifact-manifest.json",
                build_manifest(revision_root, "package", schema_version="2.0.0"),
            )
            errors, _ = validate_package(revision_root, "fast-package", "local", "", "")
            self.assertTrue(any("schemaVersion" in error and "1.0.0" in error for error in errors))
            self.assertTrue(any("producer" in error and "style-template-analyzer" in error for error in errors))
            self.assertTrue(any("None is not of type 'string'" in error for error in errors))

    def test_public_produce_verifies_approval_and_calls_proposer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            snapshot, baseline = self.baseline(repo)
            descriptor = {
                "artifactType": "style_baseline_approval",
                "schemaVersion": "1.0.0",
                "producer": "style-template-analyzer",
                "approved": True,
                "businessRoot": "baseline",
                "expectedCount": 1,
                "digest": snapshot["digest"],
            }
            approval_file = repo / "approval.json"
            write_json(approval_file, descriptor)
            fresh, evidence = compile_inputs()
            make_fresh(fresh)
            evidence["templateKey"] = fresh["key"]
            called = []
            def proposer(approved: dict, templates: list[dict]) -> list[dict]:
                called.append((approved["digest"], len(templates)))
                return [{"template": fresh, "analysis": evidence}]
            results = produce(
                repo, proposer,
                TestImagePool([pool_asset("asset-a", "a" * 64, "0" * 16)]), FakeGenerator(),
                run_root=repo / "runs", delivery_set_id="delivery-1", ledger_file=repo / "ledger.json",
                approval_file=approval_file,
                oss_adapter=FakeOssAdapter(), assets_domain="assets.example.com",
            )
            self.assertEqual(called, [(snapshot["digest"], 1)])
            self.assertEqual(results[0]["status"], "completed")
            descriptor["digest"] = "0" * 64
            write_json(approval_file, descriptor)
            with self.assertRaisesRegex(WorkflowError, "baseline_digest_mismatch"):
                produce(
                    repo, proposer, TestImagePool(), FakeGenerator(),
                    run_root=repo / "other", delivery_set_id="delivery-2", ledger_file=repo / "other-ledger.json",
                    approval_file=approval_file,
                )


class AdvanceWorkflowTests(unittest.TestCase):
    def package(self, root: Path) -> tuple[Path, dict]:
        reference = root / "reference.jpg"
        reference.write_bytes(b"reference")
        data, evidence = compile_inputs()
        result = compile_reference(
            reference, data, evidence,
            TestImagePool([pool_asset("advance-asset", "c" * 64, "a" * 16)]), FakeGenerator(),
            run_root=root / "runs", delivery_set_id="advance-delivery",
        )
        return Path(result["package"]), data

    def test_evaluation_and_oss_handoff_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, data = self.package(root)
            calls = []
            def adapter(source: Path, output: Path) -> dict:
                calls.append(output.name)
                output.parent.mkdir(parents=True, exist_ok=True)
                if output.name == "style-evaluation.json":
                    write_json(output, evaluation(output.parent))
                else:
                    handoff = dict(data)
                    handoff["cover"] = "https://assets.example.com/style/templates/00000000-0000-4000-8000-000000000000.png"
                    write_json(output, handoff)
                return {"path": output.as_posix()}
            evaluation_result = advance_package(package, "evaluation", adapter, Path(directory) / "evaluation")
            oss = advance_package(package, "oss-handoff", adapter, root / "oss", assets_domain="assets.example.com")
            self.assertEqual(evaluation_result["status"], "completed")
            self.assertEqual(oss["status"], "completed")
            self.assertTrue(Path(evaluation_result["output"]["path"]).is_file())
            self.assertEqual(evaluation_result["output"]["path"], evaluation_result["outputPath"])
            self.assertEqual(len(calls), 2)
            with self.assertRaisesRegex(WorkflowError, "stage_unsupported"):
                advance_package(package, "unknown", adapter, Path(directory) / "unknown")

    def test_advance_rejects_invalid_adapter_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, _ = self.package(root)
            def invalid(_: Path, output: Path) -> dict:
                output.parent.mkdir(parents=True, exist_ok=True)
                write_json(output, {})
                return {}
            with self.assertRaisesRegex(WorkflowError, "advance_validation_failed"):
                advance_package(package, "evaluation", invalid, root / "evaluation")
            self.assertFalse((root / "evaluation").exists())

    def test_advance_preserves_existing_output_and_rejects_source_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, _ = self.package(root)
            output_root = root / "evaluation"

            def valid(_: Path, output: Path) -> dict:
                write_json(output, evaluation(output.parent))
                return {"path": output.as_posix()}

            advance_package(package, "evaluation", valid, output_root)
            manifest_digest = hashlib.sha256((output_root / "artifact-manifest.json").read_bytes()).hexdigest()
            with self.assertRaisesRegex(WorkflowError, "output_conflict"):
                advance_package(package, "evaluation", lambda *_: {}, output_root)
            self.assertEqual(
                hashlib.sha256((output_root / "artifact-manifest.json").read_bytes()).hexdigest(),
                manifest_digest,
            )
            with self.assertRaisesRegex(WorkflowError, "advance_output_overlaps_source"):
                advance_package(package, "evaluation", valid, package / "evaluation")

    def test_oss_handoff_rejects_wrong_key_and_uncontrolled_domain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, data = self.package(root)
            def wrong(_: Path, output: Path) -> dict:
                payload = json.loads(json.dumps(data))
                payload["key"] = "another-valid-style"
                payload["metadata"]["sourceRef"]["producerKey"] = payload["key"]
                payload["cover"] = "https://evil.example/style/templates/00000000-0000-4000-8000-000000000000.png"
                write_json(output, payload)
                return {}
            with self.assertRaisesRegex(WorkflowError, "advance_validation_failed"):
                advance_package(
                    package, "oss-handoff", wrong, root / "oss",
                    assets_domain="assets.example.com",
                )

    def test_advance_rejects_damaged_source_cover(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package, _ = self.package(root)
            (package / "cover.png").write_bytes(b"not-png")
            with self.assertRaisesRegex(WorkflowError, "package_validation_failed"):
                advance_package(package, "evaluation", lambda *_: {}, root / "evaluation")


if __name__ == "__main__":
    unittest.main()
