#!/usr/bin/env python3
"""Validate a style template package through one stable interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image
from jsonschema import Draft202012Validator

from style_baseline import validate_baseline_snapshot
import validate_style_analysis
import validate_style_evaluation
import validate_style_manifest
import validate_style_template


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def collect(root: Path, filename: str) -> list[Path]:
    if root.is_file():
        return [root] if root.name == filename else []
    return sorted(root.rglob(filename))


def validate_schema(data: object, filename: str) -> list[str]:
    schema_file = Path(__file__).parents[1] / "contracts" / filename
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda item: list(item.absolute_path))
    ]


def validate_package(
    target: Path,
    profile: str,
    asset_mode: str,
    domain: str,
    prefix: str,
) -> tuple[list[str], dict[str, int]]:
    root = target.resolve()
    errors: list[str] = []
    analyses = collect(root, "style-analysis.json")
    templates = collect(root, "style-template.json")
    evaluations = collect(root, "style-evaluation.json")
    manifests = collect(root, "artifact-manifest.json")
    covers = collect(root, "cover.png")

    if not any((analyses, templates, evaluations, manifests, covers)):
        return [f"未找到风格模板产物：{root}"], {}
    if profile in {"authoring", "release"}:
        if not analyses:
            errors.append("authoring/release gate 缺少 style-analysis.json")
        if not templates:
            errors.append("authoring/release gate 缺少 style-template.json")
        if not manifests:
            errors.append("authoring/release gate 缺少 artifact-manifest.json")
    if profile == "release" and not evaluations:
        errors.append("release gate 缺少 style-evaluation.json")
    strict_profiles = {"fast-package", "prepublish", "final-package"}
    if profile in strict_profiles:
        directory_name = "prepublish" if profile == "prepublish" else "package"
        package = root / directory_name if root.is_dir() and (root / directory_name).is_dir() else root
        package_files = sorted(path.relative_to(package).as_posix() for path in package.rglob("*") if path.is_file()) if package.is_dir() else []
        if package_files != ["cover.png", "style-template.json"]:
            errors.append(f"{profile} 必须且只能包含 style-template.json 与 cover.png")
        if len(templates) != 1 or len(covers) != 1:
            errors.append(f"{profile} 必须包含且只包含一个模板和一张封面")
        if not manifests:
            errors.append(f"{profile} 缺少 revision 根目录 artifact-manifest.json")
        elif len(manifests) != 1 or manifests[0] != root / "artifact-manifest.json":
            errors.append(f"{profile} 必须且只能在 revision 根目录包含一个 artifact-manifest.json")
        if len(covers) == 1:
            try:
                with Image.open(covers[0]) as image:
                    image.verify()
                    if image.format != "PNG":
                        errors.append(f"{covers[0]}: cover 必须是有效 PNG")
            except OSError as error:
                errors.append(f"{covers[0]}: cover 不是有效 PNG：{error}")

    for file in analyses:
        try:
            data = read_json(file)
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{file}: JSON 读取失败：{error}")
            continue
        errors.extend(f"{file}: {error}" for error in validate_style_analysis.validate_data(data))

    template_keys: dict[str, Path] = {}
    template_records: dict[str, dict[str, object]] = {}
    for file in templates:
        try:
            data = read_json(file)
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{file}: JSON 读取失败：{error}")
            continue
        errors.extend(
            f"{file}: {error}"
            for error in validate_style_template.validate_data(data, file, asset_mode, domain, prefix)
        )
        key = data.get("key") if isinstance(data, dict) else None
        if isinstance(key, str):
            if key in template_keys:
                errors.append(f"{file}: 批次 key 重复，首次出现于 {template_keys[key]}")
            template_keys[key] = file
            if isinstance(data, dict):
                template_records[key] = data

    for file in evaluations:
        try:
            data = read_json(file)
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{file}: JSON 读取失败：{error}")
            continue
        errors.extend(f"{file}: {error}" for error in validate_style_evaluation.validate_data(data, file))
        if profile == "release" and isinstance(data, dict):
            aggregate = data.get("aggregate")
            if not isinstance(aggregate, dict) or aggregate.get("verdict") != "pass":
                errors.append(f"{file}: release gate 要求 aggregate.verdict=pass")

    referenced: set[Path] = set()
    manifest_stages: set[str] = set()
    for file in manifests:
        try:
            data = read_json(file)
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{file}: JSON 读取失败：{error}")
            continue
        manifest_errors = validate_style_manifest.validate_data(data, file)
        errors.extend(f"{file}: {error}" for error in manifest_errors)
        if isinstance(data, dict) and isinstance(data.get("stage"), str):
            manifest_stages.add(data["stage"])
            if profile == "fast-package" and (data.get("schemaVersion") != "2.0.0" or data.get("stage") != "package"):
                errors.append(f"{file}: fast-package 要求 manifest schemaVersion=2.0.0 且 stage=package")
            elif profile in {"prepublish", "final-package"}:
                expected_stage = "prepublish" if profile == "prepublish" else "final-package"
                if data.get("schemaVersion") != "3.0.0" or data.get("stage") != expected_stage:
                    errors.append(f"{file}: {profile} 要求 manifest schemaVersion=3.0.0 且 stage={expected_stage}")
        if isinstance(data, dict) and isinstance(data.get("artifacts"), list):
            for artifact in data["artifacts"]:
                if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
                    referenced.add((file.parent / artifact["path"]).resolve())

    if profile in {"authoring", "release", *strict_profiles}:
        required_artifacts = analyses + templates + evaluations
        if profile in strict_profiles:
            required_artifacts += covers
        for artifact in required_artifacts:
            if artifact.resolve() not in referenced:
                errors.append(f"{artifact}: 未被 artifact-manifest.json 登记")
    if profile == "release" and "evaluation" not in manifest_stages:
        errors.append("release gate 要求 manifest.stage=evaluation")
    if profile in strict_profiles:
        assignments = collect(root, "test-image-assignment.json")
        receipts = collect(root, "cover-generation-receipt.json")
        cover_checks = collect(root, "cover-check-receipt.json")
        oss_receipts = collect(root, "oss-finalization-receipt.json")
        self_analyses = collect(root, "self-production-analysis.json")
        baseline_snapshots = collect(root, "baseline-snapshot.json")
        if len(assignments) != 1 or len(receipts) != 1:
            errors.append(f"{profile} 必须包含唯一测试图分配与封面生成回执")
        if len(analyses) + len(self_analyses) != 1:
            errors.append(f"{profile} 必须包含且只包含一种分析证据")
        if profile in {"prepublish", "final-package"} and len(cover_checks) != 1:
            errors.append(f"{profile} 必须包含唯一轻量封面检查回执")
        if profile == "final-package" and len(oss_receipts) != 1:
            errors.append("final-package 必须包含唯一 OSS 最终化回执")
        if profile == "prepublish" and oss_receipts:
            errors.append("prepublish 不得包含 OSS 最终化回执")
        assignment_records: list[dict[str, object]] = []
        receipt_records: list[dict[str, object]] = []
        self_analysis_records: list[dict[str, object]] = []
        baseline_records: list[dict[str, object]] = []
        for file in assignments:
            try:
                data = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            errors.extend(f"{file}: {error}" for error in validate_schema(data, "test-image-assignment.schema.json"))
            required = {"artifactType", "schemaVersion", "producer", "deliverySetId", "templateKey", "revision", "assetId", "assignedAt", "status"}
            if not isinstance(data, dict) or set(data) != required:
                errors.append(f"{file}: assignment 字段不符合 1.0.0 契约")
            elif data.get("artifactType") != "test_image_assignment" or data.get("schemaVersion") != "1.0.0" or data.get("producer") != "style-template-analyzer" or data.get("status") != "committed":
                errors.append(f"{file}: assignment 契约值不合法")
            else:
                assignment_records.append(data)
        for file in receipts:
            try:
                data = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            errors.extend(f"{file}: {error}" for error in validate_schema(data, "cover-generation-receipt.schema.json"))
            required = {"artifactType", "schemaVersion", "producer", "templateKey", "revision", "assetId", "provider"}
            if not isinstance(data, dict) or set(data) != required:
                errors.append(f"{file}: generation receipt 字段不符合 1.0.0 契约")
            elif data.get("artifactType") != "cover_generation_receipt" or data.get("schemaVersion") != "1.0.0" or data.get("producer") != "style-template-analyzer":
                errors.append(f"{file}: generation receipt 契约值不合法")
            else:
                receipt_records.append(data)
        cover_check_records: list[dict[str, object]] = []
        for file in cover_checks:
            try:
                data = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            schema_errors = validate_schema(data, "cover-check-receipt.schema.json")
            errors.extend(f"{file}: {error}" for error in schema_errors)
            if not schema_errors and isinstance(data, dict):
                cover_check_records.append(data)
        oss_records: list[dict[str, object]] = []
        for file in oss_receipts:
            try:
                data = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            schema_errors = validate_schema(data, "oss-finalization-receipt.schema.json")
            errors.extend(f"{file}: {error}" for error in schema_errors)
            if not schema_errors and isinstance(data, dict):
                oss_records.append(data)
        for file in self_analyses:
            try:
                data = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            errors.extend(f"{file}: {error}" for error in validate_schema(data, "self-production-analysis.schema.json"))
            required = {"artifactType", "schemaVersion", "producer", "templateKey", "baselineDigest", "novelty"}
            if not isinstance(data, dict) or set(data) != required or data.get("artifactType") != "self_production_analysis" or data.get("producer") != "style-template-analyzer":
                errors.append(f"{file}: self-production analysis 不符合 1.0.0 契约")
            elif data.get("novelty") != {"key": "unique", "title": "unique", "promptMechanism": "unique", "category": "distinct"}:
                errors.append(f"{file}: self-production novelty 证据不完整")
            else:
                self_analysis_records.append(data)
        if self_analyses and len(baseline_snapshots) != 1:
            errors.append("自生产模板产物必须包含唯一 baseline-snapshot.json")
        for file in baseline_snapshots:
            try:
                baseline = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            baseline_errors = validate_schema(baseline, "baseline-snapshot.schema.json")
            baseline_errors.extend(validate_baseline_snapshot(baseline))
            errors.extend(f"{file}: {error}" for error in baseline_errors)
            if not baseline_errors:
                baseline_records.append(baseline)
        if assignment_records and receipt_records:
            assignment = assignment_records[0]
            receipt = receipt_records[0]
            if any(assignment.get(field) != receipt.get(field) for field in ("templateKey", "revision", "assetId")):
                errors.append("测试图分配与封面生成回执身份不一致")
            if template_keys and assignment.get("templateKey") not in template_keys:
                errors.append("测试图分配 templateKey 与模板不一致")
        if assignment_records and cover_check_records:
            assignment = assignment_records[0]
            check = cover_check_records[0]
            if any(assignment.get(field) != check.get(field) for field in ("templateKey", "revision")):
                errors.append("测试图分配与轻量封面检查回执身份不一致")
        if assignment_records and oss_records:
            assignment = assignment_records[0]
            oss = oss_records[0]
            if any(assignment.get(field) != oss.get(field) for field in ("templateKey", "revision")):
                errors.append("测试图分配与 OSS 最终化回执身份不一致")
            template = template_records.get(str(assignment.get("templateKey")), {})
            if template.get("cover") != oss.get("remoteCoverUrl"):
                errors.append("模板 cover 与 OSS 最终化回执 URL 不一致")
            if domain and str(oss.get("assetsDomain", "")).lower() != domain.lower():
                errors.append("OSS 最终化回执 assetsDomain 与受控域名不一致")
        if self_analysis_records and baseline_records:
            if self_analysis_records[0].get("baselineDigest") != baseline_records[0].get("digest"):
                errors.append("自生产分析与 baseline snapshot digest 不一致")

    return errors, {
        "analyses": len(analyses),
        "templates": len(templates),
        "evaluations": len(evaluations),
        "manifests": len(manifests),
        "covers": len(covers),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--profile",
        choices=["legacy", "authoring", "release", "fast-package", "prepublish", "final-package"],
        default="final-package",
    )
    parser.add_argument("--asset-mode", choices=["local", "remote", "either"])
    parser.add_argument("--assets-domain", default="")
    parser.add_argument("--key-prefix", default="")
    args = parser.parse_args()
    domain = args.assets_domain.strip().lower()
    if domain and ("://" in domain or any(char in domain for char in "/?#@:")):
        print("FAIL\n--assets-domain 必须是纯 hostname")
        return 1
    errors, summary = validate_package(
        args.target,
        args.profile,
        args.asset_mode or ("remote" if args.profile == "final-package" else "local"),
        domain,
        args.key_prefix,
    )
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print(f"PASS profile={args.profile} {json.dumps(summary, ensure_ascii=False, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
