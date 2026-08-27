#!/usr/bin/env python3
"""Rebuild the cross-batch catalog of approved style-template packages.

The migration is additive: source packages are never modified, existing v5
packages are retained, and a destination conflict aborts the run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from style_retirement import (
    RETIREMENT_REGISTRY_NAME,
    RetirementRegistryError,
    load_retired_keys as read_retired_keys,
)


PRODUCER = "style-template-analyzer"
CATALOG_SCHEMA_VERSION = "2.0.0"
MIGRATION_SCHEMA_VERSION = "1.0.0"
EXPECTED_COUNTS = {
    "legacy-delivery-confirmed": 94,
    "legacy-batch-human-pass": 43,
    "v5-human-pass": 7,
}
class CatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApprovedEntry:
    key: str
    revision: int
    title: str
    template_source: Path
    cover_source: Path
    approval_provenance: str
    approval_evidence: Path
    source_package: Path
    rewrite_cover_local: bool = False
    existing_revision_root: Path | None = None


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path, data_root: Path) -> str:
    return path.resolve().relative_to(data_root.resolve()).as_posix()


def relative_or_absolute(path: Path, data_root: Path) -> str:
    try:
        return relative(path, data_root)
    except ValueError:
        return path.resolve().as_posix()


def discover_approved_before(entry: ApprovedEntry) -> Path | None:
    roots = [entry.source_package]
    if entry.source_package.name in {"package", "review-package"}:
        roots.append(entry.source_package.parent / "internal")
    roots.extend([entry.source_package / "internal", entry.source_package.parent / "internal"])
    for root in dict.fromkeys(path.resolve() for path in roots):
        receipt = root / "cover-generation-receipt.json"
        if receipt.is_file():
            try:
                data = read_json(receipt)
            except (OSError, json.JSONDecodeError):
                data = {}
            provider = data.get("provider") if isinstance(data, dict) else None
            value = provider.get("sourceLocalPath") if isinstance(provider, dict) else None
            if isinstance(value, str) and value and Path(value).is_file():
                return Path(value).resolve()
        for name in ("before.png", "before.jpg", "before.jpeg", "source.png", "source.jpg", "source.jpeg"):
            candidate = root / name
            if candidate.is_file():
                return candidate.resolve()
    return None


def package_entry(
    package: Path,
    provenance: str,
    evidence: Path,
    *,
    revision: int = 1,
) -> ApprovedEntry:
    template = package / "style-template.json"
    cover = package / "cover.png"
    data = read_json(template)
    return ApprovedEntry(
        key=str(data["key"]),
        revision=revision,
        title=str(data["title"]),
        template_source=template,
        cover_source=cover,
        approval_provenance=provenance,
        approval_evidence=evidence,
        source_package=package,
    )


def collect_legacy_94(data_root: Path) -> list[ApprovedEntry]:
    delivery = data_root / "05-风格化模板生产/04-研发交付/2026-08-13-94个风格模板与效果图"
    backfilled = data_root / "05-风格化模板生产/04-研发交付/2026-08-13-94个风格模板-OSS回填JSON"
    evidence = delivery / "94个模板清单.json"
    entries: list[ApprovedEntry] = []
    for folder in sorted(path for path in delivery.iterdir() if path.is_dir()):
        original = read_json(folder / "style-template.json")
        key = str(original["key"])
        template = backfilled / f"{key}.json"
        final_data = read_json(template)
        if final_data.get("key") != key:
            raise CatalogError(f"legacy_key_mismatch:{folder}")
        entries.append(
            ApprovedEntry(
                key=key,
                revision=1,
                title=str(final_data["title"]),
                template_source=template,
                cover_source=folder / "effect.png",
                approval_provenance="legacy-delivery-confirmed",
                approval_evidence=evidence,
                source_package=folder,
            )
        )
    return entries


def passed_keys(path: Path) -> list[str]:
    return [str(item["key"]) for item in read_json(path).get("decisions", []) if item.get("verdict") == "pass"]


def collect_legacy_batch_passes(data_root: Path) -> list[ApprovedEntry]:
    batches = data_root / "05-风格化模板生产/03-本月生产批次"
    entries: list[ApprovedEntry] = []

    bottom = batches / "2026-08-18-二十个底层机制自生产"
    bottom_decision = bottom / "authoring/approval-decision-v1.json"
    for key in passed_keys(bottom_decision):
        entries.append(package_entry(bottom / f"runs/{key}/1/package", "legacy-batch-human-pass", bottom_decision))

    v2 = batches / "2026-08-18-二十个模板自生产-v2"
    v2_decision = v2 / "authoring/approval-decision-v1.json"
    for key in passed_keys(v2_decision):
        entries.append(package_entry(v2 / f"runs/{key}/1/package", "legacy-batch-human-pass", v2_decision))

    v3 = batches / "2026-08-18-二十个模板自生产-v3"
    v3_decision = v3 / "authoring/approval/approval-decision-v1.json"
    for key in passed_keys(v3_decision):
        entries.append(package_entry(v3 / f"final/{key}/1/package", "legacy-batch-human-pass", v3_decision))

    six = batches / "2026-08-18-六个模板自生产"
    six_decision = six / "authoring/approval-decision-v3.json"
    six_summary = read_json(six / "authoring/finalization-summary-v4.json")
    for item in six_summary["packages"]:
        key = str(item["key"])
        entries.append(package_entry(six / f"runs/{key}/1/package", "legacy-batch-human-pass", six_decision))

    dual = batches / "2026-08-18-双参考图与Skill灵感自生产"
    dual_decision = dual / "authoring/approval-decision-v2.json"
    for item in read_json(dual_decision)["approved"]:
        key = str(item["key"])
        entries.append(package_entry(dual / f"runs/{key}/1/package", "legacy-batch-human-pass", dual_decision))

    inspiration = batches / "2026-08-19-灵感参考四组模板编译-v1"
    inspiration_decision = inspiration / "authoring/approval-decision-v1.json"
    for key in passed_keys(inspiration_decision):
        if key == "palette-vinyl-echo":
            template = inspiration / "authoring/corrections/palette-vinyl-echo-rev2/style-template.json"
            cover = inspiration / "authoring/approval/selected-covers/01-palette-vinyl-echo-crop-fix-attempt-1.png"
            data = read_json(template)
            entries.append(
                ApprovedEntry(
                    key=key,
                    revision=1,
                    title=str(data["title"]),
                    template_source=template,
                    cover_source=cover,
                    approval_provenance="legacy-batch-human-pass",
                    approval_evidence=inspiration_decision,
                    source_package=inspiration / "authoring/approval/selected-covers",
                    rewrite_cover_local=True,
                )
            )
        else:
            entries.append(
                package_entry(
                    inspiration / f"final/{key}/1/package",
                    "legacy-batch-human-pass",
                    inspiration_decision,
                )
            )
    return entries


def collect_v5_passes(data_root: Path) -> list[ApprovedEntry]:
    register = data_root / "07-数据验收与上线/04-人工验收记录/风格模板/已通过/已通过模板索引.json"
    formal_root = data_root / "05-风格化模板生产/04-研发交付/已通过正式模板包"
    entries: list[ApprovedEntry] = []
    for item in read_json(register)["entries"]:
        package = data_root / str(item["finalPackage"])
        revision = int(item["revision"])
        entry = package_entry(
            package,
            "v5-human-pass",
            register.parent / str(item["receipt"]),
            revision=revision,
        )
        entries.append(
            ApprovedEntry(
                **{**entry.__dict__, "existing_revision_root": formal_root / entry.key / str(revision)}
            )
        )
    return entries


def collect_entries(data_root: Path) -> list[ApprovedEntry]:
    entries = collect_legacy_94(data_root) + collect_legacy_batch_passes(data_root) + collect_v5_passes(data_root)
    identities = [(item.key, item.revision) for item in entries]
    if len(identities) != len(set(identities)):
        raise CatalogError("duplicate_approved_identity")
    counts = {name: sum(item.approval_provenance == name for item in entries) for name in EXPECTED_COUNTS}
    if counts != EXPECTED_COUNTS:
        raise CatalogError(f"unexpected_source_counts:{counts}")
    if len(entries) != sum(EXPECTED_COUNTS.values()):
        raise CatalogError(f"unexpected_total:{len(entries)}")
    for entry in entries:
        for path in (entry.template_source, entry.cover_source, entry.approval_evidence):
            if not path.is_file():
                raise CatalogError(f"source_missing:{path}")
        template = read_json(entry.template_source)
        if template.get("key") != entry.key:
            raise CatalogError(f"template_key_mismatch:{entry.template_source}")
    return entries


def load_retired_keys(output_root: Path) -> set[str]:
    try:
        return read_retired_keys(output_root / RETIREMENT_REGISTRY_NAME)
    except RetirementRegistryError as error:
        raise CatalogError(str(error)) from error


def publish_entry(entry: ApprovedEntry, output_root: Path, data_root: Path, generated_at: str) -> None:
    if entry.existing_revision_root is not None:
        destination = entry.existing_revision_root
        if not (destination / "package/style-template.json").is_file() or not (destination / "package/cover.png").is_file():
            raise CatalogError(f"existing_package_incomplete:{destination}")
        return

    destination = output_root / entry.key / str(entry.revision)
    if destination.exists():
        template_hash = sha256_file(destination / "package/style-template.json")
        cover_hash = sha256_file(destination / "package/cover.png")
        source_template_hash = sha256_file(entry.template_source)
        if entry.rewrite_cover_local:
            template_data = read_json(entry.template_source)
            template_data["cover"] = "cover.png"
            source_template_hash = hashlib.sha256(
                (json.dumps(template_data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            ).hexdigest()
        if template_hash != source_template_hash or cover_hash != sha256_file(entry.cover_source):
            raise CatalogError(f"destination_conflict:{destination}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{entry.revision}-catalog-", dir=destination.parent))
    package = temporary / "package"
    internal = temporary / "internal"
    package.mkdir()
    internal.mkdir()
    template_data = read_json(entry.template_source)
    original_cover = template_data.get("cover")
    if entry.rewrite_cover_local:
        template_data["cover"] = "cover.png"
        write_json(package / "style-template.json", template_data)
    else:
        shutil.copy2(entry.template_source, package / "style-template.json")
    shutil.copy2(entry.cover_source, package / "cover.png")
    shutil.copy2(entry.approval_evidence, internal / "approval-evidence.json")
    migration_record = {
        "artifactType": "style_template_catalog_migration_record",
        "schemaVersion": MIGRATION_SCHEMA_VERSION,
        "producer": PRODUCER,
        "migratedAt": generated_at,
        "templateKey": entry.key,
        "revision": entry.revision,
        "verdict": "pass",
        "approvalProvenance": entry.approval_provenance,
        "sourcePackage": relative(entry.source_package, data_root),
        "sourceTemplate": relative(entry.template_source, data_root),
        "sourceCover": relative(entry.cover_source, data_root),
        "approvalEvidence": relative(entry.approval_evidence, data_root),
        "coverPolicy": "local-approved-cover-awaiting-oss" if entry.rewrite_cover_local else "preserve-finalized-cover",
    }
    if entry.rewrite_cover_local:
        migration_record["originalTemplateCover"] = original_cover
    write_json(internal / "catalog-migration-record.json", migration_record)
    manifest = {
        "artifactType": "style_template_catalog_entry",
        "schemaVersion": MIGRATION_SCHEMA_VERSION,
        "producer": PRODUCER,
        "generatedAt": generated_at,
        "status": "approved",
        "stage": "legacy-catalog-migration",
        "templateKey": entry.key,
        "revision": entry.revision,
        "approvalProvenance": entry.approval_provenance,
        "artifacts": [
            {"path": "package/style-template.json", "sha256": sha256_file(package / "style-template.json")},
            {"path": "package/cover.png", "sha256": sha256_file(package / "cover.png")},
            {"path": "internal/approval-evidence.json", "sha256": sha256_file(internal / "approval-evidence.json")},
            {"path": "internal/catalog-migration-record.json", "sha256": sha256_file(internal / "catalog-migration-record.json")},
        ],
    }
    write_json(temporary / "artifact-manifest.json", manifest)
    temporary.rename(destination)


def catalog_item(entry: ApprovedEntry, output_root: Path, data_root: Path) -> dict[str, Any]:
    revision_root = output_root / entry.key / str(entry.revision)
    package = revision_root / "package"
    template_path = package / "style-template.json"
    cover_path = package / "cover.png"
    template = read_json(template_path)
    remote_cover = template.get("cover")
    oss_status = "finalized" if isinstance(remote_cover, str) and remote_cover.startswith("https://") else "awaiting-finalization"
    approved_before = discover_approved_before(entry)
    return {
        "id": f"{entry.key}-r{entry.revision}",
        "key": entry.key,
        "title": entry.title,
        "revision": entry.revision,
        "verdict": "pass",
        "approvalProvenance": entry.approval_provenance,
        "ossStatus": oss_status,
        "template": relative(template_path, output_root),
        "effectImage": relative(cover_path, output_root),
        "templateSha256": sha256_file(template_path),
        "effectSha256": sha256_file(cover_path),
        "cover": remote_cover,
        "approvalEvidence": relative(entry.approval_evidence, data_root),
        "sourcePackage": relative(entry.source_package, data_root),
        **({"approvedBefore": relative_or_absolute(approved_before, data_root)} if approved_before else {}),
    }


def build_catalog(entries: list[ApprovedEntry], output_root: Path, data_root: Path, generated_at: str) -> dict[str, Any]:
    items = [catalog_item(entry, output_root, data_root) for entry in sorted(entries, key=lambda item: item.key)]
    provenance_counts = {
        name: sum(item["approvalProvenance"] == name for item in items) for name in EXPECTED_COUNTS
    }
    oss_counts = {
        status: sum(item["ossStatus"] == status for item in items)
        for status in ("finalized", "awaiting-finalization")
    }
    return {
        "artifactType": "style_template_delivery_catalog",
        "schemaVersion": CATALOG_SCHEMA_VERSION,
        "producer": PRODUCER,
        "generatedAt": generated_at,
        "packageName": "已通过正式模板包",
        "status": "completed",
        "templateCount": len(items),
        "effectImageCount": len(items),
        "pathPolicy": "catalog-relative",
        "approvalProvenanceCounts": provenance_counts,
        "ossStatusCounts": oss_counts,
        "items": items,
    }


def run(data_root: Path, apply: bool) -> dict[str, Any]:
    data_root = data_root.resolve()
    output_root = data_root / "05-风格化模板生产/04-研发交付/已通过正式模板包"
    entries = collect_entries(data_root)
    retired_keys = load_retired_keys(output_root)
    entries = [entry for entry in entries if entry.key not in retired_keys]
    generated_at = datetime.now(timezone.utc).isoformat()
    if apply:
        output_root.mkdir(parents=True, exist_ok=True)
        for entry in entries:
            publish_entry(entry, output_root, data_root, generated_at)
        catalog = build_catalog(entries, output_root, data_root, generated_at)
        write_json(output_root / "已通过模板清单.json", catalog)
        write_json(output_root / "统一通过模板索引.json", catalog)
        return catalog
    return {
        "artifactType": "style_template_catalog_migration_plan",
        "schemaVersion": MIGRATION_SCHEMA_VERSION,
        "producer": PRODUCER,
        "templateCount": len(entries),
        "retiredTemplateCount": len(retired_keys),
        "approvalProvenanceCounts": {
            name: sum(item.approval_provenance == name for item in entries) for name in EXPECTED_COUNTS
        },
        "outputRoot": output_root.as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Publish packages and replace the generated catalog")
    args = parser.parse_args()
    print(json.dumps(run(args.data_root, args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
