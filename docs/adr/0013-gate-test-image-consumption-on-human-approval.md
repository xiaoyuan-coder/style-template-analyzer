# 以人工通过作为测试图消费门禁

状态：已接受，2026-08-19。

## 背景

旧流程在封面生成或待发布产物落盘后把测试图记为 `committed`。这会把“已生成”和“已人工验收通过”合并为一个事件。当效果未通过或仍待定时，测试图无法按业务真实状态返回图池或保持占用。旧容量统计只查池资产的 `ready` 标签，也会显示原始目录数，未扣除 ledger 占用。

## 决策

1. 把生产分为审核包、人工验收、OSS 最终化三阶段。参考编译和自生产共用该三阶段。
2. 测试图状态改为 `reserved → awaiting_approval → released | consumed`。
3. 人工 `pass` 是 `consumed` 的唯一入口，必须冻结封面 SHA-256 与 prompt SHA-256。
4. 人工 `reject` 直接释放；`pending` 持续占用；待定后只接受人工 `manual_release`。
5. 系统只能在审核包发布前，因生成或技术检查失败释放 `reserved`。
6. 全局 ledger 决定可用容量；跨批次活跃/已消费 asset 不可复用。报告同时暴露 `catalogReady`、`ready`、`legacyHeld` 和 `consumed`。
7. OSS 失败只影响包最终化，人工通过结论和测试图消费保持不变。
8. GoodCase/BadCase 在人工 `pass/reject` 后异步沉淀，不进入当前包交付事务。

## 影响

- 测试图分配契约和 ledger 升级为 2.0.0，artifact manifest 升级为 4.0.0。
- v1 `committed` 缺少人工通过证据，兼容读取时记为 `legacyHeld`，需要人工决策表后才能迁移。
- 日常生产不再把 OSS 置于审核前，因效果未通过造成的无效上传会减少。

