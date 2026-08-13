# 整图视觉重构模板数据契约

## 1. 文件职责

每个模板目录使用三份文件：

```text
<template>/
├── style-analysis.json
├── style-template.json
└── style-evaluation.json   # 真实生成测试后出现
```

- `style-analysis.json` 保存取证与推理，遵循 `style-analysis.schema.json`。
- `style-template.json` 保存研发运行字段，遵循 `style-template-import.schema.json`。
- `style-evaluation.json` 保存测试和验收，遵循 `style-evaluation.schema.json`。

`style-template.json` 是唯一进入研发导入和 OSS handoff 的文件。`kind: STYLE_REF` 保持现有研发兼容语义，运行方式统一为 prompt-only。`STYLE_REF` 可以承载绘制风格、材质工艺、主体形态、视觉系统、信息表达和构图结构等整图重构。

## 2. 最终运行字段

| 字段 | 规则 |
| --- | --- |
| `key` | 稳定业务键，格式 `^[a-z][a-z0-9-]{1,59}$` |
| `title` | 只表达技法和视觉结果 |
| `description` | 用户可理解的成图效果 |
| `kind` | 固定为 `STYLE_REF` |
| `cover` | 本地参考图路径或受控 OSS URL |
| `referenceImage` | 离线取证与研发兼容字段；通常与 `cover` 相同，运行时不传给模型 |
| `imageSize` | `<宽>x<高>`，每边 256–4096；名义输出尺寸，不授予参考图画幅权限 |
| `imageN` | 固定为 `1` |
| `promptTemplate` | 实际生效的完整整图视觉重构提示词 |
| `inputSchema` | 固定为一个 `image/source` 输入 |
| `preprocessSteps` | 当前固定为 `[]` |
| `metadata.sourceRef` | 生产追溯信息 |

新模板暂不输出顶层 `tags/styleTags`。研发 Schema 要求标签容器时使用 `metadata.tags: []`。`metadata.styleAnalysis` 只用于留档，默认省略；所有必须生效的约束都写入 `promptTemplate`。

最终运行 JSON 不包含以下内部字段：

```text
schemaVersion taxonomyVersion category displayCategory
referenceType referenceStructure supportedModes modeInstructions
contentScope contentStrategy referenceAssets transformationIntent
analysisEvidence styleInstruction contentExclusion preservation
classificationConfidence needsReview reviewNotes testAssets
testNotes styleEvaluation qualityStatus renderingMethod
```

这些信息分别进入分析档案、验收记录或不再维护。

## 3. 固定输入结构

```json
[
  {
    "type": "image",
    "id": "source",
    "label": "你的原图",
      "hint": "上传一张想要重新设计的图片",
    "required": true,
    "maxCount": 1,
    "private": false
  }
]
```

运行时只提交用户上传的 `source`。模型图片数组固定为 `[source]`，并配合 `promptTemplate` 执行单图整图重构。`cover`、`referenceImage`、`metadata.sourceRef.styleAsset` 和 `style-analysis.json` 均不进入生成请求。完整协议见 `prompt-only-runtime.md`。

### 画幅继承

- 运行前读取用户上传图的宽、高、横竖方向和宽高比。
- 输出保持用户上传图的横竖方向与宽高比；浮窗、边框、UI 或其他获准模板结构在该画幅内自适应排布。
- `referenceImage` 的尺寸和比例只描述参考资源，`imageSize` 只提供名义像素预算，两者都不覆盖用户图画幅。
- 生成服务只接受离散尺寸时，选择与用户图宽高比最接近且方向一致的尺寸，并记录比例偏差。
- 真实生成调用不附加来自参考图、模板示例或人工测试习惯的固定比例指令。

## 4. 内容与变换边界

默认保留全部显著主体、主体集合、身份、面部与体型、轮廓、发型、花纹配色、服装、配饰、手持物、主体关联物和关键关系。全部显著主体逐一对应用户图中的原主体；`instanceMode: preserve` 要求基础实例数量一一对应，人物、动物、物体及关联物不复制、不合并、不删减、不增殖。`instanceMode: repeat-or-split` 只授权可追溯的重复、分格、局部放大或多视角派生，派生实例仍归属于原主体，不能形成新的独立主体。主主体提取、形态变换、新动作/视角、重复呈现、环境重构和构图重组需要在 `transformationContract` 中授权，并写入运行提示词。

参考图中的案例人物、动物、商品、动作、场景、故事、品牌和未授权装饰进入 `referenceContentBlocklist`。可跨输入复用的 UI、容器、边框、图表、局部放大框或其他结构可以进入 `templateConstants`。两个集合互斥，参考案例物象名称不写入运行提示词。

## 5. 内部分析结构

2.0 `style-analysis.json` 至少记录：

- 参考资源和参考结构；
- 参考图具体内容清单；
- `transformationContract` 和变换家族；
- 七维 `renderingFingerprint`；
- 3–6 个 `signatureMechanisms` 及图像证据；
- 参考内容禁迁移清单；
- 分类置信度和素材可用性。

摄影混合、拼版、覆盖层和低信息参考还要记录：

- `extractionMode`: `hybrid-operator-salvage` 或 `low-information-salvage`；
- `qualityStatus: salvaged`；
- `salvagePlan.sourceDependency`；
- 观测算子、非摄影载体、覆盖扩展和不确定性。

`salvaged` 表示已生成可测试的运行模板，尚未完成真实生成验收。`unusable` 仅用于文件损坏、完全无法读取或连两个可测视觉算子都不存在的素材。

七维成像指纹描述视觉像素世界，变换契约描述哪些内容可以改变，标志性机制驱动运行提示词与评分。

## 6. 提示词硬门槛

validator 要求 `promptTemplate` 同时包含：

1. 用户上传图是唯一图片输入和唯一内容来源；
2. 全部显著主体或主主体选择、原主体逐一对应，以及主体特征连续性；
3. 发型、服装、配饰和手持物的保留要求；
4. 主体形态、动作/视角、呈现实例、环境、构图、固定结构和受控派生的授权或保留声明；
5. 完整重绘或完整重建，以及 3–6 个标志性变换机制；
6. 模板未授权的越权新增内容边界；
7. 原照片像素必须消失；
8. 输出画幅方向与宽高比跟随用户上传图；
9. 不含“第 1 张图片”“第 2 张图片”“参考图”“仅作为风格参考”等双图依赖词。

提示词长度为 120–1200 个字符，推荐 120–700。过长提示词回到分析文件中删减重复、宽泛和低区分度描述。

## 7. 验收门槛

2.0 `style-evaluation.json` 与运行模板分离。通过状态需要：

- 至少四个跨内容案例；
- 每个输入生成 2–4 个候选；
- 独立复核者评分；
- 每个案例总分至少 90；
- 六个维度各自达到满分的 80%；
- 每个案例硬失败为空；
- 所有案例平均分至少 90。

六维分值为：标志性机制还原 30、主体特征连续性 20、内容与关系 15、授权结构与派生 15、全像素非摄影覆盖 10、画幅与构图 10。

运行请求包含参考素材、显著主体丢失/替换、基础主体实例复制/合并/删减/增殖、派生实例形成新独立主体、主体特征漂移、未授权内容或案例物象泄漏、摄影介质残留、核心标志性机制完全缺失、输出横竖方向错误或宽高比明显偏离均为硬失败，案例记 0 分。契约已授权且保持原主体归属的姿态、视角、重复呈现、环境或构图变化不计为失败。

## 8. 本地与 handoff

本地模板：

```json
{
  "cover": "./style-reference.png",
  "referenceImage": "./style-reference.png"
}
```

handoff 模板：

```json
{
  "cover": "https://assets.example.com/dev/style/templates/<uuid>.png",
  "referenceImage": "https://assets.example.com/dev/style/templates/<uuid>.png"
}
```

相同图片通过 SHA-256 只上传一次。handoff 目录只包含 `<key>.json`，不包含内部分析、验收记录、批次清单或上传状态。
