#!/usr/bin/env python3
"""Non-API institutional metadata adapters for the real-photo test pool."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


UA = "MemebuyStyleTemplatePool/4.0 (rights-aware institutional metadata maintenance)"
SMITHSONIAN_ROOT = "https://smithsonian-open-access.s3-us-west-2.amazonaws.com/metadata/edan"
LOC_METADATA = "https://data.labs.loc.gov/free-to-use/metadata.jsonl"
SMITHSONIAN_PLAN = [
    ("animal", "nzp", False),
    ("nature_outdoor", "hac", False),
    ("complex_scene", "sia", False),
    ("object", "nmah", True),
]
PHOTO_WORDS = re.compile(
    r"\b(photo(?:graph|graphs|graphic|graphy)?|negative|stereograph|daguerreotype|ambrotype|gelatin silver|albumen)\b",
    re.I,
)
NON_PHOTO_WORDS = re.compile(r"\b(drawing|engraving|lithograph|woodcut|poster|map|manuscript|sheet music|painting)\b", re.I)
CATEGORY_RULES = [
    ("food", re.compile(r"\b(food|meal|restaurant|diner|kitchen|fruit|vegetable|bread|cake|drink)\b", re.I)),
    ("animal", re.compile(r"\b(animal|bird|cat|dog|horse|fish|zoo|wildlife|chicken)\b", re.I)),
    ("interior", re.compile(r"\b(interior|room|bedroom|bathroom|kitchen|inside|library|office)\b", re.I)),
    ("nature_outdoor", re.compile(r"\b(garden|forest|mountain|river|lake|beach|landscape|farm|flower|tree|park)\b", re.I)),
    ("city_architecture", re.compile(r"\b(building|architecture|bridge|street|city|house|hotel|courthouse)\b", re.I)),
]


class InstitutionalSourceError(RuntimeError):
    """Machine-readable institutional source failure."""


def fetch_text(url: str, timeout: int = 120) -> str:
    request = Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/plain,*/*"})
    try:
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()
        with urlopen(request, timeout=timeout, context=context) as response:
            return response.read().decode("utf-8", "replace")
    except HTTPError as error:
        if error.code in {403, 429}:
            raise InstitutionalSourceError(f"source_stopped_http_{error.code}") from error
        raise InstitutionalSourceError(f"source_http_{error.code}") from error
    except URLError as error:
        raise InstitutionalSourceError(f"source_network_failed: {error.reason}") from error


def atomic_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def text_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for value_item in value for item in text_items(value_item)]
    if isinstance(value, dict):
        preferred = [value.get(key) for key in ("Name", "Role", "content", "label") if value.get(key)]
        return [str(item) for item in preferred] if preferred else [str(value)]
    return [str(value)]


def first_cc0_image(item: dict[str, Any]) -> dict[str, Any] | None:
    media = item.get("content", {}).get("descriptiveNonRepeating", {}).get("online_media", {}).get("media", [])
    return next((entry for entry in media if entry.get("type") == "Images" and entry.get("usage", {}).get("access") == "CC0"), None)


def parse_smithsonian_record(item: dict[str, Any], category: str, museum_object: bool) -> dict[str, Any] | None:
    media = first_cc0_image(item)
    if not media:
        return None
    descriptive = item.get("content", {}).get("descriptiveNonRepeating", {})
    free = item.get("content", {}).get("freetext", {})
    record_id = descriptive.get("record_ID") or item.get("id")
    image_url = media.get("content") or media.get("thumbnail")
    if not image_url:
        return None
    if "max=" not in image_url:
        image_url += ("&" if "?" in image_url else "?") + "max=1024"
    title = descriptive.get("title", {}).get("content") or item.get("title") or record_id
    credit = next((entry.get("content") for entry in free.get("objectRights", []) if entry.get("content")), "Smithsonian Institution")
    return {
        "sourceAdapter": "smithsonian-open-access-bulk",
        "sourcePageUrl": descriptive.get("record_link") or f"https://www.si.edu/object/{record_id}",
        "imageUrl": image_url,
        "title": title,
        "author": credit,
        "license": "CC0",
        "licenseUrl": "https://www.si.edu/openaccess/faq",
        "rightsStatus": "verified",
        "category": category,
        "photographic": False,
        "photographicEvidence": f"Smithsonian CC0 metadata from {item.get('unitCode')}; visual confirmation required",
        "riskLabels": ["museum-object-review"] if museum_object else [],
        "plainMuseumObject": museum_object,
    }


def parse_smithsonian_jsonl(document: str, category: str, museum_object: bool, limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in document.splitlines():
        if not line.strip():
            continue
        candidate = parse_smithsonian_record(json.loads(line), category, museum_object)
        if candidate:
            records.append(candidate)
            if len(records) >= limit:
                break
    return records


def loc_category(item: dict[str, Any]) -> str:
    text = " ".join(text_items(item.get("Title")) + text_items(item.get("Description")) + text_items(item.get("Subjects")))
    for category, pattern in CATEGORY_RULES:
        if pattern.search(text):
            return category
    return "complex_scene"


def parse_loc_jsonl(document: str, limit: int) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in document.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        evidence = " ".join(text_items(item.get("Medium")) + text_items(item.get("Genre")) + text_items(item.get("Description")))
        if not PHOTO_WORDS.search(evidence):
            continue
        if NON_PHOTO_WORDS.search(evidence) and not re.search(r"\b(photo|photograph|negative|stereograph)\b", evidence, re.I):
            continue
        previews = []
        for raw in text_items(item.get("Preview_url")):
            clean = raw.split("#", 1)[0]
            if re.search(r"\.(?:jpe?g|png|webp)$", clean, re.I) and "150px" not in clean:
                previews.append(clean)
        if not previews:
            continue
        rights = " ".join(text_items(item.get("Rights")))
        strict = bool(re.search(r"\bpublic domain\b", rights, re.I))
        category = loc_category(item)
        buckets[category].append({
            "sourceAdapter": "loc-free-to-use-bulk",
            "sourcePageUrl": item.get("Url") or item.get("Id"),
            "imageUrl": previews[0],
            "title": item.get("Title") or "Untitled",
            "author": ", ".join(
                creator.get("Name", "") for creator in (item.get("Creators") or [])
                if isinstance(creator, dict) and creator.get("Name")
            ) or "Library of Congress",
            "license": "Public Domain" if strict else "Free to Use / no known restrictions",
            "licenseUrl": "https://www.loc.gov/free-to-use/",
            "rightsStatus": "verified" if strict else "manual_review",
            "category": category,
            "photographic": False,
            "photographicEvidence": f"LOC photographic medium metadata; visual person and category confirmation required: {evidence[:300]}",
            "riskLabels": [],
        })
    chosen: list[dict[str, Any]] = []
    order = ["animal", "object", "food", "interior", "nature_outdoor", "city_architecture", "complex_scene"]
    for bucket in buckets.values():
        bucket.sort(key=lambda record: record["rightsStatus"] == "verified", reverse=True)
    while len(chosen) < limit and any(buckets.values()):
        for category in order:
            if buckets[category]:
                chosen.append(buckets[category].pop(0))
                if len(chosen) >= limit:
                    break
    return chosen


def collect_source(
    source: str,
    limit: int,
    checkpoint_file: Path,
    *,
    delay: float = 3.0,
    fetcher: Callable[[str], str] = fetch_text,
) -> dict[str, Any]:
    if checkpoint_file.is_file():
        saved = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        if saved.get("source") == source and saved.get("status") == "completed" and len(saved.get("records", [])) >= limit:
            return saved
    checkpoint = {
        "artifactType": "style_source_metadata_checkpoint",
        "schemaVersion": "2.0.0",
        "producer": "style-template-analyzer",
        "source": source,
        "records": [],
        "status": "running",
    }
    try:
        if source == "loc":
            checkpoint["records"] = parse_loc_jsonl(fetcher(LOC_METADATA), limit)
        elif source == "smithsonian":
            per_unit = max(1, (limit + len(SMITHSONIAN_PLAN) - 1) // len(SMITHSONIAN_PLAN))
            seen: set[str] = set()
            for category, unit, museum_object in SMITHSONIAN_PLAN:
                index = fetcher(f"{SMITHSONIAN_ROOT}/{unit}/index.txt")
                unit_count = 0
                for shard in (line.strip() for line in index.splitlines() if line.strip().startswith("http")):
                    for record in parse_smithsonian_jsonl(fetcher(shard), category, museum_object, per_unit - unit_count):
                        if record["sourcePageUrl"] not in seen:
                            checkpoint["records"].append(record)
                            seen.add(record["sourcePageUrl"])
                            unit_count += 1
                    atomic_json(checkpoint_file, checkpoint)
                    if unit_count >= per_unit or len(checkpoint["records"]) >= limit:
                        break
                    if delay > 0:
                        time.sleep(delay)
                if len(checkpoint["records"]) >= limit:
                    break
        else:
            raise InstitutionalSourceError("source_unknown")
        checkpoint["records"] = checkpoint["records"][:limit]
        checkpoint["status"] = "completed"
        atomic_json(checkpoint_file, checkpoint)
        return checkpoint
    except Exception as error:
        checkpoint["status"] = str(error).split(":", 1)[0]
        checkpoint["error"] = str(error)
        atomic_json(checkpoint_file, checkpoint)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["smithsonian", "loc"], required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=3.0)
    args = parser.parse_args()
    result = collect_source(args.source, args.limit, args.checkpoint, delay=args.delay)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
