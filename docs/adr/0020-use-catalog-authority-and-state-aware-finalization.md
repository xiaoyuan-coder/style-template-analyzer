# ADR 0020：统一索引权威与状态感知正式化

## 状态

Accepted，2026-08-27。

## 背景

人工 Pass 会在正式目录登记一个本地 cover 的占位 revision。旧最终化逻辑看到目录已存在便按完整远程包校验，导致合法的 `awaiting-finalization` 无法升级。工作台、delivery、统一索引和实际远程 cover 还可能出现状态差异。

## 决策

1. `统一通过模板索引.json` 是活动模板数量与状态查询入口；文件实态用于检测并修正索引漂移。
2. `dynamic-human-pass` 和受控迁移生成的正式占位 revision，在模板与 cover SHA 匹配审核包时允许原位升级。
3. 完成 OSS 后同步正式包、delivery、统一索引、镜像及 `ossStatusCounts`；重复运行负责补齐缺失的下游状态。
4. `status` 报告 catalog 状态、实际状态、delivery 和 Approved Before 可发现性；`diagnose-delivery` 判断工作台 JSON 是否落后于活动 revision。
5. 批次预检支持本地与受控远程资源混合；远程执行 HEAD，本地执行哈希与上传预检。OSS 配置支持显式环境文件与多个根目录解析。

## 后果

人工通过证据在 OSS 故障时继续保留，修复后可以幂等重试。状态漂移成为可观察问题，工作台旧数据和 Before 缺失可以在交付前发现。
