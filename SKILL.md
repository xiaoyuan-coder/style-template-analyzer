---
name: style-template-analyzer
description: 分析单张风格参考图、原图与效果图对比图或批量图片目录，让每个可用模板同时支持整图转换与主体转换，再按用户选择的运行模式处理输入；整图模式覆盖人物、背景、UI、字幕、文字、按钮、边框和布局，主体模式提取并风格化主体且默认置于纯白背景，只对明确的外部平台水印执行清理。沉淀整体风格转换模板，生成并校验 style-template.json，按九类视觉体系分类，并在用户明确要求时上传阿里云 OSS、输出每模板一个纯 JSON 的 handoff 批次。用于“风格化模板”“参考图风格迁移”“整图重绘”“保留 UI 和字体”“白底主体风格化”“去水印”“批量读图分类”“上传 OSS 并交付 JSON”等任务。
---

# 风格化模板分析器

把风格参考图转成可复用、可测试、可入库的整体图片转换模板。模板描述风格、内容保留规则和参考图权限，不提供主页模板的文字或图片槽位。

## 请求路由

| 用户意图 | 流程 | 默认产物 | 必须读取 |
| --- | --- | --- | --- |
| 单图分析、生成模板数据 | `analyze` | `style-template.json` | `references/style-template-contract.md` |
| 批量读图、分类、继续编号 | `batch-analyze` | 每模板一个 JSON、批次清单 | `references/style-template-contract.md` |
| 测试效果、用 P2 生成 | `generation-test` | 真实生成图与测试记录 | 合同中的测试规则 |
| 上传 OSS、最终 JSON、后端导入 | `oss-handoff` | handoff 目录内每模板一个纯 JSON | `references/oss-handoff.md` |
| 检查现有数据 | `validate` | 校验报告 | `references/style-template-contract.md` |

只做分析或整理时不要连接 OSS。只有用户明确要求上传、最终交付或后端导入时才执行 `oss-handoff`。

## 核心流程

1. 检查图片格式、尺寸、重复文件和编号连续性。
2. 区分参考结构：
   - `single-style-reference`：单张完成图；
   - `paired-images`：原图和目标风格分开提供；
   - `paired-comparison`：同一图片内包含原图和结果；
   - `annotated-paired-comparison`：还包含箭头、软件图标或说明。
3. 让每个可用模板的 `supportedModes` 固定为 `["whole_image", "subject_only"]`。模式由用户在本次生成请求中选择，模板只定义风格；不可用模板继续使用空数组。
4. 按用户选择的转换范围执行，转换范围优先于对元素的语义判断：
   - `whole_image` / `full_scene_preservation`：把输入画布视为一个整体。保留人物、背景、前后景、UI、对话框、字幕、角色名、按钮、HUD、文字、边框、贴纸、装饰和布局，并让所有保留内容使用同一模板风格。不要因为某个元素看起来像 UI、字幕或覆盖层就将其删除。
   - `subject_only`：识别并风格化主要主体，保持身份、数量、姿态、轮廓和关键内部特征；移除原背景、UI、文字及其他非主体内容，默认放置在纯白 `#FFFFFF` 背景上。用户明确指定透明、其他纯色或场景背景时覆盖白底默认值。
5. 再处理例外：
   - 用户明确要求移除或保留的元素，按用户指令执行。
   - 高置信度识别出的外部平台来源水印，例如角落中的“小红书”、抖音或 TikTok 平台标记，默认移除并自然补全底层区域。
   - 账号名、二维码、分享贴纸、系统栏或截图外壳只有在明确属于外部传播/截屏层时才移除；在 `whole_image` 中无法确定时默认保留，必要时只追问这一项。
   - 风格参考图中的具体人物、物件、文字、品牌、UI、水印和故事不得进入结果；只提取材质、笔触、配色、明暗、构图语言和抽象程度。
6. 为 `whole_image` 建立完整性清单，逐区记录输入画布中的主体、环境、UI、文字和边缘元素。这个清单用于防止漏画，不用于筛选“重要内容”。
7. 保留 `contentStrategy` 作为风格重建倾向，不用它替代用户本次选择的运行模式：
   - `full_scene_preservation`：保留完整场景；
   - `primary_subject_reconstruction`：重建主要主体；
   - `subject_cutout_stylization`：抠图后风格化；
   - `salient_object_extraction`：提取主要物件组合。
8. 使用九类展示分类：手绘涂鸦、动漫漫画、水彩绘景、平面图形、版画网点、像素艺术、材质立体、摄影质感、拼贴实验。具体技法放入 `styleTags`、`category.secondary` 和 `renderingMethod`。
9. 写入每模板一个 `style-template.json`，随后运行 validator。
10. 未完成跨主体真实生成测试时保留 `needsReview: true`。无法辨认风格的黑帧、损坏图或低信息图使用 `qualityStatus: unusable`。

完整的转换范围、主体白底、水印例外和生成测试规则见 `references/style-template-contract.md`。生成提示词必须先声明 `Transformation scope`。`whole_image` 提示词必须明确整张输入画布都是内容；`subject_only` 提示词必须明确移除原背景并使用纯白背景。

## 目录约定

批量数据建议采用：

```text
<batch>/
├── 风格化素材/
├── 模板数据/
│   └── 0001/style-template.json
└── 模板清单.json
```

JSON 内本地资源路径相对当前 `style-template.json` 解析。一个模板可以包含多个 `referenceAssets`，但每个值都必须指向图片。

## 校验

单模板：

```bash
python scripts/validate_style_template.py \
  <template>/style-template.json
```

批量：

```bash
python scripts/validate_style_template.py \
  <batch>/模板数据
```

本地 OSS 预检，不上传：

```bash
pnpm style:finalize <batch>/模板数据 --dry-run
```

校验失败时修正源 JSON 或资源路径后重跑。不要跳过失败模板上传剩余批次。

## OSS 最终交付

用户明确要求后，执行：

```bash
pnpm style:finalize <batch>/模板数据 \
  --output artifacts/style-template-analyzer/handoff/<batch-id>
```

脚本上传 `referenceAssets`，按 SHA-256 去重，上传后执行 `HEAD`，再输出 URL 版 JSON。它不会覆盖本地模板，也不会把 `testAssets` 放进入库 JSON。详细规则见 `references/oss-handoff.md`。

## 回复规则

完成后简洁报告：

- 本地模板目录与清单路径；
- 模板数量、分类统计、待复核和不可用数量；
- validator、OSS PUT/HEAD、远端 URL 校验结果；
- handoff 目录及实际交给后端的 `<template-key>.json`；
- 使用了整图、主体或自适应转换范围，是否完整保留范围内内容；
- 保留并风格化了哪些文字，移除了哪些已确认的外部平台水印；
- 未执行的上传或生成测试明确写“未执行”；
- 是否修改仓库内 Skill，是否同步全局运行副本。

除非用户明确要求，不在聊天中粘贴完整 JSON、完整提示词或 OSS 配置。
