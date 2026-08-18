#!/usr/bin/env python3
"""Build one adjacent artifact-manifest.json for a style template package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from style_contracts import build_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path, help="包含业务 JSON 的模板或 handoff 目录")
    parser.add_argument(
        "--stage",
        choices=["authoring", "evaluation", "handoff", "package", "oss-handoff"],
        required=True,
    )
    parser.add_argument("--revision", type=int, default=1)
    parser.add_argument("--schema-version", choices=["1.0.0", "2.0.0"])
    args = parser.parse_args()

    root = args.target.resolve()
    if not root.is_dir():
        print(f"FAIL\n输入目录不存在：{root}")
        return 1
    try:
        schema_version = args.schema_version or ("1.0.0" if args.stage in {"authoring", "evaluation", "handoff"} else "2.0.0")
        manifest = build_manifest(root, args.stage, args.revision, schema_version=schema_version)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL\n{error}")
        return 1

    output = root / "artifact-manifest.json"
    temporary = root / ".artifact-manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(f"PASS {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
