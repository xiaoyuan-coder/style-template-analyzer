# ADR 0017：模板退役释放测试图并退出活动基线

- 状态：Accepted
- 日期：2026-08-22
- 修订：ADR 0013 中“已消费测试图持续占用”的边界

## 背景

人工通过会把测试图记为 `consumed`，用于避免活动模板之间重复使用同一张测试图。模板退役后继续占用该资产不再服务当前模板集合，也会无谓降低测试图池容量。退役 key 同时需要退出统一活动目录和动态基线，历史正式 revision 与审核证据仍需保留。

## 决策

1. 新增 `retire-template` 作为唯一退役入口，要求模板 key、人工理由、退役索引、已发布测试图池和 assignment ledger。
2. 命令先幂等登记 `已退役模板索引.json`，再把该 key 的 `reserved / awaiting_approval / consumed` 分配转为 `released`。中断后重试可补齐 ledger。
3. 退役释放把 assignment 升级到 3.0.0，使用人工 `template_retired` 决定，并把原决定保存在 `previousDecision`。历史 assignment 继续保留，同一 `deliverySetId` 的禁复用记录不被删除。
4. 统一目录重建和动态基线读取都以退役索引为排除依据。退役登记与动态基线晋升共享生命周期锁；人工 Pass 在修改 ledger、回执和经验之前持有同一锁并确认 key 仍处于活动状态。
5. 正式 revision、审核回执和既有包目录继续保存，只从活动 catalog 与生产基线中退出。

## 结果

退役动作成为可重试、可审计的一次业务操作。释放后的测试图可以在新的 `deliverySetId` 中再次使用；原批次仍受完整历史去重约束。
