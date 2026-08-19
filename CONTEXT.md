# 领域术语

| 术语 | 定义 |
| --- | --- |
| 审核包 | 阶段 1 交给人工验收的本地 `style-template.json + cover.png`，尚未写 OSS。 |
| 人工审核决定 | 对一个具体视觉 revision 的 `pass/reject/pending/manual_release`，冻结决定时的封面与 prompt 哈希。 |
| 正式包 | 阶段 3 交付物，`style-template.json` 已回填受控 OSS URL，公开目录仍保持 JSON 与封面两文件。 |
| 预留测试图 | 审核包生成事务占用的真实摄影输入，尚未进入人工审核。 |
| 待验收测试图 | 已形成审核包且仍全局占用的测试图。 |
| 已释放测试图 | 人工驳回或明确释放后重新回到全局可用容量的测试图。 |
| 已消费测试图 | 人工通过的 revision 永久占用的测试图。 |
| 经验快照 | 由已通过 GoodCase 和已驳回 BadCase 编译出的版本化自生产经验集。 |

