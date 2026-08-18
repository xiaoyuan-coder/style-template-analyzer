---
name: style-template-analyzer
description: 把参考图编译为 prompt-only 风格模板最终包，或基于已批准模板基线自主生产新模板；为每个模板分配唯一真实摄影测试图、生成封面并在 OSS 回填后交付。用于风格模板、参考图编译、模板自生产、封面图、真实测试图池、批量生产、真图评测、OSS 最终化、契约迁移与维护审计。
---

# 风格模板分析与自生产

核心交付是最终模板包：一份已经回填受控 OSS 封面 URL 的 `style-template.json` 和一张 `cover.png`。封面由模板 prompt 作用于预取的唯一真实摄影测试图得到。OSS 最终化属于默认生产流程，完成前只存在内部待发布产物；完整真图评测是拿包后的显式独立阶段。

## 先选择动作

| 用户意图 | 动作 | 必读参考 |
| --- | --- | --- |
| 从参考图制作模板 | `compile` | `references/style-analysis-and-prompting.md`、`references/style-template-contract.md` |
| 基于现有模板自主生产 | `produce` | `references/self-production-strategy.md`、`references/style-template-contract.md`、`references/architecture-and-lifecycle.md` |
| 补充或审核真实摄影测试图 | `maintain-test-pool` | `references/test-image-pool.md`、`references/test-image-admission.md` |
| 只看本地草稿与封面，暂不上传 | `compile/produce: preview` | `references/architecture-and-lifecycle.md` |
| 对已有最终包做完整评测 | `evaluate` | `references/style-template-contract.md` |
| OSS 配置、恢复与正式 URL 规则 | 默认生产内核 | `references/oss-handoff.md` |
| 修改 Skill、Schema 或迁移存量 | 维护模式 | `references/architecture-and-lifecycle.md`、`references/v3-migration.md` |

服装印制分类读取 `references/garment-print-template-taxonomy.md`；摄影、拼版、覆盖层或低信息参考救援读取 `references/hybrid-reference-salvage.md`。

## `compile`：参考图编译

1. 读取参考图，建立用户内容不变量、授权变换、模板常量和参考禁迁移四本账。
2. 写 `style-analysis.json`，形成七维成像指纹和 3–6 个可评分机制。
3. 编译官方形状的 `style-template.json`；运行时只称“用户上传图”，不得依赖参考图。
4. 从本地 ready 测试图池为 `deliverySetId + key + revision` 预留唯一摄影图。
5. 用测试图作为唯一图片输入运行模板 prompt，生成 PNG 封面。
6. 执行轻量封面检查；只拦截不可读、模板效果未体现、主体严重损坏、异常文字或水印，同一测试图最多生成两次。
7. 除非用户明确 preview，上传封面到受控 OSS、回填正式 URL、执行最终契约校验，再原子发布最终模板包；失败时不留下公开半包。

参考图只提供离线设计证据。封面测试图来自测试图池，来源参考图不得直接充当默认测试图。

## `produce`：模板自生产

1. 只读取 `references/approved-baseline.json` 指向的批准基线。当前批准集合为 94 个模板，摘要必须匹配。
2. 用 `X 图形语言 × Y 空间语法 × B 内容绑定 × C 边界策略` 设计候选；四项都必须明确，X 与 Y 必须明显改变最终像素。材质默认只作辅助表现，不把工艺制作感作为印制模板的主要 X。
3. 同批候选覆盖多个 Y 家族；先从灵感来源提取内容关系和空间机制，再发明适配当前输入的载体。沿用同一结构骨架换皮、复刻固定外壳或把普通背景当成 Y 均不形成新候选；CRT、街机和窗口只算一个界面结构家族。
4. 在正式编译前直接生成效果图供用户评审。先过审美非退化门禁，再检查 Y、完整闭合与跨输入泛化，最后检查 X；文字示意不替代直接视觉结果。处理后的图必须至少维持原图的主体魅力、可读性和构图质量，花哨程度不构成通过理由。
5. 对重复、分镜、框/蒙版、变形和混合媒介执行结构有效性检查：重复或分镜必须带来信息增量；去掉框或蒙版后内容组织未改变时不算新 Y；复杂扭曲不得损伤识别与观感；允许混合媒介，但角色分工必须清楚，并通过来源联系、视觉桥接或空间互动建立关系，避免生硬并置。
6. 按语义完整性检查裁切：独立 `artwork` 和 `emblem` 默认保留完整外轮廓与约 8%–12% 安全边距；分镜景别、满版构图和抽象关系带可以主动触边，只要载体逻辑清楚，主体身份、核心识别特征与关键关系仍可读。普通印制模板使用纯图案结构；外框、放大镜小窗、连接线和分析标注只在用户明确要求图鉴、档案、分析或说明书效果时启用。
7. 保存批准项和淘汰项。批准前只交付候选效果，不编译正式包、不做测试图正式分配、不写 OSS；批准本身只更新名单。收到批准后的“产出通过的模板包”“完成 OSS 最终化”或“上传 OSS”等明确指令后，才编译批准项并进入外部写入。测试图自身难看或干扰判断时立即更换，并退出当前 ready 选择。
8. 对 key、中文标题、prompt 机制签名和类别做新颖性检查，在任何付费生成前一次性检查 ready 测试图容量。
9. 每个合格候选复用 `compile` 的唯一分配、封面生成和原子交付内核。自生产只创建新候选，不改写、移动或归档基线。

## 最终包与内部证据

```text
<run>/<key>/<revision>/
├── artifact-manifest.json
├── package/
│   ├── style-template.json
│   └── cover.png
└── internal/
    ├── style-analysis.json 或 self-production-analysis.json
    ├── baseline-snapshot.json          # produce 才有
    ├── test-image-assignment.json
    ├── cover-generation-receipt.json
    ├── cover-check-receipt.json
    └── oss-finalization-receipt.json
```

只把 `package/` 作为模板包交付给用户。内部字段留在相邻 evidence 和 manifest，禁止注入官方 `style-template.json`。

preview 产物保存于 `<run>/.prepublish/<key>/<revision>/`，目录内使用 `prepublish/`，不使用 `package/` 命名，也不向用户声称已经形成模板包。同 revision 后续正式运行复用该测试图和本地封面完成 OSS 最终化。

## 后续阶段

- 只有用户明确要求完整真图评测时，执行 `evaluate(package)`；评测不修改最终包。
- 用户请求 `compile` 或对已批准方向明确要求“产出通过的模板包”，包含 OSS 最终化授权，默认运行到正式 URL 回填。
- `produce` 必须先完成候选视觉审批；数量或“模板包”字样不能跳过审批。批准只更新批准名单，等待批准后的最终化指令再写 OSS。
- 只有明确出现“仅预览”或“暂不上传”时才停在待发布产物。
- 旧 `advance(package, oss-handoff)` 仅用于 v3 存量快速包迁移，不用于新版生产。

## 测试图池边界

- 模板生产只消费本地 ready 池，不在拿包过程中临时采集测试图。
- 当前交付集合内 `assetId` 唯一；同 revision 重试复用原分配，换图创建新 revision。
- ready 图不足时在生成前返回 `test_pool_insufficient`。
- 自动初筛只覆盖证据完整、低风险的 Public Domain / CC0 摄影图；通过视觉准入后才可标记为 ready。
- 每张 ready 图必须通过可看图的视觉准入审查，确认它像真实用户会从手机相册或个人图库上传的日常照片，同时满足成像中性、无预置风格和测试价值达标。
- 人物检测独立于元数据类别；首个 200 张国内业务主池只接受中国/东亚人物生活照，并要求平台级人物授权承诺或逐图权利证据。其他可识别人物、插画扫描、明显武器和风险项不得 ready。
- 当前正式里程碑准备 200 ready，并按人物生活照、宠物、食物饮品、室内家居、日常物品与兴趣、出游街景、花草植物执行固定配额；单类不超过 25%，单一来源不超过 40%。野生动物、馆藏文物、武器、历史档案、专业科研图和极端风光进入独立压力测试集。
- Pinterest 默认 `policy-blocked`；不得绕过登录、验证码、反爬或访问控制。
- 首个可用采集适配器读取 Wikimedia Commons 公开 HTML 与许可证据。

## 常用命令

```bash
# 新版最终包：模板 cover 必须为受控 OSS URL，公开 package/ 严格两文件
python scripts/validate_style_package.py <revision-root> --profile final-package --assets-domain <assets-host>

# 明确 preview 的待发布产物
python scripts/validate_style_package.py <prepublish-revision-root> --profile prepublish

# 固化或复核批准基线
python scripts/style_baseline.py <baseline-root> <snapshot.json> --approved-count 94

# 维护测试图来源；联网采集独立于模板生产
node scripts/style_source_adapter.mjs --source commons --category Product_photography --limit 20 --checkpoint <metadata-checkpoint.json> --chrome <chrome-path>
python scripts/style_institutional_source.py --source smithsonian --limit 250 --checkpoint <smithsonian-metadata.json>
python scripts/style_institutional_source.py --source loc --limit 150 --checkpoint <loc-metadata.json>
python scripts/style_pool_ingest.py <metadata-checkpoint.json> <pool.json> <assets-dir> --asset-checkpoint <asset-checkpoint.json>

# 存量兼容
python scripts/validate_style_package.py <target> --profile legacy
```

`style_v3_workflow.py` 的公开生产入口为可注入的 `compile` 与 `produce`；两者默认要求 OSS adapter 与受控 assets domain。`compile` 主动调用 compiler，`produce` 先核对批准基线再调用 proposer；真实生成器、轻量封面检查器和 OSS adapter 由当前执行环境接入，自动测试使用 fake adapter。`advance_package(..., evaluation)` 保留为独立评测入口；`compile_reference`、`produce_from_baseline` 与 v3 fast-package 路径只承担存量兼容。

## 完成标准

- 默认动作在封面上传、正式 URL 回填并发布 `style-template.json + cover.png` 后结束。
- 官方模板通过 STYLE_REF 契约；封面是有效 PNG，且分配账本证明集合内唯一。
- manifest 3.0.0 的 `final-package` 路径、artifact 类型、版本和 SHA-256 与实际文件一致，并登记轻量封面检查和 OSS 最终化回执。
- 失败不会留下公开半包或错误提交的测试图分配。
- 如实报告评测、OSS、联网采集和人工权利复核是否执行。
