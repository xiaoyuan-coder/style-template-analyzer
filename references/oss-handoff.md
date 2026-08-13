# STYLE_REF OSS 最终交付

## 触发边界

用户明确要求上传 OSS、最终 JSON或后端导入时执行写入。分析、模板生成、评测和 dry-run 保持本地运行。

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

最终交付：

```bash
pnpm style:finalize <input> \
  --output artifacts/style-template-analyzer/handoff/<batch-id>
```

`input` 可以是单个 `style-template.json` 或包含多个模板的目录。

## 固定流程

1. 递归查找 `style-template.json`。
2. 以 local/either 模式校验研发字段、prompt-only 角色、资源和批次 key。
3. 读取 `cover` 与 `referenceImage`，按 SHA-256 去重。
4. 上传到 `<prefix>style/templates/<uuid>.<ext>`。
5. PUT 成功后执行 HEAD。
6. 把两个字段替换为当前 assets 域名下的 HTTPS URL；它们继续只用于展示和离线追溯。
7. 以 remote 模式校验临时 JSON。
8. 原子写入 `<key>.json`。

## 输出与恢复

- handoff 目录只包含研发可导入的 `<template-key>.json`。
- `style-analysis.json` 和 `style-evaluation.json` 保持在业务产出目录，不进入 handoff。
- 恢复记录默认位于 handoff 同级：`.<batch-id>.upload-state.json`。
- 相同 SHA-256 在本次运行和重试中复用 URL。
- 源 `style-template.json` 保持不变。
- 已处于当前域名、环境前缀和 `style/templates/` 下的受控 URL 直接复用。
- handoff JSON 中保留 `referenceImage` 只为研发 Schema 兼容；生成适配器只提交用户 `source` 和 `promptTemplate`。

失败时保留恢复记录，修复配置或网络后重跑同一命令。

## 最终报告

报告模板数量、输出 JSON 数量、上传数量、复用数量、PUT/HEAD、remote validator、handoff 路径和未执行事项。
