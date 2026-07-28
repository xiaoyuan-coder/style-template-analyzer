# OSS 最终 JSON 交付

## 触发边界

只有用户明确要求上传 OSS、最终 JSON、后端导入或同等含义时才执行写入。普通分析、分类、模板生成和 dry-run 停在本地。

## 环境变量

- `ALIYUN_OSS_ACCESS_KEY_ID`
- `ALIYUN_OSS_ACCESS_KEY_SECRET`
- `ALIYUN_OSS_ASSETS_BUCKET`
- `ALIYUN_OSS_ASSETS_ENDPOINT`
- `ALIYUN_OSS_ASSETS_DOMAIN`
- `ALIYUN_OSS_KEY_PREFIX`（可空）

不得读取、打印、复制或写入 AK/SK。

## 命令

仅预检：

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
2. 以 local 模式逐个校验并检查批次 key 唯一性。
3. 读取 `referenceAssets`；本地图片按 SHA-256 去重。
4. 上传到 `<prefix>style/templates/<uuid>.<ext>`。
5. SDK `PUT` 成功后执行 `HEAD`。
6. 把资源路径替换为当前 assets 域名下的 HTTPS URL。
7. 移除本地测试资产和测试说明。
8. 以 remote 模式校验临时 JSON，通过后原子写入 `<key>.json`。

## 输出与恢复

- handoff 目录只包含 `<template-key>.json`。
- 恢复记录默认位于 handoff 同级：`.<batch-id>.upload-state.json`。
- 相同 SHA-256 在本次和重试中复用 URL。
- 源 `style-template.json` 永不覆盖。
- 已经位于当前域名、环境前缀和 `style/templates/` 下的受控 URL 直接复用。

失败时保留恢复记录。修复网络或配置后重复同一命令，不要手工编辑恢复记录。

## 最终报告

必须报告模板数量、最终 JSON 数量、上传数量、复用数量、PUT/HEAD 结果、remote validator 结果和 handoff 路径。未执行上传时明确说明。
