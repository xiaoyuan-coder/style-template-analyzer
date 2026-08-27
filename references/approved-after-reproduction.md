# Approved After 复现合同

人工通过针对的是一个具体视觉 revision。通过后，Approved After 是该 revision 的最高视觉权威；候选命名、机制说明和默认保真规则只承担解释与兜底。最终 `promptTemplate` 必须能够在只输入用户图时复现 Approved After 的可迁移视觉关系。

## 两类复现

- **原始回放**：使用生成 Approved After 时的原始 Before 与最终 `promptTemplate`，验证视觉 revision 是否能被运行数据重现。
- **换图迁移**：使用新的高认知测试图与同一 `promptTemplate`，验证机制是否跨内容成立。

原始回放和换图迁移都不得把 Approved After、候选封面、GoodCase 或其他离线图片传给生成模型。随机生成无法保证像素相同；验收目标是边界决定、模板常量、构图比例和标志性机制稳定重现。

## 权威顺序

1. 人工通过的 After 及其明确反馈；
2. 与该 After 同次生成并实际提交的最终运行提示词；
3. `effect-reproduction-contract.json` 中已消解的边界决定；
4. Before 中仍需保留的身份与来源关系；
5. 通用默认保真规则。

上层证据与下层默认冲突时，上层决定覆盖下层。覆盖必须进入复现合同，并在 `promptTemplate` 中转写为具体的可视化指令，不得依赖模型自行猜测。

## 十四项边界

每个 revision 对以下维度逐项选择模式、记录 After 证据，并给出一条不超过 120 字、可直接提交给图像模型的 `promptDirective`：

| 维度 | 需要决定的边界 |
| --- | --- |
| `subject-selection` | 全部显著主体、主主体或最小识别锚点 |
| `identity-and-recognition` | 完整身份、识别锚点或主体形态变换 |
| `base-instance-count` | 基础实例保持、来源派生重复或模板固定重复 |
| `pose-and-view` | 保持、来源派生或模板指定动作/视角 |
| `frame-orientation-and-aspect` | 继承源图、自适应重定画幅或模板固定画幅 |
| `crop-and-unseen-completion` | 保持可见裁切、自适应裁切、保守补全或模板指定补全 |
| `subject-scale-and-placement` | 保持、范围自适应或模板指定比例与位置 |
| `environment` | 保持、简化、移除、替换或重建 |
| `composition` | 保持、来源重组或模板固定构图 |
| `occlusion-and-depth` | 保持、来源派生或模板指定遮挡与景深关系 |
| `palette` | 保持源色、保留少量源色锚点或使用模板色盘 |
| `detail-and-abstraction` | 保持、简化、半抽象或抽象主导 |
| `geometry-and-proportion` | 保持、来源派生或模板指定几何比例 |
| `text-symbols-and-fixed-objects` | 只保留来源、移除或只允许模板常量 |

`unresolvedConflicts` 必须为空。Approved After 已经改变画幅、动作、裁切或环境时，复现合同不能继续声明对应维度为 `preserve` 或 `inherit-source`。

## 模板常量

跨输入稳定出现的构图骨架、遮挡关系、流带、影池、分格、容器、固定重复数量和材质转折属于模板常量。每项声明：

- `sourceBinding`：`fixed`、`adaptive` 或 `conditional`；
- 是否每次必现；
- 在 Approved After 中的证据；
- 写入运行提示词的精确指令。

模板常量可以独立于源图物象存在。案例人物、场景故事、品牌和偶发生成瑕疵继续进入禁迁移清单。

## 提示词同一性门禁

`effect-reproduction-contract.json` 是审计层，`promptTemplate` 是运行层。运行层按 `runtime-prompt-authoring-standard.md` 的九段结构组织。`promptDirective` 先编译为必现机关、空间骨架、内容映射、视觉风格或完成判据，再进入对应段落；同义重复只保留一次，冲突指令在编译前消解。

运行提示词禁止出现 `promptDirective`、“Approved After”、“复现合同”、“复现边界”、“来源绑定”、“边界策略”、“前文”等内部或悬空指代语言。画风标签必须展开为颜色、线条、材质、明暗和构图表现，不得只写内部分类名。

历史提示词重编译还必须通过通用性门禁：Before 中的案例人物、物种、道具、服装和场景只能用于识别视觉职责，不得作为新输入必备物象写入正向段落。编译时把它们改写为主主体、主识别区域、关联轮廓、接触部位、承托面、方向线索、高光切点等来源角色；形状、方向、数量、间距和接触点均从用户图实际可见内容推导。核心机关依赖的必选角色需要明确替代策略；只有不影响核心效果的辅助角色可以省略。同义长句只保留一次。

审核封面必须由审核包内最终 `promptTemplate` 原样生成。封面生成回执 2.0.0 同时冻结：

- 实际提交的 prompt SHA-256；
- 唯一用户源图 SHA-256；
- 图片输入数量固定为 1；
- Approved After 未作为生成输入。

这四项与模板、测试图和复现合同任一不一致时，revision 停留在“视觉已选、运行待复现”，不得进入人工 Pass、动态基线或正式化。

## 精确视觉 revision 绑定

用户通过附件选择首版、retry、replacement 或总览外候选时，先对所有候选计算解码后 RGBA 像素哈希。附件与候选允许文件 SHA 不同；宽高、颜色通道和逐像素内容一致时视为同一视觉 revision。

批准专用编译规格使用 `contracts/approved-variant-binding.schema.json`，每项冻结：

- `selectedVariant` 与版本处置说明；
- cover 文件 SHA 和解码像素 SHA；
- 实际生成该 cover 的 `generationPromptSha256`；
- 最终 `promptSha256`、源图 SHA 和效果合同 SHA；
- 该视觉 revision 专属的 X/Y/B/C。

`generationPromptSha256` 必须等于最终运行 Prompt SHA。用户选中旧视觉 revision 时，恢复该 revision 的真实生成提示词，重新生成或重新闭合证据，再记录 Pass。文件名、候选序号、当前最新 revision 和总览位置只用于检索，像素与哈希合同承担最终身份判断。

独立测试产物可用下列命令把合同草案与实际源图、生成图和最终模板绑定：

```bash
python scripts/style_effect_contract.py \
  effect-reproduction-contract.draft.json style-template.json \
  source.png generated.png effect-reproduction-contract.json \
  --source-asset-id <asset-id>
```

## 完成门槛

1. 复现合同十四项边界完整且无冲突；
2. 所有 `promptDirective` 与必现模板常量进入 `promptTemplate` 的对应运行段落，合同证据文本和内部字段名不进入 prompt；
3. 生成回执证明实际提交的 prompt 与入库 prompt 同 SHA；
4. 原始回放重现 Approved After 的核心构图、材质和视觉机关；
5. 换图迁移继续重现同一机制，且身份与授权边界通过；
6. 人工通过冻结同一封面文件 SHA、解码像素 SHA、生成 Prompt SHA、运行 Prompt SHA、源图 SHA 与合同 SHA。

任一项缺失时，当前 revision 继续返工。已通过的 5.x 历史包保持只读证据；进入新 revision 时必须升级到本合同。

## 历史通过包审计

对统一通过目录运行 `scripts/audit_approved_after_gate.py`。审计只读取活动 revision，排除已退役 key，并按原生产批次输出三类迁移状态：

- `blocked-evidence-recovery`：Before、After、人工通过回执或哈希链缺失；
- `known-boundary-or-prompt-drift`：已发现正式 prompt 漂移、After 哈希漂移或画幅边界冲突；
- `replay-and-contract-migration-required`：证据可恢复，仍需 v2 生成回执、十四项合同、原图回放和换图迁移。

历史人工通过事实继续保留。新门禁审计只决定是否可直接复现与进入新 revision，不自动退役、不覆盖正式包。

重编译器不得把先前自动重编译产生的 prompt 当作新的语义权威。存在 `prompt-recompilation-receipt.json` 时，沿 `fromRevision` 回溯到最后一个没有该回执的人工视觉 revision，并记录 `semanticSourceRevision` 与完整 lineage。Approved Before→After 的可见证据高于历史提示词；旧提示词描述了 After 中没有出现的结构机关时，先做证据校准，再编译新 revision。图形语言只承载颜色、线条、材质、纹理和明暗；空间语法、固定布局、实例派生、尺度跳变、路径、遮挡和边界穿插必须进入“核心效果”“空间结构”或“内容映射”。结构操作只出现在“视觉风格”时门禁失败。

活动包完成证据恢复后，先用 `--stage` 写入隔离候选目录。静态九段结构、空间蓝图、来源角色、无内部语言、无案例依赖词、无重复长句和 Schema 校验全部通过后，才能进入真实回放。原始 Before 回放与两张互不相同的换图迁移均达到 95 分，并逐项确认必现机关后，构建哈希绑定的回放报告，再使用 `--apply --replay-report` 写入递增 revision 与下游交付 JSON：

```bash
python scripts/recompile_approved_runtime_prompts.py \
  <统一通过模板索引.json> <audit-results.json> \
  --formal-root <已通过正式模板包> \
  --migration-source-root <证据恢复目录> \
  --run-root <批次目录> \
  --delivery-root <待导入交付目录> \
  --stage

python scripts/build_prompt_replay_report.py \
  <批次目录>/candidates <人工视觉评分.json> <prompt-replay-report.json>

python scripts/recompile_approved_runtime_prompts.py \
  <统一通过模板索引.json> <audit-results.json> \
  --formal-root <已通过正式模板包> \
  --migration-source-root <证据恢复目录> \
  --run-root <正式发布记录目录> \
  --delivery-root <待导入交付目录> \
  --apply --replay-report <prompt-replay-report.json>
```
