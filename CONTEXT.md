# 领域术语

| 术语 | 定义 |
| --- | --- |
| 审核包 | 阶段 1 交给人工验收的本地 `style-template.json + cover.png`，尚未写 OSS。 |
| 人工审核决定 | 对一个具体视觉 revision 的 `pass/reject/pending/manual_release`，冻结决定时的封面与 prompt 哈希。 |
| 精确视觉 revision | 用户实际选择的首版、retry、replacement 或总览外候选；用解码像素哈希、实际生成 Prompt、源图和效果合同共同绑定。 |
| 待正式化 revision | 人工 Pass 已登记到正式目录、仍使用本地 cover 的 `awaiting-finalization` 占位版本，可在身份闭合后原位升级。 |
| 正式 revision | 阶段 3 的内部可追溯版本，`package/style-template.json` 已回填受控 OSS URL，并保留封面与回执。 |
| 最终交付 JSON | 从正式 revision 导出的 `<key>.json`；保持官方 style-template 字段形状，是唯一交给下游的业务文件。 |
| 预留测试图 | 审核包生成事务占用的真实摄影输入，尚未进入人工审核。 |
| 待验收测试图 | 已形成审核包且仍全局占用的测试图。 |
| 已释放测试图 | 人工驳回或明确释放后重新回到全局可用容量的测试图。 |
| 已消费测试图 | 人工通过且模板仍活动时持续占用的测试图；人工退役模板会显式释放。 |
| 退役模板 | 人工明确停止参与活动目录与动态基线的 key；正式 revision 和历史审核证据继续保留。 |
| 经验快照 | 由已通过 GoodCase 和已驳回 BadCase 编译出的版本化自生产经验集。 |
| 创意母题 | 可跨画风、版式、素材和模板 key 重新发明的观察方式或关系算子，为自生产提供灵感。 |
| 模板实现案例 | 一个创意母题在特定素材、X/Y/B/C、版式和视觉 revision 上的具体实现。 |
| 验收案例 | 带人工判断的具体模板实现证据；通过项进入 GoodCase，驳回项进入 BadCase。 |
| 流程经验事件 | 从 Prompt、审批、扫描、生命周期、catalog、OSS 或批次审美故障提炼出的“根因—规则—门禁—回归”记录。 |
