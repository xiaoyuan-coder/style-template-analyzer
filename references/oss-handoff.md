# STYLE_REF OSS 最终交付

## 触发边界

用户请求 `compile`、`produce` 或“模板包”时已经授权完成模板生产所必需的 OSS 上传；默认流程只有在上传、正式 URL 回填和最终契约校验后才形成模板包。用户明确要求“仅预览”或“暂不上传”时停在 `prepublish`，不执行外部写入，也不创建 `package/`。完整真图评测不构成 OSS 最终化的前置条件。

## 环境变量

- `ALIYUN_OSS_ACCESS_KEY_ID`
- `ALIYUN_OSS_ACCESS_KEY_SECRET`
- `ALIYUN_OSS_ASSETS_BUCKET`
- `ALIYUN_OSS_ASSETS_ENDPOINT`
- `ALIYUN_OSS_ASSETS_DOMAIN`
- `ALIYUN_OSS_KEY_PREFIX`（可空）

凭证只用于 SDK 调用，不进入模板、日志和回复。

## 命令

预检：

```bash
pnpm style:finalize <input> --dry-run
```

独立适配器或 v3 存量迁移：

```bash
pnpm style:finalize <input> \
  --output artifacts/style-template-analyzer/handoff/<batch-id>
```

`input` 可以是单个 `style-template.json` 或包含多个模板的目录。新版 `compile/produce` 从事务内调用等价 adapter；命令行主要用于 dry-run、恢复和 v3 存量快速包迁移。

## 固定流程

1. 递归查找 `style-template.json`。
2. 以 local/either 模式校验研发字段、prompt-only 角色、资源和批次 key。
3. 读取 `cover`，按 SHA-256 去重。
4. 上传到 `<prefix>style/templates/<uuid>.<ext>`。
5. PUT 成功后执行 HEAD。
6. 把 `cover` 替换为当前 assets 域名下的 HTTPS URL；该字段继续只用于前端展示。
7. 以 remote 模式校验临时 JSON。
8. 返回最终模板 JSON 与上传回执给生产事务。
9. 生产事务把最终 JSON 与本地封面写入严格两文件 `package/`，登记 `oss-finalization-receipt.json`，以 manifest 3.0.0 `final-package` 校验后原子发布。

## 输出与恢复

- 命令行存量 handoff 目录包含研发可导入的 `<template-key>.json` 和批次 `artifact-manifest.json`；新版默认交付位于 revision 的 `package/`。
- `style-analysis.json` 和 `style-evaluation.json` 保持在业务产出目录，不进入 handoff。
- 恢复记录默认位于 handoff 同级：`.<batch-id>.upload-state.json`。
- 相同 SHA-256 在本次运行和重试中复用 URL。
- preview 源 `style-template.json` 保持不变；正式 URL 只写入最终包副本。
- 已处于当前域名、环境前缀和 `style/templates/` 下的受控 URL 直接复用。
- handoff JSON 不含 `referenceImage`；生成适配器只提交用户 `source` 和 `promptTemplate`。

失败时保留恢复记录，修复配置或网络后重跑同一命令。

## 最终报告

报告模板数量、输出 JSON 数量、上传数量、复用数量、PUT/HEAD、remote validator、handoff 路径和未执行事项。
