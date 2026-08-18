#!/usr/bin/env python3
"""Validate prompt-only whole-image visual reconstruction runtime JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from style_contracts import KEY_RE

import re

SIZE_RE = re.compile(r"^(\d{3,4})x(\d{3,4})$")
OSS_OBJECT_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-"
    r"[0-9a-f]{12}\.(?:png|jpe?g|webp|gif|avif)$",
    re.IGNORECASE,
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
REQUIRED_FIELDS = {
    "key",
    "title",
    "description",
    "kind",
    "cover",
    "imageSize",
    "imageN",
    "promptTemplate",
    "inputSchema",
    "preprocessSteps",
    "metadata",
}
ALLOWED_FIELDS = REQUIRED_FIELDS
INPUT_FIELDS = {"type", "id", "label", "hint", "required", "maxCount", "private"}
METADATA_FIELDS = {"tags", "styleAnalysis", "sourceRef"}
SOURCE_REF_FIELDS = {"producerKey", "styleAsset", "taxonomyVersion"}
STYLE_ANALYSIS_FIELDS = {"surfaceTexture", "composition", "backgroundPolicy", "note"}
SOURCE_IMAGE_MARKERS = ("用户上传图", "用户原图")
SINGLE_IMAGE_MARKERS = ("唯一图片输入", "唯一输入图片", "唯一图像输入", "只使用用户上传图这一张图片")
FRAME_DIRECTION_MARKERS = ("画幅方向", "横竖方向", "画布方向", "相同方向", "方向一致")
ASPECT_RATIO_MARKERS = ("宽高比", "纵横比")
FRAME_INHERITANCE_MARKERS = ("跟随", "保持", "继承", "沿用")
SUBJECT_SCOPE_MARKERS = ("全部显著主体", "默认保留显著主体", "主主体")
SUBJECT_FEATURE_MARKERS = ("发型", "服装", "配饰", "手持物")
SUBJECT_CORRESPONDENCE_MARKERS = ("逐一对应", "一一对应")
INSTANCE_CONTROL_MARKERS = ("不复制", "不合并", "不删减", "不增殖")
TRANSFORMATION_PERMISSION_MARKERS = ("本模板允许", "本模板仅改变", "本模板保留")
CONTENT_BOUNDARY_MARKERS = ("模板未授权", "越权新增")
REFERENCE_DEPENDENCY_TERMS = (
    "第 1 张图片",
    "第1张图片",
    "第 1 张图",
    "第1张图",
    "第 2 张图片",
    "第2张图片",
    "第 2 张图",
    "第2张图",
    "参考图",
    "风格参考",
)
PHOTOGRAPHIC_BASE_TERMS = (
    "保留原照片",
    "保留照片作为底图",
    "以原照片为底",
    "以照片为底图",
    "保留摄影底图",
    "保留摄影轮廓",
    "在原照片上叠加",
    "照片叠加",
)


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
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        errors.append(f"{path} 必须是长度 {minimum}-{maximum} 的非空字符串")


def check_string_array(errors: list[str], path: str, value: Any, maximum_items: int = 10) -> None:
    if not isinstance(value, list):
        errors.append(f"{path} 必须是数组")
        return
    if len(value) > maximum_items:
        errors.append(f"{path} 最多包含 {maximum_items} 项")
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not 1 <= len(item.strip()) <= 30:
            errors.append(f"{path}[{index}] 必须是长度 1-30 的非空字符串")
        else:
            normalized.append(item.strip())
    if len(normalized) != len(set(normalized)):
        errors.append(f"{path} 含有重复项")


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
    if parsed.scheme:
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


def check_prompt(errors: list[str], value: Any) -> None:
    check_text(errors, "promptTemplate", value, 120, 1200)
    if not isinstance(value, str):
        return
    checks = [
        (any(marker in value for marker in SOURCE_IMAGE_MARKERS)
         and any(marker in value for marker in SINGLE_IMAGE_MARKERS)
         and "唯一内容来源" in value,
         "prompt-only 输入权限：用户上传图是唯一图片输入和唯一内容来源"),
        (any(marker in value for marker in ("完整重绘", "完整重建", "全部重绘")),
         "全像素重绘要求"),
        (any(marker in value for marker in SUBJECT_SCOPE_MARKERS),
         "主体选择要求：全部显著主体或主主体"),
        ("身份" in value and "关键关系" in value and all(marker in value for marker in SUBJECT_FEATURE_MARKERS),
         "主体特征连续性：身份、发型、服装、配饰、手持物和关键关系"),
        (any(marker in value for marker in SUBJECT_CORRESPONDENCE_MARKERS)
         and all(marker in value for marker in INSTANCE_CONTROL_MARKERS),
         "主体逐一对应与实例控制：不复制、不合并、不删减、不增殖"),
        (any(marker in value for marker in TRANSFORMATION_PERMISSION_MARKERS),
         "变换权限声明：本模板允许、仅改变或保留的内容"),
        (all(marker in value for marker in CONTENT_BOUNDARY_MARKERS),
         "越权内容边界：模板未授权内容属于越权新增"),
        ("原照片像素" in value and "消失" in value,
         "去摄影化要求：原照片像素必须消失"),
        (any(marker in value for marker in SOURCE_IMAGE_MARKERS)
         and any(marker in value for marker in FRAME_DIRECTION_MARKERS)
         and any(marker in value for marker in ASPECT_RATIO_MARKERS)
         and any(marker in value for marker in FRAME_INHERITANCE_MARKERS),
         "画幅继承要求：输出方向与宽高比跟随用户上传图"),
    ]
    for valid, label in checks:
        if not valid:
            errors.append(f"promptTemplate 缺少{label}")
    matched = [term for term in PHOTOGRAPHIC_BASE_TERMS if term in value]
    if matched:
        errors.append(f"promptTemplate 禁止保留摄影底图：{', '.join(matched)}")
    dependencies = [term for term in REFERENCE_DEPENDENCY_TERMS if term in value]
    if dependencies:
        errors.append(f"promptTemplate 必须为单图 prompt-only，禁止参考图依赖：{', '.join(dependencies)}")


def check_input_schema(errors: list[str], value: Any) -> None:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        errors.append("inputSchema 必须且只能包含一个 image/source 输入")
        return
    item = value[0]
    extras = set(item) - INPUT_FIELDS
    if extras:
        errors.append(f"inputSchema[0] 包含未知字段：{', '.join(sorted(extras))}")
    expected = {
        "type": "image",
        "id": "source",
        "required": True,
        "maxCount": 1,
        "private": False,
    }
    for field, expected_value in expected.items():
        if item.get(field) != expected_value:
            errors.append(f"inputSchema[0].{field} 必须为 {json.dumps(expected_value, ensure_ascii=False)}")
    check_text(errors, "inputSchema[0].label", item.get("label"), 1, 40)
    check_text(errors, "inputSchema[0].hint", item.get("hint"), 1, 100)


def check_metadata(errors: list[str], value: Any, key: Any) -> None:
    if not isinstance(value, dict):
        errors.append("metadata 必须是 object")
        return
    extras = set(value) - METADATA_FIELDS
    if extras:
        errors.append(f"metadata 包含未知字段：{', '.join(sorted(extras))}")
    if "tags" in value:
        check_string_array(errors, "metadata.tags", value.get("tags"))
    source = value.get("sourceRef")
    if not isinstance(source, dict):
        errors.append("metadata.sourceRef 必须是 object")
    else:
        extras = set(source) - SOURCE_REF_FIELDS
        if extras:
            errors.append(f"metadata.sourceRef 包含未知字段：{', '.join(sorted(extras))}")
        for field in sorted(SOURCE_REF_FIELDS - set(source)):
            errors.append(f"metadata.sourceRef.{field} 缺失")
        if source.get("producerKey") != key:
            errors.append("metadata.sourceRef.producerKey 必须等于顶层 key")
        check_text(errors, "metadata.sourceRef.styleAsset", source.get("styleAsset"), 1, 500)
        if source.get("taxonomyVersion") != "2.0":
            errors.append("metadata.sourceRef.taxonomyVersion 必须为 2.0")
    analysis = value.get("styleAnalysis")
    if analysis is not None:
        if not isinstance(analysis, dict):
            errors.append("metadata.styleAnalysis 必须是 object")
        else:
            extras = set(analysis) - STYLE_ANALYSIS_FIELDS
            if extras:
                errors.append(f"metadata.styleAnalysis 包含未知字段：{', '.join(sorted(extras))}")
            for field, item in analysis.items():
                check_text(errors, f"metadata.styleAnalysis.{field}", item, 1, 500)


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
    for field in sorted(REQUIRED_FIELDS - set(data)):
        errors.append(f"{field} 缺失")
    extras = set(data) - ALLOWED_FIELDS
    if extras:
        errors.append(f"不允许的最终交付字段：{', '.join(sorted(extras))}")

    key = data.get("key")
    if not isinstance(key, str) or not KEY_RE.fullmatch(key):
        errors.append("key 格式不合法")
    check_text(errors, "title", data.get("title"), 3, 6)
    check_text(errors, "description", data.get("description"), 1, 240)
    if data.get("kind") != "STYLE_REF":
        errors.append("kind 必须为 STYLE_REF")
    check_asset(errors, template_file, "cover", data.get("cover"), asset_mode, domain, prefix)
    image_size = data.get("imageSize")
    match = SIZE_RE.fullmatch(image_size) if isinstance(image_size, str) else None
    if not match or any(not 256 <= int(part) <= 4096 for part in match.groups()):
        errors.append("imageSize 必须是 256-4096 范围内的 <宽>x<高>")
    if data.get("imageN") != 1 or isinstance(data.get("imageN"), bool):
        errors.append("imageN 必须为整数 1")

    check_prompt(errors, data.get("promptTemplate"))
    check_input_schema(errors, data.get("inputSchema"))
    if data.get("preprocessSteps") != []:
        errors.append("preprocessSteps 当前必须为空数组")
    check_metadata(errors, data.get("metadata"), key)
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
