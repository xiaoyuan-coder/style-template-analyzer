#!/usr/bin/env python3
"""Audit active approved style-template revisions against the v8 After gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image

from style_atomic import atomic_write_json
from style_effect_contract import validate_effect_contract
from validate_style_template import validate_data as validate_template


REPORT_ARTIFACT_TYPE = "approved_after_gate_audit_report"
REPORT_SCHEMA_VERSION = "1.0.0"
PRODUCER = "style-template-analyzer"
SKILL_VERSION = "8.1.0"
PROMPT_ONLY_GATE_VERSION = "8.0.0"
SHA_RE = re.compile(r"^[a-f0-9]{64}$")
INTEGRITY_CODES = {
    "CATALOG_TEMPLATE_MISSING",
    "CATALOG_EFFECT_MISSING",
    "CATALOG_TEMPLATE_HASH_MISMATCH",
    "CATALOG_EFFECT_HASH_MISMATCH",
    "APPROVAL_EVIDENCE_MISSING",
    "APPROVAL_NOT_HUMAN_PASS",
    "SOURCE_ASSIGNMENT_MISSING",
    "SOURCE_ASSET_UNRESOLVED",
    "SOURCE_FILE_MISSING",
    "SOURCE_HASH_MISMATCH",
}
DRIFT_CODES = {
    "APPROVAL_PROMPT_HASH_MISMATCH",
    "APPROVAL_EFFECT_HASH_MISMATCH",
    "GENERATION_REQUEST_PROMPT_DRIFT",
    "GENERATION_REQUEST_SOURCE_DRIFT",
    "GENERATION_RECEIPT_PROMPT_DRIFT",
    "GENERATION_RECEIPT_SOURCE_DRIFT",
    "FRAME_BOUNDARY_CONFLICT",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def resolve_business_path(value: object, *, catalog_root: Path, data_root: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    if candidate.parts and candidate.parts[0] in {
        "05-风格化模板生产",
        "06-模板质量评测",
        "07-数据验收与上线",
    }:
        return (data_root / candidate).resolve()
    return (catalog_root / candidate).resolve()


def batch_name(item: dict[str, Any]) -> str:
    for field in ("sourcePackage", "approvalEvidence"):
        value = item.get(field)
        if not isinstance(value, str):
            continue
        parts = Path(value).parts
        if "06-待验收模板" in parts:
            index = parts.index("06-待验收模板")
            if len(parts) > index + 1:
                return parts[index + 1]
    provenance = item.get("approvalProvenance")
    if provenance == "legacy-delivery-confirmed":
        return "2026-08-13-94个风格模板与效果图"
    return "独立人工通过记录"


def build_pool_index(pool_root: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for file in sorted(pool_root.rglob("pool.json")):
        try:
            data = read_json(file)
        except (OSError, ValueError):
            continue
        for asset in data.get("assets", []) if isinstance(data, dict) else []:
            if isinstance(asset, dict) and isinstance(asset.get("assetId"), str):
                result[asset["assetId"]].append(dict(asset, poolFile=file.as_posix()))
    return result


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.is_file():
            return path
    return None


def image_geometry(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        with Image.open(path) as image:
            width, height = image.size
    except OSError:
        return None
    ratio = width / height
    if abs(ratio - 1) <= 0.03:
        orientation = "square"
    elif ratio > 1:
        orientation = "landscape"
    else:
        orientation = "portrait"
    return {"width": width, "height": height, "aspectRatio": round(ratio, 6), "orientation": orientation}


def prompt_inherits_frame(prompt: str) -> bool:
    return (
        any(marker in prompt for marker in ("画幅方向", "横竖方向", "画布方向"))
        and any(marker in prompt for marker in ("宽高比", "纵横比"))
        and any(marker in prompt for marker in ("跟随用户", "继承用户", "保持用户", "与用户上传图一致"))
    )


def frame_conflict(prompt: str, before: dict[str, Any] | None, after: dict[str, Any] | None) -> bool:
    if not prompt_inherits_frame(prompt) or before is None or after is None:
        return False
    ratio_delta = abs(math.log(after["aspectRatio"] / before["aspectRatio"]))
    orientations = {before["orientation"], after["orientation"]}
    orientation_changed = before["orientation"] != after["orientation"] and "square" not in orientations
    return orientation_changed or ratio_delta > 0.12


def source_asset(
    asset_id: str,
    pool_index: dict[str, list[dict[str, Any]]],
    generation_request: dict[str, Any] | None,
) -> tuple[Path | None, str, str]:
    if generation_request:
        value = generation_request.get("inputPath")
        digest = generation_request.get("inputSha256")
        if isinstance(value, str) and value:
            return Path(value), str(digest or ""), "generation-request"
    assets = pool_index.get(asset_id, [])
    assets = sorted(assets, key=lambda item: not Path(str(item.get("localPath", ""))).is_file())
    if assets:
        return Path(str(assets[0].get("localPath", ""))), str(assets[0].get("sha256", "")), "test-image-pool"
    return None, "", "unresolved"


def internal_directories(template_path: Path | None, source_package: Path | None, approval: Path | None) -> list[Path]:
    result: list[Path] = []
    if template_path is not None and template_path.parent.name == "package":
        result.append(template_path.parent.parent / "internal")
    if source_package is not None:
        result.append(source_package.parent / "internal")
    if approval is not None:
        result.append(approval.parent)
    unique: list[Path] = []
    for path in result:
        if path not in unique:
            unique.append(path)
    return unique


def add_issue(issues: list[dict[str, str]], code: str, message: str) -> None:
    if not any(item["code"] == code for item in issues):
        issues.append({"code": code, "message": message})


def audit_item(
    item: dict[str, Any],
    *,
    catalog_root: Path,
    data_root: Path,
    pool_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    template_path = resolve_business_path(item.get("template"), catalog_root=catalog_root, data_root=data_root)
    effect_path = resolve_business_path(item.get("effectImage"), catalog_root=catalog_root, data_root=data_root)
    approval_path = resolve_business_path(item.get("approvalEvidence"), catalog_root=catalog_root, data_root=data_root)
    source_package = resolve_business_path(item.get("sourcePackage"), catalog_root=catalog_root, data_root=data_root)

    if template_path is None or not template_path.is_file():
        add_issue(issues, "CATALOG_TEMPLATE_MISSING", "统一通过索引指向的 style-template.json 不存在。")
    if effect_path is None or not effect_path.is_file():
        add_issue(issues, "CATALOG_EFFECT_MISSING", "统一通过索引指向的 Approved After 不存在。")

    template: dict[str, Any] = {}
    prompt = ""
    prompt_sha = ""
    if template_path and template_path.is_file():
        try:
            value = read_json(template_path)
            template = value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            add_issue(issues, "TEMPLATE_JSON_INVALID", "style-template.json 无法解析。")
        prompt = str(template.get("promptTemplate", ""))
        prompt_sha = sha256_text(prompt) if prompt else ""
        expected = item.get("templateSha256")
        if isinstance(expected, str) and SHA_RE.fullmatch(expected) and sha256_file(template_path) != expected:
            add_issue(issues, "CATALOG_TEMPLATE_HASH_MISMATCH", "模板文件与统一通过索引的 SHA 不一致。")
        cover = str(template.get("cover", ""))
        domain = urlparse(cover).hostname or ""
        mode = "remote" if domain else "local"
        template_errors = validate_template(template, template_path, mode, domain, "")
        if template_errors:
            add_issue(issues, "PROMPT_SCHEMA_FAILED", f"当前运行 JSON 未通过 v8 提示词门槛，共 {len(template_errors)} 项。")
    else:
        template_errors = []

    effect_sha = ""
    if effect_path and effect_path.is_file():
        effect_sha = sha256_file(effect_path)
        expected = item.get("effectSha256")
        if isinstance(expected, str) and SHA_RE.fullmatch(expected) and effect_sha != expected:
            add_issue(issues, "CATALOG_EFFECT_HASH_MISMATCH", "Approved After 与统一通过索引的 SHA 不一致。")

    approval: dict[str, Any] | None = None
    if approval_path is None or not approval_path.is_file():
        add_issue(issues, "APPROVAL_EVIDENCE_MISSING", "人工通过回执缺失。")
    else:
        try:
            value = read_json(approval_path)
            approval = value if isinstance(value, dict) else None
        except (OSError, ValueError):
            approval = None
        if not approval or approval.get("verdict") != "pass" or approval.get("authority") != "human":
            add_issue(issues, "APPROVAL_NOT_HUMAN_PASS", "回执未证明 human pass。")
        elif prompt_sha and approval.get("promptSha256") != prompt_sha:
            add_issue(issues, "APPROVAL_PROMPT_HASH_MISMATCH", "人工通过冻结的 prompt SHA 与当前 JSON 不一致。")
        if approval and effect_sha and approval.get("coverSha256") != effect_sha:
            add_issue(issues, "APPROVAL_EFFECT_HASH_MISMATCH", "人工通过冻结的 cover SHA 与当前 Approved After 不一致。")

    internals = internal_directories(template_path, source_package, approval_path)
    assignment_file = first_existing([path / "test-image-assignment.json" for path in internals])
    receipt_file = first_existing([path / "cover-generation-receipt.json" for path in internals])
    request_file = first_existing([path / "generation-request.json" for path in internals])
    contract_file = first_existing([path / "effect-reproduction-contract.json" for path in internals])
    assignment = read_json(assignment_file) if assignment_file else None
    receipt = read_json(receipt_file) if receipt_file else None
    request = read_json(request_file) if request_file else None
    asset_id = ""
    for candidate in (assignment, receipt, approval):
        if isinstance(candidate, dict) and isinstance(candidate.get("assetId"), str):
            asset_id = candidate["assetId"]
            break
    if not assignment_file:
        add_issue(issues, "SOURCE_ASSIGNMENT_MISSING", "测试图分配回执缺失。")

    source_path, source_expected_sha, source_origin = source_asset(asset_id, pool_index, request if isinstance(request, dict) else None)
    source_sha = ""
    if not asset_id or source_path is None:
        add_issue(issues, "SOURCE_ASSET_UNRESOLVED", "无法从分配、生成请求或测试图池恢复 Approved Before。")
    elif not source_path.is_file():
        add_issue(issues, "SOURCE_FILE_MISSING", "Approved Before 文件已缺失。")
    else:
        source_sha = sha256_file(source_path)
        if SHA_RE.fullmatch(source_expected_sha) and source_sha != source_expected_sha:
            add_issue(issues, "SOURCE_HASH_MISMATCH", "Approved Before 文件与登记 SHA 不一致。")

    if isinstance(request, dict):
        request_prompt = request.get("promptTemplate")
        request_prompt_sha = request.get("promptSha256")
        if isinstance(request_prompt, str):
            calculated = sha256_text(request_prompt)
            if request_prompt_sha != calculated or calculated != prompt_sha:
                add_issue(issues, "GENERATION_REQUEST_PROMPT_DRIFT", "生成请求中的 prompt 与当前正式 JSON 不一致。")
        elif request_prompt_sha != prompt_sha:
            add_issue(issues, "GENERATION_REQUEST_PROMPT_DRIFT", "生成请求的 prompt SHA 与当前正式 JSON 不一致。")
        if source_sha and request.get("inputSha256") != source_sha:
            add_issue(issues, "GENERATION_REQUEST_SOURCE_DRIFT", "生成请求的源图 SHA 与已恢复 Before 不一致。")
    else:
        add_issue(issues, "GENERATION_REQUEST_MISSING", "缺少可核对的生成请求。")

    receipt_v2_ready = False
    if not isinstance(receipt, dict) or receipt.get("schemaVersion") != "2.0.0":
        add_issue(issues, "GENERATION_RECEIPT_V2_MISSING", "生成回执未升级到 2.0.0，无法证明最终 prompt、单图输入和 After 未入参。")
    else:
        receipt_v2_ready = True
        if receipt.get("submittedPromptSha256") != prompt_sha:
            add_issue(issues, "GENERATION_RECEIPT_PROMPT_DRIFT", "生成回执的实际 prompt SHA 与当前 JSON 不一致。")
        if source_sha and receipt.get("sourceSha256") != source_sha:
            add_issue(issues, "GENERATION_RECEIPT_SOURCE_DRIFT", "生成回执的源图 SHA 与 Before 不一致。")
        if receipt.get("inputImageCount") != 1:
            add_issue(issues, "SINGLE_INPUT_UNPROVEN", "生成回执未证明单图输入。")
        if receipt.get("approvedAfterUsedAsInput") is not False:
            add_issue(issues, "AFTER_INPUT_PROHIBITION_UNPROVEN", "生成回执未证明 Approved After 没有进入图片输入。")

    contract_ready = False
    contract_errors: list[str] = []
    if contract_file is None:
        add_issue(issues, "EFFECT_CONTRACT_MISSING", "缺少十四项 effect-reproduction-contract.json。")
    else:
        try:
            contract = read_json(contract_file)
            contract_errors = validate_effect_contract(
                contract,
                expected_key=str(item.get("key", "")),
                prompt_template=prompt,
            )
        except (OSError, ValueError):
            contract_errors = ["合同 JSON 无法解析"]
        if contract_errors:
            add_issue(issues, "EFFECT_CONTRACT_INVALID", f"效果复现合同无效，共 {len(contract_errors)} 项。")
        else:
            contract_ready = True

    before_geometry = image_geometry(source_path)
    after_geometry = image_geometry(effect_path)
    if frame_conflict(prompt, before_geometry, after_geometry):
        add_issue(issues, "FRAME_BOUNDARY_CONFLICT", "prompt 声明继承源画幅，Approved After 的方向或比例却明显改变。")

    codes = {issue["code"] for issue in issues}
    if codes.intersection(INTEGRITY_CODES):
        gate_status = "blocked-evidence-recovery"
        priority = 0
    elif codes.intersection(DRIFT_CODES):
        gate_status = "known-boundary-or-prompt-drift"
        priority = 1
    elif not receipt_v2_ready or not contract_ready or "PROMPT_SCHEMA_FAILED" in codes:
        gate_status = "replay-and-contract-migration-required"
        priority = 2
    else:
        gate_status = "gate-ready"
        priority = 3

    return {
        "key": item.get("key"),
        "title": item.get("title"),
        "revision": item.get("revision"),
        "batch": batch_name(item),
        "approvalProvenance": item.get("approvalProvenance"),
        "ossStatus": item.get("ossStatus"),
        "gateStatus": gate_status,
        "priority": priority,
        "paths": {
            "template": template_path.as_posix() if template_path else None,
            "approvedAfter": effect_path.as_posix() if effect_path else None,
            "approvedBefore": source_path.as_posix() if source_path else None,
            "approvalEvidence": approval_path.as_posix() if approval_path else None,
            "generationRequest": request_file.as_posix() if request_file else None,
            "generationReceipt": receipt_file.as_posix() if receipt_file else None,
            "effectContract": contract_file.as_posix() if contract_file else None,
        },
        "evidence": {
            "promptSha256": prompt_sha or None,
            "sourceSha256": source_sha or None,
            "effectSha256": effect_sha or None,
            "sourceOrigin": source_origin,
            "receiptSchemaVersion": receipt.get("schemaVersion") if isinstance(receipt, dict) else None,
            "effectContractReady": contract_ready,
            "beforeGeometry": before_geometry,
            "afterGeometry": after_geometry,
        },
        "promptValidationErrors": template_errors,
        "effectContractErrors": contract_errors,
        "issues": sorted(issues, key=lambda value: value["code"]),
    }


def markdown_summary(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 187 个活动已通过风格模板·v8 新门禁审计",
        "",
        f"- 审计时间：{report['auditedAt']}",
        f"- 权威目录：`{report['catalog']}`",
        f"- 活动模板：{summary['total']} 个；已退役模板不在本次范围。",
        "- 本报告只评估 v8 复现证据完整性，保留历史人工通过事实，不自动退役或覆盖正式包。",
        "",
        "## 总体结果",
        "",
        "| 新门禁状态 | 数量 | 处置 |",
        "| --- | ---: | --- |",
    ]
    labels = {
        "blocked-evidence-recovery": "证据恢复受阻",
        "known-boundary-or-prompt-drift": "已知边界或 prompt 漂移",
        "replay-and-contract-migration-required": "需原图回放与合同迁移",
        "gate-ready": "已通过 v8 门禁",
    }
    actions = {
        "blocked-evidence-recovery": "先恢复 Before、After、通过回执或哈希链。",
        "known-boundary-or-prompt-drift": "优先重编 prompt 和十四项边界，再回放。",
        "replay-and-contract-migration-required": "编译效果合同，用最终 prompt 原图回放和换图迁移。",
        "gate-ready": "可保留当前 revision。",
    }
    for status in labels:
        lines.append(f"| {labels[status]} | {summary['statusCounts'].get(status, 0)} | {actions[status]} |")
    lines.extend(["", "## 逐批结果", "", "| 批次 | 总数 | 证据受阻 | 已知漂移 | 待回放迁移 | 通过 v8 |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for batch in report["batches"]:
        counts = batch["statusCounts"]
        lines.append(
            f"| {batch['batch']} | {batch['total']} | {counts.get('blocked-evidence-recovery', 0)} | "
            f"{counts.get('known-boundary-or-prompt-drift', 0)} | "
            f"{counts.get('replay-and-contract-migration-required', 0)} | {counts.get('gate-ready', 0)} |"
        )
    lines.extend(["", "## 高频问题", ""])
    for code, count in summary["issueCounts"][:20]:
        lines.append(f"- `{code}`：{count}")
    lines.extend([
        "",
        "## 迁移顺序",
        "",
        "1. P0：恢复缺失或不一致的源图、After、回执和 SHA。",
        "2. P1：修复已确认的 prompt 漂移与画幅边界冲突。",
        "3. P2：按批次编译十四项复现合同，执行原图回放与换图迁移。",
        "4. 人工再确认后，用新 revision 发布；历史 revision 保留为审计证据。",
        "",
    ])
    return "\n".join(lines)


def safe_filename(index: int, value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "-", value).strip(" .")
    return f"{index:02d}-{cleaned or 'unknown'}"


def write_reports(output: Path, report: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output / "audit-results.json", report)
    (output / "summary.md").write_text(markdown_summary(report), encoding="utf-8")
    batch_root = output / "batches"
    for index, batch in enumerate(report["batches"], 1):
        name = safe_filename(index, batch["batch"])
        rows = [item for item in report["items"] if item["batch"] == batch["batch"]]
        artifact = {
            "artifactType": "approved_after_gate_batch_audit",
            "schemaVersion": REPORT_SCHEMA_VERSION,
            "producer": PRODUCER,
            "batch": batch["batch"],
            "summary": batch,
            "items": rows,
        }
        atomic_write_json(batch_root / f"{name}.json", artifact)
        lines = [
            f"# {batch['batch']}",
            "",
            f"共 {batch['total']} 个活动已通过模板。",
            "",
            "| P | key | revision | v8 状态 | 主要问题 |",
            "| ---: | --- | ---: | --- | --- |",
        ]
        for item in sorted(rows, key=lambda value: (value["priority"], str(value["key"]))):
            codes = ", ".join(issue["code"] for issue in item["issues"][:5])
            lines.append(f"| {item['priority']} | `{item['key']}` | {item['revision']} | {item['gateStatus']} | {codes} |")
        lines.append("")
        (batch_root / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")

    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "artifact-manifest.json")
    manifest = {
        "artifactType": REPORT_ARTIFACT_TYPE,
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "producer": PRODUCER,
        "skillVersion": SKILL_VERSION,
        "gateVersion": PROMPT_ONLY_GATE_VERSION,
        "auditedAt": report["auditedAt"],
        "catalog": report["catalog"],
        "catalogSha256": report["catalogSha256"],
        "templateCount": report["summary"]["total"],
        "statusCounts": report["summary"]["statusCounts"],
        "files": [
            {"path": path.relative_to(output).as_posix(), "sha256": sha256_file(path)}
            for path in files
        ],
    }
    atomic_write_json(output / "artifact-manifest.json", manifest)


def audit_catalog(catalog: Path, data_root: Path, pool_root: Path) -> dict[str, Any]:
    catalog_data = read_json(catalog)
    items = catalog_data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("catalog.items must be an array")
    pool_index = build_pool_index(pool_root)
    audited = [
        audit_item(item, catalog_root=catalog.parent, data_root=data_root, pool_index=pool_index)
        for item in items if isinstance(item, dict)
    ]
    status_counts = Counter(item["gateStatus"] for item in audited)
    issue_counts = Counter(issue["code"] for item in audited for issue in item["issues"])
    by_batch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in audited:
        by_batch[item["batch"]].append(item)
    batches = []
    for name, rows in sorted(by_batch.items()):
        batches.append({
            "batch": name,
            "total": len(rows),
            "statusCounts": dict(sorted(Counter(row["gateStatus"] for row in rows).items())),
            "provenanceCounts": dict(sorted(Counter(str(row["approvalProvenance"]) for row in rows).items())),
        })
    return {
        "artifactType": REPORT_ARTIFACT_TYPE,
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "producer": PRODUCER,
        "skillVersion": SKILL_VERSION,
        "gateVersion": PROMPT_ONLY_GATE_VERSION,
        "auditedAt": datetime.now(timezone.utc).isoformat(),
        "catalog": catalog.resolve().as_posix(),
        "catalogSha256": sha256_file(catalog),
        "dataRoot": data_root.resolve().as_posix(),
        "scope": "active-approved-revisions-only",
        "summary": {
            "total": len(audited),
            "statusCounts": dict(sorted(status_counts.items())),
            "issueCounts": [[code, count] for code, count in issue_counts.most_common()],
        },
        "batches": batches,
        "items": sorted(audited, key=lambda value: (value["batch"], value["priority"], str(value["key"]))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--pool-root", type=Path)
    args = parser.parse_args()
    pool_root = args.pool_root or args.data_root / "06-模板质量评测" / "02-标准测试集"
    report = audit_catalog(args.catalog.resolve(), args.data_root.resolve(), pool_root.resolve())
    write_reports(args.output.resolve(), report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
