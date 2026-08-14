#!/usr/bin/env python3
"""Migrate legacy dual-image style prompts to conservative prompt-only reconstruction."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any


LEGACY_SOURCE_RE = re.compile(
    r"^以第\s*2\s*张图片（用户上传图）作为唯一内容来源，保持(?P<preservation>.+)$"
)
LEGACY_STYLE_RE = re.compile(
    r"^第\s*1\s*张图片仅作为风格参考，把第\s*2\s*张图片的"
)
PROMPT_ONLY_OPENING_RE = re.compile(
    r"^只使用用户上传图这一张图片作为唯一图片输入和唯一内容来源(?:[，,].*)?$"
)
REFERENCE_TERMS = (
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
CONTENT_BOUNDARY = (
    "只生成用户内容和本提示词明确授权的变换；"
    "模板未授权的新主体、物件、关系或可读文字均为越权新增。"
)
SUBJECT_CONTINUITY = (
    "保留全部显著主体与主体集合；全部显著主体逐一对应用户图中的原主体，"
    "未经本提示词明确授权，不复制、不合并、不删减、不增殖人物、动物、物体或其关联物；"
    "每个呈现实例持续保留身份、面部与体型、"
    "轮廓、发型、花纹配色、服装、配饰、手持物和关键关系"
)
CONSERVATIVE_PERMISSION = (
    "本模板仅改变绘制语言与材质表现，保留主体形态、姿态与视角、"
    "呈现实例、环境和构图。"
)
EXPLICIT_ONLY_PERMISSION = (
    "本模板允许执行且仅执行下文明确写出的绘制语言、材质表现、主体形态和构图变化；"
    "下文未明确要求改变的主体形态、姿态与视角、呈现实例、环境和构图均保持不变。"
)


def split_sentences(prompt: str) -> list[str]:
    return [item.strip() for item in prompt.split("。") if item.strip()]


def is_existing_continuity_sentence(sentence: str) -> bool:
    return (
        any(marker in sentence for marker in ("全部显著主体", "默认保留显著主体", "主主体"))
        and "身份" in sentence
        and "关键关系" in sentence
        and all(marker in sentence for marker in ("发型", "服装", "配饰", "手持物"))
    )


def migrate_prompt(prompt: str) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("promptTemplate 必须是非空字符串")
    if (
        "唯一图片输入" in prompt
        and "唯一内容来源" in prompt
        and "逐一对应" in prompt
        and all(marker in prompt for marker in ("不复制", "不合并", "不删减", "不增殖"))
        and "模板未授权" in prompt
        and not any(term in prompt for term in REFERENCE_TERMS)
    ):
        return prompt.strip()

    sentences = split_sentences(prompt)
    if not sentences:
        raise ValueError("promptTemplate 没有可迁移句子")
    opening = LEGACY_SOURCE_RE.fullmatch(sentences[0])
    prompt_only_opening = PROMPT_ONLY_OPENING_RE.fullmatch(sentences[0])
    if prompt_only_opening:
        migrated = [
            "只使用用户上传图这一张图片作为唯一图片输入和唯一内容来源。"
            f"{SUBJECT_CONTINUITY}",
        ]
        remaining = [
            sentence for sentence in sentences[1:]
            if not is_existing_continuity_sentence(sentence)
        ]
        if not any(
            sentence.startswith(("本模板允许", "本模板仅改变", "本模板保留"))
            for sentence in remaining
        ):
            migrated.append(EXPLICIT_ONLY_PERMISSION.removesuffix("。"))
        migrated.extend(remaining)
        if not any("模板未授权" in sentence and "越权新增" in sentence for sentence in migrated):
            migrated.append(CONTENT_BOUNDARY.removesuffix("。"))
        result = "。".join(migrated) + "。"
        dependencies = [term for term in REFERENCE_TERMS if term in result]
        if dependencies:
            raise ValueError(f"迁移后仍含参考依赖：{', '.join(dependencies)}")
        return result
    if not opening:
        raise ValueError("promptTemplate 不符合受支持的双图开头，停止迁移")

    migrated = [
        "只使用用户上传图这一张图片作为唯一图片输入和唯一内容来源。"
        f"{SUBJECT_CONTINUITY}。输出画幅方向与宽高比跟随用户上传图",
        CONSERVATIVE_PERMISSION.removesuffix("。"),
    ]
    style_transformed = False
    boundary_added = False

    for sentence in sentences[1:]:
        if LEGACY_STYLE_RE.match(sentence):
            sentence = LEGACY_STYLE_RE.sub("把用户上传图的", sentence)
            style_transformed = True
        if sentence.startswith("参考图中的摄影成像只用于观测上述"):
            if "；" not in sentence:
                raise ValueError("摄影救援句缺少覆盖扩展子句，停止迁移")
            sentence = sentence.split("；", 1)[1].replace("这些算子", "上述风格算子")
        if re.match(r"^严禁复制第\s*1\s*张图片中的", sentence):
            if not boundary_added:
                migrated.append(CONTENT_BOUNDARY.removesuffix("。"))
                boundary_added = True
            continue
        migrated.append(sentence)

    if not style_transformed:
        raise ValueError("promptTemplate 缺少可迁移的风格执行句，停止迁移")
    if not boundary_added:
        migrated.append(CONTENT_BOUNDARY.removesuffix("。"))

    result = "。".join(migrated) + "。"
    dependencies = [term for term in REFERENCE_TERMS if term in result]
    if dependencies:
        raise ValueError(f"迁移后仍含参考依赖：{', '.join(dependencies)}")
    return result


def migrate_template(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("模板根节点必须是 JSON object")
    migrated = dict(data)
    migrated["promptTemplate"] = migrate_prompt(data.get("promptTemplate"))
    return migrated


def collect_templates(root: Path) -> list[Path]:
    if root.is_file():
        if root.name != "style-template.json":
            raise ValueError("输入文件必须名为 style-template.json")
        return [root]
    if not root.is_dir():
        raise ValueError(f"输入路径不存在：{root}")
    return sorted(root.rglob("style-template.json"))


def retarget_local_asset(value: Any, source_file: Path, output_file: Path) -> Any:
    if not isinstance(value, str) or not value or "://" in value:
        return value
    resolved = (source_file.parent / value).resolve()
    return os.path.relpath(resolved, output_file.parent)


def migrate_directory(input_path: Path, output_path: Path) -> dict[str, Any]:
    source = input_path.resolve()
    output = output_path.resolve()
    files = collect_templates(source)
    if not files:
        raise ValueError(f"未找到 style-template.json：{source}")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"输出目录必须为空：{output}")

    migrated_keys: list[str] = []
    for source_file in files:
        relative = source_file.relative_to(source) if source.is_dir() else Path(source_file.name)
        output_file = output / relative
        source_dir = source_file.parent
        output_dir = output_file.parent
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, output_dir, dirs_exist_ok=False)
        data = json.loads(source_file.read_text(encoding="utf-8"))
        migrated = migrate_template(data)
        migrated.pop("referenceImage", None)
        for field in ("cover",):
            migrated[field] = retarget_local_asset(data.get(field), source_file, output_file)
        output_file.write_text(
            json.dumps(migrated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        migrated_keys.append(str(migrated.get("key", "")))

    return {
        "input": str(source),
        "output": str(output),
        "templates": len(files),
        "keys": migrated_keys,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        summary = migrate_directory(args.input, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL\n{error}")
        return 1
    print(json.dumps({"ok": True, **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
