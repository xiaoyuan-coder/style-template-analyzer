#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import unittest

from style_effect_contract import BOUNDARY_MODES, bind_effect_contract, validate_effect_contract


PROMPT = " ".join(f"执行边界：{dimension}" for dimension in BOUNDARY_MODES) + " 必须生成连续水墨叠纸带"


def draft() -> dict:
    return {
        "artifactType": "effect_reproduction_contract",
        "schemaVersion": "1.0.0",
        "producer": "style-template-analyzer",
        "templateKey": "ink-water-paper-ribbon",
        "authorityMode": "after-first",
        "boundaryDecisions": [
            {
                "dimension": dimension,
                "mode": next(iter(sorted(modes))),
                "evidence": f"Approved After evidence for {dimension}",
                "promptDirective": f"执行边界：{dimension}",
            }
            for dimension, modes in BOUNDARY_MODES.items()
        ],
        "templateConstants": [{
            "name": "水墨叠纸带",
            "sourceBinding": "adaptive",
            "required": True,
            "evidence": "Approved After 中跨越主体的连续材质转折",
            "promptDirective": "必须生成连续水墨叠纸带",
        }],
        "unresolvedConflicts": [],
        "evidenceBinding": {
            "sourceAssetId": "asset-a",
            "sourceSha256": "a" * 64,
            "effectSha256": "b" * 64,
            "promptSha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
            "generationMode": "single-image-prompt-only",
            "approvedAfterUsedAsInput": False,
        },
    }


class EffectContractTests(unittest.TestCase):
    def test_complete_contract_passes(self) -> None:
        self.assertEqual(validate_effect_contract(
            draft(),
            expected_key="ink-water-paper-ribbon",
            prompt_template=PROMPT,
        ), [])

    def test_missing_boundary_is_rejected(self) -> None:
        data = draft()
        data["boundaryDecisions"].pop()
        self.assertTrue(any("boundaryDecisions" in error for error in validate_effect_contract(data)))

    def test_directive_must_be_in_runtime_prompt(self) -> None:
        data = draft()
        self.assertTrue(any("未进入 promptTemplate" in error for error in validate_effect_contract(
            data,
            prompt_template="只有通用水彩说明",
        )))

    def test_rejects_internal_or_dangling_directive_wording(self) -> None:
        data = draft()
        data["boundaryDecisions"][0]["promptDirective"] = "主体范围遵循前文来源绑定"
        self.assertTrue(any("内部合同或悬空指代用语" in error for error in validate_effect_contract(data)))

    def test_binding_freezes_source_effect_and_prompt(self) -> None:
        data = draft()
        data.pop("evidenceBinding")
        bound = bind_effect_contract(
            data,
            template_key="ink-water-paper-ribbon",
            prompt_template=PROMPT,
            source_asset_id="asset-a",
            source_sha256="c" * 64,
            effect_sha256="d" * 64,
        )
        self.assertEqual(bound["evidenceBinding"]["sourceSha256"], "c" * 64)
        self.assertEqual(bound["evidenceBinding"]["effectSha256"], "d" * 64)
        self.assertEqual(
            bound["evidenceBinding"]["promptSha256"],
            hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
