# v3 / v4 → v5 迁移

## v5 变更

- `compile-reference` 与 `self-produce` 默认停在 manifest 4.0.0 `review-package`。
- 人工审核后写 `approval-decision-receipt.json`。通过项继续 OSS 最终化，其他项停留在审核阶段。
- 测试图分配升级为 2.0.0：`reserved → awaiting_approval → released | consumed`。
- 全局可用容量由池目录与 ledger 合并计算。`ready` 报告可实际分配数，`catalogReady` 报告权利与视觉准入通过的原始目录数。
- GoodCase/BadCase 以人工 `pass/reject` 为准，与 OSS 结果解耦。

## v1 ledger 兼容策略

v1 `committed` 只能证明旧代流程已发布封面，无法证明人工验收通过。新运行时按以下方式处理：

1. 保留 v1 记录和原始时间，不伪造 `pass` 回执。
2. `reserved/publishing/committed` 都计入 `legacyHeld`，对新分配全局占用。历史上重复绑定的同一 asset 只占一份容量，保留所有历史记录。
3. 用人工决策表为每个具体 revision 补齐 `pass/reject/pending/manual_release`、封面 SHA 和 prompt SHA。
4. 只把有明确 `pass` 证据的记录迁移为 `consumed`；`reject/manual_release` 迁移为 `released`；`pending` 迁移为 `awaiting_approval`。
5. 同一 asset 存在多个历史 `pass` 时中止自动迁移，交给人工指定唯一归属或补换测试图。

未完成人工决策表前，系统使用兼容读取路径，不覆盖业务 ledger。

```bash
python scripts/migrate_test_image_ledger_v2.py \
  <legacy-ledger.json> <human-decisions.json> <new-ledger.json>
```

迁移命令要求决策表覆盖全部 v1 identity，输出路径必须尚不存在。两条 `pass` 试图消费同一 asset 时直接失败，不自动选择归属。

## 存量包

- manifest 2.0.0 `package` 和 manifest 3.0.0 `prepublish/final-package` 保持可读。
- v4 正式包可直接作为历史交付物，不原地改写。
- 需要重做效果或纳入新状态机时创建新 revision，从 `review-package` 重新走人工验收。
- 存量 `effect.png` 与 analysis/evaluation 2.0 继续通过 legacy profile。

## 迁移校验

1. 运行池分布报告，分别核对 `catalogReady`、`ready`、`legacyHeld`、`consumed`。
2. 审计 asset 的全局重复占用和多通过冲突。
3. 对新 ledger 运行 assignment 2.0.0 Schema 与状态迁移测试。
4. 执行 94 基线回归、全量契约测试和 Skill 快速校验。
