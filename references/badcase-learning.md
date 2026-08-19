# BadCase 自动沉淀与负向学习

本规则用于 `produce` 的用户视觉审批。完成标准是每个用户明确拒绝的视觉 revision 都进入 BadCase 库，并在下一轮候选设计前参与重复失败拦截。

## 写入边界

- 把 `reject`、`rejected`、`excluded` 和用户批准记录中的明确淘汰项写入 BadCase。
- 只接受用户、用户附件选图或可追溯的历史用户排除记录作为决策权威。
- 把待审核、未表态、生成失败、自动门禁失败和未进入选中集合但缺少明确决策的候选保留在原批次证据中。
- 以具体视觉 revision 为记录单位；同 key 的不同 after 图分别记录。
- 新 approval revision 推翻旧决定时保留历史记录，并按最新决定决定是否进入下一轮负向约束。

## 记录内容

每条 BadCase 保存 `key/title`、候选序号、after 图、可取得的 before 图、X/Y/B/C、拒绝原因、决策权威、决策文件和批次根目录。`badcaseId` 由决策文件、候选身份和 after 图摘要稳定生成，重复运行执行幂等合并。

语料库使用 `contracts/style-badcase-corpus.schema.json`，正式业务文件写入总库 `06-模板质量评测/05-问题分类与案例/风格模板BadCase库/`。生产批次保持只读，语料库引用原证据路径。

## 下一轮使用

在发明候选前同时读取 GoodCase 机制库和 BadCase 库：

1. 从 GoodCase 提取值得迁移的 after-first 机制。
2. 从 BadCase 提取失败的 X/Y 组合、来源适配、边界、印制和视觉退化模式。
3. 新候选命中相同失败机制时，写出具体差异证据；缺少实质差异时淘汰或重做。
4. BadCase 只参与负向约束，不进入批准基线、正式模板包、测试图正式分配或 OSS 最终化。

使用以下命令从批准决策幂等更新语料库，并生成 after 缩略图索引：

```bash
python scripts/build_style_badcase_corpus.py \
  --output <style-badcase-corpus.json> \
  --contact-sheet-dir <contact-sheets-dir> \
  <approval-decision.json> [...]
```

存量批准文件只有 `excluded` 且缺少显式用户权威字段时，在人工确认它属于用户决策后增加 `--accept-legacy-exclusions`。
