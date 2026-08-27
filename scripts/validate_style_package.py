#!/usr/bin/env python3
"""Validate a style template package through one stable interface."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image
from jsonschema import Draft202012Validator

from style_baseline import validate_baseline_snapshot
from style_effect_contract import validate_effect_contract
from style_reference_gate import validate_reference_interpretation, validate_visual_gate
import validate_style_analysis
import validate_style_evaluation
import validate_style_manifest
import validate_style_template
from style_assignment_contracts import assignment_schema_name


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
    strict_profiles = {"fast-package", "prepublish", "review-package", "final-package"}
    if profile in strict_profiles:
        directory_name = (
            "prepublish" if profile == "prepublish"
            else "review-package" if profile == "review-package"
            else "package"
        )
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
    manifest_v5_final = False
    manifest_schema_versions: set[str] = set()
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
            if isinstance(data.get("schemaVersion"), str):
                manifest_schema_versions.add(data["schemaVersion"])
            manifest_v5_final = (
                manifest_v5_final
                or (data.get("schemaVersion") in {"4.0.0", "5.0.0", "5.1.0", "6.0.0"} and data.get("stage") == "final-package")
            )
            if profile == "fast-package" and (data.get("schemaVersion") != "2.0.0" or data.get("stage") != "package"):
                errors.append(f"{file}: fast-package 要求 manifest schemaVersion=2.0.0 且 stage=package")
            elif profile == "prepublish":
                if data.get("schemaVersion") != "3.0.0" or data.get("stage") != "prepublish":
                    errors.append(f"{file}: prepublish 要求 manifest schemaVersion=3.0.0 且 stage=prepublish")
            elif profile == "review-package":
                if data.get("schemaVersion") not in {"4.0.0", "5.0.0", "5.1.0", "6.0.0"} or data.get("stage") != "review-package":
                    errors.append(f"{file}: review-package 要求 manifest schemaVersion=4.0.0/5.0.0/5.1.0/6.0.0 且 stage=review-package")
            elif profile == "final-package":
                if data.get("schemaVersion") not in {"3.0.0", "4.0.0", "5.0.0", "5.1.0", "6.0.0"} or data.get("stage") != "final-package":
                    errors.append(f"{file}: final-package 要求 manifest schemaVersion=3.0.0/4.0.0/5.0.0/5.1.0/6.0.0 且 stage=final-package")
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
        approval_receipts = collect(root, "approval-decision-receipt.json")
        self_analyses = collect(root, "self-production-analysis.json")
        baseline_snapshots = collect(root, "baseline-snapshot.json")
        reference_interpretations = collect(root, "reference-interpretation.json")
        reference_visual_gates = collect(root, "reference-visual-gate-receipt.json")
        experience_receipts = collect(root, "experience-deposit-receipt.json")
        dynamic_baseline_receipts = collect(root, "dynamic-baseline-registration-receipt.json")
        effect_contracts = collect(root, "effect-reproduction-contract.json")
        if len(assignments) != 1 or len(receipts) != 1:
            errors.append(f"{profile} 必须包含唯一测试图分配与封面生成回执")
        if len(analyses) + len(self_analyses) != 1:
            errors.append(f"{profile} 必须包含且只包含一种分析证据")
        if manifest_schema_versions.intersection({"5.0.0", "5.1.0", "6.0.0"}) and analyses:
            if len(reference_interpretations) != 1 or len(reference_visual_gates) != 1:
                errors.append(f"{profile} 的参考图模板必须包含唯一语义解释与独立视觉验收回执")
        if profile in {"prepublish", "review-package", "final-package"} and len(cover_checks) != 1:
            errors.append(f"{profile} 必须包含唯一轻量封面检查回执")
        if profile == "final-package" and len(oss_receipts) != 1:
            errors.append("final-package 必须包含唯一 OSS 最终化回执")
        if profile == "prepublish" and oss_receipts:
            errors.append("prepublish 不得包含 OSS 最终化回执")
        if profile == "review-package" and oss_receipts:
            errors.append("review-package 不得包含 OSS 最终化回执")
        assignment_records: list[dict[str, object]] = []
        receipt_records: list[dict[str, object]] = []
        self_analysis_records: list[dict[str, object]] = []
        baseline_records: list[dict[str, object]] = []
        interpretation_records: list[dict[str, object]] = []
        visual_gate_records: list[dict[str, object]] = []
        effect_contract_records: list[dict[str, object]] = []
        for file in assignments:
            try:
                data = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            version = data.get("schemaVersion") if isinstance(data, dict) else None
            schema_name = assignment_schema_name(version)
            schema_errors = validate_schema(data, schema_name)
            errors.extend(f"{file}: {error}" for error in schema_errors)
            if not schema_errors and isinstance(data, dict):
                if profile == "review-package" and data.get("status") not in {"awaiting_approval", "released", "consumed"}:
                    errors.append(f"{file}: review-package assignment 必须已进入人工审核状态")
                elif profile == "final-package" and data.get("schemaVersion") == "2.0.0" and data.get("status") != "consumed":
                    errors.append(f"{file}: v5 final-package assignment 必须为 consumed")
                else:
                    assignment_records.append(data)
        for file in receipts:
            try:
                data = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            version = data.get("schemaVersion") if isinstance(data, dict) else None
            schema_name = (
                "cover-generation-receipt-v2.schema.json"
                if version == "2.0.0"
                else "cover-generation-receipt.schema.json"
            )
            schema_errors = validate_schema(data, schema_name)
            errors.extend(f"{file}: {error}" for error in schema_errors)
            if not schema_errors and isinstance(data, dict):
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
        approval_records: list[dict[str, object]] = []
        for file in approval_receipts:
            try:
                data = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            schema_errors = validate_schema(data, "approval-decision-receipt.schema.json")
            errors.extend(f"{file}: {error}" for error in schema_errors)
            if not schema_errors and isinstance(data, dict):
                approval_records.append(data)
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
        for file in reference_interpretations:
            try:
                interpretation = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            interpretation_errors = validate_reference_interpretation(interpretation)
            errors.extend(f"{file}: {error}" for error in interpretation_errors)
            if not interpretation_errors and isinstance(interpretation, dict):
                interpretation_records.append(interpretation)
        for file in reference_visual_gates:
            try:
                visual_gate = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            analysis_producer = str(interpretation_records[0].get("producer", "")) if interpretation_records else ""
            visual_errors = validate_visual_gate(visual_gate, analysis_producer=analysis_producer)
            errors.extend(f"{file}: {error}" for error in visual_errors)
            if not visual_errors and isinstance(visual_gate, dict):
                visual_gate_records.append(visual_gate)
        for file in effect_contracts:
            try:
                effect_contract = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            template = template_records.get(str(effect_contract.get("templateKey")), {}) if isinstance(effect_contract, dict) else {}
            prompt = template.get("promptTemplate") if isinstance(template, dict) else ""
            contract_errors = validate_effect_contract(
                effect_contract,
                expected_key=str(effect_contract.get("templateKey", "")) if isinstance(effect_contract, dict) else "",
                prompt_template=str(prompt) if isinstance(prompt, str) else "",
            )
            errors.extend(f"{file}: {error}" for error in contract_errors)
            if not contract_errors and isinstance(effect_contract, dict):
                effect_contract_records.append(effect_contract)
        for file in experience_receipts:
            try:
                experience_receipt = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            errors.extend(f"{file}: {error}" for error in validate_schema(experience_receipt, "experience-deposit-receipt.schema.json"))
        for file in dynamic_baseline_receipts:
            try:
                baseline_receipt = read_json(file)
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{file}: JSON 读取失败：{error}")
                continue
            errors.extend(f"{file}: {error}" for error in validate_schema(
                baseline_receipt,
                "dynamic-baseline-registration-receipt.schema.json",
            ))
        if assignment_records and receipt_records:
            assignment = assignment_records[0]
            receipt = receipt_records[0]
            if any(assignment.get(field) != receipt.get(field) for field in ("templateKey", "revision", "assetId")):
                errors.append("测试图分配与封面生成回执身份不一致")
            if template_keys and assignment.get("templateKey") not in template_keys:
                errors.append("测试图分配 templateKey 与模板不一致")
            if receipt.get("schemaVersion") == "2.0.0":
                template = template_records.get(str(assignment.get("templateKey")), {})
                prompt = template.get("promptTemplate") if isinstance(template, dict) else None
                if isinstance(prompt, str) and receipt.get("submittedPromptSha256") != hashlib.sha256(prompt.encode("utf-8")).hexdigest():
                    errors.append("封面生成回执 submittedPromptSha256 与模板不一致")
        if "6.0.0" in manifest_schema_versions:
            if len(effect_contract_records) != 1:
                errors.append(f"{profile} manifest 6.0.0 必须包含唯一 After 复现合同")
            if not receipt_records or receipt_records[0].get("schemaVersion") != "2.0.0":
                errors.append(f"{profile} manifest 6.0.0 必须使用封面生成回执 2.0.0")
        if assignment_records and receipt_records and effect_contract_records:
            assignment = assignment_records[0]
            receipt = receipt_records[0]
            effect_contract = effect_contract_records[0]
            binding = effect_contract.get("evidenceBinding", {})
            if assignment.get("assetId") != binding.get("sourceAssetId"):
                errors.append("测试图分配与 After 复现合同 sourceAssetId 不一致")
            if receipt.get("sourceSha256") != binding.get("sourceSha256"):
                errors.append("封面生成回执与 After 复现合同 sourceSha256 不一致")
            if receipt.get("submittedPromptSha256") != binding.get("promptSha256"):
                errors.append("封面生成回执与 After 复现合同 promptSha256 不一致")
            if len(covers) == 1 and binding.get("effectSha256") != hashlib.sha256(covers[0].read_bytes()).hexdigest():
                errors.append("After 复现合同 effectSha256 与封面不一致")
        if assignment_records and cover_check_records:
            assignment = assignment_records[0]
            check = cover_check_records[0]
            if any(assignment.get(field) != check.get(field) for field in ("templateKey", "revision")):
                errors.append("测试图分配与轻量封面检查回执身份不一致")
        if assignment_records and interpretation_records and visual_gate_records:
            assignment = assignment_records[0]
            interpretation = interpretation_records[0]
            visual_gate = visual_gate_records[0]
            if any(assignment.get(field) != visual_gate.get(field) for field in ("templateKey", "revision")):
                errors.append("测试图分配与独立视觉验收回执身份不一致")
            if assignment.get("templateKey") != interpretation.get("templateKey"):
                errors.append("测试图分配与参考图语义解释身份不一致")
            if len(covers) == 1 and visual_gate.get("coverSha256") != hashlib.sha256(covers[0].read_bytes()).hexdigest():
                errors.append("独立视觉验收 coverSha256 与封面不一致")
            if reference_interpretations and visual_gate.get("referenceInterpretationSha256") != hashlib.sha256(reference_interpretations[0].read_bytes()).hexdigest():
                errors.append("独立视觉验收与参考图语义解释摘要不一致")
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
        if approval_records and assignment_records:
            approval = approval_records[0]
            assignment = assignment_records[0]
            if any(approval.get(field) != assignment.get(field) for field in ("deliverySetId", "templateKey", "revision", "assetId")):
                errors.append("审核决定回执与测试图分配身份不一致")
            if assignment.get("status") == "consumed" and approval.get("verdict") != "pass":
                errors.append("已消费测试图必须对应人工通过回执")
            decision = assignment.get("decision") if isinstance(assignment.get("decision"), dict) else {}
            if assignment.get("status") in {"consumed", "released"}:
                if any(
                    approval.get(field) != decision.get(field)
                    for field in ("verdict", "decidedAt", "reason", "coverSha256", "promptSha256")
                ):
                    errors.append("审核决定回执与测试图终态证据不一致")
            if len(covers) == 1 and approval.get("coverSha256") != hashlib.sha256(covers[0].read_bytes()).hexdigest():
                errors.append("审核决定 coverSha256 与封面不一致")
            template = template_records.get(str(assignment.get("templateKey")), {})
            prompt = template.get("promptTemplate") if isinstance(template, dict) else None
            if isinstance(prompt, str) and approval.get("promptSha256") != hashlib.sha256(prompt.encode("utf-8")).hexdigest():
                errors.append("审核决定 promptSha256 与模板不一致")
        if profile == "final-package" and manifest_v5_final and len(approval_records) != 1:
            errors.append("v5 final-package 必须包含唯一人工审核决定回执")
        if profile == "final-package" and manifest_schema_versions.intersection({"5.0.0", "5.1.0", "6.0.0"}) and len(experience_receipts) != 1:
            errors.append("v6 final-package 必须包含唯一经验沉淀回执")
        if profile == "final-package" and manifest_schema_versions.intersection({"5.1.0", "6.0.0"}) and len(dynamic_baseline_receipts) != 1:
            errors.append("v6 final-package 必须包含唯一动态基线登记回执")
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
        choices=["legacy", "authoring", "release", "fast-package", "prepublish", "review-package", "final-package"],
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
