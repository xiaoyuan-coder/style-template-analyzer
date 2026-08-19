#!/usr/bin/env python3
"""Shared contracts for style-template-analyzer package tooling."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


PRODUCER = "style-template-analyzer"
PACKAGE_SCHEMA_VERSION = "4.0.0"
SUPPORTED_PACKAGE_VERSIONS = {"1.0.0", "2.0.0", "3.0.0", "4.0.0"}
KEY_RE = re.compile(r"^[a-z][a-z0-9-]{1,59}$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

ARTIFACT_SPECS = {
    "style_analysis": {
        "filenames": {"style-analysis.json"},
        "schemaVersion": "2.0.0",
        "officialShape": False,
    },
    "style_template": {
        "filenames": {"style-template.json"},
        "schemaVersion": "1.0.0",
        "officialShape": True,
    },
    "style_evaluation": {
        "filenames": {"style-evaluation.json"},
        "schemaVersion": "2.0.0",
        "officialShape": False,
    },
    "style_handoff": {
        "filenames": set(),
        "schemaVersion": "1.0.0",
        "officialShape": True,
    },
    "style_cover": {
        "filenames": {"cover.png"},
        "schemaVersion": "1.0.0",
        "officialShape": False,
    },
    "test_image_assignment": {
        "filenames": {"test-image-assignment.json"},
        "schemaVersion": "2.0.0",
        "officialShape": False,
    },
    "cover_generation_receipt": {
        "filenames": {"cover-generation-receipt.json"},
        "schemaVersion": "1.0.0",
        "officialShape": False,
    },
    "cover_check_receipt": {
        "filenames": {"cover-check-receipt.json"},
        "schemaVersion": "1.0.0",
        "officialShape": False,
    },
    "approval_decision_receipt": {
        "filenames": {"approval-decision-receipt.json"},
        "schemaVersion": "1.0.0",
        "officialShape": False,
    },
    "oss_finalization_receipt": {
        "filenames": {"oss-finalization-receipt.json"},
        "schemaVersion": "1.0.0",
        "officialShape": False,
    },
    "baseline_snapshot": {
        "filenames": {"baseline-snapshot.json"},
        "schemaVersion": "1.0.0",
        "officialShape": False,
    },
    "self_production_analysis": {
        "filenames": {"self-production-analysis.json"},
        "schemaVersion": "1.0.0",
        "officialShape": False,
    },
    "source_package_receipt": {
        "filenames": {"source-package-receipt.json"},
        "schemaVersion": "1.0.0",
        "officialShape": False,
    },
    "style_badcase_corpus": {
        "filenames": set(),
        "schemaVersion": "1.0.0",
        "officialShape": False,
    },
}

LEGACY_STAGE_REQUIREMENTS = {
    "authoring": {"style_analysis", "style_template"},
    "evaluation": {"style_analysis", "style_template", "style_evaluation"},
    "handoff": {"style_handoff"},
}

V3_STAGE_REQUIREMENTS = {
    "package": {
        "style_template",
        "style_cover",
        "test_image_assignment",
        "cover_generation_receipt",
    },
    "evaluation": {"style_template", "style_cover", "style_evaluation", "source_package_receipt"},
    "oss-handoff": {"style_template", "style_cover", "style_handoff", "source_package_receipt"},
}

V4_STAGE_REQUIREMENTS = {
    "prepublish": {
        "style_template",
        "style_cover",
        "test_image_assignment",
        "cover_generation_receipt",
        "cover_check_receipt",
    },
    "final-package": {
        "style_template",
        "style_cover",
        "test_image_assignment",
        "cover_generation_receipt",
        "cover_check_receipt",
        "oss_finalization_receipt",
    },
    "evaluation": {"style_template", "style_cover", "style_evaluation", "source_package_receipt"},
}

V5_STAGE_REQUIREMENTS = {
    "review-package": {
        "style_template",
        "style_cover",
        "test_image_assignment",
        "cover_generation_receipt",
        "cover_check_receipt",
    },
    "final-package": {
        "style_template",
        "style_cover",
        "test_image_assignment",
        "cover_generation_receipt",
        "cover_check_receipt",
        "approval_decision_receipt",
        "oss_finalization_receipt",
    },
    "evaluation": {"style_template", "style_cover", "style_evaluation", "source_package_receipt"},
}

STAGE_REQUIREMENTS = {**LEGACY_STAGE_REQUIREMENTS, **V3_STAGE_REQUIREMENTS, **V4_STAGE_REQUIREMENTS, **V5_STAGE_REQUIREMENTS}
LEGACY_STAGES = set(LEGACY_STAGE_REQUIREMENTS)
V3_STAGES = set(V3_STAGE_REQUIREMENTS)
V4_STAGES = set(V4_STAGE_REQUIREMENTS)
V5_STAGES = set(V5_STAGE_REQUIREMENTS)


def artifact_type_for(path: Path, stage: str) -> str | None:
    """Return the contract artifact type for a business JSON path."""
    for artifact_type, spec in ARTIFACT_SPECS.items():
        if path.name in spec["filenames"]:
            return artifact_type
    if stage in {"handoff", "oss-handoff"} and path.suffix.lower() == ".json" and path.name != "artifact-manifest.json":
        return "style_handoff"
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def template_key_for(data: Any, artifact_type: str) -> str | None:
    if not isinstance(data, dict):
        return None
    field = "key" if artifact_type in {"style_template", "style_handoff"} else "templateKey"
    value = data.get(field)
    return value if isinstance(value, str) and KEY_RE.fullmatch(value) else None


def artifact_schema_version(artifact_type: str, package_schema_version: str) -> str:
    if artifact_type == "test_image_assignment" and package_schema_version != "4.0.0":
        return "1.0.0"
    return str(ARTIFACT_SPECS[artifact_type]["schemaVersion"])


def artifact_record(path: Path, root: Path, stage: str, package_schema_version: str) -> dict[str, Any]:
    artifact_type = artifact_type_for(path, stage)
    if artifact_type is None:
        raise ValueError(f"无法识别产物类型：{path}")
    spec = ARTIFACT_SPECS[artifact_type]
    return {
        "path": path.relative_to(root).as_posix(),
        "artifactType": artifact_type,
        "schemaVersion": artifact_schema_version(artifact_type, package_schema_version),
        "officialShape": spec["officialShape"],
        "sha256": sha256_file(path),
    }


def build_manifest(
    root: Path,
    stage: str,
    revision: int = 1,
    *,
    schema_version: str = "1.0.0",
) -> dict[str, Any]:
    root = root.resolve()
    supported_stages = (
        LEGACY_STAGES
        if schema_version == "1.0.0"
        else V3_STAGES
        if schema_version == "2.0.0"
        else V4_STAGES
        if schema_version == "3.0.0"
        else V5_STAGES
    )
    if schema_version not in SUPPORTED_PACKAGE_VERSIONS:
        raise ValueError(f"不支持的 schemaVersion：{schema_version}")
    if stage not in supported_stages:
        raise ValueError(f"不支持的 stage：{stage}")
    if revision < 1:
        raise ValueError("revision 必须大于等于 1")

    candidates = sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path.name != "artifact-manifest.json"
        and artifact_type_for(path, stage)
    )
    if not candidates:
        raise ValueError(f"未找到 {stage} 阶段业务 JSON：{root}")

    artifacts = [artifact_record(path, root, stage, schema_version) for path in candidates]
    artifact_types = {item["artifactType"] for item in artifacts}
    requirements = (
        LEGACY_STAGE_REQUIREMENTS
        if schema_version == "1.0.0"
        else V3_STAGE_REQUIREMENTS
        if schema_version == "2.0.0"
        else V4_STAGE_REQUIREMENTS
        if schema_version == "3.0.0"
        else V5_STAGE_REQUIREMENTS
    )
    missing = requirements[stage] - artifact_types
    if missing:
        raise ValueError(f"{stage} 阶段缺少产物：{', '.join(sorted(missing))}")
    if schema_version in {"2.0.0", "3.0.0", "4.0.0"} and stage in {"package", "prepublish", "review-package", "final-package"} and not artifact_types.intersection({"style_analysis", "self_production_analysis"}):
        raise ValueError(f"{stage} 阶段缺少分析证据")

    keys: set[str] = set()
    for path, record in zip(candidates, artifacts):
        if path.suffix.lower() != ".json":
            continue
        key = template_key_for(read_json(path), record["artifactType"])
        if key:
            keys.add(key)
    template_key = next(iter(keys)) if len(keys) == 1 else None
    if stage != "handoff" and template_key is None:
        raise ValueError("同一包内产物必须共享一个 templateKey")

    manifest: dict[str, Any] = {
        "artifactType": "style_template_package",
        "schemaVersion": schema_version,
        "producer": PRODUCER,
        "status": "completed",
        "revision": revision,
        "contractStatus": "verified",
        "stage": stage,
        "artifacts": artifacts,
    }
    if template_key is not None:
        manifest["templateKey"] = template_key
    return manifest
