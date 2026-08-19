---
name: style-template-analyzer
description: 把参考图编译为 prompt-only 风格模板审核包，或基于已批准基线、GoodCase 和 BadCase 自主生产新模板；根据人工验收决定释放或消费真实测试图，对通过项执行 OSS 上传、URL 回填与正式包交付。用于风格模板、参考图编译、模板自生产、阶段路由、审核验收、真实测试图池、GoodCase/BadCase 沉淀、OSS 最终化、契约迁移与维护审计。
---

# 风格模板生产

把两个业务意图统一路由到三个阶段。日常主流使用 `scripts/style_review_workflow.py`；`scripts/style_v3_workflow.py` 只承担存量包兼容。

## 先路由意图和阶段

| 业务意图 | 阶段 1：审核包 | 阶段 2：人工验收 | 阶段 3：正式化 |
| --- | --- | --- | --- |
| 根据参考编译 | `compile-reference` | `review-decision` | `finalize` |
| 自生产 | `self-produce` | `review-decision` | `finalize` |

阶段 1 只交付当前 revision 的 `style-template.json + cover.png`，保存分析、真图分配和生成回执，不写 OSS。阶段 2 以人工对这个具体视觉 revision 的决定为准。阶段 3 只处理通过项，上传 OSS、回填 URL，交付正式包。批次允许部分通过，每个 revision 独立最终化。

## 阶段 1：生成审核包

### 参考编译

1. 读取 `references/style-analysis-and-prompting.md` 和 `references/style-template-contract.md`。
2. 分解用户内容不变量、授权变换、模板常量和参考禁迁移项；形成七维成像指纹与 3–6 个可评分机制。
3. 编译官方形状 `style-template.json`；运行时只依赖用户上传图和 prompt。
4. 从全局真图池预留一张可用真实摄影图，生成封面并执行轻量技术检查。
5. 用 manifest 4.0.0 `review-package` 校验后原子发布，把测试图转为 `awaiting_approval`。

### 自生产

1. 读取 `references/self-production-strategy.md`、`references/goodcase-after-aesthetics.md`、`references/badcase-learning.md` 和最新有效批准基线。
2. 用 `X 图形语言 × Y 空间语法 × B 内容绑定 × C 边界策略` 设计候选，执行审美非退化、信息增量、结构有效性、识别度和印制闭合门禁；材质默认只作辅助表现。
3. 在基线、当前批次和经验快照中检查 key、标题、prompt 机制和类别新颖性。
4. 每个合格候选调用同一审核包内核。经验快照不可用时使用最新有效版并记录警告，继续交付当前批次。

## 阶段 2：记录人工验收

人工决定支持四种值：

- `pass`：冻结封面 SHA-256 和 prompt SHA-256，测试图转为 `consumed`，立即进入阶段 3。
- `reject`：记录人工驳回证据，测试图转为 `released`，该 revision 可异步进入 BadCase。
- `pending`：保持 `awaiting_approval` 和当前占用，不设超时自动释放。
- `manual_release`：只在人工明确要求时把待定测试图转为 `released`。

通过与驳回决定可调用经验沉淀 adapter。沉淀失败只返回 warning，不回滚审核决定，不阻塞 OSS 正式化。

## 阶段 3：正式化

1. 校验 `approval-decision-receipt.json` 为人工 `pass`，测试图状态为 `consumed`，双 SHA 与审核包一致。
2. 按封面内容哈希执行可恢复 OSS 上传，回填受控 HTTPS URL，运行 remote validator。
3. 用 manifest 4.0.0 `final-package` 原子发布严格两文件 `package/`。
4. OSS 失败时保留人工通过结论与测试图消费状态；修复配置后重试阶段 3。

读取 `references/oss-handoff.md` 获取受控域名、恢复和密钥边界。

## 测试图状态机

```text
ready → reserved → awaiting_approval → released
                                  └→ consumed
```

- 唯一性按全局 ledger 计算，跨 `deliverySetId` 也不得并发复用。
- 技术失败只能在进入人工审核前由系统释放 `reserved`。
- 进入 `awaiting_approval` 后，系统无权根据超时、任务结束或 OSS 失败释放。
- 只有人工 `pass` 会消费；人工 `reject` 和 `manual_release` 返回可用容量。
- v1 `committed` 存量记录缺少人工通过证据，读取时按 `legacyHeld` 安全占用；只能根据人工决策表迁移。

测试图池维护时读取 `references/test-image-pool.md` 和 `references/test-image-admission.md`。

## 交付结构

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
    └── approval-decision-receipt.json  # 人工表态后

<run>/<key>/<revision>/
├── artifact-manifest.json
├── package/
│   ├── style-template.json
│   └── cover.png
└── internal/
    ├── approval-decision-receipt.json
    └── oss-finalization-receipt.json
```

只交付当前阶段的两文件公开目录。内部证据通过相邻 manifest 追溯，不注入官方 `style-template.json`。

## 后续经验与评测

- 把通过 revision 写入 GoodCase，把驳回 revision 写入 BadCase，重建可版本化经验快照。
- 当前生产任务在正式包交付后即可完成；经验沉淀、测试图补池和完整真图评测走旁路。
- 只在用户明确要求完整评测时运行 `evaluate(final-package)`，评测不修改正式包。

## 验证

```bash
python scripts/validate_style_package.py <review-root> --profile review-package
python scripts/validate_style_package.py <final-root> --profile final-package --assets-domain <assets-host>
python scripts/audit_style_test_pool.py <pool.json> <assignment-ledger.json>
python scripts/migrate_test_image_ledger_v2.py <legacy-ledger.json> <human-decisions.json> <new-ledger.json>
corepack pnpm test
python /Users/xiaoyuan/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

完成时报告审核包、人工决定、正式包、OSS 和经验沉淀各自的实际状态。
