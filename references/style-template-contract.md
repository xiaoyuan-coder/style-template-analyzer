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
- `tags`、`styleTags`：当前版本要求内容一致。
- `referenceType`、`referenceStructure`：当前版本要求内容一致。
- `supportedModes`: `whole_image`、`subject_only` 中至少一项；不可用模板可为空。
- `contentScope`: `scene`、`subject`、`adaptive` 或 `unavailable`。
- `contentStrategy`、`referenceAssets`。
- `styleInstruction`、`contentExclusion`。
- `classificationConfidence`: 0 到 1。
- `needsReview`: 布尔值。

完整机器契约见 `style-template-import.schema.json`。

## 九类展示分类

| primary | displayName |
| --- | --- |
| `hand-drawn-doodle` | 手绘涂鸦 |
| `anime-comic` | 动漫漫画 |
| `watercolor-painting` | 水彩绘景 |
| `flat-graphic` | 平面图形 |
| `print-halftone` | 版画网点 |
| `pixel-art` | 像素艺术 |
| `material-3d` | 材质立体 |
| `photographic-look` | 摄影质感 |
| `collage-experimental` | 拼贴实验 |

主分类服务于用户浏览。蜡笔、彩铅、孔版、网点、胶片、辉光、黏土等具体效果写入 `styleTags` 和 `category.secondary`。

## 参考图权限

当前输入图决定主体身份、数量、姿态和内部特征。风格参考图决定材质、笔触、配色、明暗组织和构图语言。`contentExclusion` 必须排除参考图中的具体人物、动物、商品、品牌、文字和故事内容。

对比图必须写 `comparisonLayout`：

- `sourcePosition`: 原图所在位置；
- `outputPosition`: 效果图所在位置；
- `ignoredElements`: 箭头、软件 UI、说明文字、拼接边界等。

## 生成测试

用户明确要求测试时，使用与参考主体明显不同的输入图。结果通过后可补充：

- `testAssets.input`
- `testAssets.output`
- `testNotes`

跨主体测试至少检查身份、数量、姿态、风格强度、参考内容泄漏和背景策略。未经测试保持 `needsReview: true`。

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
