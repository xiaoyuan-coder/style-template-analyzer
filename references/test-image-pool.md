# 真实摄影测试图池

测试图的逐图准入读取 `references/test-image-admission.md`。该文件是中性成像、测试价值、边界判断和审查记录的唯一规则源；本文件只维护池状态、来源、分布与运行纪律。

## 目标

封面图用于展示模板应用效果。所有批次共享一份全局分配 ledger；任何正在预留、等待人工验收或已消费的真实摄影图都不得分配给另一个 revision。

## 状态

```text
collected → manual_review → ready → reserved → awaiting_approval → released
                     ↘ rejected                              └→ consumed
```

- `collected`：已取得网页证据，尚未完成门禁。
- `manual_review`：许可证、人物权利或品牌风险需要人工判断。
- `ready`：权利与视觉准入通过，且 ledger 中没有活跃或已消费占用时可分配。
- `reserved`：审核包生成事务临时占用。技术失败发生在人工审核前时，系统可释放。
- `awaiting_approval`：审核包已发布，等待人工对具体视觉 revision 表态。该状态持续占用，无自动超时。
- `released`：人工驳回或明确释放；该 asset 重新进入全局可用容量。
- `consumed`：人工验收通过，且封面/prompt 双 SHA 已冻结；该 asset 永久退出可用容量。

`ready` 数量指当前可实际分配数。`catalogReady` 指权利与视觉准入通过的原始目录数，可以大于 `ready`。`legacyHeld` 表示尚未补齐人工决策证据的 v1 存量占用。

## ready 门禁

必须同时满足：

- 来源页、原图 URL、作者与许可证 URL 完整。
- Public Domain / CC0，且 `rightsStatus=verified`。
- 可确认是摄影图片，宽高都不少于 512。
- 视觉模型未检测到画作、插画、海报、文档或屏幕扫描，也未检测到明显武器、仇恨、色情或水印风险。
- 人物检测独立于来源元数据类别；任何可识别人物都必须具备现成的人物权利证据，否则进入 `manual_review`。
- MIME 为 JPEG、PNG 或 WebP。
- SHA-256 无精确重复，64-bit 感知哈希距离大于阈值。
- 不含 `identifiable-person-rights-unknown`、`license-unknown`、`trademark-sensitive` 等高风险标签。
- 通过 `references/test-image-admission.md` 的中性摄影硬门槛和测试价值评分，并留存视觉准入记录。

Pexels License 只对 `pexels-sitemap-manual` 中完成逐图视觉审核、作者核验和人物条款核验的中国/东亚生活照开放 ready。CC BY 需要确认交付链能够履行署名；CC BY-SA、未知许可证和可识别真人权利不明默认人工审查。

元数据自动化只负责缩小候选范围。缺少可看图的视觉准入审查时，候选最多进入 `manual_review`，不得自动标记为 `ready`。

## 多样性

采集查询围绕用户手机相册和个人图库：人物生活照、宠物、食物饮品、室内家居、日常物品与兴趣、出游街景、花草植物，并兼顾横、竖、方画幅。正式 200 张主池执行 `references/test-image-admission.md` 的固定题材配额；分配排序继续兼顾类别和画幅。

野生动物、馆藏文物、武器、档案扫描、专业科研图和极端风光不参与主池配额。它们只能进入名称和用途均独立的专项压力测试集。

## 来源策略

- `pexels-sitemap-manual`：中国/东亚人物生活照的受控来源。候选发现只读取 robots.txt 明确允许的官方 sitemap，不调用 API、不访问受限搜索参数、不做全站抓取；最终只下载逐张人工选中的照片。每张保留 Pexels License、来源页、作者和平台要求投稿者持有人物授权的条款证据。原图只在内部测试池使用，公开交付只出现经过模板实质性转换的封面。
- `freestocks-html`：家居、日常物品与普通出游的优先补充来源。只读取站点允许访问的摄影详情页与图片地址，保留 CC0 条款和逐图来源证据；禁止访问 robots.txt 排除的 `?download=` 路径。
- `skitterphoto-html`：日常非人物题材来源。站点虽要求上传者持有人物授权，当前无法逐图取得授权文件，因此可识别人物仍进入人工审查。
- `picography-html`：日常非人物题材补充来源。逐图核对摄影真实性、作者、CC0 来源页和广告混入；可识别人物不自动 ready。
- `wikimedia-commons-html`：仅作为日常题材补充来源。只解析白名单摄影分类页与文件详情页，保留作者及许可证据；不访问 robots.txt 限制的 `Special:MediaSearch`。
- `smithsonian-open-access-bulk`、`loc-free-to-use-bulk`：只服务独立的馆藏或档案压力测试集，不向日常主 ready 池供图。
- `pinterest`：`policy-blocked`。当前公开页面存在登录墙，且没有明确自动抓取许可；不得启动绕过方案。

采集使用 Playwright 读取网页 HTML，不调用站点 API。遇到 403、429、登录墙或验证码时保存 checkpoint，停止或退避。选择器只放在 adapter 内，主要测试使用保存的 HTML fixture。

采集保存两个相互独立的 checkpoint：metadata checkpoint 保存候选网页证据，asset checkpoint 保存逐图下载、格式、哈希和门禁结果。随后运行 `style_pool_ingest.py` 下载图片、限制文件体积、验证真实图片格式、计算 SHA-256 与 dHash，并原子写入测试图池。单一来源触发 403、429、登录墙或验证码时只熔断该来源，保留其他来源与已完成资产。无法自动确认摄影真实性的记录停在 `manual_review`。

2026-08-17 的 1,000 候选容量原型得到 330 条元数据规则结果，但 23 张视觉审计样本发现人物漏检、插画扫描、武器、类别误判和连续近似画面。该原型与用户上传相册的业务分布也不一致，330 条结果不得直接导入 ready。当前里程碑先建立 200 张日常主池；后续扩容到 500 时继续沿用相同题材比例、单一来源不超过 40% 和逐图视觉门禁。

## 运行纪律

- 采集是独立维护任务，禁止在 compile/produce 热路径执行。
- 设置查询、最大条数、请求间隔和 checkpoint。
- 下载后计算真实文件 SHA-256 与感知哈希，再进入池。
- pool 与 assignment ledger 更新使用文件锁和原子替换；活跃/已消费 `assetId` 在全局 ledger 唯一。
- 人工验收后的测试图状态只由 `pass/reject/manual_release` 驱动。任务结束、待定时长和 OSS 结果不触发释放。
- ready 容量小于待生成模板数时，在任何生成器调用前停止。

```bash
python scripts/audit_style_test_pool.py <pool.json> <assignment-ledger.json>
node scripts/style_source_adapter.mjs --source commons --category Product_photography --limit 20 --checkpoint <metadata-checkpoint.json> --chrome <chrome-path>
python scripts/style_institutional_source.py --source smithsonian --limit 250 --checkpoint <smithsonian-metadata.json>
python scripts/style_institutional_source.py --source loc --limit 150 --checkpoint <loc-metadata.json>
python scripts/style_pool_ingest.py <metadata-checkpoint.json> <pool.json> <assets-dir> --asset-checkpoint <asset-checkpoint.json>
```
