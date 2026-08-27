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

配置解析按以下优先级执行：显式 `--env-file`、输入目录向上查找、显式 `--data-root` 向上查找、Skill 仓库目录向上查找；当前进程环境变量覆盖文件值。staging 位于仓库外时优先传 `--env-file` 或 `--data-root`。

## 固定流程

1. 读取已通过审核包，校验人工 `pass`、`consumed` 与双 SHA。
2. 预检允许同批混合本地 cover 与受控远程 cover；本地资源检查 MIME、存在性和内容哈希，远程资源检查域名、路径和 HEAD 可读性。
3. 对本地 `cover.png` 计算 SHA-256，在恢复记录中查找已有 URL。
4. 需要上传时写 `<prefix>style/templates/<uuid>.<ext>`，PUT 成功后执行 HEAD。
5. 把 `cover` 替换为当前 assets 域名下的 HTTPS URL，执行 remote validator。
6. 在 staging 写严格两文件 `package/`、`oss-finalization-receipt.json` 和 manifest `final-package`。
7. 原位升级已有 `awaiting-finalization` 正式 revision，或发布新的正式 revision。
8. 导出 `<key>.json`，再对账统一索引、镜像和 OSS 聚合计数。

adapter 必须以内容哈希提供幂等上传。同一封面在当次运行、中断恢复和后续重试中复用 URL。

## 恢复语义

- OSS 或 remote validator 失败：不发布正式包，保留审核包、人工通过回执和 `consumed` 状态。
- 正式 revision 已存在且校验通过：幂等返回，不调用 OSS。
- 正式 revision 为 `dynamic-human-pass` 或受控迁移产生的待正式化占位：校验与审核包同 SHA 后原位升级。
- 受控 URL 已存在：校验域名、前缀和对象可读后直接复用。
- 上传成功但本地原子发布前中断：从恢复记录取回 URL，继续生成正式包。

## 存量命令

```bash
pnpm finalize <input> --dry-run
pnpm finalize <input> --dry-run --env-file <env-file>
pnpm finalize <input> --output <handoff-dir> --data-root <总库根目录>
```

正式执行在 `<handoff-dir>/<key>.json` 写最终交付文件，并把相邻 `artifact-manifest.json` 作为内部批次追溯。该命令主要服务 v3/v4 存量包 dry-run、恢复和迁移。新生产使用 `style_review_workflow.finalize_approved`，完成后执行相同的 `<key>.json` 导出合同。
