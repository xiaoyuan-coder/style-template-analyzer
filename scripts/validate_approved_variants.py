#!/usr/bin/env python3
"""Validate exact approved visual revisions before formal assignment and OSS."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from style_contracts import KEY_RE, SEMVER_RE
from validate_style_template import check_prompt


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, errors: list[str], label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{label} 无法读取：{error}")
        return None


def check_envelope(value: Any, artifact_type: str, label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} 必须是 object")
        return False
    if value.get("artifactType") != artifact_type:
        errors.append(f"{label}.artifactType 必须为 {artifact_type}")
    version = value.get("schemaVersion")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version) or not version.startswith("1."):
        errors.append(f"{label}.schemaVersion 必须是受支持的 1.x.x")
    producer = value.get("producer")
    if not isinstance(producer, str) or not producer.startswith("style-template-analyzer"):
        errors.append(f"{label}.producer 必须由 style-template-analyzer 声明")
    return True


def validate(approval_file: Path, compilation_file: Path) -> list[str]:
    errors: list[str] = []
    approval = read_json(approval_file, errors, "approval")
    compilation = read_json(compilation_file, errors, "compilation")
    if not check_envelope(approval, "style_template_visual_gate_decision", "approval", errors):
        return errors
    if not check_envelope(compilation, "style_template_approved_compilation_spec", "compilation", errors):
        return errors
    if approval.get("deliverySetId") != compilation.get("deliverySetId"):
        errors.append("deliverySetId 不一致")
    if approval.get("approvalRevision") != compilation.get("approvalRevision"):
        errors.append("approvalRevision 不一致")
    authorization = compilation.get("finalizationAuthorization")
    if not isinstance(authorization, str) or not authorization.strip():
        errors.append("compilation.finalizationAuthorization 缺失")

    decisions = approval.get("decisions")
    templates = compilation.get("templates")
    if not isinstance(decisions, list) or not all(isinstance(item, dict) for item in decisions):
        errors.append("approval.decisions 必须是 object 数组")
        decisions = []
    if not isinstance(templates, list) or not all(isinstance(item, dict) for item in templates):
        errors.append("compilation.templates 必须是 object 数组")
        templates = []
    passed = [item for item in decisions if item.get("verdict") == "pass"]
    if approval.get("approvedCount") != len(passed):
        errors.append("approval.approvedCount 与 pass 决策数不一致")
    if compilation.get("templateCount") != len(templates):
        errors.append("compilation.templateCount 与 templates 数量不一致")

    passed_by_key: dict[str, dict[str, Any]] = {}
    for item in passed:
        key = item.get("key")
        if not isinstance(key, str) or not KEY_RE.fullmatch(key):
            errors.append(f"approval pass key 无效：{key}")
            continue
        if key in passed_by_key:
            errors.append(f"approval pass key 重复：{key}")
        passed_by_key[key] = item
    compiled_by_key: dict[str, dict[str, Any]] = {}
    asset_ids: list[str] = []
    for item in templates:
        key = item.get("key")
        if not isinstance(key, str) or not KEY_RE.fullmatch(key):
            errors.append(f"compilation key 无效：{key}")
            continue
        if key in compiled_by_key:
            errors.append(f"compilation key 重复：{key}")
        compiled_by_key[key] = item
        asset_id = item.get("testAssetId")
        if not isinstance(asset_id, str) or not asset_id.strip():
            errors.append(f"{key}.testAssetId 缺失")
        else:
            asset_ids.append(asset_id)
    if set(passed_by_key) != set(compiled_by_key):
        errors.append("approval pass key 集合与 compilation key 集合不一致")
    if len(asset_ids) != len(set(asset_ids)):
        errors.append("compilation.testAssetId 在当前交付集内不唯一")

    for key in sorted(set(passed_by_key) & set(compiled_by_key)):
        decision = passed_by_key[key]
        item = compiled_by_key[key]
        if decision.get("index") != item.get("index"):
            errors.append(f"{key}.index 不一致")
        if decision.get("cover") != item.get("selectedCover"):
            errors.append(f"{key}.selectedCover 未指向用户批准的精确 revision")
        if decision.get("testAssetId") != item.get("testAssetId"):
            errors.append(f"{key}.testAssetId 与批准记录不一致")
        selected_variant = item.get("selectedVariant")
        if not isinstance(selected_variant, str) or not selected_variant.strip():
            errors.append(f"{key}.selectedVariant 缺失")
        variant_note = item.get("variantNote")
        if not isinstance(variant_note, str) or len(variant_note.strip()) < 8:
            errors.append(f"{key}.variantNote 需说明精确视觉 revision 的编译处置")
        for field in ("x", "y", "b", "c"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{key}.{field} 缺失")
        cover_hash = item.get("selectedCoverSha256")
        if not isinstance(cover_hash, str) or not SHA256_RE.fullmatch(cover_hash):
            errors.append(f"{key}.selectedCoverSha256 无效")
        cover_path = compilation_file.parent / str(item.get("selectedCover", ""))
        if not cover_path.is_file():
            errors.append(f"{key}.selectedCover 文件不存在：{cover_path}")
        elif isinstance(cover_hash, str) and sha256(cover_path) != cover_hash:
            errors.append(f"{key}.selectedCoverSha256 与实际文件不一致")
        prompt = item.get("promptTemplate")
        prompt_hash = item.get("promptSha256")
        prompt_errors: list[str] = []
        check_prompt(prompt_errors, prompt)
        errors.extend(f"{key}.{message}" for message in prompt_errors)
        if not isinstance(prompt_hash, str) or not SHA256_RE.fullmatch(prompt_hash):
            errors.append(f"{key}.promptSha256 无效")
        elif isinstance(prompt, str) and hashlib.sha256(prompt.encode("utf-8")).hexdigest() != prompt_hash:
            errors.append(f"{key}.promptSha256 与 promptTemplate 不一致")

    evidence = approval.get("selectionEvidence")
    if approval.get("decisionAuthority") == "user_attached_selection":
        if not isinstance(evidence, list):
            errors.append("user_attached_selection 需要 selectionEvidence")
        else:
            evidence_by_key = {item.get("matchedKey"): item for item in evidence if isinstance(item, dict)}
            for key, decision in passed_by_key.items():
                item = evidence_by_key.get(key)
                if not item:
                    errors.append(f"{key} 缺少附件匹配证据")
                elif item.get("matchedCover") != decision.get("cover"):
                    errors.append(f"{key} 附件匹配证据未指向批准 cover")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("approval", type=Path)
    parser.add_argument("compilation", type=Path)
    args = parser.parse_args()
    errors = validate(args.approval.resolve(), args.compilation.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    compilation = json.loads(args.compilation.read_text(encoding="utf-8"))
    print(json.dumps({
        "status": "pass",
        "deliverySetId": compilation["deliverySetId"],
        "approvedVariantCount": compilation["templateCount"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
