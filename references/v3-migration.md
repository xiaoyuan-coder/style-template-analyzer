# v2 / v3 → v4 迁移

## 保持不变

- `kind: STYLE_REF` 与官方 `style-template.json` 字段不变。
- prompt-only 单图运行语义不变。
- analysis/evaluation 的 2.0.0 与存量 2.0 继续可读。
- `legacy`、`authoring`、`release` profile 和单文件 validator 保留。

## v3 历史默认

- 默认完成点改为快速包。
- v3 包目录只含 `style-template.json` 与 `cover.png`。
- manifest 位于 revision 根目录，使用 schema 2.0.0 与 stage `package`。
- 分析、测试图分配和生成回执进入 `internal/`。
- evaluation 与 oss-handoff 改为显式独立 stage。

## v4 新默认

- `compile` 与 `produce` 默认完成 OSS 上传和正式 URL 回填。
- 本地模板与封面只形成隐藏 `prepublish` 待发布产物，不称为模板包。
- 最终 `package/` 仍严格只含 `style-template.json` 与 `cover.png`；模板 `cover` 已是受控 OSS URL。
- manifest 使用 schema 3.0.0 与 stage `final-package`，内部必须登记 `cover-check-receipt.json` 和 `oss-finalization-receipt.json`。
- 明确 preview 时使用 manifest 3.0.0 `prepublish`；同 revision 后续正式运行复用原测试图和本地封面。
- evaluation 保持独立；v3 `oss-handoff` 只用于存量迁移。
- v4.5 起，用户视觉审批把明确拒绝的 revision 写入独立 `style_badcase_corpus` 1.0.0；该语料库位于质量评测目录，不改变模板包和 manifest 3.0.0 的形状。

## 存量 `effect.png`

当前 94 个研发交付目录无需改名或改写。兼容校验继续接受 `style-template.json + effect.png`。需要进入 v3 新 revision 时：

1. 保留旧目录只读。
2. 创建新的 revision 目录。
3. 将模板 cover 改为 `cover.png`，并复制对应 PNG。
4. 补充可追溯的测试图分配与生成来源；证据不足时标记为 legacy migration，不伪造 assetId。
5. 构建 v3 manifest 并运行 `fast-package` 校验。

v3 快速包升级到 v4 时不覆盖原 revision：读取本地两文件包，执行 OSS 上传与 remote validator，创建新的 v4 revision 或明确迁移 revision，写入 OSS 最终化回执并运行 `final-package` 校验。

## 当前批准基线

`references/approved-baseline.json` 固定本轮 94 集合的 count 与 digest。自生产每次运行都从业务目录重建快照并与批准记录比较；不扫描其他历史目录。批准集合变化时创建新的批准记录，不能直接修改通用算法中的常量。
