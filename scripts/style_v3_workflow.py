#!/usr/bin/env python3
"""V3 orchestration: compile, produce, and explicit post-package stages."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from difflib import SequenceMatcher
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from style_baseline import validate_baseline_snapshot, verify_approval_descriptor
from style_contracts import build_manifest, read_json
from style_test_pool import TestImagePool, TestPoolError
from validate_style_package import validate_package
from validate_style_analysis import validate_data as validate_analysis
from validate_style_evaluation import validate_data as validate_evaluation
from validate_style_template import validate_data as validate_template


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class WorkflowError(RuntimeError):
    """Machine-readable workflow failure."""


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _publish_revision(source: Path, target: Path) -> None:
    os.replace(source, target)


@contextmanager
def _exclusive_file_lock(path: Path):
    """Serialize one filesystem identity across processes."""
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def _paths_overlap(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left in right.parents or right in left.parents


def _relocate_staging_paths(value: Any, staging: Path, published: Path) -> Any:
    if isinstance(value, dict):
        return {key: _relocate_staging_paths(item, staging, published) for key, item in value.items()}
    if isinstance(value, list):
        return [_relocate_staging_paths(item, staging, published) for item in value]
    if isinstance(value, str):
        staging_text = staging.as_posix()
        if value == staging_text or value.startswith(staging_text + "/"):
            return published.as_posix() + value[len(staging_text):]
    return value


def _prompt_signature(prompt: str) -> str:
    normalized = "".join(prompt.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _mechanism_text(data: dict[str, Any]) -> str:
    prompt = "".join(str(data.get("promptTemplate", "")).split())
    start = prompt.find("将全部目标画面")
    if start < 0:
        start = prompt.find("把用户上传图")
    end = prompt.find("只生成用户内容")
    if start >= 0 and end > start:
        return prompt[start:end]
    return prompt


def _category_tokens(data: dict[str, Any]) -> set[str]:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []
    if tags:
        return {str(tag).strip().lower() for tag in tags if str(tag).strip()}
    description = "".join(str(data.get("description", "")).lower().split())
    return {description[index:index + 2] for index in range(max(0, len(description) - 1))}


def _is_near_candidate(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    mechanism_similarity = SequenceMatcher(None, _mechanism_text(candidate), _mechanism_text(existing)).ratio()
    left = _category_tokens(candidate)
    right = _category_tokens(existing)
    category_similarity = len(left & right) / len(left | right) if left and right else 0.0
    return mechanism_similarity >= 0.82 or category_similarity >= 0.9


def _validate_template_payload(data: dict[str, Any], path: Path) -> list[str]:
    cover = data.get("cover")
    parsed = urlparse(cover) if isinstance(cover, str) else None
    if parsed and parsed.scheme:
        marker = "/style/templates/"
        prefix = parsed.path.split(marker, 1)[0].strip("/") if marker in parsed.path else ""
        return validate_template(data, path, "either", parsed.hostname or "", prefix)
    return validate_template(data, path, "local", "", "")


def _preflight(template_data: dict[str, Any], analysis_data: dict[str, Any], analysis_filename: str) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        candidate = json.loads(json.dumps(template_data, ensure_ascii=False))
        candidate["cover"] = "cover.png"
        (root / "cover.png").write_bytes(PNG_SIGNATURE)
        template_errors = validate_template(candidate, root / "style-template.json", "local", "", "")
    if template_errors:
        raise WorkflowError(f"package_validation_failed: {'; '.join(template_errors)}")
    if analysis_filename == "style-analysis.json":
        analysis_errors = validate_analysis(analysis_data)
        if analysis_errors:
            raise WorkflowError(f"package_validation_failed: {'; '.join(analysis_errors)}")


def _existing_revision(
    revision_root: Path,
    pool: TestImagePool,
    delivery_set_id: str,
    template_key: str,
    revision: int,
    ledger_file: Path | None,
) -> dict[str, Any] | None:
    if not revision_root.is_dir():
        return None
    errors, _ = validate_package(revision_root, "fast-package", "local", "", "")
    if errors:
        raise WorkflowError(f"package_validation_failed: {'; '.join(errors)}")
    assignment_file = revision_root / "internal" / "test-image-assignment.json"
    assignment = read_json(assignment_file)
    expected = (delivery_set_id, template_key, revision)
    actual = (assignment.get("deliverySetId"), assignment.get("templateKey"), assignment.get("revision"))
    if actual != expected or assignment.get("status") != "committed":
        raise WorkflowError("package_validation_failed: assignment identity mismatch")
    if ledger_file is not None:
        try:
            pool.reconcile_persisted(assignment, ledger_file)
        except TestPoolError as error:
            raise WorkflowError(str(error)) from error
        return {"status": "completed", "revisionRoot": revision_root.as_posix(), "idempotent": True}
    existing = [
        item for item in pool.assignments
        if (item["deliverySetId"], item["templateKey"], item["revision"]) == expected
    ]
    if existing and existing[0]["assetId"] != assignment.get("assetId"):
        raise WorkflowError("test_asset_already_assigned")
    occupied = any(
        item["deliverySetId"] == delivery_set_id
        and item["assetId"] == assignment.get("assetId")
        and (item["templateKey"], item["revision"]) != (template_key, revision)
        for item in pool.assignments
    )
    if occupied:
        raise WorkflowError("test_asset_already_assigned")
    if not existing:
        pool.assignments.append(dict(assignment))
    return {"status": "completed", "revisionRoot": revision_root.as_posix(), "idempotent": True}


def _deliver_fast_package_locked(
    template_data: dict[str, Any],
    analysis_data: dict[str, Any],
    pool: TestImagePool,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    *,
    run_root: Path,
    delivery_set_id: str,
    revision: int,
    analysis_filename: str,
    extra_internal: dict[str, object] | None = None,
    ledger_file: Path | None = None,
) -> dict[str, Any]:
    key = template_data.get("key")
    if not isinstance(key, str):
        raise WorkflowError("package_validation_failed: template key missing")
    revision_root = run_root.resolve() / key / str(revision)
    _preflight(template_data, analysis_data, analysis_filename)
    existing = _existing_revision(revision_root, pool, delivery_set_id, key, revision, ledger_file)
    if existing:
        return existing
    revision_root.parent.mkdir(parents=True, exist_ok=True)
    try:
        assignment = (
            pool.reserve_persisted(delivery_set_id, key, revision, ledger_file, legacy=True)
            if ledger_file is not None
            else pool.reserve(delivery_set_id, key, revision, legacy=True)
        )
    except TestPoolError as error:
        raise WorkflowError(str(error)) from error
    temporary = Path(tempfile.mkdtemp(prefix=f".{revision}-", dir=revision_root.parent))
    try:
        package = temporary / "package"
        internal = temporary / "internal"
        package.mkdir()
        internal.mkdir()
        output_template = json.loads(json.dumps(template_data, ensure_ascii=False))
        output_template["cover"] = "cover.png"
        _write_json(package / "style-template.json", output_template)
        _write_json(internal / analysis_filename, analysis_data)
        _write_json(internal / "test-image-assignment.json", assignment)
        for filename, value in (extra_internal or {}).items():
            _write_json(internal / filename, value)
        asset = pool.asset(assignment["assetId"])
        try:
            provider_receipt = generator(asset, output_template, package / "cover.png")
        except Exception as error:
            raise WorkflowError(f"cover_generation_failed: {error}") from error
        cover = package / "cover.png"
        try:
            with Image.open(cover) as generated:
                generated.verify()
                if generated.format != "PNG":
                    raise ValueError("format is not PNG")
        except (OSError, ValueError) as error:
            raise WorkflowError(f"cover_generation_failed: invalid PNG: {error}") from error
        if not isinstance(provider_receipt, dict) or provider_receipt.get("sourceAssetId") != assignment["assetId"]:
            raise WorkflowError("cover_generation_failed: provider sourceAssetId mismatch")
        receipt = {
            "artifactType": "cover_generation_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": key,
            "revision": revision,
            "assetId": assignment["assetId"],
            "provider": provider_receipt,
        }
        _write_json(internal / "cover-generation-receipt.json", receipt)
        committed_assignment = dict(assignment, status="committed")
        _write_json(internal / "test-image-assignment.json", committed_assignment)
        manifest = build_manifest(temporary, "package", revision, schema_version="2.0.0")
        _write_json(temporary / "artifact-manifest.json", manifest)
        errors, _ = validate_package(temporary, "fast-package", "local", "", "")
        if errors:
            raise WorkflowError(f"package_validation_failed: {'; '.join(errors)}")
        if ledger_file is not None:
            pool.mark_publishing_persisted(delivery_set_id, key, revision, ledger_file)
        _publish_revision(temporary, revision_root)
        try:
            assignment = (
                pool.commit_persisted(delivery_set_id, key, revision, ledger_file)
                if ledger_file is not None
                else pool.commit(delivery_set_id, key, revision)
            )
        except Exception:
            shutil.rmtree(revision_root, ignore_errors=True)
            raise
        return {
            "status": "completed",
            "revisionRoot": revision_root.as_posix(),
            "package": (revision_root / "package").as_posix(),
            "assetId": assignment["assetId"],
            "idempotent": False,
        }
    except Exception:
        if ledger_file is not None:
            pool.release_persisted(delivery_set_id, key, revision, ledger_file)
        else:
            pool.release(delivery_set_id, key, revision)
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _deliver_fast_package(
    template_data: dict[str, Any],
    analysis_data: dict[str, Any],
    pool: TestImagePool,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    *,
    run_root: Path,
    delivery_set_id: str,
    revision: int,
    analysis_filename: str,
    extra_internal: dict[str, object] | None = None,
    ledger_file: Path | None = None,
) -> dict[str, Any]:
    key = template_data.get("key")
    if not isinstance(key, str):
        raise WorkflowError("package_validation_failed: template key missing")
    identity = hashlib.sha256(
        f"{run_root.resolve()}\0{delivery_set_id}\0{key}\0{revision}".encode("utf-8")
    ).hexdigest()
    lock_file = (ledger_file.parent if ledger_file is not None else run_root.resolve()) / ".style-transaction-locks" / f"{identity}.lock"
    with _exclusive_file_lock(lock_file):
        return _deliver_fast_package_locked(
            template_data,
            analysis_data,
            pool,
            generator,
            run_root=run_root,
            delivery_set_id=delivery_set_id,
            revision=revision,
            analysis_filename=analysis_filename,
            extra_internal=extra_internal,
            ledger_file=ledger_file,
        )


def _verify_png(cover: Path) -> None:
    try:
        with Image.open(cover) as generated:
            generated.verify()
            if generated.format != "PNG":
                raise ValueError("format is not PNG")
    except (OSError, ValueError) as error:
        raise WorkflowError(f"cover_generation_failed: invalid PNG: {error}") from error


def _run_cover_generation(
    asset: dict[str, Any],
    output_template: dict[str, Any],
    cover: Path,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    checker: Callable[[Path, dict[str, Any], int], dict[str, Any]] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    provider_receipt: dict[str, Any] | None = None
    for attempt in (1, 2):
        try:
            provider_receipt = generator(asset, output_template, cover)
        except Exception as error:
            raise WorkflowError(f"cover_generation_failed: {error}") from error
        _verify_png(cover)
        if not isinstance(provider_receipt, dict) or provider_receipt.get("sourceAssetId") != asset.get("assetId"):
            raise WorkflowError("cover_generation_failed: provider sourceAssetId mismatch")
        decision = checker(cover, output_template, attempt) if checker is not None else {"verdict": "pass", "reasons": []}
        if not isinstance(decision, dict) or decision.get("verdict") not in {"pass", "retry"}:
            raise WorkflowError("cover_check_invalid")
        reasons = decision.get("reasons", [])
        if not isinstance(reasons, list) or any(not isinstance(reason, str) or not reason for reason in reasons):
            raise WorkflowError("cover_check_invalid")
        verdict = str(decision["verdict"])
        attempts.append({"attempt": attempt, "verdict": verdict, "reasons": reasons})
        if verdict == "pass":
            return provider_receipt, attempts
    raise WorkflowError("cover_check_failed")


def _reconcile_v4_assignment(
    revision_root: Path,
    pool: TestImagePool,
    delivery_set_id: str,
    template_key: str,
    revision: int,
    ledger_file: Path | None,
) -> dict[str, Any]:
    assignment = read_json(revision_root / "internal" / "test-image-assignment.json")
    expected = (delivery_set_id, template_key, revision)
    actual = (assignment.get("deliverySetId"), assignment.get("templateKey"), assignment.get("revision"))
    if actual != expected or assignment.get("status") != "committed":
        raise WorkflowError("package_validation_failed: assignment identity mismatch")
    if ledger_file is not None:
        try:
            pool.reconcile_persisted(assignment, ledger_file)
        except TestPoolError as error:
            raise WorkflowError(str(error)) from error
    return assignment


def _finalize_oss_in_staging(
    staging: Path,
    key: str,
    revision: int,
    oss_adapter: Callable[[Path, Path], dict[str, Any]],
    assets_domain: str,
    key_prefix: str,
) -> dict[str, Any]:
    prepublish = staging / "prepublish"
    output = staging / ".oss-finalized-template.json"
    try:
        provider_receipt = oss_adapter(prepublish, output)
    except Exception as error:
        raise WorkflowError(f"oss_finalization_failed: {error}") from error
    if not output.is_file():
        raise WorkflowError("oss_finalization_failed: output_missing")
    final_data = read_json(output)
    if not isinstance(final_data, dict) or final_data.get("key") != key:
        raise WorkflowError("oss_finalization_failed: template_key_mismatch")
    template_errors = validate_template(final_data, output, "remote", assets_domain.lower(), key_prefix)
    if template_errors:
        raise WorkflowError(f"oss_finalization_failed: {'; '.join(template_errors)}")
    remote_cover = final_data.get("cover")
    if not isinstance(remote_cover, str):
        raise WorkflowError("oss_finalization_failed: remote_cover_missing")
    package = staging / "package"
    package.mkdir()
    _write_json(package / "style-template.json", final_data)
    shutil.copy2(prepublish / "cover.png", package / "cover.png")
    receipt = {
        "artifactType": "oss_finalization_receipt",
        "schemaVersion": "1.0.0",
        "producer": "style-template-analyzer",
        "templateKey": key,
        "revision": revision,
        "assetsDomain": assets_domain.lower(),
        "remoteCoverUrl": remote_cover,
        "provider": provider_receipt if isinstance(provider_receipt, dict) else {},
    }
    _write_json(staging / "internal" / "oss-finalization-receipt.json", receipt)
    shutil.rmtree(prepublish)
    output.unlink(missing_ok=True)
    manifest = build_manifest(staging, "final-package", revision, schema_version="3.0.0")
    _write_json(staging / "artifact-manifest.json", manifest)
    errors, _ = validate_package(staging, "final-package", "remote", assets_domain.lower(), key_prefix)
    if errors:
        raise WorkflowError(f"package_validation_failed: {'; '.join(errors)}")
    return receipt


def _deliver_v4_locked(
    template_data: dict[str, Any],
    analysis_data: dict[str, Any],
    pool: TestImagePool,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    *,
    run_root: Path,
    delivery_set_id: str,
    revision: int,
    analysis_filename: str,
    oss_adapter: Callable[[Path, Path], dict[str, Any]] | None,
    assets_domain: str,
    key_prefix: str,
    preview: bool,
    cover_checker: Callable[[Path, dict[str, Any], int], dict[str, Any]] | None,
    extra_internal: dict[str, object] | None,
    ledger_file: Path | None,
) -> dict[str, Any]:
    key = template_data.get("key")
    if not isinstance(key, str):
        raise WorkflowError("package_validation_failed: template key missing")
    if not preview and (oss_adapter is None or not assets_domain):
        raise WorkflowError("oss_adapter_required")
    run_root = run_root.resolve()
    revision_root = run_root / key / str(revision)
    preview_root = run_root / ".prepublish" / key / str(revision)
    _preflight(template_data, analysis_data, analysis_filename)

    if revision_root.is_dir():
        errors, _ = validate_package(revision_root, "final-package", "remote", assets_domain.lower(), key_prefix)
        if errors:
            raise WorkflowError(f"package_validation_failed: {'; '.join(errors)}")
        assignment = _reconcile_v4_assignment(revision_root, pool, delivery_set_id, key, revision, ledger_file)
        return {
            "status": "completed",
            "revisionRoot": revision_root.as_posix(),
            "package": (revision_root / "package").as_posix(),
            "assetId": assignment["assetId"],
            "idempotent": True,
        }

    if preview_root.is_dir():
        errors, _ = validate_package(preview_root, "prepublish", "local", "", "")
        if errors:
            raise WorkflowError(f"prepublish_validation_failed: {'; '.join(errors)}")
        assignment = _reconcile_v4_assignment(preview_root, pool, delivery_set_id, key, revision, ledger_file)
        if preview:
            return {
                "status": "awaiting_oss",
                "prepublishRoot": preview_root.as_posix(),
                "assetId": assignment["assetId"],
                "idempotent": True,
            }
        revision_root.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{revision}-", dir=revision_root.parent))
        try:
            shutil.copytree(preview_root, temporary, dirs_exist_ok=True)
            _finalize_oss_in_staging(temporary, key, revision, oss_adapter, assets_domain, key_prefix)
            _publish_revision(temporary, revision_root)
            return {
                "status": "completed",
                "revisionRoot": revision_root.as_posix(),
                "package": (revision_root / "package").as_posix(),
                "assetId": assignment["assetId"],
                "idempotent": False,
            }
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    target = preview_root if preview else revision_root
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        assignment = (
            pool.reserve_persisted(delivery_set_id, key, revision, ledger_file, legacy=True)
            if ledger_file is not None
            else pool.reserve(delivery_set_id, key, revision, legacy=True)
        )
    except TestPoolError as error:
        raise WorkflowError(str(error)) from error
    temporary = Path(tempfile.mkdtemp(prefix=f".{revision}-", dir=target.parent))
    try:
        prepublish = temporary / "prepublish"
        internal = temporary / "internal"
        prepublish.mkdir()
        internal.mkdir()
        output_template = json.loads(json.dumps(template_data, ensure_ascii=False))
        output_template["cover"] = "cover.png"
        _write_json(prepublish / "style-template.json", output_template)
        _write_json(internal / analysis_filename, analysis_data)
        _write_json(internal / "test-image-assignment.json", assignment)
        for filename, value in (extra_internal or {}).items():
            _write_json(internal / filename, value)
        asset = pool.asset(assignment["assetId"])
        provider_receipt, check_attempts = _run_cover_generation(
            asset, output_template, prepublish / "cover.png", generator, cover_checker
        )
        generation_receipt = {
            "artifactType": "cover_generation_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": key,
            "revision": revision,
            "assetId": assignment["assetId"],
            "provider": provider_receipt,
        }
        _write_json(internal / "cover-generation-receipt.json", generation_receipt)
        _write_json(internal / "cover-check-receipt.json", {
            "artifactType": "cover_check_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": key,
            "revision": revision,
            "verdict": "pass",
            "attempts": check_attempts,
        })
        _write_json(internal / "test-image-assignment.json", dict(assignment, status="committed"))
        if preview:
            manifest = build_manifest(temporary, "prepublish", revision, schema_version="3.0.0")
            _write_json(temporary / "artifact-manifest.json", manifest)
            errors, _ = validate_package(temporary, "prepublish", "local", "", "")
            if errors:
                raise WorkflowError(f"prepublish_validation_failed: {'; '.join(errors)}")
        else:
            _finalize_oss_in_staging(temporary, key, revision, oss_adapter, assets_domain, key_prefix)
        if ledger_file is not None:
            pool.mark_publishing_persisted(delivery_set_id, key, revision, ledger_file)
        _publish_revision(temporary, target)
        try:
            committed = (
                pool.commit_persisted(delivery_set_id, key, revision, ledger_file)
                if ledger_file is not None
                else pool.commit(delivery_set_id, key, revision)
            )
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        if preview:
            return {
                "status": "awaiting_oss",
                "prepublishRoot": target.as_posix(),
                "assetId": committed["assetId"],
                "idempotent": False,
            }
        return {
            "status": "completed",
            "revisionRoot": target.as_posix(),
            "package": (target / "package").as_posix(),
            "assetId": committed["assetId"],
            "idempotent": False,
        }
    except Exception:
        if ledger_file is not None:
            pool.release_persisted(delivery_set_id, key, revision, ledger_file)
        else:
            pool.release(delivery_set_id, key, revision)
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _deliver_v4(
    template_data: dict[str, Any],
    analysis_data: dict[str, Any],
    pool: TestImagePool,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    key = template_data.get("key")
    if not isinstance(key, str):
        raise WorkflowError("package_validation_failed: template key missing")
    run_root = Path(kwargs["run_root"])
    ledger_file = kwargs.get("ledger_file")
    identity = hashlib.sha256(
        f"{run_root.resolve()}\0{kwargs['delivery_set_id']}\0{key}\0{kwargs['revision']}".encode("utf-8")
    ).hexdigest()
    lock_file = (ledger_file.parent if ledger_file is not None else run_root.resolve()) / ".style-transaction-locks" / f"{identity}.lock"
    with _exclusive_file_lock(lock_file):
        return _deliver_v4_locked(template_data, analysis_data, pool, generator, **kwargs)


def compile_reference(
    reference: Path,
    template_data: dict[str, Any],
    analysis_data: dict[str, Any],
    pool: TestImagePool,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    *,
    run_root: Path,
    delivery_set_id: str,
    revision: int = 1,
    ledger_file: Path | None = None,
) -> dict[str, Any]:
    if not reference.is_file():
        raise WorkflowError("reference_missing")
    if ledger_file is not None:
        pool.refresh_persisted(ledger_file)
    if pool.capacity(delivery_set_id) < 1 and not any(
        (item["deliverySetId"], item["templateKey"], item["revision"])
        == (delivery_set_id, template_data.get("key"), revision)
        for item in pool.assignments
    ):
        raise WorkflowError("test_pool_insufficient")
    return _deliver_fast_package(
        template_data, analysis_data, pool, generator,
        run_root=run_root, delivery_set_id=delivery_set_id, revision=revision,
        analysis_filename="style-analysis.json",
        ledger_file=ledger_file,
    )


def produce_from_baseline(
    snapshot: dict[str, Any],
    baseline_root: Path,
    candidates: list[dict[str, Any]],
    pool: TestImagePool,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    *,
    run_root: Path,
    delivery_set_id: str,
    ledger_file: Path | None = None,
    oss_adapter: Callable[[Path, Path], dict[str, Any]] | None = None,
    assets_domain: str = "",
    key_prefix: str = "",
    preview: bool = False,
    cover_checker: Callable[[Path, dict[str, Any], int], dict[str, Any]] | None = None,
    v4: bool = False,
) -> list[dict[str, Any]]:
    errors = validate_baseline_snapshot(snapshot, baseline_root)
    if errors:
        raise WorkflowError(errors[0])
    if ledger_file is not None:
        pool.refresh_persisted(ledger_file)
    baseline_templates = [read_json(baseline_root / item["path"]) for item in snapshot["entries"]]
    keys = {item["key"] for item in baseline_templates}
    titles = {item["title"] for item in baseline_templates}
    signatures = {_prompt_signature(item["promptTemplate"]) for item in baseline_templates}
    novelty_corpus = list(baseline_templates)
    results: list[dict[str, Any] | None] = []
    eligible: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for candidate in candidates:
        data = candidate.get("template", {})
        evidence = candidate.get("analysis", {})
        code = None
        if data.get("key") in keys:
            code = "candidate_duplicate_key"
        elif data.get("title") in titles:
            code = "candidate_duplicate_title"
        elif _prompt_signature(str(data.get("promptTemplate", ""))) in signatures:
            code = "candidate_duplicate_mechanism"
        elif any(_is_near_candidate(data, existing) for existing in novelty_corpus):
            code = "candidate_near_duplicate"
        if code:
            results.append({"status": "failed", "code": code, "key": data.get("key")})
        else:
            index = len(results)
            results.append(None)
            eligible.append((index, data, evidence))
            keys.add(data.get("key"))
            titles.add(data.get("title"))
            signatures.add(_prompt_signature(str(data.get("promptTemplate", ""))))
            novelty_corpus.append(data)
    required_new_assignments = sum(
        not (run_root.resolve() / str(data.get("key")) / "1").is_dir()
        and not (
            v4
            and (run_root.resolve() / ".prepublish" / str(data.get("key")) / "1").is_dir()
        )
        for _, data, _ in eligible
    )
    if pool.capacity(delivery_set_id) < required_new_assignments:
        for index, data, _ in eligible:
            results[index] = {"status": "failed", "code": "test_pool_insufficient", "key": data.get("key")}
        return [item for item in results if item is not None]
    baseline_evidence = snapshot
    for index, data, evidence in eligible:
        self_analysis = {
            "artifactType": "self_production_analysis",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": data.get("key"),
            "baselineDigest": snapshot["digest"],
            "novelty": {
                "key": "unique",
                "title": "unique",
                "promptMechanism": "unique",
                "category": "distinct",
            },
        }
        try:
            if v4:
                results[index] = _deliver_v4(
                    data, self_analysis, pool, generator,
                    run_root=run_root, delivery_set_id=delivery_set_id, revision=1,
                    analysis_filename="self-production-analysis.json",
                    oss_adapter=oss_adapter, assets_domain=assets_domain, key_prefix=key_prefix,
                    preview=preview, cover_checker=cover_checker,
                    extra_internal={"baseline-snapshot.json": baseline_evidence},
                    ledger_file=ledger_file,
                )
            else:
                results[index] = _deliver_fast_package(
                    data, self_analysis, pool, generator,
                    run_root=run_root, delivery_set_id=delivery_set_id, revision=1,
                    analysis_filename="self-production-analysis.json",
                    extra_internal={"baseline-snapshot.json": baseline_evidence},
                    ledger_file=ledger_file,
                )
        except (WorkflowError, TestPoolError) as error:
            results[index] = {"status": "failed", "code": str(error).split(":", 1)[0], "key": data.get("key")}
    return [item for item in results if item is not None]


def compile(
    reference: Path,
    compiler: Callable[[Path], dict[str, dict[str, Any]]],
    pool: TestImagePool,
    generator: Callable[[dict[str, Any], dict[str, Any], Path], dict[str, Any]],
    *,
    run_root: Path,
    delivery_set_id: str,
    ledger_file: Path,
    revision: int = 1,
    oss_adapter: Callable[[Path, Path], dict[str, Any]] | None = None,
    assets_domain: str = "",
    key_prefix: str = "",
    preview: bool = False,
    cover_checker: Callable[[Path, dict[str, Any], int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    compiled = compiler(reference)
    if not isinstance(compiled, dict) or not isinstance(compiled.get("template"), dict) or not isinstance(compiled.get("analysis"), dict):
        raise WorkflowError("compiler_output_invalid")
    pool.refresh_persisted(ledger_file)
    if pool.capacity(delivery_set_id) < 1 and not any(
        (item["deliverySetId"], item["templateKey"], item["revision"])
        == (delivery_set_id, compiled["template"].get("key"), revision)
        for item in pool.assignments
    ):
        raise WorkflowError("test_pool_insufficient")
    return _deliver_v4(
        compiled["template"], compiled["analysis"], pool, generator,
        run_root=run_root, delivery_set_id=delivery_set_id, revision=revision,
        analysis_filename="style-analysis.json", oss_adapter=oss_adapter,
        assets_domain=assets_domain, key_prefix=key_prefix, preview=preview,
        cover_checker=cover_checker, extra_internal=None, ledger_file=ledger_file,
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
    oss_adapter: Callable[[Path, Path], dict[str, Any]] | None = None,
    assets_domain: str = "",
    key_prefix: str = "",
    preview: bool = False,
    cover_checker: Callable[[Path, dict[str, Any], int], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    approval_path = approval_file or (Path(__file__).parents[1] / "references" / "approved-baseline.json")
    approval_descriptor = read_json(approval_path)
    snapshot, errors = verify_approval_descriptor(approval_descriptor, repo_root)
    if errors or snapshot is None:
        raise WorkflowError(errors[0] if errors else "baseline_not_approved")
    baseline_root = (repo_root / approval_descriptor["businessRoot"]).resolve()
    templates = [read_json(baseline_root / item["path"]) for item in snapshot["entries"]]
    candidates = proposer(snapshot, templates)
    if not isinstance(candidates, list):
        raise WorkflowError("proposer_output_invalid")
    return produce_from_baseline(
        snapshot, baseline_root, candidates, pool, generator,
        run_root=run_root, delivery_set_id=delivery_set_id, ledger_file=ledger_file,
        oss_adapter=oss_adapter, assets_domain=assets_domain, key_prefix=key_prefix,
        preview=preview, cover_checker=cover_checker, v4=True,
    )


def advance_package(
    package: Path,
    stage: str,
    adapter: Callable[[Path, Path], dict[str, Any]],
    output_root: Path,
    *,
    assets_domain: str = "",
    key_prefix: str = "",
) -> dict[str, Any]:
    if stage not in {"evaluation", "oss-handoff"}:
        raise WorkflowError("stage_unsupported")
    revision_root = package.parent if package.name == "package" else package
    package = revision_root / "package" if (revision_root / "package").is_dir() else package
    output_root = output_root.resolve()
    if _paths_overlap(output_root, revision_root) or _paths_overlap(output_root, package):
        raise WorkflowError("advance_output_overlaps_source")
    if output_root.exists():
        raise WorkflowError("output_conflict")
    source_manifest_data = read_json(revision_root / "artifact-manifest.json")
    final_source = source_manifest_data.get("schemaVersion") == "3.0.0" and source_manifest_data.get("stage") == "final-package"
    if final_source and stage == "oss-handoff":
        raise WorkflowError("stage_already_completed")
    if final_source and not assets_domain:
        raise WorkflowError("assets_domain_required")
    source_errors, _ = validate_package(
        revision_root,
        "final-package" if final_source else "fast-package",
        "remote" if final_source else "local",
        assets_domain.lower() if final_source else "",
        key_prefix if final_source else "",
    )
    if source_errors:
        raise WorkflowError(f"package_validation_failed: {'; '.join(source_errors)}")
    template_file = package / "style-template.json"
    cover = package / "cover.png"
    if not template_file.is_file() or not cover.is_file():
        raise WorkflowError("package_validation_failed")
    data = read_json(template_file)
    errors = validate_template(
        data,
        template_file,
        "remote" if final_source else "local",
        assets_domain.lower() if final_source else "",
        key_prefix if final_source else "",
    )
    if errors:
        raise WorkflowError(f"package_validation_failed: {'; '.join(errors)}")
    filename = "style-evaluation.json" if stage == "evaluation" else f"{data['key']}.json"
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
    try:
        output = temporary / filename
        receipt = adapter(package, output)
        if not output.is_file():
            raise WorkflowError("advance_output_missing")
        shutil.copy2(template_file, temporary / "style-template.json")
        shutil.copy2(cover, temporary / "cover.png")
        payload = read_json(output)
        if stage == "evaluation":
            output_errors = validate_evaluation(payload, output)
        else:
            if not assets_domain:
                output_errors = ["oss-handoff 必须声明受控 assets_domain"]
            else:
                output_errors = validate_template(payload, output, "remote", assets_domain.lower(), key_prefix)
            if isinstance(payload, dict) and payload.get("key") != data.get("key"):
                output_errors.append("oss-handoff key 与源模板不一致")
        if output_errors:
            raise WorkflowError(f"advance_validation_failed: {'; '.join(output_errors)}")
        source_manifest = revision_root / "artifact-manifest.json"
        source_receipt = {
            "artifactType": "source_package_receipt",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "templateKey": data["key"],
            "revision": source_manifest_data["revision"],
            "sourcePackagePath": package.resolve().as_posix(),
            "sourceManifestSha256": hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
        }
        _write_json(temporary / "source-package-receipt.json", source_receipt)
        manifest = build_manifest(
            temporary,
            stage,
            revision=source_manifest_data["revision"],
            schema_version="2.0.0",
        )
        _write_json(temporary / "artifact-manifest.json", manifest)
        stage_errors, _ = validate_package(
            temporary,
            "legacy",
            "either" if stage == "oss-handoff" or final_source else "local",
            assets_domain.lower() if stage == "oss-handoff" or final_source else "",
            key_prefix if stage == "oss-handoff" or final_source else "",
        )
        if stage_errors:
            raise WorkflowError(f"advance_validation_failed: {'; '.join(stage_errors)}")
        _publish_revision(temporary, output_root)
        stable_receipt = _relocate_staging_paths(receipt, temporary, output_root)
        return {
            "status": "completed",
            "stage": stage,
            "output": stable_receipt,
            "outputPath": (output_root / filename).as_posix(),
            "manifest": (output_root / "artifact-manifest.json").as_posix(),
        }
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
