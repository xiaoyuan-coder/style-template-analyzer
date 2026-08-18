#!/usr/bin/env python3
"""Build and validate immutable approved style-template baseline snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

from style_contracts import PRODUCER, read_json, sha256_file
from validate_style_template import validate_data as validate_template


def _template_errors(data: Any, path: Path) -> list[str]:
    cover = data.get("cover") if isinstance(data, dict) else None
    if isinstance(cover, str) and urlparse(cover).scheme:
        parsed = urlparse(cover)
        marker = "/style/templates/"
        prefix = parsed.path.split(marker, 1)[0].strip("/") if marker in parsed.path else ""
        return validate_template(data, path, "either", parsed.hostname or "", prefix)
    return validate_template(data, path, "local", "", "")


def _digest_entries(entries: list[dict[str, Any]]) -> str:
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _contract_errors(data: Any, schema_name: str) -> list[str]:
    if isinstance(data, dict):
        version = data.get("schemaVersion")
        if isinstance(version, str) and version.count(".") == 2:
            try:
                if int(version.split(".", 1)[0]) > 1:
                    return ["failed: contract_version_unsupported"]
            except ValueError:
                pass
    schema_file = Path(__file__).parents[1] / "contracts" / schema_name
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    return ["baseline_contract_invalid"] if list(Draft202012Validator(schema).iter_errors(data)) else []


def build_baseline_snapshot(
    root: Path,
    *,
    approved_count: int,
    created_at: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    files = sorted(root.rglob("style-template.json"))
    if len(files) != approved_count:
        raise ValueError(f"baseline_count_mismatch: expected={approved_count} actual={len(files)}")
    entries: list[dict[str, Any]] = []
    keys: set[str] = set()
    titles: set[str] = set()
    for file in files:
        data = read_json(file)
        errors = _template_errors(data, file)
        if errors:
            raise ValueError(f"baseline_template_invalid: {file}: {'; '.join(errors)}")
        key = data["key"]
        title = data["title"]
        if key in keys:
            raise ValueError(f"baseline_duplicate_key: {key}")
        if title in titles:
            raise ValueError(f"baseline_duplicate_title: {title}")
        keys.add(key)
        titles.add(title)
        entries.append({
            "key": key,
            "title": title,
            "path": file.relative_to(root).as_posix(),
            "sha256": sha256_file(file),
        })
    return {
        "artifactType": "style_baseline_snapshot",
        "schemaVersion": "1.0.0",
        "producer": PRODUCER,
        "approved": True,
        "root": root.as_posix(),
        "createdAt": created_at or datetime.now(timezone.utc).isoformat(),
        "count": len(entries),
        "digest": _digest_entries(entries),
        "entries": entries,
    }


def validate_baseline_snapshot(snapshot: Any, root: Path | None = None) -> list[str]:
    if not isinstance(snapshot, dict):
        return ["baseline_not_approved"]
    errors = _contract_errors(snapshot, "baseline-snapshot.schema.json")
    if errors == ["failed: contract_version_unsupported"]:
        return errors
    if snapshot.get("artifactType") != "style_baseline_snapshot" or snapshot.get("approved") is not True:
        errors.append("baseline_not_approved")
    entries = snapshot.get("entries")
    if not isinstance(entries, list) or snapshot.get("count") != len(entries):
        errors.append("baseline_count_mismatch")
        return errors
    if snapshot.get("digest") != _digest_entries(entries):
        errors.append("baseline_digest_mismatch")
    keys = [item.get("key") for item in entries if isinstance(item, dict)]
    titles = [item.get("title") for item in entries if isinstance(item, dict)]
    if len(keys) != len(set(keys)):
        errors.append("baseline_duplicate_key")
    if len(titles) != len(set(titles)):
        errors.append("baseline_duplicate_title")
    resolved_root = (root or Path(str(snapshot.get("root", "")))).resolve()
    for item in entries:
        if not isinstance(item, dict):
            errors.append("baseline_entry_invalid")
            continue
        file = (resolved_root / str(item.get("path", ""))).resolve()
        if resolved_root not in file.parents:
            errors.append("baseline_entry_outside_root")
        elif not file.is_file() or sha256_file(file) != item.get("sha256"):
            errors.append("baseline_digest_mismatch")
    return list(dict.fromkeys(errors))


def verify_approval_descriptor(descriptor: Any, repo_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if isinstance(descriptor, dict):
        version = descriptor.get("schemaVersion")
        if isinstance(version, str) and version.count(".") == 2:
            try:
                if int(version.split(".", 1)[0]) > 1:
                    return None, ["failed: contract_version_unsupported"]
            except ValueError:
                pass
    if (
        not isinstance(descriptor, dict)
        or descriptor.get("artifactType") != "style_baseline_approval"
        or descriptor.get("schemaVersion") != "1.0.0"
        or descriptor.get("producer") != PRODUCER
        or descriptor.get("approved") is not True
    ):
        return None, ["baseline_not_approved"]
    business_root = descriptor.get("businessRoot")
    expected_count = descriptor.get("expectedCount")
    if not isinstance(business_root, str) or not isinstance(expected_count, int):
        return None, ["baseline_not_approved"]
    try:
        snapshot = build_baseline_snapshot(repo_root / business_root, approved_count=expected_count)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return None, [str(error).split(":", 1)[0]]
    errors = []
    if snapshot["digest"] != descriptor.get("digest"):
        errors.append("baseline_digest_mismatch")
    return snapshot, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--approved-count", type=int, required=True)
    args = parser.parse_args()
    try:
        snapshot = build_baseline_snapshot(args.root, approved_count=args.approved_count)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL\n{error}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS count={snapshot['count']} digest={snapshot['digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
