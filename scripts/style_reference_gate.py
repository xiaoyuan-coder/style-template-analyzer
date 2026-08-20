#!/usr/bin/env python3
"""Reference semantics and independent visual-comparison gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


CONTRACTS = Path(__file__).parents[1] / "contracts"
DIMENSIONS = (
    "imagingMedium",
    "shapeAndDetail",
    "linesAndEdges",
    "marksAndTexture",
    "colorOrganization",
    "compositionAndSpace",
)


def _schema_errors(data: object, filename: str) -> list[str]:
    schema = json.loads((CONTRACTS / filename).read_text(encoding="utf-8"))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(data),
            key=lambda item: list(item.absolute_path),
        )
    ]


def validate_reference_interpretation(data: object, *, expected_key: str = "") -> list[str]:
    errors = _schema_errors(data, "reference-interpretation.schema.json")
    if errors or not isinstance(data, dict):
        return errors
    if expected_key and data.get("templateKey") != expected_key:
        errors.append("templateKey 与模板不一致")
    roles = {
        role
        for image in data["sourceImages"]
        for role in image.get("roles", [])
    }
    reference_type = data["referenceType"]
    if reference_type != "single-style-reference":
        if data["extractionMode"] != "paired-difference":
            errors.append("成对参考图必须使用 paired-difference")
        if not {"before", "target-effect"}.issubset(roles):
            errors.append("成对参考图必须明确 before 与 target-effect 角色")
    elif "target-effect" not in roles:
        errors.append("单图参考必须明确 target-effect 角色")
    if reference_type in {"paired-comparison", "annotated-paired-comparison"}:
        if not data["excludedElements"]:
            errors.append("对比/标注参考图必须列出需要排除的解释性元素")
        if not roles.intersection({"annotation-ui", "explanatory-layout"}):
            errors.append("对比/标注参考图必须标记 annotation-ui 或 explanatory-layout")
    unauthorized = [
        item["name"]
        for item in data["templateConstants"]
        if item["category"] == "explanatory-element" and not item["explicitlyAuthorized"]
    ]
    if unauthorized:
        errors.append(f"解释性元素未获明确授权，不得进入模板常量：{', '.join(unauthorized)}")
    if data["ambiguities"]:
        errors.append("参考图仍有未消解歧义")
    return errors


def validate_visual_gate(data: object, *, analysis_producer: str = "") -> list[str]:
    errors = _schema_errors(data, "reference-visual-gate-receipt.schema.json")
    if errors or not isinstance(data, dict):
        return errors
    reviewer = data["reviewer"].strip()
    if reviewer in {"style-template-analyzer", analysis_producer.strip()}:
        errors.append("视觉验收 reviewer 必须独立于分析与提示词生产者")
    scores = data["scores"]
    if data["verdict"] == "pass":
        low = [name for name in DIMENSIONS if scores[name] < 80]
        average = sum(scores[name] for name in DIMENSIONS) / len(DIMENSIONS)
        if low:
            errors.append(f"pass 的单项分数不得低于 80：{', '.join(low)}")
        if average < 90:
            errors.append("pass 的六维平均分不得低于 90")
        if data["hardFailures"]:
            errors.append("存在 hardFailures 时不得 pass")
    return errors
