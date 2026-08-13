---
name: style-template-analyzer
description: 把单张参考图、原图/效果图对比、结构化视觉系统或批量素材离线编译为 prompt-only 整图视觉重构模板；识别绘制风格、材质工艺、主体形态、视觉系统、信息表达和构图结构，声明主体、环境、派生内容与固定结构权限，运行时只输入用户图。用于风格迁移、玩偶/黏土/像素等形态转换、CRT/UI、分格与多视角、摄影素材救援、参考内容泄漏、整批重跑和 90 分质量验收。
---

# 整图视觉重构模板分析器

把离线参考素材编译成可重复执行的视觉变换契约和运行提示词。运行时只向模型提交用户上传图；`cover` 与 `referenceImage` 只用于展示、取证和追溯。现有技术名称 `style-template-analyzer`、`STYLE_REF` 和 `style-*.json` 作为兼容层保留。

## 请求路由

| 意图 | 产物 | 必读 |
| --- | --- | --- |
| 分析参考素材、生成模板 | `style-analysis.json`、`style-template.json` | `references/style-analysis-and-prompting.md`、`references/style-template-contract.md` |
| 批量分析或整批重跑 | 每模板两份 JSON、批次清单 | 同上 |
| 摄影、拼版、覆盖层或低信息救援 | 分析、运行模板、待验证标记 | `references/hybrid-reference-salvage.md` |
| 真实生成与验收 | 候选图、`style-evaluation.json` | `references/style-analysis-and-prompting.md`、`references/style-template-contract.md` |
| OSS 与研发交付 | `<key>.json` | `references/oss-handoff.md` |

普通分析停在本地。用户明确要求上传、最终交付或后端导入时再执行 OSS 流程。

## 三层产物

1. `style-analysis.json`：内部取证档案。使用 2.0 分析契约，保存视觉变换契约、七维成像指纹、3–6 个标志性机制、参考内容禁迁移清单和可选救援计划。
2. `style-template.json`：研发运行模板。只保存现有研发字段；所有必须生效的变换权限都编入 `promptTemplate`。
3. `style-evaluation.json`：独立验收记录。使用 2.0 评分维度，检查机制还原、主体特征连续性、内容与关系、固定结构与派生、全像素非摄影覆盖、画幅与构图。

## 核心流程

1. 检查参考图片格式、尺寸、重复文件和编号连续性。
2. 识别参考结构：单图、分离的原图/效果图、拼接对比图、带标注对比图。
3. 建立参考内容清单，分开案例主体、可授权的固定视觉结构和纯成像规律。
4. 选择提取模式：直接重构、前后差分、混合算子救援或低信息救援。
5. 确定一个或多个变换家族：绘制风格、材质工艺、主体形态、视觉系统、信息表达、构图结构。
6. 编写 `transformationContract`：声明显著主体或主主体选择、形态、动作/视角、呈现实例、环境、构图、固定结构与受控派生内容。
7. 取证七维成像指纹，再选出 3–6 个标志性机制。机制需要肉眼可证、跨主体成立、能够改变最终像素并可评分。
8. 用“变换机制 + 视觉结果”命名。新 key 表达输出效果；存量 key 保持稳定。
9. 按变换契约编译 prompt-only `promptTemplate`。运行提示词只称“用户上传图”，不提参考图、图片序号或案例物象。
10. 先运行分析 validator，再运行模板 validator。静态证据、权限、字段和 prompt-only 角色全部通过后进入生成测试。
11. 真实生成每次只提交 `source` 一张图和 `promptTemplate`，输出沿用用户图横竖方向和宽高比。
12. 使用至少四类差异明显的输入，每类生成 2–4 个候选，由独立复核者填写 2.0 验收记录。

## 全局内容不变量

- 默认保留全部显著主体。只有契约明确使用 `primary-subject` 时才选取主主体。
- 保留主体集合、身份、面部与体型、轮廓、发型、花纹与配色、服装、配饰、手持物和关键关系。
- 全部显著主体逐一对应用户图中的原主体。`instanceMode: preserve` 保持基础实例数量；人物、动物、物体及关联物不复制、不合并、不删减、不增殖。
- `instanceMode: repeat-or-split` 只允许可追溯的重复、分格、局部放大或多视角派生；派生实例保持原主体身份与特征，不扩增为新的独立主体。
- 环境可以按契约保留、简化、移除、替换或重建。主体关联物不进入普通背景。
- 模板可以保留经过明确授权的界面、容器、装饰或其他固定视觉结构。案例主体和未授权物象进入禁迁移清单。
- 用户图的横竖方向和宽高比始终继承；画幅内部构图可以按契约重组。
- 业务输出使用全像素非摄影重绘。摄影底图、写实皮肤、真实毛发、镜头景深和滤镜式叠加全部退出。

## 提示词编译

按四段编译：

1. 单图独占权、显著主体范围、主体逐一对应、主体特征连续性和画幅继承；
2. 契约授权的形态、动作/视角、呈现实例、环境、构图、固定结构和受控派生内容；
3. 3–6 个标志性变换机制及其全局像素表现；
4. 全像素非摄影重绘、模板未授权内容边界和输出检查。

参考内容禁迁移清单只用于离线审查，不把案例物象名称写回运行提示词。使用“保留原照片、以照片为底图、在原照片上叠加”直接校验失败。详细契约与示例见 `references/style-analysis-and-prompting.md`。

## 校验

```bash
python skills/style-template-analyzer/scripts/validate_style_analysis.py <template>/style-analysis.json
python skills/style-template-analyzer/scripts/validate_style_template.py <template>/style-template.json
python skills/style-template-analyzer/scripts/validate_style_evaluation.py <template>/style-evaluation.json
```

OSS 本地预检：

```bash
pnpm style:finalize <batch>/模板数据 --dry-run
```

## 完成标准

- 分析档案使用 2.0 变换契约，每项变化都有授权或保留声明；
- 最终 JSON 只包含现有研发字段，`STYLE_REF` 和 `referenceImage` 只承担兼容语义；
- 运行请求只包含用户图和提示词，输出继承用户图横竖方向与宽高比；
- 运行提示词完整表达主体逐一对应、主体特征连续性、授权变换、标志性机制和越权内容边界；
- 真实验收覆盖至少四类输入，每个案例和总体平均分都达到 90，六个维度无短板且无硬失败；
- 上传、生成测试和独立复核的实际执行情况如实报告。
