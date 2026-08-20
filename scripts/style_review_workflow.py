#!/usr/bin/env python3
"""Approval-gated style-template workflow and phase router."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from style_baseline import verify_approval_descriptor
from style_contracts import build_manifest, read_json, sha256_file
from style_dynamic_baseline import DynamicBaselineCatalog, DynamicBaselineError
from style_experience_store import DurableExperienceStore, ExperienceStoreError
from style_reference_gate import validate_reference_interpretation, validate_visual_gate
from style_test_pool import TestImagePool, TestPoolError
from validate_style_analysis import validate_data as validate_analysis
from validate_style_package import validate_package
from validate_style_template import validate_data as validate_template


class ReviewWorkflowError(RuntimeError):
    """Machine-readable approval workflow failure."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@contextmanager
def _lock(path: Path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def _identity_lock(run_root: Path, ledger_file: Path, delivery_set_id: str, key: str, revision: int) -> Path:
    digest = hashlib.sha256(
        f"{run_root.resolve()}\0{delivery_set_id}\0{key}\0{revision}".encode("utf-8")
    ).hexdigest()
    return ledger_file.parent / ".style-transaction-locks" / f"{digest}.lock"


def _prompt_sha256(template_data: dict[str, Any]) -> str:
    prompt = template_data.get("promptTemplate")
    if not isinstance(prompt, str) or not prompt:
        raise ReviewWorkflowError("template_prompt_missing")
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _verify_png(path: Path) -> None:
    try:
        with Image.open(path) as image:
            image.verify()
            if image.format != "PNG":
                raise ValueError("format is not PNG")
    except (OSError, ValueError) as error:
        raise ReviewWorkflowError(f"cover_generation_failed: {error}") from error


def _preflight(template_data: dict[str, Any], analysis_data: dict[str, Any], analysis_filename: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        local = json.loads(json.dumps(template_data, ensure_ascii=False))
        local["cover"] = "cover.png"
        Image.new("RGB", (8, 8), (0, 0, 0)).save(root / "cover.png", format="PNG")
        errors = validate_template(local, root / "style-template.json", "local", "", "")
    if errors:
        raise ReviewWorkflowError(f"package_validation_failed: {'; '.join(errors)}")
    if analysis_filename == "style-analysis.json":
        errors = validate_analysis(analysis_data)
        if errors:
            raise ReviewWorkflowError(f"package_validation_failed: {'; '.join(errors)}")


def _generate_cover(
    asset: dict[str, Any],
    template_data: dict[str, Any],
    output: Path,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    checker: Callable[[Path, dict[str, Any], int], dict[str, Any]] | None,
    *,
    reference_interpretation: dict[str, Any] | None = None,
    reference_interpretation_file: Path | None = None,
    reference_visual_checker: Callable[[Path, dict[str, Any], dict[str, Any], int], dict[str, Any]] | None = None,
    revision: int = 1,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    attempts: list[dict[str, Any]] = []
    for attempt in (1, 2):
        try:
            receipt = generator(asset, template_data, output)
        except Exception as error:
            raise ReviewWorkflowError(f"cover_generation_failed: {error}") from error
        _verify_png(output)
        if not isinstance(receipt, dict) or receipt.get("sourceAssetId") != asset.get("assetId"):
            raise ReviewWorkflowError("cover_generation_failed: provider sourceAssetId mismatch")
        decision = checker(output, template_data, attempt) if checker else {"verdict": "pass", "reasons": []}
        if not isinstance(decision, dict) or decision.get("verdict") not in {"pass", "retry"}:
            raise ReviewWorkflowError("cover_check_invalid")
        reasons = decision.get("reasons", [])
        if not isinstance(reasons, list) or any(not isinstance(reason, str) or not reason for reason in reasons):
            raise ReviewWorkflowError("cover_check_invalid")
        attempts.append({"attempt": attempt, "verdict": decision["verdict"], "reasons": reasons})
        if decision["verdict"] != "pass":
            continue
        if reference_interpretation is None:
            return receipt, attempts, None
        if reference_visual_checker is None or reference_interpretation_file is None:
            raise ReviewWorkflowError("reference_visual_checker_required")
        try:
            visual = reference_visual_checker(output, template_data, reference_interpretation, attempt)
        except Exception as error:
            raise ReviewWorkflowError(f"reference_visual_gate_failed: {error}") from error
        if not isinstance(visual, dict):
            raise ReviewWorkflowError("reference_visual_gate_invalid: reviewer output must be an object")
        visual_receipt = {
            "artifactType": "reference_visual_gate_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": template_data["key"],
            "revision": revision,
            "attempt": attempt,
            "reviewer": visual.get("reviewer"),
            "independenceDeclaration": visual.get("independenceDeclaration"),
            "referenceInterpretationSha256": sha256_file(reference_interpretation_file),
            "coverSha256": sha256_file(output),
            "verdict": visual.get("verdict"),
            "scores": visual.get("scores"),
            "evidence": visual.get("evidence"),
            "hardFailures": visual.get("hardFailures"),
        }
        visual_errors = validate_visual_gate(
            visual_receipt,
            analysis_producer=str(reference_interpretation.get("producer", "")),
        )
        if visual_errors:
            raise ReviewWorkflowError(f"reference_visual_gate_invalid: {'; '.join(visual_errors)}")
        if visual_receipt["verdict"] == "pass":
            return receipt, attempts, visual_receipt
    raise ReviewWorkflowError(
        "reference_visual_gate_failed" if reference_interpretation is not None else "cover_check_failed"
    )


def _review_root(run_root: Path, key: str, revision: int) -> Path:
    return run_root.resolve() / "review-packages" / key / str(revision)


def _final_root(run_root: Path, key: str, revision: int) -> Path:
    return run_root.resolve() / key / str(revision)


def create_review_package(
    template_data: dict[str, Any],
    analysis_data: dict[str, Any],
    pool: TestImagePool,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    *,
    run_root: Path,
    delivery_set_id: str,
    ledger_file: Path,
    revision: int = 1,
    analysis_filename: str = "style-analysis.json",
    extra_internal: dict[str, object] | None = None,
    cover_checker: Callable[[Path, dict[str, Any], int], dict[str, Any]] | None = None,
    reference_interpretation: dict[str, Any] | None = None,
    reference_visual_checker: Callable[[Path, dict[str, Any], dict[str, Any], int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    key = template_data.get("key")
    if not isinstance(key, str):
        raise ReviewWorkflowError("template_key_missing")
    _preflight(template_data, analysis_data, analysis_filename)
    if analysis_filename == "style-analysis.json":
        if reference_interpretation is None:
            raise ReviewWorkflowError("reference_interpretation_required")
        interpretation_errors = validate_reference_interpretation(reference_interpretation, expected_key=key)
        if interpretation_errors:
            raise ReviewWorkflowError(f"reference_interpretation_failed: {'; '.join(interpretation_errors)}")
        if reference_visual_checker is None:
            raise ReviewWorkflowError("reference_visual_checker_required")
    target = _review_root(run_root, key, revision)
    lock_file = _identity_lock(run_root, ledger_file, delivery_set_id, key, revision)
    with _lock(lock_file):
        if target.is_dir():
            errors, _ = validate_package(target, "review-package", "local", "", "")
            if errors:
                raise ReviewWorkflowError(f"review_package_validation_failed: {'; '.join(errors)}")
            existing_manifest = read_json(target / "artifact-manifest.json")
            if analysis_filename == "style-analysis.json" and existing_manifest.get("schemaVersion") not in {"5.0.0", "5.1.0"}:
                raise ReviewWorkflowError("reference_gate_upgrade_required")
            assignment = read_json(target / "internal" / "test-image-assignment.json")
            pool.refresh_persisted(ledger_file)
            matches = [
                item for item in pool.assignments
                if (item.get("deliverySetId"), item.get("templateKey"), item.get("revision"))
                == (delivery_set_id, key, revision)
            ]
            if not matches or matches[0] != assignment:
                raise ReviewWorkflowError("test_assignment_state_mismatch")
            return {
                "status": "awaiting_approval" if assignment["status"] == "awaiting_approval" else assignment["status"],
                "reviewRoot": target.as_posix(),
                "reviewPackage": (target / "review-package").as_posix(),
                "assetId": assignment["assetId"],
                "idempotent": True,
            }

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            assignment = pool.reserve_persisted(delivery_set_id, key, revision, ledger_file)
        except TestPoolError as error:
            raise ReviewWorkflowError(str(error)) from error
        temporary = Path(tempfile.mkdtemp(prefix=f".{revision}-", dir=target.parent))
        try:
            public = temporary / "review-package"
            internal = temporary / "internal"
            public.mkdir()
            internal.mkdir()
            local_template = json.loads(json.dumps(template_data, ensure_ascii=False))
            local_template["cover"] = "cover.png"
            _write_json(public / "style-template.json", local_template)
            _write_json(internal / analysis_filename, analysis_data)
            interpretation_file: Path | None = None
            if reference_interpretation is not None:
                interpretation_file = internal / "reference-interpretation.json"
                _write_json(interpretation_file, reference_interpretation)
            for filename, value in (extra_internal or {}).items():
                _write_json(internal / filename, value)
            asset = pool.asset(assignment["assetId"])
            provider, attempts, visual_receipt = _generate_cover(
                asset,
                local_template,
                public / "cover.png",
                generator,
                cover_checker,
                reference_interpretation=reference_interpretation,
                reference_interpretation_file=interpretation_file,
                reference_visual_checker=reference_visual_checker,
                revision=revision,
            )
            _write_json(internal / "cover-generation-receipt.json", {
                "artifactType": "cover_generation_receipt",
                "schemaVersion": "1.0.0",
                "producer": "style-template-analyzer",
                "templateKey": key,
                "revision": revision,
                "assetId": assignment["assetId"],
                "provider": provider,
            })
            _write_json(internal / "cover-check-receipt.json", {
                "artifactType": "cover_check_receipt",
                "schemaVersion": "1.0.0",
                "producer": "style-template-analyzer",
                "templateKey": key,
                "revision": revision,
                "verdict": "pass",
                "attempts": attempts,
            })
            if visual_receipt is not None:
                _write_json(internal / "reference-visual-gate-receipt.json", visual_receipt)
            ready_at = _now()
            review_assignment = dict(assignment, status="awaiting_approval", reviewReadyAt=ready_at)
            _write_json(internal / "test-image-assignment.json", review_assignment)
            _write_json(temporary / "artifact-manifest.json", build_manifest(
                temporary,
                "review-package",
                revision,
                schema_version="5.1.0",
            ))
            errors, _ = validate_package(temporary, "review-package", "local", "", "")
            if errors:
                raise ReviewWorkflowError(f"review_package_validation_failed: {'; '.join(errors)}")
            os.replace(temporary, target)
            try:
                persisted = pool.mark_awaiting_approval_persisted(
                    delivery_set_id,
                    key,
                    revision,
                    ledger_file,
                    review_ready_at=ready_at,
                )
            except Exception:
                shutil.rmtree(target, ignore_errors=True)
                raise
            return {
                "status": "awaiting_approval",
                "reviewRoot": target.as_posix(),
                "reviewPackage": (target / "review-package").as_posix(),
                "assetId": persisted["assetId"],
                "idempotent": False,
            }
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
            if not target.exists():
                try:
                    pool.release_persisted(
                        delivery_set_id,
                        key,
                        revision,
                        ledger_file,
                        verdict="system_failure",
                        authority="system",
                        reason="review package generation failed before human review",
                    )
                except TestPoolError:
                    pass
            raise


def compile_reference(
    reference: Path,
    compiler: Callable[[Path], dict[str, dict[str, Any]]],
    pool: TestImagePool,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    if not reference.is_file():
        raise ReviewWorkflowError("reference_missing")
    compiled = compiler(reference)
    if not isinstance(compiled, dict) or not isinstance(compiled.get("template"), dict) or not isinstance(compiled.get("analysis"), dict):
        raise ReviewWorkflowError("compiler_output_invalid")
    interpretation = compiled.get("referenceInterpretation")
    if not isinstance(interpretation, dict):
        raise ReviewWorkflowError("reference_interpretation_required")
    return create_review_package(
        compiled["template"],
        compiled["analysis"],
        pool,
        generator,
        reference_interpretation=interpretation,
        **kwargs,
    )


def produce(
    repo_root: Path,
    proposer: Callable[[dict[str, Any], list[dict[str, Any]]], list[dict[str, Any]]],
    pool: TestImagePool,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    *,
    run_root: Path,
    delivery_set_id: str,
    ledger_file: Path,
    approval_file: Path | None = None,
    baseline_catalog_file: Path | None = None,
    cover_checker: Callable[[Path, dict[str, Any], int], dict[str, Any]] | None = None,
    experience_store: DurableExperienceStore | None = None,
) -> list[dict[str, Any]]:
    if experience_store is None:
        raise ReviewWorkflowError("experience_store_required")
    try:
        experience_snapshot = experience_store.load_fresh_snapshot()
    except ExperienceStoreError as error:
        raise ReviewWorkflowError(str(error)) from error
    if approval_file is not None:
        descriptor = read_json(approval_file)
        snapshot, errors = verify_approval_descriptor(descriptor, repo_root)
        if errors or snapshot is None:
            raise ReviewWorkflowError(errors[0] if errors else "baseline_not_approved")
        baseline_root = (repo_root / descriptor["businessRoot"]).resolve()
        templates = [read_json(baseline_root / item["path"]) for item in snapshot["entries"]]
    else:
        catalog_path = baseline_catalog_file or (
            Path(__file__).parents[1]
            / "references/dynamic-baseline.json"
        )
        try:
            snapshot, templates = DynamicBaselineCatalog(catalog_path).load_active()
        except DynamicBaselineError as error:
            raise ReviewWorkflowError(str(error)) from error
    candidates = proposer(snapshot, templates)
    if not isinstance(candidates, list):
        raise ReviewWorkflowError("proposer_output_invalid")
    used_keys = {item.get("key") for item in templates} | set(experience_snapshot["activeGoodcaseKeys"])
    used_titles = {item.get("title") for item in templates}
    used_prompts = {_prompt_sha256(item) for item in templates}
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        data = candidate.get("template") if isinstance(candidate, dict) else None
        if not isinstance(data, dict) or not isinstance(candidate.get("analysis"), dict):
            results.append({"status": "failed", "code": "candidate_invalid"})
            continue
        prompt_digest = _prompt_sha256(data)
        code = (
            "candidate_duplicate_key" if data.get("key") in used_keys
            else "candidate_duplicate_title" if data.get("title") in used_titles
            else "candidate_duplicate_mechanism" if prompt_digest in used_prompts
            else None
        )
        if code:
            results.append({"status": "failed", "code": code, "key": data.get("key")})
            continue
        used_keys.add(data.get("key"))
        used_titles.add(data.get("title"))
        used_prompts.add(prompt_digest)
        self_analysis = {
            "artifactType": "self_production_analysis",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": data.get("key"),
            "baselineDigest": snapshot["digest"],
            "novelty": {"key": "unique", "title": "unique", "promptMechanism": "unique", "category": "distinct"},
        }
        try:
            results.append(create_review_package(
                data,
                self_analysis,
                pool,
                generator,
                run_root=run_root,
                delivery_set_id=delivery_set_id,
                ledger_file=ledger_file,
                analysis_filename="self-production-analysis.json",
                extra_internal={"baseline-snapshot.json": snapshot},
                cover_checker=cover_checker,
            ))
        except (ReviewWorkflowError, TestPoolError) as error:
            results.append({"status": "failed", "code": str(error).split(":", 1)[0], "key": data.get("key")})
    return results


def record_review_decision(
    review_root: Path,
    verdict: str,
    reason: str,
    pool: TestImagePool,
    ledger_file: Path,
    *,
    experience_sink: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    baseline_sink: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    if verdict not in {"pass", "reject", "pending", "manual_release"}:
        raise ReviewWorkflowError("review_verdict_invalid")
    if not reason.strip():
        raise ReviewWorkflowError("review_reason_required")
    if verdict in {"pass", "reject"} and experience_sink is None:
        raise ReviewWorkflowError("experience_sink_required")
    if verdict == "pass" and baseline_sink is None:
        raise ReviewWorkflowError("dynamic_baseline_sink_required")
    review_root = review_root.resolve()
    errors, _ = validate_package(review_root, "review-package", "local", "", "")
    if errors:
        raise ReviewWorkflowError(f"review_package_validation_failed: {'; '.join(errors)}")
    assignment = read_json(review_root / "internal" / "test-image-assignment.json")
    template_data = read_json(review_root / "review-package" / "style-template.json")
    cover_sha = sha256_file(review_root / "review-package" / "cover.png")
    prompt_sha = _prompt_sha256(template_data)
    identity = (assignment["deliverySetId"], assignment["templateKey"], assignment["revision"])
    existing_receipt_file = review_root / "internal" / "approval-decision-receipt.json"
    if assignment.get("status") in {"consumed", "released"}:
        existing_receipt = read_json(existing_receipt_file) if existing_receipt_file.is_file() else {}
        if existing_receipt.get("verdict") == verdict:
            if verdict in {"pass", "reject"}:
                if experience_sink is None:
                    raise ReviewWorkflowError("experience_sink_required")
                _deposit_experience(review_root, existing_receipt, experience_sink)
            if verdict == "pass":
                if baseline_sink is None:
                    raise ReviewWorkflowError("dynamic_baseline_sink_required")
                _register_dynamic_baseline(review_root, existing_receipt, baseline_sink)
            return {
                "status": "approved" if verdict == "pass" else "released",
                "verdict": verdict,
                "reviewRoot": review_root.as_posix(),
                "assetId": assignment["assetId"],
                "nextPhase": "finalization" if verdict == "pass" else None,
                "idempotent": True,
            }
        raise ReviewWorkflowError("review_decision_terminal")
    lock_file = _identity_lock(review_root, ledger_file, *identity)
    with _lock(lock_file):
        decided_at = _now()
        if verdict == "pass":
            updated = pool.consume_persisted(
                *identity,
                ledger_file,
                cover_sha256=cover_sha,
                prompt_sha256=prompt_sha,
                reason=reason,
                decided_at=decided_at,
            )
        elif verdict in {"reject", "manual_release"}:
            updated = pool.release_persisted(
                *identity,
                ledger_file,
                verdict=verdict,
                authority="human",
                reason=reason,
                decided_at=decided_at,
                cover_sha256=cover_sha,
                prompt_sha256=prompt_sha,
            )
        else:
            pool.refresh_persisted(ledger_file)
            matches = [
                item for item in pool.assignments
                if (item["deliverySetId"], item["templateKey"], item["revision"]) == identity
            ]
            if not matches or matches[0].get("status") != "awaiting_approval":
                raise ReviewWorkflowError("pending_requires_awaiting_approval")
            updated = matches[0]
        temporary = Path(tempfile.mkdtemp(prefix=f".{review_root.name}-review-", dir=review_root.parent))
        try:
            shutil.copytree(review_root, temporary, dirs_exist_ok=True)
            receipt = {
                "artifactType": "approval_decision_receipt",
                "schemaVersion": "1.0.0",
                "producer": "style-template-analyzer",
                "deliverySetId": identity[0],
                "templateKey": identity[1],
                "revision": identity[2],
                "assetId": assignment["assetId"],
                "verdict": verdict,
                "authority": "human",
                "decidedAt": decided_at,
                "reason": reason,
                "coverSha256": cover_sha,
                "promptSha256": prompt_sha,
            }
            _write_json(temporary / "internal" / "test-image-assignment.json", updated)
            _write_json(temporary / "internal" / "approval-decision-receipt.json", receipt)
            _write_json(temporary / "artifact-manifest.json", build_manifest(
                temporary,
                "review-package",
                identity[2],
                schema_version="5.1.0",
            ))
            package_errors, _ = validate_package(temporary, "review-package", "local", "", "")
            if package_errors:
                raise ReviewWorkflowError(f"review_package_validation_failed: {'; '.join(package_errors)}")
            backup = review_root.with_name(f".{review_root.name}.previous")
            if backup.exists():
                shutil.rmtree(backup)
            os.replace(review_root, backup)
            try:
                os.replace(temporary, review_root)
            except Exception:
                os.replace(backup, review_root)
                raise
            shutil.rmtree(backup)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
    if verdict in {"pass", "reject"}:
        if experience_sink is None:
            raise ReviewWorkflowError("experience_sink_required")
        _deposit_experience(review_root, receipt, experience_sink)
    if verdict == "pass":
        if baseline_sink is None:
            raise ReviewWorkflowError("dynamic_baseline_sink_required")
        _register_dynamic_baseline(review_root, receipt, baseline_sink)
    return {
        "status": "approved" if verdict == "pass" else "released" if verdict in {"reject", "manual_release"} else "awaiting_approval",
        "verdict": verdict,
        "reviewRoot": review_root.as_posix(),
        "assetId": assignment["assetId"],
        "nextPhase": "finalization" if verdict == "pass" else None,
        "idempotent": False,
    }


def _deposit_experience(
    review_root: Path,
    decision: dict[str, Any],
    experience_sink: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> None:
    receipt_file = review_root / "internal" / "experience-deposit-receipt.json"
    if receipt_file.is_file():
        return
    event = {
        "casePool": "goodcase" if decision["verdict"] == "pass" else "badcase",
        "reviewRoot": review_root.as_posix(),
        "decision": decision,
    }
    try:
        sink_receipt = experience_sink(event)
    except Exception as error:
        raise ReviewWorkflowError(f"experience_deposit_failed: {error}") from error
    temporary = Path(tempfile.mkdtemp(prefix=f".{review_root.name}-experience-", dir=review_root.parent))
    try:
        shutil.copytree(review_root, temporary, dirs_exist_ok=True)
        _write_json(temporary / "internal" / "experience-deposit-receipt.json", {
            "artifactType": "experience_deposit_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": decision["templateKey"],
            "revision": decision["revision"],
            "casePool": event["casePool"],
            "depositedAt": _now(),
            "sinkReceipt": sink_receipt if isinstance(sink_receipt, dict) else {},
        })
        manifest = read_json(review_root / "artifact-manifest.json")
        _write_json(temporary / "artifact-manifest.json", build_manifest(
            temporary,
            "review-package",
            decision["revision"],
            schema_version=str(manifest["schemaVersion"]),
        ))
        package_errors, _ = validate_package(temporary, "review-package", "local", "", "")
        if package_errors:
            raise ReviewWorkflowError(f"review_package_validation_failed: {'; '.join(package_errors)}")
        backup = review_root.with_name(f".{review_root.name}.before-experience")
        if backup.exists():
            shutil.rmtree(backup)
        os.replace(review_root, backup)
        try:
            os.replace(temporary, review_root)
        except Exception:
            os.replace(backup, review_root)
            raise
        shutil.rmtree(backup)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _register_dynamic_baseline(
    review_root: Path,
    decision: dict[str, Any],
    baseline_sink: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> None:
    receipt_file = review_root / "internal" / "dynamic-baseline-registration-receipt.json"
    if receipt_file.is_file():
        return
    event = {"reviewRoot": review_root.as_posix(), "decision": decision}
    try:
        sink_receipt = baseline_sink(event)
    except Exception as error:
        raise ReviewWorkflowError(f"dynamic_baseline_registration_failed: {error}") from error
    if not isinstance(sink_receipt, dict):
        raise ReviewWorkflowError("dynamic_baseline_registration_failed: sink receipt missing")
    temporary = Path(tempfile.mkdtemp(prefix=f".{review_root.name}-baseline-", dir=review_root.parent))
    try:
        shutil.copytree(review_root, temporary, dirs_exist_ok=True)
        _write_json(temporary / "internal" / "dynamic-baseline-registration-receipt.json", {
            "artifactType": "dynamic_baseline_registration_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": decision["templateKey"],
            "revision": decision["revision"],
            "registeredAt": _now(),
            "catalog": str(sink_receipt.get("catalog", "")),
            "catalogDigest": str(sink_receipt.get("catalogDigest", "")),
            "activeRevision": sink_receipt.get("activeRevision"),
            "sinkReceipt": sink_receipt,
        })
        manifest = read_json(review_root / "artifact-manifest.json")
        _write_json(temporary / "artifact-manifest.json", build_manifest(
            temporary,
            "review-package",
            decision["revision"],
            schema_version=str(manifest["schemaVersion"]),
        ))
        package_errors, _ = validate_package(temporary, "review-package", "local", "", "")
        if package_errors:
            raise ReviewWorkflowError(f"review_package_validation_failed: {'; '.join(package_errors)}")
        backup = review_root.with_name(f".{review_root.name}.before-baseline")
        if backup.exists():
            shutil.rmtree(backup)
        os.replace(review_root, backup)
        try:
            os.replace(temporary, review_root)
        except Exception:
            os.replace(backup, review_root)
            raise
        shutil.rmtree(backup)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def finalize_approved(
    review_root: Path,
    run_root: Path,
    oss_adapter: Callable[[Path, Path], dict[str, Any]],
    *,
    assets_domain: str,
    key_prefix: str = "",
) -> dict[str, Any]:
    if not assets_domain or "://" in assets_domain:
        raise ReviewWorkflowError("assets_domain_required")
    review_root = review_root.resolve()
    errors, _ = validate_package(review_root, "review-package", "local", "", "")
    if errors:
        raise ReviewWorkflowError(f"review_package_validation_failed: {'; '.join(errors)}")
    assignment = read_json(review_root / "internal" / "test-image-assignment.json")
    approval = read_json(review_root / "internal" / "approval-decision-receipt.json")
    manifest = read_json(review_root / "artifact-manifest.json")
    if manifest.get("schemaVersion") in {"5.0.0", "5.1.0"} and not (review_root / "internal" / "experience-deposit-receipt.json").is_file():
        raise ReviewWorkflowError("experience_deposit_required")
    if manifest.get("schemaVersion") == "5.1.0" and not (review_root / "internal" / "dynamic-baseline-registration-receipt.json").is_file():
        raise ReviewWorkflowError("dynamic_baseline_registration_required")
    if assignment.get("status") != "consumed" or approval.get("verdict") != "pass":
        raise ReviewWorkflowError("human_approval_required")
    cover_sha = sha256_file(review_root / "review-package" / "cover.png")
    prompt_sha = _prompt_sha256(read_json(review_root / "review-package" / "style-template.json"))
    decision = assignment.get("decision") if isinstance(assignment.get("decision"), dict) else {}
    if (
        approval.get("coverSha256") != cover_sha
        or approval.get("promptSha256") != prompt_sha
        or decision.get("coverSha256") != cover_sha
        or decision.get("promptSha256") != prompt_sha
    ):
        raise ReviewWorkflowError("approval_evidence_mismatch")
    key = assignment["templateKey"]
    revision = assignment["revision"]
    final_root = _final_root(run_root, key, revision)
    if final_root.is_dir():
        final_errors, _ = validate_package(final_root, "final-package", "remote", assets_domain.lower(), key_prefix)
        if final_errors:
            raise ReviewWorkflowError(f"final_package_validation_failed: {'; '.join(final_errors)}")
        return {
            "status": "completed",
            "revisionRoot": final_root.as_posix(),
            "package": (final_root / "package").as_posix(),
            "assetId": assignment["assetId"],
            "idempotent": True,
        }
    final_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{revision}-final-", dir=final_root.parent))
    try:
        shutil.copytree(review_root / "internal", temporary / "internal")
        public = review_root / "review-package"
        output = temporary / ".oss-finalized-template.json"
        try:
            provider = oss_adapter(public, output)
        except Exception as error:
            raise ReviewWorkflowError(f"oss_finalization_failed: {error}") from error
        if not output.is_file():
            raise ReviewWorkflowError("oss_finalization_failed: output_missing")
        final_data = read_json(output)
        if not isinstance(final_data, dict) or final_data.get("key") != key:
            raise ReviewWorkflowError("oss_finalization_failed: template_key_mismatch")
        template_errors = validate_template(final_data, output, "remote", assets_domain.lower(), key_prefix)
        if template_errors:
            raise ReviewWorkflowError(f"oss_finalization_failed: {'; '.join(template_errors)}")
        package = temporary / "package"
        package.mkdir()
        _write_json(package / "style-template.json", final_data)
        shutil.copy2(public / "cover.png", package / "cover.png")
        _write_json(temporary / "internal" / "oss-finalization-receipt.json", {
            "artifactType": "oss_finalization_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": key,
            "revision": revision,
            "assetsDomain": assets_domain.lower(),
            "remoteCoverUrl": final_data["cover"],
            "provider": provider if isinstance(provider, dict) else {},
        })
        output.unlink()
        _write_json(temporary / "artifact-manifest.json", build_manifest(
            temporary,
            "final-package",
            revision,
            schema_version="5.1.0",
        ))
        final_errors, _ = validate_package(temporary, "final-package", "remote", assets_domain.lower(), key_prefix)
        if final_errors:
            raise ReviewWorkflowError(f"final_package_validation_failed: {'; '.join(final_errors)}")
        os.replace(temporary, final_root)
        return {
            "status": "completed",
            "revisionRoot": final_root.as_posix(),
            "package": (final_root / "package").as_posix(),
            "assetId": assignment["assetId"],
            "idempotent": False,
        }
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def route_workflow(intent: str, phase: str, **kwargs: Any) -> Any:
    """Route the two business intents through the shared three-phase lifecycle."""
    if phase == "review-package":
        if intent == "compile-reference":
            return compile_reference(**kwargs)
        if intent == "self-produce":
            return produce(**kwargs)
        raise ReviewWorkflowError("intent_unsupported")
    if phase == "review-decision":
        finalize_kwargs = kwargs.pop("finalize_on_pass", None)
        result = record_review_decision(**kwargs)
        if result["verdict"] == "pass" and isinstance(finalize_kwargs, dict):
            result["finalization"] = finalize_approved(
                review_root=Path(result["reviewRoot"]),
                **finalize_kwargs,
            )
        return result
    if phase == "finalize":
        return finalize_approved(**kwargs)
    raise ReviewWorkflowError("phase_unsupported")
