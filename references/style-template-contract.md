# 风格模板数据契约

## 文件职责

一个风格模板对应一个 `style-template.json`。本地版本保留相对图片路径、分析证据和可选测试记录；OSS handoff 版本只把 `referenceAssets` 改成受控 HTTPS URL，并移除 `testAssets`、`testNotes` 和 `reviewNotes`。

`模板清单.json` 用于批次追踪和浏览统计，不进入后端单模板导入。

## 必填字段

- `schemaVersion`: 当前为 `"1.0"`。
- `taxonomyVersion`: 当前为 `"2.0"`。
- `key`: `^[a-z][a-z0-9-]{1,59}$`，批次内唯一。
- `title`、`description`。
- `category.primary`、`category.secondary`、`category.displayName`。
- `displayCategory`：必须等于 `category.displayName`。
- `referenceType`、`referenceStructure`：当前版本要求内容一致。
- `supportedModes`: 可用模板固定为 `["whole_image", "subject_only"]`；不可用模板为空。
- `modeInstructions`: 可用模板分别提供 `whole_image` 和 `subject_only` 运行规则。
- `contentScope`: `scene`、`subject`、`adaptive` 或 `unavailable`。
- `contentStrategy`、`referenceAssets`。
- `styleInstruction`、`contentExclusion`。
- `classificationConfidence`: 0 到 1。
- `needsReview`: 布尔值。

可用模板的 `styleInstruction` 必须使用七维风格指纹结构并包含“去摄影化”段落，长度至少 200 字；`contentExclusion` 必须包含“参考内容禁迁移清单”及当前参考图的具体内容词。完整写法见 `style-analysis-and-prompting.md`。

完整机器契约见 `style-template-import.schema.json`。

## 八类展示分类

| primary | displayName |
| --- | --- |
| `hand-drawn-doodle` | 手绘涂鸦 |
| `anime-comic` | 动漫漫画 |
| `watercolor-painting` | 水彩绘景 |
| `flat-graphic` | 平面图形 |
| `print-halftone` | 版画网点 |
| `pixel-art` | 像素艺术 |
| `material-3d` | 材质立体 |
| `collage-experimental` | 拼贴实验 |

主分类服务于用户浏览。业务不提供摄影目标，`photographic-look / 摄影质感` 不得用于可用模板。蜡笔、彩铅、孔版、网点、胶片颗粒、漏光、辉光、黏土等具体效果写入 `category.secondary`；新模板暂不输出 `tags` 或 `styleTags`。胶片颗粒与漏光只能作为非摄影重绘后的表面语言。

## 参考图权限

当前输入图决定主体身份、数量、姿态、内部特征、物件、场景、视角、画幅和构图。风格参考图只决定成像媒介、形体抽象、线条边缘、笔触纹理、色彩组织、明暗空间、细节密度和非语义材料痕迹。`contentExclusion` 必须排除参考图中的具体人物、动物、商品、服饰、动作、道具、场景、品牌、文字、UI、边框、徽章、几何容器、装饰和故事内容。

禁止把参考图的构图、主体重建方式、裁切、圆形包围、边框、贴纸排版、星星或爱心等装饰写入 `styleInstruction`。这些变化只可由输入内容、`mode` 或用户明确指令授权。

对比图必须写 `comparisonLayout`：

- `sourcePosition`: 原图所在位置；
- `outputPosition`: 效果图所在位置；
- `ignoredElements`: 箭头、软件 UI、说明文字、拼接边界等。

## 转换范围优先规则

先依据模板确定转换范围，再决定保留内容。不要用“是否属于产品”“是否像 UI”或“是否重要”筛选整图模式中的元素。

| 转换范围 | 输入内容规则 | 常见对应 |
| --- | --- | --- |
| `whole_image` | 整张输入画布都是待保留内容。人物、背景、UI、对话框、字幕、角色名、按钮、HUD、文字、边框、贴纸、装饰和布局都要保留并统一风格化 | `full_scene_preservation`、`contentScope: scene` |
| `subject_only` | 识别并风格化主要主体；移除原背景、UI、文字和其他非主体内容，默认使用纯白 `#FFFFFF` 背景 | 运行请求中的 `mode: subject_only` |

所有可用模板同时支持两种转换范围，因此静态 `contentScope` 统一为 `adaptive`。`contentStrategy` 只用于检索和兼容旧数据，不能进入生成命令，也不能覆盖用户本次选择的 `mode`。

统一运行规则：

```json
"modeInstructions": {
  "whole_image": "保留整张输入画布的全部内容、文字、UI、布局与空间关系，并对所有内容统一应用模板风格。",
  "subject_only": "只提取并风格化主要主体，保持身份、数量、姿态、轮廓和关键内部特征；移除原背景及其他非主体内容，使用均匀纯白 #FFFFFF 背景。"
}
```

`whole_image` 的“完整保留”包括：

1. 保持画布比例、视角和总体构图。
2. 保持所有可见区域及其空间关系，边缘和角落也要检查。
3. 保持 UI、字幕和文字的位置、尺寸、层级及逐字内容，同时让字体、边框、图标和面板使用目标风格。
4. 允许材质、笔触、配色、明暗和细节抽象程度发生变化。
5. 禁止擅自裁掉、清空、简化或替换输入图的某一部分。

## 外部平台水印例外

水印清理是转换范围之外的窄例外：

- 高置信度的外部平台来源水印默认移除，例如角落中的“小红书”、抖音或 TikTok 平台标记。移除后依据相邻背景、面板或纹理自然补全。
- 账号名、二维码、分享贴纸、系统栏、浏览器/相册外壳只有在明确属于外部传播或截屏层时才移除。
- 场景内品牌、游戏 UI、字幕、海报文字、物件标签、装饰贴纸和边框属于输入图内容；`whole_image` 必须保留并风格化。
- 无法确定某个角标是否为外部水印时，`whole_image` 默认保留；该判断会实质改变结果时只追问这一项。
- 用户明确要求拥有最高优先级。用户要求保留水印时保留，要求移除其他元素时移除。

风格参考图中的具体人物、物件、文字、品牌、UI、水印和故事始终属于参考内容排除项，只允许提供视觉规律。

提示词先加载 `style-analysis-and-prompting.md` 的七维风格指纹和内容禁迁移规则，并至少明确列出：

```text
Transformation scope: whole_image | subject_only | adaptive
Whole-image invariant: <整张输入画布是否完整保留>
Exact text: "<范围内需要逐字保留的文字>"
Confirmed external watermark removal: <只列出高置信度平台水印>
Reference-only exclusions: <参考图具体内容>
Rendering completion: <全像素非摄影重绘要求>
```

对于 `whole_image`，不要使用“只保留主体”“简化背景”“移除 UI”“删除文字”等指令，除非用户明确要求。

对于 `subject_only`：

1. 保持主体身份、数量、姿态、轮廓、关键内部特征和主体内部文字。
2. 移除原背景及其他非主体元素。
3. 默认在纯白 `#FFFFFF` 背景上重新构图，背景保持均匀，无纹理、渐变和无关物件。
4. 保持主体边缘干净，不残留原背景碎片。
5. 用户明确指定透明、其他纯色或新场景时，按用户指令覆盖白底默认值。

## 生成测试

用户明确要求测试时，使用与参考主体明显不同的输入图。结果通过后可补充：

- `testAssets.input`
- `testAssets.output`
- `testNotes`

跨主体测试至少检查：

- 身份、数量、姿态和空间关系；
- 风格强度与背景策略；
- 转换范围是否正确；
- `whole_image` 是否逐区覆盖完整输入画布，包括 UI、字幕、文字、边缘和角落；
- `subject_only` 是否完整保留主体、清除背景残片并使用纯白背景；
- 范围内需要精确保留的文字是否逐字正确；
- 已确认的外部平台水印是否完全消失；
- 移除区域是否自然补全；
- 参考图具体人物、物件、文字、品牌、UI 和水印是否泄漏。

所有模板都要逐区检查写实皮肤、真实毛发、照片型物体表面、摄影景深、原始镜头光照和未重绘像素。任一区域保留写实摄影介质，或只叠加调色、颗粒、漏光、网点和纸纹，记为“摄影介质残留”硬失败，风格还原分为 0。

测试结果使用：

```json
"styleEvaluation": {
  "score": 92,
  "verdict": "pass",
  "hardFailures": [],
  "dimensionScores": {
    "imagingMedium": 19,
    "marksAndTexture": 19,
    "colorOrganization": 14,
    "linesAndEdges": 14,
    "shapeAndDetail": 9,
    "toneAndSpace": 8,
    "globalCoverage": 9
  },
  "evidence": "跨主体测试中全部可见区域完成孔版重绘，未出现参考物件或写实照片残留。"
}
```

七项满分依次为 20、20、15、15、10、10、10。只有 `score >= 90`、`hardFailures` 为空且 `verdict: pass` 时才能把 `needsReview` 改为 `false`。`needsReview: false` 还必须同时提供 `testAssets.input` 与 `testAssets.output`。

`whole_image` 中任一输入区域被擅自删除、漏画、裁切或语义替换，测试不得标记为通过。已确认移除的平台水印仍可见，或只是被风格化后保留，也不得标记为通过。参考内容泄漏和任意摄影介质残留都触发硬失败。未经测试保持 `needsReview: true`。

## 本地与 handoff

本地：

```json
"referenceAssets": {
  "style": "../../风格化素材/0006.png"
}
```

handoff：

```json
"referenceAssets": {
  "style": "https://assets.example.com/dev/style/templates/<uuid>.png"
}
```

handoff 目录中每个 `<key>.json` 都是独立导入项；不要提交本地路径版 JSON、批次清单或上传恢复记录。
