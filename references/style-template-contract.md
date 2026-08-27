# 整图视觉重构模板数据契约

## 目录

- [1. 文件职责](#1-文件职责)
- [2. 最终运行字段](#2-最终运行字段)
- [3. 固定输入结构](#3-固定输入结构)
- [4. 内容与变换边界](#4-内容与变换边界)
- [5. 内部分析结构](#5-内部分析结构)
- [6. 提示词硬门槛](#6-提示词硬门槛)
- [7. 可选完整验收门槛](#7-可选完整验收门槛)
- [8. 审核包与正式包](#8-审核包与正式包)

## 1. 文件职责

每个已完成 revision 使用正式版本与内部证据分层，并从中导出单文件交付：

```text
<revision>/
├── artifact-manifest.json
├── package/
│   ├── style-template.json
│   └── cover.png
└── internal/
    ├── style-analysis.json 或 self-production-analysis.json
    ├── test-image-assignment.json
    ├── cover-generation-receipt.json
    ├── effect-reproduction-contract.json
    ├── cover-check-receipt.json
    ├── approval-decision-receipt.json
    └── oss-finalization-receipt.json

<delivery>/
└── <key>.json
```

- `package/` 是正式 revision 的可追溯运行包，严格只含两个文件。
- `style-template.json` 保存研发运行字段，其 `cover` 已回填受控 OSS URL，遵循 `style-template-import.schema.json`。
- `<delivery>/<key>.json` 复制正式 `style-template.json` 的官方字段形状，文件名与 JSON 内 `key` 完全一致，是唯一最终下游交付文件。
- `统一通过模板索引.json` 是工作台和运维读取的相邻发现层，登记活动 revision、Approved After、Approved Before 或其可解析证据路径、OSS 状态与 SHA；这些内部发现字段不注入官方 `<key>.json`。
- `internal/` 保存取证、唯一测试图分配、封面生成、轻量检查和 OSS 最终化回执；自生产 revision 另含基线快照。
- `artifact-manifest.json` 声明 `review-package` 或 `final-package` 阶段、产物类型、三段式版本、producer 和 SHA-256，遵循 `contracts/artifact-manifest.schema.json`。
- `style-evaluation.json` 由完整真图评测阶段单独产生，不进入最终模板包。

`kind: STYLE_REF` 保持现有研发兼容语义，运行方式统一为 prompt-only。`STYLE_REF` 可以承载绘制风格、材质工艺、主体形态、视觉系统、信息表达和构图结构等整图重构。

## 2. 最终运行字段

| 字段 | 规则 |
| --- | --- |
| `key` | 稳定业务键，格式 `^[a-z][a-z0-9-]{1,59}$` |
| `title` | 只表达技法和视觉结果 |
| `description` | 用户可理解的成图效果 |
| `kind` | 固定为 `STYLE_REF` |
| `cover` | 本地效果图路径或受控 OSS URL；只用于前端展示，运行时不传给模型 |
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

运行时只提交用户上传的 `source`。模型图片数组固定为 `[source]`，并配合 `promptTemplate` 执行单图整图重构。`cover`、`metadata.sourceRef.styleAsset` 和 `style-analysis.json` 均不进入生成请求。完整协议见 `prompt-only-runtime.md`。

### 画幅策略

- 运行前读取用户上传图的宽、高、横竖方向和宽高比。
- 默认使用 `inherit-source-aspect-ratio`。Approved After 明确展示了重定画幅时，可以选择 `adaptive-reframe` 或 `fixed-template-aspect-ratio`；该决定同时进入 analysis 3.0.0、After 复现合同和运行 prompt。
- `adaptive-reframe` 根据用户内容和 Approved After 的构图关系选择横竖方向与比例；`fixed-template-aspect-ratio` 使用模板明确声明的方向与比例。
- `cover` 和 `imageSize` 只提供证据与名义像素预算。只有复现合同的画幅边界可以覆盖源图比例，封面尺寸本身没有运行授权。
- 生成服务只接受离散尺寸时，选择与已决定画幅策略最接近的尺寸，并记录比例偏差。
- 真实生成调用不附加来自参考图、模板示例或人工测试习惯的固定比例指令。

## 4. 内容与变换边界

默认保留全部显著主体、主体集合、身份、面部与体型、轮廓、发型、花纹配色、服装、配饰、手持物、主体关联物和关键关系。全部显著主体逐一对应用户图中的原主体；`instanceMode: preserve` 要求基础实例数量一一对应，人物、动物、物体及关联物不复制、不合并、不删减、不增殖。`instanceMode: repeat-or-split` 只授权可追溯的重复、分格、局部放大或多视角派生，派生实例仍归属于原主体，不能形成新的独立主体。主主体提取、形态变换、新动作/视角、重复呈现、环境重构和构图重组需要在 `transformationContract` 中授权，并写入运行提示词。

参考图中的案例人物、动物、商品、动作、场景、故事、品牌和未授权装饰进入 `referenceContentBlocklist`。可跨输入复用的 UI、容器、边框、图表、局部放大框或其他结构可以进入 `templateConstants`。两个集合互斥，参考案例物象名称不写入运行提示词。

固定结构还要通过服装印制适配判断。普通模板只授权有审美作用的边框、分格、拼贴或界面；连接线、定位点、分析框、刻度、图例、编号、仪表和说明性局部放大窗默认退出。用户明确要求图鉴、档案、分析或说明书效果时，才把这些组件列入 `templateConstants`。

## 5. 内部分析结构

3.0.0 `style-analysis.json` 至少记录；存量 `2.0/2.0.0` 由 legacy gate 读取：

- 参考资源和参考结构；
- 参考图具体内容清单；
- `transformationContract` 和变换家族；
- 七维 `renderingFingerprint`；
- 3–6 个 `signatureMechanisms` 及图像证据；
- 参考内容禁迁移清单；
- 分类置信度和素材可用性。
- 新产物的 `garmentPrintClassification` 四轴分类；旧 2.0 档案可在迁移前暂缺该字段。

摄影混合、拼版、覆盖层和低信息参考还要记录：

- `extractionMode`: `hybrid-operator-salvage` 或 `low-information-salvage`；
- `qualityStatus: salvaged`；
- `salvagePlan.sourceDependency`；
- 观测算子、非摄影载体、覆盖扩展和不确定性。

`salvaged` 表示已生成可测试的运行模板，尚未完成真实生成验收。`unusable` 仅用于文件损坏、完全无法读取或连两个可测视觉算子都不存在的素材。

七维成像指纹描述视觉像素世界，变换契约描述哪些内容可以改变，标志性机制驱动运行提示词与评分。

## 6. 提示词硬门槛

新 revision 的 validator 要求 `promptTemplate` 按“任务、保留、变换权限、核心效果、空间结构、内容映射、视觉风格、完成判据、限制”九段组织；历史六段提示词只用于只读迁移。详细写法以 `runtime-prompt-authoring-standard.md` 为准。新提示词同时包含：

1. 明确以用户上传图为内容依据；单图数量由 `inputSchema` 和运行适配器保证；
2. 全部显著主体或主主体选择、原主体逐一对应，以及主体特征连续性；
3. 发型、服装、配饰和手持物的保留要求；
4. 主体形态、动作/视角、呈现实例、环境、构图、固定结构和受控派生的授权或保留声明；
5. 完整重绘或完整重建，以及 1–3 个具备来源角色、变换动作和可见结果的必现机关；
6. 画布区域骨架、逐区内容职责、实例次数和来源角色替代策略；
7. 3–5 个可从最终图直接观察的完成判据；
8. 直接说明不要新增的主体、物件、关系或文字；
9. 不要保留照片像素；
10. 输出画幅方向与宽高比具有明确策略：继承用户图，或按 Approved After 合同重定；
11. 不含“第 1 张图片”“第 2 张图片”“参考图”“仅作为风格参考”等双图依赖词。

提示词长度为 120–1200 个字符，推荐 450–1100。过长提示词回到分析文件中删减重复、宽泛和低区分度描述。运行 prompt 不得出现合同字段名、证据文本、内部分类标签和“前文”类悬空指代。

## 7. 可选完整验收门槛

最终模板包完成后不自动执行本节。用户明确调用 `evaluate(package)` 时，2.0.0 `style-evaluation.json` 与运行模板分离。通过状态需要：

- 至少四个跨内容案例；
- 每个输入生成 2–4 个候选；
- 独立复核者评分；
- 每个案例总分至少 90；
- 六个维度各自达到满分的 80%；
- 每个案例硬失败为空；
- 所有案例平均分至少 90。

六维分值为：标志性机制还原 30、主体特征连续性 20、内容与关系 15、授权结构与派生 15、全像素非摄影覆盖 10、画幅与构图 10。

运行请求包含参考素材、显著主体丢失/替换、基础主体实例越权复制/合并/删减/增殖、派生实例形成新独立主体、主体特征漂移、未授权内容或案例物象泄漏、摄影介质残留、核心标志性机制完全缺失、输出画幅偏离复现合同均为硬失败，案例记 0 分。契约已授权且保持原主体归属的姿态、视角、重复呈现、画幅、裁切补全、比例位置、环境、遮挡或构图变化不计为失败。

普通服装图案还要通过 `garment-print-template-taxonomy.md` 的印制适配门。意外分析线和说明组件先判 `needs-prompt-revision`；它们压过主体或破坏图案完整性时按业务硬失败处理。

## 8. 审核包与正式包

阶段 1 的审核包使用本地封面：

```json
{
  "cover": "cover.png"
}
```

人工验收 `pass` 后进入阶段 3，正式模板回填受控 URL：

```json
{
  "cover": "https://assets.example.com/dev/style/templates/<uuid>.png"
}
```

第一种状态放在 `review-package/`，第二种状态放在正式 revision 的 `package/`；两个目录都严格只含 JSON 与封面。正式 revision 通过后再导出 `<key>.json`，下游不接收本地 `cover.png`。`cover` 按 SHA-256 去重上传，OSS 失败或最终契约失败时不发布正式 revision，也不导出交付 JSON；保留已通过审核包供恢复。

自生产的候选审批图只提供离线设计证据。当用户选中总览外候选、首版或同 key 的其他视觉 revision 时，最终编译使用精确封面 SHA 绑定的批准专用规格；运行时仍只提交用户 `source` 和冻结后的 `promptTemplate`。

存量 `effect.png`、v3 `fast-package`、v4 `prepublish/final-package` 和独立 `oss-handoff` 继续由兼容 profile 读取。
