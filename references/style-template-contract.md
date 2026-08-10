# 风格模板数据契约

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

`style-template.json` 是唯一进入研发导入和 OSS handoff 的文件。

## 2. 最终运行字段

| 字段 | 规则 |
| --- | --- |
| `key` | 稳定业务键，格式 `^[a-z][a-z0-9-]{1,59}$` |
| `title` | 只表达技法和视觉结果 |
| `description` | 用户可理解的成图效果 |
| `kind` | 固定为 `STYLE_REF` |
| `cover` | 本地参考图路径或受控 OSS URL |
| `referenceImage` | 固定风格参考图；通常与 `cover` 相同 |
| `imageSize` | `<宽>x<高>`，每边 256–4096 |
| `imageN` | 固定为 `1` |
| `promptTemplate` | 实际生效的完整风格迁移提示词 |
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
    "hint": "上传一张想要转换风格的图片",
    "required": true,
    "maxCount": 1,
    "private": false
  }
]
```

运行时图片顺序：

- 第 1 张图片：`referenceImage`，提供风格；
- 第 2 张图片：用户上传的 `source`，提供全部内容。

图片顺序变化会改变提示词含义。生成适配器必须保持这个顺序；无法保证时先修正适配器。

## 4. 内容与背景边界

风格模板保持用户当前输入中的主体、物件、场景、文字、视角和构图。App 的抠图功能决定用户是否移除背景；模板本身不从参考图继承白底、透明背景、圆形裁切、主体居中或贴纸轮廓。

参考图中的人物、动物、物件、服饰、动作、场景、文字、品牌、UI、边框、徽章、几何容器和装饰进入 `referenceContentBlocklist`，并编入 `promptTemplate` 的禁止迁移段落。

## 5. 内部分析结构

`style-analysis.json` 至少记录：

- 参考资源和参考结构；
- 参考图具体内容清单；
- 七维风格指纹；
- 3–5 个区分性特征及图像证据；
- 参考内容禁迁移清单；
- 分类置信度和素材可用性。

七维分析提供完整理解，区分性特征驱动运行提示词。参考主体、故事和构图载体只进入内容清单。

## 6. 提示词硬门槛

validator 要求 `promptTemplate` 同时包含：

1. 第 2 张图片为唯一内容来源；
2. 第 1 张图片仅作为风格参考；
3. 完整重绘或完整重建；
4. 具体参考内容禁迁移；
5. 原照片像素必须消失。

提示词长度为 120–1200 个字符，推荐 120–700。过长提示词回到分析文件中删减重复、宽泛和低区分度描述。

## 7. 验收门槛

`style-evaluation.json` 与运行模板分离。通过状态需要：

- 至少四个跨内容案例；
- 每个输入生成 2–4 个候选；
- 独立复核者评分；
- 每个案例总分至少 90；
- 七个维度各自达到满分的 80%；
- 每个案例硬失败为空；
- 所有案例平均分至少 90。

七维分值为：成像媒介 20、笔触纹理 20、色彩组织 15、线条边缘 15、形体细节 10、明暗空间 10、全局覆盖 10。

内容泄漏、摄影介质残留、输入内容被替换、关键风格维度完全缺失均为硬失败，案例记 0 分。内容保持正确和画面好看不直接提高风格还原分；评分始终对照参考图的具体视觉规律。

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
