# 审核门禁架构与生命周期

## 公开 seam

| 接口 | 责任 | 完成点 |
| --- | --- | --- |
| `compile-reference` | 解析参考并编译一个审核包 | `awaiting_approval` |
| `self-produce` | 读取批准基线与经验快照，生成若干独立审核包 | 逐项 `awaiting_approval` |
| `review-decision` | 记录人工通过、驳回、待定或明确释放 | 决定回执与测试图终态/持续占用 |
| `finalize` | 对已通过 revision 上传 OSS 并回填 URL | `final-package` |
| `evaluate` | 使用独立测试集评测正式包 | 独立评测交接物 |

`compile-reference` 与 `self-produce` 是两个业务意图，共用审核包、人工决定、最终化三阶段内核。网页来源、生成器、经验沉淀和 OSS 通过 adapter 接入。

## 双状态机

```text
包生命周期：  review-package → approved → final-package
                                   ├→ rejected
                                   └→ pending

测试图生命周期：ready → reserved → awaiting_approval → released
                                                        └→ consumed
```

两条状态线通过 `approval-decision-receipt.json` 关联。`pass` 使测试图进入 `consumed`；`reject` 进入 `released`；`pending` 保持 `awaiting_approval`；`manual_release` 是待定后唯一的主动释放命令。

OSS 属于包最终化。OSS 失败不改变人工通过证据，不释放已消费测试图。

## 单 revision 事务

### 阶段 1

1. 对 `runRoot + deliverySetId + key + revision` 取身份锁。
2. 校验模板、分析、基线与当前全局可用容量。
3. 写全局 ledger `reserved`，在 revision 同级 staging 生成封面与技术回执。
4. 写入预期 `awaiting_approval` 分配，执行 manifest 4.0.0 `review-package` 校验。
5. 原子发布审核包，再原子提交 ledger `awaiting_approval`。提交失败时撤回审核包。

封面生成或技术检查失败发生在人工审核前，系统可写 `system_failure` 并释放预留。

### 阶段 2

1. 读取审核包与当前 ledger，校验身份和状态。
2. 冻结封面 SHA-256 与 prompt SHA-256。
3. 先原子提交 ledger 决定，再替换审核包内部证据；如文件替换中断，重试根据 ledger 恢复。
4. 对 `pass/reject` 投递异步 GoodCase/BadCase 事件。投递失败记 warning。

同一 revision 的人工终态不可改写；要求新效果时创建新 revision。

### 阶段 3

1. 只接受 `consumed + human pass + 双 SHA 一致` 的审核包。
2. OSS adapter 按封面内容哈希去重，上传后 HEAD 验证，输出受控域名 URL。
3. 在 staging 生成严格两文件 `package/`，运行 manifest 4.0.0 `final-package` 与 remote validator。
4. 原子发布。已存在且校验通过的正式 revision 作为幂等成功返回。

批量任务中每个 revision 独立发布，允许部分成功。

## 后台旁路

- GoodCase/BadCase 沉淀以人工视觉决定为边界，与 OSS 成功无关。
- 自生产读取最新有效经验快照；快照更新失败不阻塞当前交付。
- 测试图补池、权利审计和完整真图评测均不进入日常主事务。

## 契约版本

- 官方 `style-template.json`：1.0.0，形状保持不变。
- 测试图分配与 ledger：2.0.0，存量 v1 只读兼容。
- artifact manifest：4.0.0 提供 `review-package/final-package`。
- 审核决定回执：1.0.0。
- 未知更高 major 返回 `failed: contract_version_unsupported`。

## 模块责任

| 模块 | 责任 |
| --- | --- |
| `style_review_workflow.py` | 两意图、三阶段路由和事务编排 |
| `style_test_pool.py` | 全局容量、唯一预留和人工释放/消费状态机 |
| `style_contracts.py` | artifact、版本、stage、哈希和 manifest |
| `validate_style_package.py` | 审核包、正式包和两文件门禁 |
| `style_v3_workflow.py` | v3/v4 存量包读取、评测与迁移兼容 |

## 业务目录

- 审核包与正式包：总库 `05-风格化模板生产`。
- 测试图池、GoodCase/BadCase、经验快照与评测：总库 `06-模板质量评测`。
- UAT、待导入、人工验收与上线记录：总库 `07-数据验收与上线`。
