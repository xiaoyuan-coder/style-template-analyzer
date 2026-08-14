#!/usr/bin/env python3
"""Validate 2.0 whole-image visual reconstruction analyses."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


KEY_RE = re.compile(r"^[a-z][a-z0-9-]{1,59}$")
REQUIRED_FIELDS = {
    "schemaVersion",
    "templateKey",
    "referenceAsset",
    "referenceType",
    "extractionMode",
    "referenceContentInventory",
    "transformationContract",
    "renderingFingerprint",
    "signatureMechanisms",
    "referenceContentBlocklist",
    "classificationConfidence",
    "qualityStatus",
}
ALLOWED_FIELDS = REQUIRED_FIELDS | {"salvagePlan", "reviewNotes", "garmentPrintClassification"}
REFERENCE_TYPES = {
    "single-style-reference",
    "paired-images",
    "paired-comparison",
    "annotated-paired-comparison",
}
EXTRACTION_MODES = {
    "direct-reconstruction",
    "paired-difference",
    "hybrid-operator-salvage",
    "low-information-salvage",
}
SALVAGE_MODES = {"hybrid-operator-salvage", "low-information-salvage"}
QUALITY_STATUSES = {"usable", "salvaged", "unusable"}
RENDERING_DIMENSIONS = {
    "imagingMedium",
    "shapeAndDetail",
    "linesAndEdges",
    "marksAndTexture",
    "colorOrganization",
    "toneAndSpace",
    "globalCoverage",
}
TRANSFORMATION_FAMILIES = {
    "drawing-style",
    "material-craft",
    "subject-form",
    "visual-system",
    "information-expression",
    "composition-structure",
}
MECHANISM_FAMILIES = TRANSFORMATION_FAMILIES | {"rendering"}
CONTRACT_FIELDS = {
    "families",
    "subjectSelection",
    "subjectForm",
    "poseAndView",
    "instanceMode",
    "environmentMode",
    "compositionMode",
    "contentInvariants",
    "templateConstants",
    "allowedDerivations",
    "textPolicy",
    "framePolicy",
    "renderingTarget",
}
CONTENT_INVARIANTS = {
    "subject-set",
    "subject-features",
    "associated-objects",
    "key-relationships",
    "source-frame",
}
DERIVATIONS = {
    "local-enlargement",
    "feature-statistics",
    "subject-repetition",
    "new-viewpoint",
    "new-action",
    "environment-reconstruction",
    "composition-reorganization",
}
TEXT_POLICY_FIELDS = {"subjectText", "environmentText", "templateText"}
SALVAGE_FIELDS = {
    "sourceDependency",
    "observedOperators",
    "nonPhotographicCarrier",
    "coverageExpansion",
    "uncertainty",
}
SOURCE_DEPENDENCIES = {
    "partial-photographic",
    "dominant-photographic",
    "overlay-dependent",
    "layout-dependent",
    "near-empty",
}
GARMENT_CLASSIFICATION_FIELDS = {
    "userFacingCategory",
    "designProduct",
    "renderingMedium",
    "subjectTreatment",
    "visualSystem",
    "layoutStructure",
    "printReadiness",
    "deanalysisRequired",
}
USER_FACING_CATEGORIES = {"手绘", "版印", "漫画", "像素", "材质", "图形", "拼贴", "分镜", "界面"}
DESIGN_PRODUCTS = {"artwork", "emblem", "pattern", "panel-sequence", "interface-system", "analysis-board"}
SUBJECT_TREATMENTS = {"preserve-form", "stylize-form", "transform-form"}
VISUAL_SYSTEMS = {"none", "decorative-system", "interface-system", "analysis-system"}
LAYOUT_STRUCTURES = {
    "single-scene", "cutout-subject", "badge-or-sticker", "repeat-pattern",
    "narrative-panels", "decorative-collage", "ui-windows", "annotated-callouts",
}
PRINT_READINESS_LEVELS = {"A", "B", "C", "D"}


def check_text(errors: list[str], path: str, value: Any, minimum: int, maximum: int) -> None:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        errors.append(f"{path} 必须是长度 {minimum}-{maximum} 的非空字符串")


def check_text_list(
    errors: list[str], path: str, value: Any, minimum_items: int, maximum_items: int,
    *, maximum_length: int = 240,
) -> list[str]:
    if not isinstance(value, list) or not minimum_items <= len(value) <= maximum_items:
        errors.append(f"{path} 必须包含 {minimum_items}-{maximum_items} 项")
        return []
    normalized: list[str] = []
    for index, item in enumerate(value):
        check_text(errors, f"{path}[{index}]", item, 1, maximum_length)
        if isinstance(item, str):
            normalized.append(item.strip())
    if len(normalized) != len(set(normalized)):
        errors.append(f"{path} 含有重复项")
    return normalized


def check_enum_list(
    errors: list[str], path: str, value: Any, allowed: set[str], minimum: int, maximum: int
) -> set[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        errors.append(f"{path} 必须包含 {minimum}-{maximum} 项")
        return set()
    invalid = [item for item in value if item not in allowed]
    if invalid:
        errors.append(f"{path} 包含不合法值：{', '.join(map(str, invalid))}")
    if len(value) != len(set(value)):
        errors.append(f"{path} 含有重复项")
    return {item for item in value if isinstance(item, str) and item in allowed}


def check_contract(errors: list[str], value: Any) -> tuple[set[str], set[str], set[str]]:
    if not isinstance(value, dict):
        errors.append("transformationContract 必须是 object")
        return set(), set(), set()
    extras = set(value) - CONTRACT_FIELDS
    missing = CONTRACT_FIELDS - set(value)
    if extras:
        errors.append(f"transformationContract 包含未知字段：{', '.join(sorted(extras))}")
    for field in sorted(missing):
        errors.append(f"transformationContract.{field} 缺失")

    families = check_enum_list(
        errors, "transformationContract.families", value.get("families"), TRANSFORMATION_FAMILIES, 1, 6
    )
    if value.get("subjectSelection") not in {"all-salient", "primary-subject"}:
        errors.append("transformationContract.subjectSelection 不合法")
    if value.get("subjectForm") not in {"preserve", "transform"}:
        errors.append("transformationContract.subjectForm 不合法")
    if value.get("poseAndView") not in {"preserve", "derive"}:
        errors.append("transformationContract.poseAndView 不合法")
    if value.get("instanceMode") not in {"preserve", "repeat-or-split"}:
        errors.append("transformationContract.instanceMode 不合法")
    if value.get("environmentMode") not in {"preserve", "simplify", "remove", "replace", "rebuild"}:
        errors.append("transformationContract.environmentMode 不合法")
    if value.get("compositionMode") not in {"preserve", "reorganize"}:
        errors.append("transformationContract.compositionMode 不合法")

    invariants = check_enum_list(
        errors, "transformationContract.contentInvariants", value.get("contentInvariants"), CONTENT_INVARIANTS, 5, 5
    )
    if invariants != CONTENT_INVARIANTS:
        errors.append("transformationContract.contentInvariants 必须完整包含五项全局不变量")
    constants = set(
        check_text_list(
            errors, "transformationContract.templateConstants", value.get("templateConstants"), 0, 12,
            maximum_length=160,
        )
    )
    derivations = check_enum_list(
        errors, "transformationContract.allowedDerivations", value.get("allowedDerivations"), DERIVATIONS, 0, 7
    )

    text_policy = value.get("textPolicy")
    if not isinstance(text_policy, dict) or set(text_policy) != TEXT_POLICY_FIELDS:
        errors.append("transformationContract.textPolicy 必须且只能包含三个文字策略字段")
    else:
        if text_policy.get("subjectText") != "preserve-when-legible":
            errors.append("transformationContract.textPolicy.subjectText 必须为 preserve-when-legible")
        if text_policy.get("environmentText") not in {"preserve", "remove-with-environment"}:
            errors.append("transformationContract.textPolicy.environmentText 不合法")
        if text_policy.get("templateText") not in {"none", "template-specific"}:
            errors.append("transformationContract.textPolicy.templateText 不合法")
    if value.get("framePolicy") != "inherit-source-aspect-ratio":
        errors.append("transformationContract.framePolicy 必须为 inherit-source-aspect-ratio")
    if value.get("renderingTarget") != "full-non-photographic-redraw":
        errors.append("transformationContract.renderingTarget 必须为 full-non-photographic-redraw")

    if value.get("subjectForm") == "transform" and "subject-form" not in families:
        errors.append("subjectForm=transform 必须启用 subject-form 家族")
    if "subject-form" in families and value.get("subjectForm") != "transform":
        errors.append("subject-form 家族必须配合 subjectForm=transform")
    if value.get("poseAndView") == "derive" and not derivations.intersection({"new-viewpoint", "new-action"}):
        errors.append("poseAndView=derive 必须授权 new-viewpoint 或 new-action")
    if value.get("poseAndView") == "preserve" and derivations.intersection({"new-viewpoint", "new-action"}):
        errors.append("poseAndView=preserve 不得授权新视角或新动作")
    if value.get("instanceMode") == "repeat-or-split" and "subject-repetition" not in derivations:
        errors.append("instanceMode=repeat-or-split 必须授权 subject-repetition")
    if value.get("instanceMode") == "preserve" and "subject-repetition" in derivations:
        errors.append("instanceMode=preserve 不得授权 subject-repetition")
    if value.get("environmentMode") != "preserve" and "environment-reconstruction" not in derivations:
        errors.append("环境发生变化时必须授权 environment-reconstruction")
    if value.get("environmentMode") == "preserve" and "environment-reconstruction" in derivations:
        errors.append("environmentMode=preserve 不得授权 environment-reconstruction")
    if value.get("compositionMode") == "reorganize" and "composition-reorganization" not in derivations:
        errors.append("compositionMode=reorganize 必须授权 composition-reorganization")
    if value.get("compositionMode") == "preserve" and "composition-reorganization" in derivations:
        errors.append("compositionMode=preserve 不得授权 composition-reorganization")
    return families, constants, derivations


def check_salvage(errors: list[str], data: dict[str, Any]) -> None:
    status = data.get("qualityStatus")
    mode = data.get("extractionMode")
    plan = data.get("salvagePlan")
    if status != "salvaged":
        if plan is not None:
            errors.append("salvagePlan 只允许用于 qualityStatus=salvaged")
        if mode in SALVAGE_MODES:
            errors.append("救援 extractionMode 必须配合 qualityStatus=salvaged")
        return
    if mode not in SALVAGE_MODES:
        errors.append("qualityStatus=salvaged 必须使用救援 extractionMode")
    if not isinstance(plan, dict):
        errors.append("qualityStatus=salvaged 必须提供 salvagePlan")
        return
    extras = set(plan) - SALVAGE_FIELDS
    if extras:
        errors.append(f"salvagePlan 包含未知字段：{', '.join(sorted(extras))}")
    for field in sorted(SALVAGE_FIELDS - set(plan)):
        errors.append(f"salvagePlan.{field} 缺失")
    if plan.get("sourceDependency") not in SOURCE_DEPENDENCIES:
        errors.append("salvagePlan.sourceDependency 不合法")
    minimum = 2 if mode == "low-information-salvage" else 3
    check_text_list(errors, "salvagePlan.observedOperators", plan.get("observedOperators"), minimum, 8)
    check_text(errors, "salvagePlan.nonPhotographicCarrier", plan.get("nonPhotographicCarrier"), 5, 500)
    check_text(errors, "salvagePlan.coverageExpansion", plan.get("coverageExpansion"), 5, 500)
    check_text(errors, "salvagePlan.uncertainty", plan.get("uncertainty"), 5, 500)


def check_garment_print_classification(errors: list[str], value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != GARMENT_CLASSIFICATION_FIELDS:
        errors.append("garmentPrintClassification 必须且只能包含八个分类字段")
        return
    if value.get("userFacingCategory") not in USER_FACING_CATEGORIES:
        errors.append("garmentPrintClassification.userFacingCategory 不合法")
    if value.get("designProduct") not in DESIGN_PRODUCTS:
        errors.append("garmentPrintClassification.designProduct 不合法")
    check_text(errors, "garmentPrintClassification.renderingMedium", value.get("renderingMedium"), 2, 80)
    if value.get("subjectTreatment") not in SUBJECT_TREATMENTS:
        errors.append("garmentPrintClassification.subjectTreatment 不合法")
    if value.get("visualSystem") not in VISUAL_SYSTEMS:
        errors.append("garmentPrintClassification.visualSystem 不合法")
    layout = value.get("layoutStructure")
    if layout not in LAYOUT_STRUCTURES:
        errors.append("garmentPrintClassification.layoutStructure 不合法")
    readiness = value.get("printReadiness")
    if readiness not in PRINT_READINESS_LEVELS:
        errors.append("garmentPrintClassification.printReadiness 不合法")
    deanalysis = value.get("deanalysisRequired")
    if not isinstance(deanalysis, bool):
        errors.append("garmentPrintClassification.deanalysisRequired 必须是 boolean")
    if layout == "annotated-callouts" and value.get("designProduct") != "analysis-board":
        errors.append("annotated-callouts 只能归入 analysis-board")
    if readiness == "C" and deanalysis is not True:
        errors.append("printReadiness=C 必须设置 deanalysisRequired=true")
    if readiness in {"A", "B"} and deanalysis is not False:
        errors.append("printReadiness=A/B 必须设置 deanalysisRequired=false")


def validate_data(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["根节点必须是 JSON object"]
    for field in sorted(REQUIRED_FIELDS - set(data)):
        errors.append(f"{field} 缺失")
    extras = set(data) - ALLOWED_FIELDS
    if extras:
        errors.append(f"未知字段：{', '.join(sorted(extras))}")
    if data.get("schemaVersion") != "2.0":
        errors.append("schemaVersion 必须为 2.0")
    key = data.get("templateKey")
    if not isinstance(key, str) or not KEY_RE.fullmatch(key):
        errors.append("templateKey 格式不合法")
    check_text(errors, "referenceAsset", data.get("referenceAsset"), 1, 1000)
    if data.get("referenceType") not in REFERENCE_TYPES:
        errors.append("referenceType 不合法")
    if data.get("extractionMode") not in EXTRACTION_MODES:
        errors.append("extractionMode 不合法")
    check_garment_print_classification(errors, data.get("garmentPrintClassification"))
    check_text_list(errors, "referenceContentInventory", data.get("referenceContentInventory"), 1, 100, maximum_length=120)
    blocklist = set(check_text_list(errors, "referenceContentBlocklist", data.get("referenceContentBlocklist"), 1, 100, maximum_length=120))

    families, constants, _ = check_contract(errors, data.get("transformationContract"))
    overlap = constants.intersection(blocklist)
    if overlap:
        errors.append(f"templateConstants 与 referenceContentBlocklist 互斥，发现重复项：{', '.join(sorted(overlap))}")

    fingerprint = data.get("renderingFingerprint")
    if not isinstance(fingerprint, dict):
        errors.append("renderingFingerprint 必须是 object")
    else:
        extras = set(fingerprint) - RENDERING_DIMENSIONS
        if extras:
            errors.append(f"renderingFingerprint 包含未知字段：{', '.join(sorted(extras))}")
        for dimension in sorted(RENDERING_DIMENSIONS):
            check_text(errors, f"renderingFingerprint.{dimension}", fingerprint.get(dimension), 5, 500)

    mechanisms = data.get("signatureMechanisms")
    if not isinstance(mechanisms, list) or not 3 <= len(mechanisms) <= 6:
        errors.append("signatureMechanisms 必须包含 3-6 项")
    else:
        for index, mechanism in enumerate(mechanisms):
            if not isinstance(mechanism, dict):
                errors.append(f"signatureMechanisms[{index}] 必须是 object")
                continue
            if set(mechanism) != {"family", "mechanism", "evidence"}:
                errors.append(f"signatureMechanisms[{index}] 字段不完整")
            family = mechanism.get("family")
            if family not in MECHANISM_FAMILIES:
                errors.append(f"signatureMechanisms[{index}].family 不合法")
            elif family != "rendering" and family not in families:
                errors.append(f"signatureMechanisms[{index}].family 未在 transformationContract.families 启用")
            check_text(errors, f"signatureMechanisms[{index}].mechanism", mechanism.get("mechanism"), 3, 200)
            check_text(errors, f"signatureMechanisms[{index}].evidence", mechanism.get("evidence"), 3, 300)

    confidence = data.get("classificationConfidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("classificationConfidence 必须在 0-1 之间")
    if data.get("qualityStatus") not in QUALITY_STATUSES:
        errors.append("qualityStatus 不合法")
    if "reviewNotes" in data:
        check_text_list(errors, "reviewNotes", data.get("reviewNotes"), 0, 100, maximum_length=500)
    check_salvage(errors, data)
    return errors


def collect(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if not target.is_dir():
        raise ValueError(f"输入路径不存在：{target}")
    return sorted(target.rglob("style-analysis.json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    try:
        files = collect(args.target.resolve())
    except ValueError as error:
        print(f"FAIL\n{error}")
        return 1
    if not files:
        print(f"FAIL\n未找到 style-analysis.json：{args.target}")
        return 1
    all_errors = []
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            all_errors.append(f"{file}: JSON 读取失败：{error}")
            continue
        all_errors.extend(f"{file}: {error}" for error in validate_data(data))
    if all_errors:
        print("FAIL")
        print("\n".join(all_errors))
        return 1
    print(f"PASS {len(files)} analysis file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
