# 风格模板工作流经验学习

当用户连续测试、指出复现偏差、选择旧候选、发现工作台旧数据或要求批量交付时，按本规范把一次问题升级为可复用门禁。视觉案例继续进入 GoodCase/BadCase；流程问题进入 `style_workflow_learning_event`。

## 经验事件

每个事件使用 `contracts/workflow-learning-event.schema.json`，完整填写：

```text
现象 → 用户预期 → 根因 → 永久规则 → 门禁 → 自动化 → 回归案例 → 证据
```

一条事件只描述一个可复现根因。用户附件、批次文件和临时脚本作为证据路径保存；长期规则使用通用业务语言。

## 分类

| category | 触发信号 | 应沉淀的门禁 |
| --- | --- | --- |
| `prompt-compilation-drift` | Before 加提示词无法出现 Approved After 的结构机关 | 九段提示词、十四项边界、X/Y/B/C、原始回放和两张换图迁移 |
| `selected-variant-drift` | 用户选择首版或 retry 版本，交付却指向另一张 | 解码像素哈希、实际生成 Prompt SHA、源图 SHA 和效果合同 SHA 闭合 |
| `scanner-path-drift` | 工作台继续读取旧 JSON，或找不到 Before | 统一索引权威、交付路径诊断、Approved Before 可发现性与 revision 对账 |
| `lifecycle-state-drift` | 人工已通过，正式目录存在，OSS 最终化仍拒绝 | `awaiting-finalization` 原位升级、幂等恢复和明确状态机 |
| `catalog-reconciliation-drift` | 图片已经远程化，索引仍显示待正式化 | 文件实态、catalog、镜像、UAT 和 delivery 同步对账 |
| `oss-configuration-routing-drift` | staging 目录外运行时找不到 `.env` | 显式 `--env-file`、数据根/仓库根解析、密钥零输出、混合资源预检 |
| `batch-aesthetic-drift` | 多样性存在，整批仍偏暗、偏重或机制单一 | 亮度、暗色面积、留白、色温、表现模式和结构机制配额 |

## 晋升规则

经验进入长期 Skill 规则需要同时满足：

1. 用户反馈或可复现失败提供明确证据；
2. 根因可以从单个案例抽象为业务边界；
3. 新规则会改变后续决策；
4. 至少有一个自动门禁或明确人工检查点；
5. 至少有一个回归案例；
6. 规则只写在一个权威位置，其他文件通过指针引用。

单次审美偏好先作为批次约束。相同信号跨批次复现，或用户明确要求形成长期规则时，再晋升到自生产规范。

## 本轮已晋升经验

### Prompt 编译

- Approved After 决定模板视觉目标。
- 具体人物、道具和场景先转换为视觉角色，再进入运行提示词。
- 解构、抽象、重构、重复、路径、遮挡和尺度变化进入核心效果与空间结构。
- 视觉风格承担线条、色彩、材质、纹理和明暗，不能代替结构机关。
- 复现评分使用机制级 95 分门槛；原始回放和换图迁移共同通过后才允许覆盖正式数据。

### 精确视觉 revision

- 用户附件按解码像素匹配候选，允许 PNG 元数据或压缩差异。
- 选择旧 revision 时恢复该 revision 的真实生成提示词，并重新闭合 Prompt、Cover、Before 和合同 SHA。
- 人工 Pass 只冻结用户选择的精确 revision；同 key 的首版、retry 和 replacement 保持独立。

### 状态与交付

- `统一通过模板索引.json` 是数量和状态的权威入口。
- 正式化根据文件实态判断 `finalized`，并把状态回填 catalog 与镜像。
- 人工通过时创建的正式占位目录属于 `awaiting-finalization`，OSS 阶段原位升级。
- Dry-run 同时接受本地 cover 和受控远程 cover；远程资源执行 HEAD 校验，本地资源执行哈希与上传预检。
- 工作台问题先运行 `status` 和 `diagnose-delivery`，报告实际读取路径、revision、JSON SHA 与 Approved Before。

### 批次审美

- 自生产同时控制题材、成像语言、空间语法和表现模式的多样性。
- 每批声明高调明亮、开放留白、有限暗色面积和结构性变换配额。
- 接触表展示缩略图亮度与机制分布，人工判断保留最终权威。

## 完成条件

一次经验沉淀完成时，事件通过 Schema、权威规范已更新、自动化门禁可以运行、回归测试能够复现原失败并验证修复。原始对话无需复制到 Skill 正文；证据路径足以回溯判断来源。
