#!/usr/bin/env python3
"""Report globally available test-image capacity and legacy conflicts."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from style_test_pool import TestImagePool


def audit(pool_file: Path, ledger_file: Path) -> dict[str, object]:
    pool = TestImagePool.load(pool_file.resolve(), ledger_file.resolve())
    distribution = pool.ready_distribution()
    identities_by_asset: dict[str, list[str]] = defaultdict(list)
    for item in pool.assignments:
        if pool._blocks_asset(item):
            identities_by_asset[str(item["assetId"])].append(
                f"{item['deliverySetId']}:{item['templateKey']}:{item['revision']}"
            )
    duplicates = {
        asset_id: identities
        for asset_id, identities in sorted(identities_by_asset.items())
        if len(identities) > 1
    }
    statuses = Counter(str(item.get("status")) for item in pool.assignments)
    return {
        "artifactType": "style_test_pool_audit",
        "schemaVersion": "1.0.0",
        "producer": "style-template-analyzer",
        "pool": pool_file.resolve().as_posix(),
        "ledger": ledger_file.resolve().as_posix(),
        "capacity": distribution,
        "assignmentCount": len(pool.assignments),
        "assignmentStatuses": dict(sorted(statuses.items())),
        "duplicateActiveAssetCount": len(duplicates),
        "duplicateActiveAssets": duplicates,
        "migrationRequired": any(item.get("schemaVersion") == "1.0.0" for item in pool.assignments),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pool", type=Path)
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.pool, args.ledger), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

