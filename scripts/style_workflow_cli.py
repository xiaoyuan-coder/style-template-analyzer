#!/usr/bin/env python3
"""One command surface for gated style-template production phases."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from style_experience_store import DurableExperienceStore, ExperienceStoreError
from style_dynamic_baseline import DynamicBaselineCatalog, DynamicBaselineError
from style_reference_gate import validate_reference_interpretation
from style_retirement import RetirementRegistryError, retire_template_transaction
from style_operational_audit import (
    OperationalAuditError,
    diagnose_delivery,
    workflow_status_snapshot,
)
from style_review_workflow import ReviewWorkflowError, compile_reference, record_review_decision
from style_test_pool import TestImagePool, TestPoolError
from validate_approved_variants import validate as validate_approved_variants


DEFAULT_BASELINE_CATALOG = (
    Path(__file__).parents[1]
    / "references/dynamic-baseline.json"
).resolve()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _emit(value: object) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


def _compile_prebuilt(args: argparse.Namespace) -> dict[str, Any]:
    template = _read(args.template)
    analysis = _read(args.analysis)
    interpretation = _read(args.interpretation)
    visual_review = _read(args.visual_review)
    generation_receipt = _read(args.generation_receipt)
    pool = TestImagePool.load(args.pool, args.ledger)
    identity = (args.delivery_set, template.get("key"), args.revision)
    assignment = next((
        item for item in pool.assignments
        if (item.get("deliverySetId"), item.get("templateKey"), item.get("revision")) == identity
    ), None)
    if assignment is None or assignment.get("status") not in {"reserved", "awaiting_approval"}:
        raise ReviewWorkflowError("test_asset_must_be_reserved_before_generation")
    if generation_receipt.get("sourceAssetId") != assignment.get("assetId"):
        raise ReviewWorkflowError("generated_cover_source_asset_mismatch")

    def compiler(reference: Path) -> dict[str, dict[str, Any]]:
        return {"template": template, "analysis": analysis, "referenceInterpretation": interpretation}

    def generator(asset: dict[str, Any], template_data: dict[str, Any], output: Path) -> dict[str, Any]:
        shutil.copy2(args.generated_cover, output)
        return generation_receipt

    def visual_checker(output: Path, template_data: dict[str, Any], semantics: dict[str, Any], attempt: int) -> dict[str, Any]:
        return visual_review

    return compile_reference(
        args.reference,
        compiler,
        pool,
        generator,
        run_root=args.run_root,
        delivery_set_id=args.delivery_set,
        ledger_file=args.ledger,
        revision=args.revision,
        reference_visual_checker=visual_checker,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="风格模板生产统一门禁命令")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reference = subparsers.add_parser("validate-reference", help="校验参考图语义解释")
    reference.add_argument("interpretation", type=Path)
    reference.add_argument("--template-key", default="")

    compile_parser = subparsers.add_parser("compile-reference", help="从预编译输入原子生成待审核包")
    for name in ("reference", "template", "analysis", "interpretation", "generated-cover", "generation-receipt", "visual-review", "pool", "ledger", "run-root"):
        compile_parser.add_argument(f"--{name}", type=Path, required=True)
    compile_parser.add_argument("--delivery-set", required=True)
    compile_parser.add_argument("--revision", type=int, default=1)

    reserve = subparsers.add_parser("reserve-test-image", help="先预留测试图，再进行封面生成")
    reserve.add_argument("--pool", type=Path, required=True)
    reserve.add_argument("--ledger", type=Path, required=True)
    reserve.add_argument("--delivery-set", required=True)
    reserve.add_argument("--template-key", required=True)
    reserve.add_argument("--revision", type=int, default=1)

    review = subparsers.add_parser("review-decision", help="记录人工结论并强制沉淀经验")
    review.add_argument("--review-root", type=Path, required=True)
    review.add_argument("--verdict", choices=["pass", "reject", "pending", "manual_release"], required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--pool", type=Path, required=True)
    review.add_argument("--ledger", type=Path, required=True)
    review.add_argument("--experience-root", type=Path, required=True)
    review.add_argument("--baseline-catalog", type=Path, default=DEFAULT_BASELINE_CATALOG)

    audit = subparsers.add_parser("audit-experience", help="校验当前经验快照是否新鲜")
    audit.add_argument("experience_root", type=Path)

    rebuild = subparsers.add_parser("rebuild-experience", help="合并现有 GoodCase/BadCase 并重建当前经验快照")
    rebuild.add_argument("--experience-root", type=Path, required=True)
    rebuild.add_argument("--goodcase", type=Path, required=True)
    rebuild.add_argument("--badcase", type=Path, required=True)

    audit_baseline = subparsers.add_parser("audit-baseline", help="校验动态基线并报告当前有效模板")
    audit_baseline.add_argument("catalog", type=Path, nargs="?", default=DEFAULT_BASELINE_CATALOG)

    status = subparsers.add_parser("status", help="以统一通过索引为权威报告正式化、交付和 Before 可发现性")
    status.add_argument("--catalog", type=Path, required=True)
    status.add_argument("--data-root", type=Path)
    status.add_argument("--delivery-root", type=Path)

    diagnose = subparsers.add_parser("diagnose-delivery", help="诊断工作台 JSON 是否仍指向旧 revision")
    diagnose.add_argument("delivery", type=Path)
    diagnose.add_argument("--catalog", type=Path, required=True)
    diagnose.add_argument("--data-root", type=Path)

    approved_variants = subparsers.add_parser(
        "validate-approved-variants",
        help="校验用户附件、精确视觉 revision 与实际生成提示词的绑定",
    )
    approved_variants.add_argument("approval", type=Path)
    approved_variants.add_argument("compilation", type=Path)

    retire = subparsers.add_parser("retire-template", help="登记人工退役并释放该模板占用的测试图")
    retire.add_argument("--template-key", required=True)
    retire.add_argument("--reason", required=True)
    retire.add_argument("--registry", type=Path, required=True)
    retire.add_argument("--catalog", type=Path, required=True)
    retire.add_argument("--pool", type=Path, required=True)
    retire.add_argument("--ledger", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-reference":
            errors = validate_reference_interpretation(_read(args.interpretation), expected_key=args.template_key)
            if errors:
                raise ReviewWorkflowError(f"reference_interpretation_failed: {'; '.join(errors)}")
            return _emit({"ok": True, "gate": "reference-semantics"})
        if args.command == "compile-reference":
            return _emit({"ok": True, **_compile_prebuilt(args)})
        if args.command == "reserve-test-image":
            pool = TestImagePool.load(args.pool, args.ledger)
            assignment = pool.reserve_persisted(
                args.delivery_set,
                args.template_key,
                args.revision,
                args.ledger,
            )
            return _emit({"ok": True, "assignment": assignment})
        if args.command == "review-decision":
            pool = TestImagePool.load(args.pool, args.ledger)
            store = DurableExperienceStore(args.experience_root)
            baseline = DynamicBaselineCatalog(args.baseline_catalog)
            return _emit({"ok": True, **record_review_decision(
                args.review_root,
                args.verdict,
                args.reason,
                pool,
                args.ledger,
                experience_sink=store,
                baseline_sink=baseline,
            )})
        if args.command == "rebuild-experience":
            store = DurableExperienceStore(args.experience_root)
            return _emit({"ok": True, **store.merge_legacy_corpora(args.goodcase, args.badcase)})
        if args.command == "audit-baseline":
            snapshot, _ = DynamicBaselineCatalog(args.catalog).load_active()
            return _emit({"ok": True, "snapshot": snapshot})
        if args.command == "status":
            return _emit({"ok": True, "snapshot": workflow_status_snapshot(
                args.catalog,
                data_root=args.data_root,
                delivery_root=args.delivery_root,
            )})
        if args.command == "diagnose-delivery":
            report = diagnose_delivery(args.delivery, args.catalog, data_root=args.data_root)
            return _emit({"ok": not report["issues"], "diagnostic": report})
        if args.command == "validate-approved-variants":
            errors = validate_approved_variants(args.approval.resolve(), args.compilation.resolve())
            if errors:
                raise ReviewWorkflowError(f"approved_variant_binding_failed: {'; '.join(errors)}")
            return _emit({"ok": True, "gate": "approved-variant-binding"})
        if args.command == "retire-template":
            pool = TestImagePool.load(args.pool, args.ledger)
            retirement, removed_catalog_entries, released = retire_template_transaction(
                pool,
                args.ledger,
                args.registry,
                args.catalog,
                args.template_key,
                args.reason,
            )
            return _emit({
                "ok": True,
                "retirement": retirement,
                "removedCatalogEntries": removed_catalog_entries,
                "releasedAssetIds": sorted({item["assetId"] for item in released}),
            })
        store = DurableExperienceStore(args.experience_root)
        return _emit({"ok": True, "snapshot": store.load_fresh_snapshot()})
    except (
        OSError,
        json.JSONDecodeError,
        ReviewWorkflowError,
        TestPoolError,
        ExperienceStoreError,
        DynamicBaselineError,
        RetirementRegistryError,
        OperationalAuditError,
    ) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
