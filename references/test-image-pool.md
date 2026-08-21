# 高认知测试图池消费约定

候选采集、人工筛选、历史批次、筛选经验和准入池发布由独立 `test-image-pool-curator` Skill 负责。本仓库只读取已经发布的 `pool.json`，并管理模板生产侧的 assignment ledger。

## 支持的交接身份

测试图池版本与生产方必须严格成对出现：

| 用途 | `schemaVersion` | `producer` |
| --- | --- | --- |
| 历史高认知池兼容 | `2.0.0` | `style-template-analyzer` |
| 当前正式交接 | `2.1.0` | `test-image-pool-curator` |

交叉组合一律拒绝。schema `1.0.0` / `1.1.0` 仅用于既有真实摄影池兼容，不作为新增高认知测试图入口。

## 消费门禁

读取池时必须同时满足：

- `artifactType` 为 `style_test_image_pool`；
- 版本和生产方符合上表；
- 每张高认知测试图的状态为 `ready`，并带有完整 `recognitionAnchor`；
- 本地图片存在，实际 SHA-256、尺寸和 MIME 与池记录一致；
- 同一池内不混用旧摄影资产和高认知锚点资产。

2.x 上游池是只读交接物。模板生产不得追加、删除或改写其资产；所有占用和人工验收状态只写入 assignment ledger。

## 预留与状态管理

```bash
python scripts/style_workflow_cli.py reserve-test-image \
  --pool <pool.json> \
  --ledger <assignment-ledger.json> \
  --delivery-set <delivery-set-id> \
  --template-key <key>
```

```text
ready → reserved → awaiting_approval → released
                                  └→ consumed
```

- `reserved`：审核包生成事务已占用；进入人工审核前的技术失败可由系统释放。
- `awaiting_approval`：封面已进入人工验收，持续占用。
- `released`：人工 Reject 或明确释放，测试图恢复可分配。
- `consumed`：人工 Pass，测试图永久退出可用容量。

唯一性按全局 ledger 计算，跨 `deliverySetId` 也不得并发复用。历史 v1 `committed` 记录按 `legacyHeld` 安全占用，只能依据人工决策表迁移。

## 上下游边界

需要采集、筛选、查看历史批次、重建经验或发布新池时，切换到 `test-image-pool-curator` 仓库。style-template-analyzer 只负责：

1. 校验并加载已发布池；
2. 为模板 revision 预留测试图；
3. 在人工审核阶段维护 `reserved / awaiting_approval / released / consumed`；
4. 审计容量、重复占用和历史 ledger 迁移。
