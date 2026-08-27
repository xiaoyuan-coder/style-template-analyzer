#!/usr/bin/env python3
"""Validate and bind Approved-After reproduction boundaries."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from style_atomic import atomic_write_json


CONTRACTS = Path(__file__).parents[1] / "contracts"
BOUNDARY_MODES = {
    "subject-selection": {"all-salient", "primary-subject", "recognition-anchor"},
    "identity-and-recognition": {"preserve", "preserve-anchors", "transform-form"},
    "base-instance-count": {"preserve", "source-derived-repeat", "fixed-template-repeat"},
    "pose-and-view": {"preserve", "source-derived", "template-directed"},
    "frame-orientation-and-aspect": {"inherit-source", "adaptive-reframe", "fixed-template"},
    "crop-and-unseen-completion": {
        "preserve-visible",
        "adaptive-crop",
        "allow-conservative-completion",
        "template-directed-completion"
    },
    "subject-scale-and-placement": {"preserve", "adaptive-range", "template-directed"},
    "environment": {"preserve", "simplify", "remove", "replace", "rebuild"},
    "composition": {"preserve", "source-derived-recompose", "template-constant"},
    "occlusion-and-depth": {"preserve", "source-derived", "template-directed"},
    "palette": {"preserve", "retain-source-anchors", "template-palette"},
    "detail-and-abstraction": {"preserve", "simplify", "semi-abstract", "abstract-dominant"},
    "geometry-and-proportion": {"preserve", "source-derived", "template-directed"},
    "text-symbols-and-fixed-objects": {"source-only", "remove", "template-constants-only"},
}
DIRECTIVE_INTERNAL_TERMS = (
    "Approved After",
    "promptDirective",
    "前文",
    "上述授权",
    "复现边界",
    "来源绑定",
    "边界策略",
    "执行来源逻辑",
)


def _validate_runtime_directive(value: object, path: str) -> list[str]:
    if not isinstance(value, str):
        return []
    errors: list[str] = []
    if len(value.strip()) > 120:
        errors.append(f"{path} 应是 120 字内、可直接执行的生图指令")
    matched = [term for term in DIRECTIVE_INTERNAL_TERMS if term in value]
    if matched:
        errors.append(f"{path} 含内部合同或悬空指代用语：{', '.join(matched)}")
    return errors


def _schema_errors(data: object) -> list[str]:
    schema = json.loads(
        (CONTRACTS / "effect-reproduction-contract.schema.json").read_text(encoding="utf-8")
    )
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(data),
            key=lambda item: list(item.absolute_path),
        )
    ]


def validate_effect_contract(
    data: object,
    *,
    expected_key: str = "",
    prompt_template: str = "",
) -> list[str]:
    errors = _schema_errors(data)
    if errors or not isinstance(data, dict):
        return errors
    if expected_key and data.get("templateKey") != expected_key:
        errors.append("templateKey 与模板不一致")
    decisions = data["boundaryDecisions"]
    dimensions = [item.get("dimension") for item in decisions]
    if len(dimensions) != len(set(dimensions)):
        errors.append("boundaryDecisions.dimension 不得重复")
    missing = set(BOUNDARY_MODES) - set(dimensions)
    extras = set(dimensions) - set(BOUNDARY_MODES)
    if missing:
        errors.append(f"boundaryDecisions 缺少边界：{', '.join(sorted(missing))}")
    if extras:
        errors.append(f"boundaryDecisions 包含未知边界：{', '.join(sorted(extras))}")
    for item in decisions:
        dimension = item.get("dimension")
        if dimension in BOUNDARY_MODES and item.get("mode") not in BOUNDARY_MODES[dimension]:
            errors.append(f"{dimension}.mode 不合法：{item.get('mode')}")
        directive = item.get("promptDirective")
        errors.extend(_validate_runtime_directive(directive, f"{dimension}.promptDirective"))
        if prompt_template and isinstance(directive, str) and directive not in prompt_template:
            errors.append(f"{dimension}.promptDirective 未进入 promptTemplate 的对应运行段落")
    for item in data["templateConstants"]:
        directive = item.get("promptDirective")
        errors.extend(_validate_runtime_directive(
            directive,
            f"模板常量 {item.get('name')}.promptDirective",
        ))
        if item.get("required") and prompt_template and isinstance(directive, str) and directive not in prompt_template:
            errors.append(f"模板常量 {item.get('name')}.promptDirective 未进入 promptTemplate 的对应运行段落")
    binding = data["evidenceBinding"]
    if prompt_template:
        expected_prompt = hashlib.sha256(prompt_template.encode("utf-8")).hexdigest()
        if binding.get("promptSha256") != expected_prompt:
            errors.append("evidenceBinding.promptSha256 与 promptTemplate 不一致")
    return errors


def validate_effect_contract_draft(
    data: object,
    *,
    expected_key: str,
    prompt_template: str,
) -> list[str]:
    if not isinstance(data, dict):
        return ["effectContract 必须是 object"]
    candidate = copy.deepcopy(data)
    candidate["templateKey"] = expected_key
    candidate["evidenceBinding"] = {
        "sourceAssetId": "pending-source",
        "sourceSha256": "0" * 64,
        "effectSha256": "0" * 64,
        "promptSha256": hashlib.sha256(prompt_template.encode("utf-8")).hexdigest(),
        "generationMode": "single-image-prompt-only",
        "approvedAfterUsedAsInput": False,
    }
    return validate_effect_contract(
        candidate,
        expected_key=expected_key,
        prompt_template=prompt_template,
    )


def bind_effect_contract(
    draft: dict[str, Any],
    *,
    template_key: str,
    prompt_template: str,
    source_asset_id: str,
    source_sha256: str,
    effect_sha256: str,
) -> dict[str, Any]:
    bound = copy.deepcopy(draft)
    bound["templateKey"] = template_key
    bound["evidenceBinding"] = {
        "sourceAssetId": source_asset_id,
        "sourceSha256": source_sha256,
        "effectSha256": effect_sha256,
        "promptSha256": hashlib.sha256(prompt_template.encode("utf-8")).hexdigest(),
        "generationMode": "single-image-prompt-only",
        "approvedAfterUsedAsInput": False,
    }
    errors = validate_effect_contract(
        bound,
        expected_key=template_key,
        prompt_template=prompt_template,
    )
    if errors:
        raise ValueError("; ".join(errors))
    return bound


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path)
    parser.add_argument("template", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("effect", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-asset-id", required=True)
    args = parser.parse_args()
    draft = json.loads(args.draft.read_text(encoding="utf-8"))
    template = json.loads(args.template.read_text(encoding="utf-8"))
    prompt_template = template.get("promptTemplate")
    template_key = template.get("key")
    if not isinstance(prompt_template, str) or not isinstance(template_key, str):
        raise SystemExit("template must contain key and promptTemplate")
    bound = bind_effect_contract(
        draft,
        template_key=template_key,
        prompt_template=prompt_template,
        source_asset_id=args.source_asset_id,
        source_sha256=sha256_file(args.source),
        effect_sha256=sha256_file(args.effect),
    )
    atomic_write_json(args.output, bound)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
