---
name: style-template-analyzer
description: 分析单张风格参考图、原图/效果图对比或批量图片目录，分离可迁移画风与参考内容，生成研发可直接入库的 STYLE_REF JSON，并通过跨内容真实生成验证非摄影风格还原。用于风格化模板、画风提取、风格还原不足、结果仍像照片、参考人物或边框泄漏、风格模板字段整理、OSS 交付和批量质量评测。
---

# 风格化模板分析器

把参考图编译成稳定的风格预设。用户上传图决定全部画面内容；固定参考图只决定成像媒介、形体抽象、线条边缘、笔触纹理、色彩组织、明暗空间和覆盖方式。

## 请求路由

| 意图 | 产物 | 读取 |
| --- | --- | --- |
| 分析参考图、生成模板 | `style-analysis.json`、`style-template.json` | `references/style-analysis-and-prompting.md`、`references/style-template-contract.md` |
| 批量分析 | 每模板两份 JSON、批次清单 | 同上 |
| 真实生成与验收 | 候选图、`style-evaluation.json` | `references/style-analysis-and-prompting.md`、`references/style-template-contract.md` |
| OSS 和研发交付 | `<key>.json` | `references/oss-handoff.md` |
| 检查最终模板 | 校验结果 | `references/style-template-contract.md` |

普通分析停在本地。用户明确要求上传、最终交付或后端导入时再执行 OSS 流程。

## 三层产物

1. `style-analysis.json`：内部取证档案。保存七维指纹、3–5 个区分性特征和参考内容禁迁移清单；遵循 `references/style-analysis.schema.json`。
2. `style-template.json`：研发运行模板。只保存 `key/title/description/kind/cover/referenceImage/imageSize/imageN/promptTemplate/inputSchema/preprocessSteps/metadata`；遵循 `references/style-template-import.schema.json`。
3. `style-evaluation.json`：独立验收记录。保存至少四个跨内容案例、候选数量、逐项评分和总体结论；遵循 `references/style-evaluation.schema.json`。

分析字段只进入第一层，评分字段只进入第三层。最终运行 JSON 保持研发字段纯净。

## 核心流程

1. 检查参考图片格式、尺寸、重复文件和编号连续性。
2. 识别参考结构：单图、分离的原图/效果图、拼接对比图、带标注对比图。
3. 建立参考内容清单。记录人物、动物、物件、服饰、动作、场景、文字、品牌、UI、边框、徽章、几何容器和装饰。
4. 提取七维风格指纹。把媒介、形体、线条、笔触、色彩、明暗和覆盖方式写成可观察事实。
5. 从七维中选择 3–5 个最能区分该参考图的特征。区分性特征必须同时满足：肉眼可证、跨主体仍成立、能够改变最终像素、可用于评分。
6. 用“技法 + 视觉结果”命名。标题、描述和新 key 只表达风格；存量 key 保持稳定。
7. 编译 `promptTemplate`。使用第 2 张图作为唯一内容来源，第 1 张图作为纯风格参考；写入区分性特征、参考内容禁迁移和全像素去摄影化要求。
8. 写入固定研发字段。`cover` 与 `referenceImage` 在本地阶段指向风格参考图；`inputSchema` 固定为一个 `image/source` 输入；`preprocessSteps` 固定为空数组。
9. 运行模板 validator。字段、资源和提示词角色全部通过后才进入生成测试。
10. 使用至少四张差异明显的输入图，每张生成 2–4 个候选并选出最接近参考风格的结果。
11. 由独立复核者填写 `style-evaluation.json`。平均分达到 90、每个案例达到 90、七个维度各自达到 80% 且无硬失败时才通过。

## 内容权限

- 第 2 张图片决定主体、数量、身份、姿态、轮廓、内部特征、物件、场景、文字、视角、画幅和构图。
- 第 1 张图片决定视觉渲染规律，并且只提供这些规律。
- App 的抠图功能处理背景移除。风格模板保持用户当前输入内容；参考图中的白底、圆章、贴纸排版或居中构图不获得迁移权限。
- 业务输出全部为非摄影重绘。网点、颗粒、色偏、纸纹和漏光必须参与形体与明暗构成，形成完整新画面。

## 提示词编译

最终 `promptTemplate` 使用四段：

1. 第 2 张图片的内容独占权与保真项目；
2. 第 1 张图片的风格权限与 3–5 个区分性特征；
3. 当前参考图的具体内容禁迁移清单；
4. 全像素重绘、去摄影化和可识别性检查。

目标长度为 120–700 个中文字符，最大 1200。七维完整分析保存在 `style-analysis.json`，最终提示词只携带最有辨识度、彼此不重复的特征。完整方法见 `references/style-analysis-and-prompting.md`。

## 校验

模板：

```bash
python skills/style-template-analyzer/scripts/validate_style_template.py \
  <template>/style-template.json
```

验收：

```bash
python skills/style-template-analyzer/scripts/validate_style_evaluation.py \
  <template>/style-evaluation.json
```

本地 OSS 预检：

```bash
pnpm style:finalize <batch>/模板数据 --dry-run
```

## OSS 交付

用户明确要求后执行：

```bash
pnpm style:finalize <batch>/模板数据 \
  --output artifacts/style-template-analyzer/handoff/<batch-id>
```

脚本上传 `cover` 和 `referenceImage`，按 SHA-256 去重，执行 PUT/HEAD 校验，再输出远端 URL 版纯运行 JSON。源文件保持不变。

## 完成标准

- 本地分析、运行模板和验收记录职责清楚；
- 最终 JSON 只包含研发字段；
- 用户图和风格图权限完整分离；
- 提示词包含具体风格特征与具体参考内容禁迁移项；
- 真实验收覆盖至少四类内容和多个候选；
- 通过模板平均分与逐案例均达到 90，关键维度无短板；
- 上传、生成测试和独立复核的实际执行情况如实报告。
