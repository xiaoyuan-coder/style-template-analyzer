#!/usr/bin/env python3
"""Validate local or OSS-ready style-template.json files without dependencies."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


KEY_RE = re.compile(r"^[a-z][a-z0-9-]{1,59}$")
OSS_OBJECT_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-"
    r"[0-9a-f]{12}\.(?:png|jpe?g|webp|gif|avif)$",
    re.IGNORECASE,
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
CATEGORIES = {
    "hand-drawn-doodle": "手绘涂鸦",
    "anime-comic": "动漫漫画",
    "watercolor-painting": "水彩绘景",
    "flat-graphic": "平面图形",
    "print-halftone": "版画网点",
    "pixel-art": "像素艺术",
    "material-3d": "材质立体",
    "photographic-look": "摄影质感",
    "collage-experimental": "拼贴实验",
}
REFERENCE_TYPES = {
    "single-style-reference",
    "paired-images",
    "paired-comparison",
    "annotated-paired-comparison",
}
MODES = {"whole_image", "subject_only"}
STRATEGIES = {
    "full_scene_preservation",
    "primary_subject_reconstruction",
    "subject_cutout_stylization",
    "salient_object_extraction",
}
REQUIRED = {
    "schemaVersion",
    "taxonomyVersion",
    "key",
    "title",
    "description",
    "category",
    "displayCategory",
    "tags",
    "styleTags",
    "referenceType",
    "referenceStructure",
    "supportedModes",
    "contentScope",
    "contentStrategy",
    "referenceAssets",
    "styleInstruction",
    "contentExclusion",
    "classificationConfidence",
    "needsReview",
}


def normalize_prefix(value: str) -> str:
    cleaned = value.strip().strip("/")
    return f"{cleaned}/" if cleaned else ""


def managed_url(value: str, domain: str, prefix: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    expected = f"/{normalize_prefix(prefix)}style/templates/"
    if (
        parsed.scheme != "https"
        or parsed.hostname != domain.lower()
        or parsed.port
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith(expected)
    ):
        return False
    return bool(OSS_OBJECT_RE.fullmatch(parsed.path[len(expected) :]))


def check_text(errors: list[str], path: str, value: Any, minimum: int, maximum: int) -> None:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        errors.append(f"{path} 必须是长度 {minimum}-{maximum} 的字符串")


def check_string_array(errors: list[str], path: str, value: Any, maximum: int = 30) -> None:
    if not isinstance(value, list):
        errors.append(f"{path} 必须是数组")
        return
    if len(value) != len(set(item for item in value if isinstance(item, str))):
        errors.append(f"{path} 含有重复项")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not 1 <= len(item) <= maximum:
            errors.append(f"{path}[{index}] 必须是长度 1-{maximum} 的字符串")


def check_asset(
    errors: list[str],
    template_file: Path,
    field: str,
    value: Any,
    asset_mode: str,
    domain: str,
    prefix: str,
) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} 必须是非空图片路径或 URL")
        return
    parsed = urlparse(value)
    has_scheme = bool(parsed.scheme)
    if has_scheme:
        if asset_mode == "local":
            errors.append(f"{field} 在 local 模式下不能使用 URL")
        elif not domain:
            errors.append(f"{field} 需要 --assets-domain 才能校验远端 URL")
        elif not managed_url(value, domain, prefix):
            errors.append(f"{field} 不是受控 OSS URL")
        return
    if asset_mode == "remote":
        errors.append(f"{field} 在 remote 模式下必须是 HTTPS URL")
        return
    resolved = (template_file.parent / value).resolve()
    if resolved.suffix.lower() not in IMAGE_EXTENSIONS:
        errors.append(f"{field} 使用了不支持的图片格式：{value}")
    elif not resolved.is_file():
        errors.append(f"{field} 本地图片不存在：{resolved}")


def validate_data(
    data: Any,
    template_file: Path,
    asset_mode: str,
    domain: str,
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["根节点必须是 JSON object"]
    for field in sorted(REQUIRED - set(data)):
        errors.append(f"{field} 缺失")

    if data.get("schemaVersion") != "1.0":
        errors.append("schemaVersion 必须为 1.0")
    if data.get("taxonomyVersion") != "2.0":
        errors.append("taxonomyVersion 必须为 2.0")
    if not KEY_RE.fullmatch(str(data.get("key", ""))):
        errors.append("key 格式不合法")
    check_text(errors, "title", data.get("title"), 1, 60)
    check_text(errors, "description", data.get("description"), 1, 240)

    category = data.get("category")
    if not isinstance(category, dict):
        errors.append("category 必须是 object")
    else:
        primary = category.get("primary")
        if primary not in CATEGORIES:
            errors.append("category.primary 不在九类体系中")
        check_text(errors, "category.secondary", category.get("secondary"), 1, 80)
        expected_name = CATEGORIES.get(primary)
        if expected_name and category.get("displayName") != expected_name:
            errors.append("category.displayName 与 primary 不匹配")
        if data.get("displayCategory") != category.get("displayName"):
            errors.append("displayCategory 必须等于 category.displayName")

    check_string_array(errors, "tags", data.get("tags"))
    check_string_array(errors, "styleTags", data.get("styleTags"))
    if data.get("tags") != data.get("styleTags"):
        errors.append("当前契约要求 styleTags 与 tags 保持一致")

    reference_type = data.get("referenceType")
    if reference_type not in REFERENCE_TYPES:
        errors.append("referenceType 不合法")
    if data.get("referenceStructure") != reference_type:
        errors.append("referenceStructure 必须等于 referenceType")

    modes = data.get("supportedModes")
    if not isinstance(modes, list) or len(modes) != len(set(modes)):
        errors.append("supportedModes 必须是无重复数组")
        modes = []
    elif any(mode not in MODES for mode in modes):
        errors.append("supportedModes 含有未知模式")
    expected_scope = {
        (): "unavailable",
        ("subject_only",): "subject",
        ("whole_image",): "scene",
        ("subject_only", "whole_image"): "adaptive",
    }.get(tuple(sorted(modes)))
    if expected_scope and data.get("contentScope") != expected_scope:
        errors.append(f"contentScope 应为 {expected_scope}")
    if data.get("contentStrategy") not in STRATEGIES:
        errors.append("contentStrategy 不合法")

    quality = data.get("qualityStatus")
    if quality is not None and quality not in {"usable", "unusable"}:
        errors.append("qualityStatus 只能是 usable 或 unusable")
    if quality == "unusable":
        if modes:
            errors.append("unusable 模板的 supportedModes 必须为空")
        if data.get("needsReview") is not True:
            errors.append("unusable 模板必须 needsReview=true")
    elif not modes:
        errors.append("可用模板至少支持一种模式")

    assets = data.get("referenceAssets")
    if not isinstance(assets, dict) or not assets:
        errors.append("referenceAssets 必须是非空 object")
    else:
        for name, value in assets.items():
            if not re.fullmatch(r"[a-z][a-zA-Z0-9_-]{0,39}", str(name)):
                errors.append(f"referenceAssets.{name} 名称不合法")
            check_asset(
                errors,
                template_file,
                f"referenceAssets.{name}",
                value,
                asset_mode,
                domain,
                prefix,
            )

    if reference_type in {"paired-comparison", "annotated-paired-comparison"}:
        layout = data.get("comparisonLayout")
        if not isinstance(layout, dict):
            errors.append("对比图模板必须提供 comparisonLayout")
        else:
            for field in ["sourcePosition", "outputPosition", "ignoredElements"]:
                if field not in layout:
                    errors.append(f"comparisonLayout.{field} 缺失")
            check_string_array(errors, "comparisonLayout.ignoredElements", layout.get("ignoredElements"), 80)

    check_text(errors, "styleInstruction", data.get("styleInstruction"), 20, 4000)
    check_text(errors, "contentExclusion", data.get("contentExclusion"), 20, 2000)
    confidence = data.get("classificationConfidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("classificationConfidence 必须在 0-1 之间")
    if not isinstance(data.get("needsReview"), bool):
        errors.append("needsReview 必须是 boolean")

    test_assets = data.get("testAssets")
    if test_assets is not None:
        if not isinstance(test_assets, dict):
            errors.append("testAssets 必须是 object")
        elif asset_mode != "remote":
            for name, value in test_assets.items():
                check_asset(
                    errors,
                    template_file,
                    f"testAssets.{name}",
                    value,
                    "local",
                    domain,
                    prefix,
                )
    if asset_mode == "remote" and any(field in data for field in ["testAssets", "testNotes", "reviewNotes"]):
        errors.append("handoff JSON 不得包含 testAssets、testNotes 或 reviewNotes")
    return errors


def collect(target: Path) -> list[Path]:
    if target.is_file():
        if target.suffix.lower() != ".json":
            raise ValueError(f"输入文件必须是 JSON：{target}")
        return [target]
    if not target.is_dir():
        raise ValueError(f"输入路径不存在：{target}")
    return sorted(target.rglob("style-template.json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--asset-mode", choices=["local", "remote", "either"], default="local")
    parser.add_argument("--assets-domain", default="")
    parser.add_argument("--key-prefix", default="")
    args = parser.parse_args()
    domain = args.assets_domain.strip().lower()
    if domain and ("://" in domain or any(char in domain for char in "/?#@:")):
        print("FAIL\n--assets-domain 必须是纯 hostname")
        return 1

    try:
        files = collect(args.target.resolve())
    except ValueError as error:
        print(f"FAIL\n{error}")
        return 1
    if not files:
        print(f"FAIL\n未找到 style-template.json：{args.target}")
        return 1

    all_errors: list[str] = []
    keys: dict[str, Path] = {}
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            all_errors.append(f"{file}: JSON 读取失败：{error}")
            continue
        for error in validate_data(data, file, args.asset_mode, domain, args.key_prefix):
            all_errors.append(f"{file}: {error}")
        key = data.get("key") if isinstance(data, dict) else None
        if isinstance(key, str):
            if key in keys:
                all_errors.append(f"{file}: 批次 key 重复，首次出现于 {keys[key]}")
            keys[key] = file

    if all_errors:
        print("FAIL")
        print("\n".join(all_errors))
        return 1
    print(f"PASS {len(files)} template(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
