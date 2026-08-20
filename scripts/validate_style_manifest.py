#!/usr/bin/env python3
"""Validate style-template-analyzer package manifests and referenced artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from style_contracts import (
    ARTIFACT_SPECS,
    KEY_RE,
    PACKAGE_SCHEMA_VERSION,
    PRODUCER,
    SUPPORTED_PACKAGE_VERSIONS,
    LEGACY_STAGES,
    V3_STAGES,
    V4_STAGES,
    V5_STAGES,
    V6_STAGES,
    STAGE_REQUIREMENTS,
    LEGACY_STAGE_REQUIREMENTS,
    V3_STAGE_REQUIREMENTS,
    V4_STAGE_REQUIREMENTS,
    V5_STAGE_REQUIREMENTS,
    V6_STAGE_REQUIREMENTS,
    SEMVER_RE,
    read_json,
    sha256_file,
    template_key_for,
    artifact_schema_version,
)


REQUIRED_FIELDS = {
    "artifactType",
    "schemaVersion",
    "producer",
    "status",
    "revision",
    "contractStatus",
    "stage",
    "artifacts",
}
ALLOWED_FIELDS = REQUIRED_FIELDS | {"templateKey"}
ARTIFACT_FIELDS = {"path", "artifactType", "schemaVersion", "officialShape", "sha256"}


def validate_data(data: Any, manifest_file: Path, *, verify_files: bool = True) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["根节点必须是 JSON object"]
    for field in sorted(REQUIRED_FIELDS - set(data)):
        errors.append(f"{field} 缺失")
    extras = set(data) - ALLOWED_FIELDS
    if extras:
        errors.append(f"未知字段：{', '.join(sorted(extras))}")
    if data.get("artifactType") != "style_template_package":
        errors.append("artifactType 必须为 style_template_package")
    package_version = data.get("schemaVersion")
    if isinstance(package_version, str) and SEMVER_RE.fullmatch(package_version):
        if int(package_version.split(".")[0]) > int(PACKAGE_SCHEMA_VERSION.split(".")[0]):
            errors.append("failed: contract_version_unsupported")
        elif package_version not in SUPPORTED_PACKAGE_VERSIONS:
            errors.append(f"schemaVersion 必须是受支持版本：{', '.join(sorted(SUPPORTED_PACKAGE_VERSIONS))}")
    else:
        errors.append(f"schemaVersion 必须为 {PACKAGE_SCHEMA_VERSION}")
    if data.get("producer") != PRODUCER:
        errors.append(f"producer 必须为 {PRODUCER}")
    if data.get("status") not in {"completed", "needs_input", "blocked", "failed"}:
        errors.append("status 不合法")
    revision = data.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        errors.append("revision 必须是大于等于 1 的整数")
    if data.get("contractStatus") not in {"verified", "unverified", "blocked"}:
        errors.append("contractStatus 不合法")

    stage = data.get("stage")
    supported_stages = (
        LEGACY_STAGES
        if package_version == "1.0.0"
        else V3_STAGES
        if package_version == "2.0.0"
        else V4_STAGES
        if package_version == "3.0.0"
        else V5_STAGES
        if package_version == "4.0.0"
        else V6_STAGES
    )
    if stage not in supported_stages:
        errors.append("stage 不合法")
    template_key = data.get("templateKey")
    if template_key is not None and (not isinstance(template_key, str) or not KEY_RE.fullmatch(template_key)):
        errors.append("templateKey 格式不合法")
    if stage in {"authoring", "evaluation", "package", "oss-handoff", "prepublish", "review-package", "final-package"} and template_key is None:
        errors.append(f"{stage} 阶段必须声明 templateKey")

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts 必须是非空数组")
        return errors

    seen_paths: set[str] = set()
    seen_types: set[str] = set()
    business_keys: set[str] = set()
    root = manifest_file.parent.resolve()
    for index, artifact in enumerate(artifacts):
        path_label = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{path_label} 必须是 object")
            continue
        if set(artifact) != ARTIFACT_FIELDS:
            errors.append(f"{path_label} 必须且只能包含五个标准字段")
        relative = artifact.get("path")
        if not isinstance(relative, str) or not relative.strip():
            errors.append(f"{path_label}.path 必须是非空相对路径")
            continue
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            errors.append(f"{path_label}.path 必须位于 manifest 目录内")
            continue
        normalized = relative_path.as_posix()
        if normalized in seen_paths:
            errors.append(f"{path_label}.path 重复")
        seen_paths.add(normalized)

        artifact_type = artifact.get("artifactType")
        spec = ARTIFACT_SPECS.get(artifact_type)
        if spec is None:
            errors.append(f"{path_label}.artifactType 不合法")
            continue
        seen_types.add(artifact_type)
        version = artifact.get("schemaVersion")
        if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
            errors.append(f"{path_label}.schemaVersion 必须为三段版本")
        else:
            expected_version = artifact_schema_version(str(artifact_type), str(package_version))
            if version != expected_version:
                errors.append(f"{path_label}.schemaVersion 必须为 {expected_version}")
        if artifact.get("officialShape") is not spec["officialShape"]:
            errors.append(f"{path_label}.officialShape 与契约登记不一致")
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            errors.append(f"{path_label}.sha256 格式不合法")

        business_file = (root / relative_path).resolve()
        if root not in business_file.parents and business_file != root:
            errors.append(f"{path_label}.path 越出 manifest 目录")
        elif verify_files and not business_file.is_file():
            errors.append(f"{path_label}.path 不存在：{business_file}")
        elif verify_files and isinstance(digest, str) and len(digest) == 64 and sha256_file(business_file) != digest:
            errors.append(f"{path_label}.sha256 与业务文件不一致")
        if verify_files and business_file.is_file() and business_file.suffix.lower() == ".json":
            try:
                business_key = template_key_for(read_json(business_file), artifact_type)
            except (OSError, json.JSONDecodeError):
                business_key = None
            if business_key is not None:
                business_keys.add(business_key)

    requirements = (
        LEGACY_STAGE_REQUIREMENTS
        if package_version == "1.0.0"
        else V3_STAGE_REQUIREMENTS
        if package_version == "2.0.0"
        else V4_STAGE_REQUIREMENTS
        if package_version == "3.0.0"
        else V5_STAGE_REQUIREMENTS
        if package_version == "4.0.0"
        else V6_STAGE_REQUIREMENTS
    )
    if stage in supported_stages:
        missing = requirements[stage] - seen_types
        if missing:
            errors.append(f"{stage} 阶段缺少产物：{', '.join(sorted(missing))}")
        if package_version in {"2.0.0", "3.0.0", "4.0.0", "5.0.0", "5.1.0"} and stage in {"package", "prepublish", "review-package", "final-package"} and not seen_types.intersection({"style_analysis", "self_production_analysis"}):
            errors.append(f"{stage} 阶段缺少分析证据")
        if package_version in {"5.0.0", "5.1.0"} and "style_analysis" in seen_types:
            missing_reference = {"reference_interpretation", "reference_visual_gate_receipt"} - seen_types
            if missing_reference:
                errors.append(f"{stage} 阶段缺少参考图门禁证据：{', '.join(sorted(missing_reference))}")
    if stage in {"authoring", "evaluation", "package", "oss-handoff", "prepublish", "review-package", "final-package"} and business_keys != {template_key}:
        errors.append("manifest.templateKey 必须与全部业务产物的 key 一致")
    return errors


def collect(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if not target.is_dir():
        raise ValueError(f"输入路径不存在：{target}")
    return sorted(target.rglob("artifact-manifest.json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--skip-files", action="store_true", help="只校验 manifest 形状")
    args = parser.parse_args()
    try:
        files = collect(args.target.resolve())
    except ValueError as error:
        print(f"FAIL\n{error}")
        return 1
    if not files:
        print(f"FAIL\n未找到 artifact-manifest.json：{args.target}")
        return 1

    all_errors: list[str] = []
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            all_errors.append(f"{file}: JSON 读取失败：{error}")
            continue
        all_errors.extend(
            f"{file}: {error}" for error in validate_data(data, file, verify_files=not args.skip_files)
        )
    if all_errors:
        print("FAIL")
        print("\n".join(all_errors))
        return 1
    print(f"PASS {len(files)} manifest(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
