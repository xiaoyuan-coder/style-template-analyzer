#!/usr/bin/env python3
"""Build an idempotent BadCase corpus from explicit user rejection decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont


ARTIFACT_TYPE = "style_badcase_corpus"
SCHEMA_VERSION = "1.0.0"
PRODUCER = "style-template-analyzer"
REJECT_VERDICTS = {"reject", "rejected", "excluded", "fail", "failed", "not_approved"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def batch_root_for(decision_path: Path) -> Path:
    return decision_path.parent.parent if decision_path.parent.name == "authoring" else decision_path.parent


def authority_for(data: dict[str, Any], *, legacy_exclusion: bool) -> str | None:
    raw = str(data.get("decisionAuthority") or data.get("approvalSource") or "").lower()
    if raw == "user_attached_selection":
        return "user_attached_selection"
    if raw.startswith("user") or data.get("userInstruction") or data.get("approvalText"):
        return "user"
    if legacy_exclusion:
        return "legacy_user_exclusion"
    return None


def rejected_entries(data: dict[str, Any], *, accept_legacy_exclusions: bool) -> list[tuple[dict[str, Any], bool]]:
    result: list[tuple[dict[str, Any], bool]] = []
    for item in data.get("decisions") or []:
        if isinstance(item, dict) and str(item.get("verdict", "")).lower() in REJECT_VERDICTS:
            result.append((item, False))
    for field in ("rejected", "excluded"):
        for item in data.get(field) or []:
            if isinstance(item, dict):
                legacy = field == "excluded" and authority_for(data, legacy_exclusion=False) is None
                if legacy and not accept_legacy_exclusions:
                    continue
                result.append((item, legacy))
    return result


def iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def candidate_identity(item: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        item.get("key"),
        item.get("index") or item.get("order"),
        item.get("title") or item.get("workingTitle"),
    )


def score_match(target: tuple[Any, Any, Any], candidate: dict[str, Any]) -> int:
    identity = candidate_identity(candidate)
    return sum(3 if a == b and a is not None else 0 for a, b in zip(target, identity))


def enrich_from_batch(item: dict[str, Any], decision_path: Path) -> dict[str, Any]:
    best = dict(item)
    best_score = 0
    target = candidate_identity(item)
    authoring = decision_path.parent if decision_path.parent.name == "authoring" else decision_path.parent / "authoring"
    for path in sorted(authoring.rglob("*.json")):
        if path.resolve() == decision_path.resolve():
            continue
        try:
            value = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        for candidate in iter_dicts(value):
            score = score_match(target, candidate)
            if score > best_score:
                best = {**candidate, **item}
                best_score = score
            elif score == best_score and score > 0:
                best = {**best, **candidate, **item}
    return best


def resolve_path(raw: Any, decision_path: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw)
    if candidate.is_absolute() and candidate.is_file():
        return candidate.resolve()
    batch_root = batch_root_for(decision_path)
    authoring = decision_path.parent if decision_path.parent.name == "authoring" else batch_root / "authoring"
    choices = [decision_path.parent / candidate, batch_root / candidate, authoring / candidate]
    for choice in choices:
        if choice.is_file():
            return choice.resolve()
    matches = sorted(authoring.rglob(candidate.name)) if authoring.is_dir() else []
    if not matches:
        return None
    matches.sort(key=lambda path: (path.stat().st_mtime_ns, path.as_posix()), reverse=True)
    return matches[0].resolve()


def reasons_for(item: dict[str, Any]) -> list[str]:
    raw = item.get("reasons") or item.get("reason") or "user_rejected"
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(value) for value in raw if str(value).strip()] or ["user_rejected"]
    return ["user_rejected"]


def badcase_id(decision_path: Path, item: dict[str, Any], after_sha: str | None) -> str:
    identity = "|".join(str(value or "") for value in candidate_identity(item))
    payload = f"{decision_path.resolve()}|{identity}|{after_sha or ''}".encode("utf-8")
    return "style-bad-" + hashlib.sha256(payload).hexdigest()[:16]


def build_item(
    decision_path: Path,
    decision: dict[str, Any],
    item: dict[str, Any],
    *,
    legacy_exclusion: bool,
) -> dict[str, Any]:
    item = enrich_from_batch(item, decision_path)
    authority = authority_for(decision, legacy_exclusion=legacy_exclusion)
    if authority is None:
        raise ValueError(f"缺少用户拒绝权威：{decision_path}")

    after_raw = item.get("selectedCover") or item.get("cover") or item.get("output")
    before_raw = item.get("previewInput") or item.get("beforeImage") or item.get("testAsset") or item.get("input")
    after = resolve_path(after_raw, decision_path)
    before = resolve_path(before_raw, decision_path)
    after_sha = sha256_file(after) if after else None
    recorded_at = str(decision.get("decisionAt") or decision.get("approvedAt") or decision.get("reviewedAt") or iso_mtime(decision_path))
    result: dict[str, Any] = {
        "badcaseId": badcase_id(decision_path, item, after_sha),
        "decision": "reject",
        "authority": authority,
        "reasons": reasons_for(item),
        "sourceDecisionPath": decision_path.resolve().as_posix(),
        "batchRoot": batch_root_for(decision_path).resolve().as_posix(),
        "recordedAt": recorded_at,
    }
    optional = {
        "key": item.get("key"),
        "title": item.get("title") or item.get("workingTitle"),
        "candidateIndex": item.get("index") or item.get("order"),
        "deliverySetId": decision.get("deliverySetId"),
        "beforeImage": before.as_posix() if before else None,
        "afterImage": after.as_posix() if after else None,
        "afterImageSha256": after_sha,
        "x": item.get("x"),
        "y": item.get("y"),
        "b": item.get("b"),
        "c": item.get("c"),
    }
    result.update({key: value for key, value in optional.items() if value is not None})
    return result


def load_existing(output: Path) -> dict[str, dict[str, Any]]:
    if not output.is_file():
        return {}
    data = read_json(output)
    if data.get("artifactType") != ARTIFACT_TYPE or data.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"不支持的存量 BadCase 语料库：{output}")
    return {item["badcaseId"]: item for item in data.get("items", [])}


def logical_identity(item: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (
        item.get("sourceDecisionPath"),
        item.get("key"),
        item.get("candidateIndex"),
        item.get("title"),
    )


def write_contact_sheets(items: list[dict[str, Any]], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("badcase-after-*.jpg"):
        stale.unlink()
    visible = [item for item in items if item.get("afterImage") and Path(item["afterImage"]).is_file()]
    font = ImageFont.load_default()
    outputs: list[Path] = []
    cell_w, cell_h, columns, rows = 360, 270, 4, 4
    for page_no, start in enumerate(range(0, len(visible), columns * rows), 1):
        page_items = visible[start : start + columns * rows]
        canvas = Image.new("RGB", (cell_w * columns, cell_h * rows), "#f3efe6")
        draw = ImageDraw.Draw(canvas)
        for offset, item in enumerate(page_items):
            row, column = divmod(offset, columns)
            x0, y0 = column * cell_w, row * cell_h
            with Image.open(item["afterImage"]) as source:
                thumb = source.convert("RGB")
                thumb.thumbnail((cell_w - 20, cell_h - 54))
            x = x0 + (cell_w - thumb.width) // 2
            y = y0 + 10
            canvas.paste(thumb, (x, y))
            label = f"{start + offset + 1:02d}  {item.get('key') or item['badcaseId']}"
            draw.rectangle((x0, y0 + cell_h - 38, x0 + cell_w, y0 + cell_h), fill="#16232b")
            draw.text((x0 + 10, y0 + cell_h - 28), label[:48], fill="white", font=font)
        path = output_dir / f"badcase-after-{page_no:02d}.jpg"
        canvas.save(path, format="JPEG", quality=90, optimize=True)
        outputs.append(path)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decisions", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--contact-sheet-dir", type=Path)
    parser.add_argument("--accept-legacy-exclusions", action="store_true")
    args = parser.parse_args()

    merged = load_existing(args.output)
    for decision_path in args.decisions:
        decision_path = decision_path.resolve()
        decision = read_json(decision_path)
        for item, legacy_exclusion in rejected_entries(
            decision,
            accept_legacy_exclusions=args.accept_legacy_exclusions,
        ):
            record = build_item(
                decision_path,
                decision,
                item,
                legacy_exclusion=legacy_exclusion,
            )
            same_identity = [key for key, value in merged.items() if logical_identity(value) == logical_identity(record)]
            for key in same_identity:
                merged.pop(key, None)
            merged[record["badcaseId"]] = record

    items = sorted(
        merged.values(),
        key=lambda value: (value.get("recordedAt", ""), value.get("sourceDecisionPath", ""), value.get("candidateIndex", 0)),
    )
    payload = {
        "artifactType": ARTIFACT_TYPE,
        "schemaVersion": SCHEMA_VERSION,
        "producer": PRODUCER,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "items": items,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sheets = write_contact_sheets(items, args.contact_sheet_dir) if args.contact_sheet_dir else []
    print(json.dumps({"output": args.output.resolve().as_posix(), "count": len(items), "contactSheets": [path.resolve().as_posix() for path in sheets]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
