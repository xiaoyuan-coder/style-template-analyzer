# 审核门禁架构与生命周期

## 公开 seam

| 接口 | 责任 | 完成点 |
| --- | --- | --- |
| `compile-reference` | 解析参考并编译一个审核包 | `awaiting_approval` |
| `self-produce` | 读取创意母题、动态基线与经验快照，生成若干独立审核包 | 逐项 `awaiting_approval` |
| `review-decision` | 记录人工通过、驳回、待定或明确释放 | 决定回执与测试图终态/持续占用 |
| `finalize` | 对已通过 revision 上传 OSS 并回填 URL | `final-package` |
| `evaluate` | 使用独立测试集评测正式包 | 独立评测交接物 |

`compile-reference` 与 `self-produce` 是两个业务意图，共用审核包、人工决定、最终化三阶段内核。统一命令入口是 `style_workflow_cli.py`，网页来源、生成器、独立视觉 reviewer、经验沉淀和 OSS 通过 adapter 接入。

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
2. 参考编译先校验参考语义角色、解释性结构排除和歧义清零；自生产先校验经验快照与语料摘要一致。
3. 校验模板、分析、基线与当前全局可用容量。
4. 写全局 ledger `reserved`，在 revision 同级 staging 生成封面与技术回执。
5. 参考编译由独立 reviewer 生成六维视觉回执，排除自审、低分和解释性结构复制。
6. 写入预期 `awaiting_approval` 分配，执行 manifest 5.1.0 `review-package` 校验。
7. 原子发布审核包，再原子提交 ledger `awaiting_approval`。提交失败时撤回审核包。

封面生成或技术检查失败发生在人工审核前，系统可写 `system_failure` 并释放预留。

### 阶段 2

1. 读取审核包与当前 ledger，校验身份和状态。
2. 冻结封面 SHA-256 与 prompt SHA-256。
3. 先原子提交 ledger 决定，再替换审核包内部证据；如文件替换中断，重试根据 ledger 恢复。
4. 对 `pass/reject` 幂等写入 GoodCase/BadCase 经验账本并重建当前快照，随后写入经验沉淀回执。
5. 对 `pass` 幂等登记统一通过目录并刷新动态基线；同 key 激活最高通过 revision。经验或基线登记失败时保留重试入口，并拦截 OSS。

同一 revision 的人工终态不可改写；要求新效果时创建新 revision。

### 阶段 3

1. 只接受 `consumed + human pass + 双 SHA 一致` 的审核包。
2. OSS adapter 按封面内容哈希去重，上传后 HEAD 验证，输出受控域名 URL。
3. 要求经验沉淀和动态基线登记回执已经存在，在 staging 生成严格两文件 `package/`，运行 manifest 5.1.0 `final-package` 与 remote validator。
4. 原子发布。已存在且校验通过的正式 revision 作为幂等成功返回。

批量任务中每个 revision 独立发布，允许部分成功。

## 后台旁路

- 自生产先从创意提炼库选择高层关系算子，再读取模板实现案例做重复检查；具体实现状态不改写上层创意。
- GoodCase/BadCase 沉淀以人工视觉决定为边界，与 OSS 成功无关。
- 自生产读取与经验语料摘要一致的当前快照；快照缺失、无效或过期时停止新一轮生产。
- 测试图补池、权利审计和完整真图评测均不进入日常主事务。

## 契约版本

- 官方 `style-template.json`：1.0.0，形状保持不变。
- 测试图分配与 ledger：2.0.0，存量 v1 只读兼容。
- artifact manifest：5.1.0 增加动态基线登记回执；5.0.0 提供参考语义、独立视觉和经验回执；4.0.0 只读兼容。
- 审核决定回执：1.0.0。
- 未知更高 major 返回 `failed: contract_version_unsupported`。

## 模块责任

| 模块 | 责任 |
| --- | --- |
| `style_review_workflow.py` | 两意图、三阶段路由和事务编排 |
| `style_workflow_cli.py` | 日常生产、人工决定与经验审计的统一命令入口 |
| `style_reference_gate.py` | 参考语义与独立视觉比较门禁 |
| `style_experience_store.py` | 幂等经验账本与新鲜度快照 |
| `style_dynamic_baseline.py` | 人工通过登记、当前 revision 选择与动态快照 |
| `style_test_pool.py` | 全局容量、唯一预留和人工释放/消费状态机 |
| `style_contracts.py` | artifact、版本、stage、哈希和 manifest |
| `validate_style_package.py` | 审核包、正式包和两文件门禁 |
| `style_v3_workflow.py` | v3/v4 存量包读取、评测与迁移兼容 |

## 业务目录

- 创意母题与模板实现案例：总库 `05-风格化模板生产/01-风格参考素材` 下分库存放。
- 审核包：总库 `05-风格化模板生产/06-待验收模板/<batch>/review-packages`。
- 已通过正式包：总库 `05-风格化模板生产/04-研发交付/已通过正式模板包/<key>/<revision>`。
- 测试图池、GoodCase/BadCase 与评测：总库 `06-模板质量评测`；统一经验总账固定在 `05-问题分类与案例/风格模板经验总账`。
- 人工通过回执：总库 `07-数据验收与上线/04-人工验收记录/风格模板/已通过`。
- UAT、待导入与上线记录：总库 `07-数据验收与上线`。
