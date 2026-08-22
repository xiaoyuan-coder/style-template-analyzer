# STYLE_REF OSS 最终化

## 触发边界

OSS 只在阶段 3 运行。阶段 2 的人工 `pass` 让该 revision 进入阶段 3；`reject/pending/manual_release` 均不调用 OSS。完整真图评测不是 OSS 前置条件。

## 环境变量

- `ALIYUN_OSS_ACCESS_KEY_ID`
- `ALIYUN_OSS_ACCESS_KEY_SECRET`
- `ALIYUN_OSS_ASSETS_BUCKET`
- `ALIYUN_OSS_ASSETS_ENDPOINT`
- `ALIYUN_OSS_ASSETS_DOMAIN`
- `ALIYUN_OSS_KEY_PREFIX`（可空）

凭证只用于 SDK 调用，不进入模板、回执、日志和对话。

## 固定流程

1. 读取已通过审核包，校验人工 `pass`、`consumed` 与双 SHA。
2. 对 `cover.png` 计算 SHA-256，在恢复记录中查找已有 URL。
3. 需要上传时写 `<prefix>style/templates/<uuid>.<ext>`，PUT 成功后执行 HEAD。
4. 把 `cover` 替换为当前 assets 域名下的 HTTPS URL，执行 remote validator。
5. 在 staging 写严格两文件 `package/`、`oss-finalization-receipt.json` 和 manifest 4.0.0 `final-package`。
6. 原子发布正式 revision。
7. 把已回填 URL 的官方 JSON 导出为 `<key>.json`；该单文件是最终下游交付物，封面与内部回执继续留在正式 revision 中。

adapter 必须以内容哈希提供幂等上传。同一封面在当次运行、中断恢复和后续重试中复用 URL。

## 恢复语义

- OSS 或 remote validator 失败：不发布正式包，保留审核包、人工通过回执和 `consumed` 状态。
- 正式 revision 已存在且校验通过：幂等返回，不调用 OSS。
- 受控 URL 已存在：校验域名、前缀和对象可读后直接复用。
- 上传成功但本地原子发布前中断：从恢复记录取回 URL，继续生成正式包。

## 存量命令

```bash
pnpm finalize <input> --dry-run
pnpm finalize <input> --output <handoff-dir>
```

正式执行在 `<handoff-dir>/<key>.json` 写最终交付文件，并把相邻 `artifact-manifest.json` 作为内部批次追溯。该命令主要服务 v3/v4 存量包 dry-run、恢复和迁移。新生产使用 `style_review_workflow.finalize_approved`，完成后执行相同的 `<key>.json` 导出合同。
