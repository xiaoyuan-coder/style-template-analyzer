---
name: style-template-analyzer
description: 把参考图编译为 prompt-only 风格模板审核包，或基于已批准基线、GoodCase 和 BadCase 自主生产新模板；消费人工准入的高认知测试图，根据模板验收决定释放或消费测试图，对通过项执行 OSS 上传、URL 回填与以 key 命名的单 JSON 交付。用于风格模板、参考图编译、模板自生产、阶段路由、审核验收、GoodCase/BadCase 沉淀、动态基线、OSS 最终化、契约迁移与维护审计。
---

# 风格模板生产

把两个业务意图统一路由到三个阶段。日常操作统一使用 `python scripts/style_workflow_cli.py <command>`；`scripts/style_review_workflow.py` 承担事务内核，`scripts/style_v3_workflow.py` 只承担存量包兼容。

## 先路由意图和阶段

| 业务意图 | 阶段 1：审核包 | 阶段 2：人工验收 | 阶段 3：正式化 |
| --- | --- | --- | --- |
| 根据参考编译 | `compile-reference` | `review-decision` | `finalize` |
| 自生产 | `self-produce` | `review-decision` | `finalize` |

阶段 1 只交付当前 revision 的 `style-template.json + cover.png` 审核包，保存分析、真图分配和生成回执，不写 OSS。阶段 2 以人工对这个具体视觉 revision 的决定为准。阶段 3 只处理通过项，上传 OSS、回填 URL，内部发布正式 revision，并向下游交付一个 `<key>.json`。批次允许部分通过，每个 revision 独立最终化。

## 阶段 1：生成审核包

### 参考编译

1. 读取 `references/style-analysis-and-prompting.md` 和 `references/style-template-contract.md`。
2. 先生成 `reference-interpretation.json`，明确单图/成对/带标注对比、before 与 target-effect 角色、解释性结构排除项和仍存歧义。歧义未清空时停止编译。
3. 分解用户内容不变量、授权变换、模板常量和参考禁迁移项；形成七维成像指纹与 3–6 个可评分机制。
4. 编译官方形状 `style-template.json`；运行时只依赖用户上传图和 prompt。
5. 从高认知测试图池预留一张人工 Pass 的可用图片，生成封面并执行轻量技术检查。
6. 由未参与分析和 prompt 编写的视觉 reviewer 对六个视觉维度独立评分；单项低于 80、平均低于 90、自审或出现对比版式/标题/色条/套准线复制时停止发布。
7. 用 manifest 5.1.0 `review-package` 校验后原子发布，把测试图转为 `awaiting_approval`。

### 自生产

1. 读取 `references/self-production-strategy.md`、独立自生产创意库、`references/goodcase-after-aesthetics.md`、`references/badcase-learning.md` 和 `references/dynamic-baseline.json` 指向的最新动态基线。
2. 根据输入的 `sourceAdvantage` 先选择一个高层创意母题，用其启发问题和变体轴发明内容落点、关系结构与载体；创意母题不绑定固定模板 key、画风或版式。
3. 用 `X 图形语言 × Y 空间语法 × B 内容绑定 × C 边界策略` 编译候选，再读取相关模板实现案例做重复检查和成败校验；材质默认只作辅助表现。
4. 在基线、当前批次和经验快照中检查 key、标题、prompt 机制和类别新颖性，执行审美非退化、信息增量、结构有效性、识别度和印制闭合门禁。
5. 每个合格候选调用同一审核包内核。经验快照缺失、无效或与语料摘要不一致时停止新一轮自生产，先重建 `current.json`。

## 阶段 2：记录人工验收

人工决定支持四种值：

- `pass`：冻结封面 SHA-256 和 prompt SHA-256，测试图转为 `consumed`，沉淀 GoodCase 并自动登记动态基线，然后进入阶段 3。
- `reject`：记录人工驳回证据，测试图转为 `released`，该 revision 同步进入 BadCase 经验总账。
- `pending`：保持 `awaiting_approval` 和当前占用，不设超时自动释放。
- `manual_release`：只在人工明确要求时把待定测试图转为 `released`。

通过与驳回决定必须调用经验沉淀 adapter。`pass` 还必须使用带 `approval_guard` 的权威动态基线 adapter，在任何 ledger、回执和经验变更前锁定生命周期并排除退役 key；缺少该门禁时拒绝 Pass。沉淀成功后写入 `experience-deposit-receipt.json`，基线登记成功后写入 `dynamic-baseline-registration-receipt.json`；任一步失败都会保留可重试的人工结论，并暂停正式化。

## 阶段 3：正式化

1. 校验 `approval-decision-receipt.json` 为人工 `pass`，测试图状态为 `consumed`，双 SHA 与审核包一致。
2. 按封面内容哈希执行可恢复 OSS 上传，回填受控 HTTPS URL，运行 remote validator。
3. 校验经验沉淀与动态基线登记回执已经存在，用 manifest 5.1.0 `final-package` 原子发布严格两文件 `package/`。
4. 从正式 `style-template.json` 导出 `<key>.json`。该 JSON 保持官方字段形状，`cover` 为已验证的 OSS URL，是阶段 3 唯一下游交付文件。
5. OSS 失败时保留人工通过结论与测试图消费状态；修复配置后重试阶段 3。

读取 `references/oss-handoff.md` 获取受控域名、恢复和密钥边界。

## 测试图状态机

```text
ready → reserved → awaiting_approval → released
                                  └→ consumed
                                         └─ 人工退役模板 → released
```

- 唯一性按全局 ledger 计算，跨 `deliverySetId` 也不得并发复用。
- 同一 `deliverySetId` 内保留完整使用历史；测试图即使已 `released`，也不得分配给该批次的其他模板或返工 revision。
- `released` 资产可以在后续新的 `deliverySetId` 中重新分配；`consumed` 资产在模板活动期间退出可用容量，人工执行模板退役时转为 `released`。
- 退役释放会把 assignment 升级为 3.0.0，使用 `template_retired` 决定并在 `previousDecision` 保留原人工结论；普通审核包继续使用 assignment 2.0.0。任何持久化变更都会把 ledger 外层升级为 4.0.0；读取继续兼容外层 1.0.0–3.0.0。
- 技术失败只能在进入人工审核前由系统释放 `reserved`。
- 进入 `awaiting_approval` 后，系统无权根据超时、任务结束或 OSS 失败释放。
- 只有人工 `pass` 会消费；人工 `reject` 和 `manual_release` 返回可用容量。
- v1 `committed` 存量记录缺少人工通过证据，读取时按 `legacyHeld` 安全占用；只能根据人工决策表迁移。

候选采集、人工筛选、历史批次、准入池发布和筛选经验由独立 `test-image-pool-curator` Skill 管理。本 Skill 只消费版本化 `pool.json`：兼容历史 `2.0.0 / style-template-analyzer`，新交接使用 `2.1.0 / test-image-pool-curator`。读取时必须校验图片存在性、SHA-256、尺寸和 MIME；预留、待验收、释放和消费只写入 assignment ledger，不回写上游准入池。具体交接与状态约定见 `references/test-image-pool.md`。

## 交付结构

业务根目录按阶段分开：审核包写入总库 `05-风格化模板生产/06-待验收模板/<batch>/review-packages/`；人工 `pass` 的 revision 立即登记到 `05-风格化模板生产/04-研发交付/已通过正式模板包/<key>/<revision>/`，OSS 完成后更新正式地址。审核回执同步登记到 `07-数据验收与上线/04-人工验收记录/风格模板/已通过/`。每次 `pass` 自动更新动态基线；同 key 以最高通过 revision 为当前有效版本。

统一通过模板目录覆盖新版正式包与已确认通过的历史交付。历史包保持源目录不变，通过 `scripts/rebuild_approved_template_catalog.py` 复制到统一目录并登记 `approvalProvenance`；不得为旧流程伪造新版逐 revision 回执。统一目录清单同时报告 OSS 已正式化与待正式化数量。

人工退役统一执行 `retire-template`：退役索引必须是活动 catalog 同目录的 `已退役模板索引.json`。命令在同一生命周期锁内预校验全部输入，幂等登记退役、从活动 catalog 移除该 key，再把该 key 的测试图占用转为 `released`；任一步失败时回滚已写入的 registry 和 catalog。活动目录和动态基线读取时必须排除退役 key，原正式 revision 与历史审核证据继续保留。

```text
<run>/review-packages/<key>/<revision>/
├── artifact-manifest.json
├── review-package/
│   ├── style-template.json
│   └── cover.png
└── internal/
    ├── style-analysis.json 或 self-production-analysis.json
    ├── test-image-assignment.json
    ├── cover-generation-receipt.json
    ├── cover-check-receipt.json
    ├── reference-interpretation.json  # 参考编译意图
    ├── reference-visual-gate-receipt.json  # 参考编译意图
    ├── approval-decision-receipt.json  # 人工表态后
    ├── experience-deposit-receipt.json  # pass/reject 后
    └── dynamic-baseline-registration-receipt.json  # pass 后

<run>/<key>/<revision>/
├── artifact-manifest.json
├── package/
│   ├── style-template.json
│   └── cover.png
└── internal/
    ├── approval-decision-receipt.json
    └── oss-finalization-receipt.json

<run>/delivery/
├── artifact-manifest.json
└── <key>.json
```

`review-package/` 和正式 revision 的 `package/` 服务审核、回溯与目录管理。阶段 3 的最终下游交付只取 `delivery/<key>.json`；文件名必须与 JSON 内的 `key` 完全一致。内部证据通过相邻 manifest 追溯，不注入交付 JSON。

## 经验与后续评测

- 把通过 revision 写入 GoodCase，把驳回 revision 写入 BadCase，并在同一审核事务中重建可版本化经验快照。
- 统一经验总账位于总库 `06-模板质量评测/05-问题分类与案例/风格模板经验总账/`；`style-experience-corpus.json` 是追加账本，`current.json` 是生产读取入口。
- 经验沉淀是 `pass/reject` 的完成条件；测试图补池和完整真图评测继续走旁路。
- 只在用户明确要求完整评测时运行 `evaluate(final-package)`，评测不修改正式包。

## 验证

```bash
python scripts/style_workflow_cli.py validate-reference <reference-interpretation.json> --template-key <key>
python scripts/style_workflow_cli.py reserve-test-image --help
python scripts/style_workflow_cli.py compile-reference --help
python scripts/style_workflow_cli.py review-decision --help
python scripts/style_workflow_cli.py retire-template --help
python scripts/style_workflow_cli.py rebuild-experience --help
python scripts/style_workflow_cli.py audit-experience <experience-root>
python scripts/style_workflow_cli.py audit-baseline
python scripts/validate_style_package.py <review-root> --profile review-package
python scripts/validate_style_package.py <final-root> --profile final-package --assets-domain <assets-host>
python scripts/audit_style_test_pool.py <pool.json> <assignment-ledger.json>
python scripts/migrate_test_image_ledger_v2.py <legacy-ledger.json> <human-decisions.json> <new-ledger.json>
python scripts/rebuild_approved_template_catalog.py --data-root <总库根目录> --apply
corepack pnpm test
python /Users/xiaoyuan/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

完成时报告审核包、人工决定、正式包、OSS 和经验沉淀各自的实际状态。
