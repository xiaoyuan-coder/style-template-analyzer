#!/usr/bin/env python3
"""Durable, append-only review experience with a freshness-checked snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class ExperienceStoreError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            output.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def _lock(path: Path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


class DurableExperienceStore:
    """Owns corpus persistence and derives the only consumable current snapshot."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.corpus_file = self.root / "style-experience-corpus.json"
        self.snapshot_file = self.root / "current.json"
        self.lock_file = self.root / ".experience.lock"

    def _empty_corpus(self) -> dict[str, Any]:
        return {
            "artifactType": "style_experience_corpus",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "cases": [],
        }

    def _snapshot(self, corpus: dict[str, Any]) -> dict[str, Any]:
        digest = hashlib.sha256(self.corpus_file.read_bytes()).hexdigest()
        cases = corpus["cases"]
        latest_good: dict[str, dict[str, Any]] = {}
        for item in cases:
            if item["casePool"] != "goodcase":
                continue
            previous = latest_good.get(item["templateKey"])
            if previous is None or (item["revision"], item["depositedAt"]) > (previous["revision"], previous["depositedAt"]):
                latest_good[item["templateKey"]] = item
        return {
            "artifactType": "style_experience_snapshot",
            "schemaVersion": "1.0.0",
            "producer": "style-template-analyzer",
            "generatedAt": _now(),
            "corpusSha256": digest,
            "caseCount": len(cases),
            "goodcaseCount": sum(item["casePool"] == "goodcase" for item in cases),
            "badcaseCount": sum(item["casePool"] == "badcase" for item in cases),
            "activeGoodcaseKeys": sorted(latest_good),
        }

    def __call__(self, event: dict[str, Any]) -> dict[str, Any]:
        decision = event.get("decision")
        case_pool = event.get("casePool")
        if case_pool not in {"goodcase", "badcase"} or not isinstance(decision, dict):
            raise ExperienceStoreError("experience_event_invalid")
        identity = "\0".join(str(decision.get(field, "")) for field in (
            "templateKey", "revision", "verdict", "coverSha256", "promptSha256"
        ))
        event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        with _lock(self.lock_file):
            corpus = _read(self.corpus_file) if self.corpus_file.is_file() else self._empty_corpus()
            if not isinstance(corpus, dict) or not isinstance(corpus.get("cases"), list):
                raise ExperienceStoreError("experience_corpus_invalid")
            existing = next((item for item in corpus["cases"] if item.get("eventId") == event_id), None)
            if existing is None:
                corpus["cases"].append({
                    "eventId": event_id,
                    "casePool": case_pool,
                    "templateKey": decision["templateKey"],
                    "revision": decision["revision"],
                    "verdict": decision["verdict"],
                    "reason": decision["reason"],
                    "coverSha256": decision["coverSha256"],
                    "promptSha256": decision["promptSha256"],
                    "reviewRoot": event["reviewRoot"],
                    "depositedAt": _now(),
                })
                _atomic_json(self.corpus_file, corpus)
            elif self.snapshot_file.is_file():
                snapshot = _read(self.snapshot_file)
                corpus_digest = hashlib.sha256(self.corpus_file.read_bytes()).hexdigest()
                if isinstance(snapshot, dict) and snapshot.get("corpusSha256") == corpus_digest:
                    return {
                        "eventId": event_id,
                        "snapshotSha256": hashlib.sha256(self.snapshot_file.read_bytes()).hexdigest(),
                    }
            snapshot = self._snapshot(corpus)
            _atomic_json(self.snapshot_file, snapshot)
        return {"eventId": event_id, "snapshotSha256": hashlib.sha256(self.snapshot_file.read_bytes()).hexdigest()}

    def merge_legacy_corpora(self, goodcase_file: Path, badcase_file: Path) -> dict[str, Any]:
        """Seed the durable ledger from the existing GoodCase and BadCase corpora."""
        goodcase = _read(goodcase_file)
        badcase = _read(badcase_file)
        sources = (("goodcase", goodcase_file, goodcase), ("badcase", badcase_file, badcase))
        with _lock(self.lock_file):
            corpus = _read(self.corpus_file) if self.corpus_file.is_file() else self._empty_corpus()
            if not isinstance(corpus, dict) or not isinstance(corpus.get("cases"), list):
                raise ExperienceStoreError("experience_corpus_invalid")
            existing_ids = {item.get("eventId") for item in corpus["cases"]}
            added = 0
            for case_pool, source_file, source in sources:
                items = source.get("items") if isinstance(source, dict) else None
                if not isinstance(items, list):
                    raise ExperienceStoreError(f"legacy_{case_pool}_corpus_invalid")
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    raw_key = item.get("key")
                    source_id = item.get("goodcaseId") or item.get("badcaseId") or item.get("afterImageSha256") or raw_key
                    if not isinstance(source_id, str) or not source_id:
                        source_id = hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
                    key = raw_key if isinstance(raw_key, str) and raw_key else f"unresolved-{case_pool}-{hashlib.sha256(source_id.encode('utf-8')).hexdigest()[:12]}"
                    revision = item.get("revision") if isinstance(item.get("revision"), int) else 1
                    event_id = hashlib.sha256(f"legacy\0{case_pool}\0{source_id}".encode("utf-8")).hexdigest()
                    if event_id in existing_ids:
                        continue
                    reason = item.get("reason")
                    if not isinstance(reason, str):
                        reasons = item.get("reasons")
                        reason = "; ".join(str(value) for value in reasons) if isinstance(reasons, list) else "legacy corpus import"
                    corpus["cases"].append({
                        "eventId": event_id,
                        "casePool": case_pool,
                        "templateKey": key,
                        "revision": revision,
                        "verdict": "pass" if case_pool == "goodcase" else "reject",
                        "reason": reason,
                        "coverSha256": item.get("afterImageSha256", ""),
                        "promptSha256": item.get("promptSha256", ""),
                        "reviewRoot": source_file.resolve().as_posix(),
                        "depositedAt": item.get("recordedAt") or source.get("updatedAt") or _now(),
                        "identityResolved": isinstance(raw_key, str) and bool(raw_key),
                    })
                    existing_ids.add(event_id)
                    added += 1
            _atomic_json(self.corpus_file, corpus)
            snapshot = self._snapshot(corpus)
            _atomic_json(self.snapshot_file, snapshot)
        return {"added": added, "snapshot": snapshot}

    def load_fresh_snapshot(self) -> dict[str, Any]:
        if not self.corpus_file.is_file() or not self.snapshot_file.is_file():
            raise ExperienceStoreError("experience_snapshot_missing")
        snapshot = _read(self.snapshot_file)
        schema = _read(Path(__file__).parents[1] / "contracts" / "style-experience-snapshot.schema.json")
        schema_errors = list(Draft202012Validator(schema).iter_errors(snapshot))
        if schema_errors:
            raise ExperienceStoreError("experience_snapshot_invalid")
        digest = hashlib.sha256(self.corpus_file.read_bytes()).hexdigest()
        if snapshot["corpusSha256"] != digest:
            raise ExperienceStoreError("experience_snapshot_stale")
        return snapshot
