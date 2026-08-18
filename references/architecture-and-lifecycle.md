# v3 架构与生命周期

## 1. 公开 seam

| 接口 | 输入 | 成功结果 |
| --- | --- | --- |
| `compile(reference)` | 参考图、compiler、ready 测试图池、持久 ledger、OSS adapter | 默认返回一个最终模板包；明确 preview 时返回待发布产物 |
| `produce(baseline)` | 批准记录、candidate proposer、ready 测试图池、持久 ledger、OSS adapter | 批准前返回候选效果；批准后收到最终化指令才返回逐条最终模板包结果 |
| `evaluate(package)` | 已完成最终模板包与独立真图测试集 | 独立评测交接物 |
| `maintain-test-pool` | 来源、查询、采集上限、checkpoint | 待门禁测试图记录 |

`compile` 与 `produce` 是两个一等入口，共用测试图分配、封面生成、轻量封面检查、OSS 上传、正式 URL 回填、最终契约校验和原子发布内核。网页来源、生成器、OSS 和评测通过适配器接入。`compile` 的模板包请求包含 OSS 授权；`produce` 先停在候选视觉审批，数量目标或“模板包”字样不能跳过该门禁。批准只更新名单，批准后的“产出通过的模板包”“完成 OSS 最终化”或“上传 OSS”等指令才授权外部写入。

## 2. 生命周期

```text
reference → compile ───────────────────────────────────────┐
baseline → produce → candidate preview → explicit approval │
                    → exact variant freeze
                    → post-approval finalization request ──┤
                                                          ↓
                      cover → lightweight check → OSS upload
                            → URL backfill → final package → evaluation
```

`final package` 是默认完成点，且只在 OSS 上传、正式 URL 回填和最终契约校验完成后存在。待发布产物是内部状态，不使用 package 命名。真图评测是独立、显式阶段，不阻塞拿包，也不参与 OSS 是否执行的判断。

### 2.1 `produce` 的批准前门禁

自生产先执行 `references/self-production-strategy.md`：以图形语言 X 和空间结构 Y 组成候选，直接生成效果图，检查审美非退化、结构差异、信息增量、完整闭合、跨输入泛化和测试图展示质量。用户通过附件选图时，批准对象是具体视觉 revision；首版、retry、replacement 和总览副本统一纳入精确匹配。收到最终化指令后，先冻结批准专用编译规格并通过封面/prompt 双 SHA 门禁，再进入测试图正式分配和 OSS 最终化。弱 Y、同构换皮、机械重复、伪框/伪蒙版、无关系的媒介并置、过度变形、随机裁切或测试图干扰判断的方向在此阶段淘汰。

## 3. 单模板事务

1. 对 `runRoot + deliverySetId + key + revision` 取得跨进程 identity 锁。
2. 校验具体批准 revision、批准专用编译规格、封面/prompt 双 SHA、批准基线、新颖性和整批 ready 容量，预留 `deliverySetId + key + revision → assetId`。
3. 在 revision 同级临时工作区写模板草稿、分析、预留证据和状态 checkpoint。
4. 调用生成器产出本地 `cover.png`，执行轻量封面检查；模板画面问题最多重生成一次，仍失败则保存失败 revision。
5. preview 请求在待发布产物处结束，不创建模板包；`compile` 默认请求继续进入 OSS，`produce` 仅在批准记录和批准后的最终化指令同时存在时继续进入 OSS。
6. 上传封面，保存上传回执，把受控正式 URL 回填模板草稿，在 staging 目录执行最终 Schema、URL 域名、哈希、manifest 和严格两文件校验。
7. 把 ledger 标记为 `publishing`，原子发布最终 revision 目录，再把 ledger 提交为 `committed` 并释放 identity 锁。

失败时只清理本事务精确 staging；OSS 已上传但最终包未发布时保留上传回执并进入可恢复或待清理状态。原子发布后提交失败会删除本事务刚发布的 revision 并释放未提交预留。进程在发布后中断时，重试会校验最终 revision 与 OSS 回执，并把相同 identity/asset 的 `publishing` 记录恢复为 `committed`。已存在且最终校验通过的 revision 作为幂等成功返回。

评测阶段先在目标同级 staging 写入并完成契约校验，再原子发布；它只引用最终模板包，不修改包内两文件。

批量生产在调用生成器前检查整批容量；每个候选独立发布，批次允许部分成功。

## 4. 契约版本

- `style-template.json`：官方业务形状保持 `1.0.0`。
- analysis/evaluation：新文件使用 `2.0.0`，legacy 继续读取 `2.0`。
- artifact manifest：v1 对应 authoring/evaluation/handoff 旧生命周期；v2 记录 candidate、prepublish、OSS receipt、final-package 与 evaluation 的内部关联。
- 收到未知更高 major 时返回 `failed: contract_version_unsupported`。
- 新封面名为 `cover.png`；旧 `effect.png` 由 legacy 路径继续识别。

## 5. 模块责任

| 模块 | 责任 |
| --- | --- |
| `style_contracts.py` | artifact、版本、stage、哈希和 manifest 构建 |
| `validate_style_package.py` | profile 编排、两文件门禁、manifest 引用 |
| `style_baseline.py` | 批准基线快照、数量/身份/digest 校验 |
| `style_test_pool.py` | 权利门禁、照片元数据、去重、容量和唯一分配 |
| `style_source_adapter.mjs` | 合规来源采集、来源级熔断、metadata checkpoint |
| `style_pool_ingest.py` | 图片下载、视觉门禁、asset checkpoint、标准化与入池 |
| `style_v3_workflow.py` | compile/produce、轻量封面检查、OSS 最终化和评测事务编排 |
| `validate_approved_variants.py` | 批准集合、精确视觉 revision、封面/prompt 双 SHA 和测试图唯一性门禁 |
| `finalize_style_batch.mjs` | OSS dry-run、受控域名上传、正式 URL 回填与官方 JSON 输出适配 |

## 6. 业务目录

- 待发布产物与最终模板包：总库 `05-风格化模板生产` 下的明确批次目录，使用独立内部记录目录与严格两文件公开包目录。
- 测试图池、完整评测与报告：总库 `06-模板质量评测`。
- OSS 待导入、人工验收与上线记录：总库 `07-数据验收与上线`。
- 仓库 `artifacts/` 只放自动测试和临时运行产物。

## 7. 修改规则

1. 保持官方 STYLE_REF 业务载荷与内部证据隔离。
2. 字段语义破坏性变化递增 major；向后兼容新增递增 minor；说明和校验修正递增 patch。
3. 同步 contract registry、Schema、运行常量、契约测试、Skill manifest 和迁移说明。
4. 保留 v1/v2 读取路径，除非明确发布新的破坏性迁移。
5. 修改后运行专项测试、94 基线回归、Skill 结构验证和全局副本 hash 校验。
