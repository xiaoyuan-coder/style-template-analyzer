# ADR 0018：Approved After 与运行提示词同源绑定

## 状态

Accepted，2026-08-26。

## 背景

历史自生产批次允许先用候选提示词生成视觉 After，再把机制说明扩写为另一份正式 `promptTemplate`。人工通过冻结了候选封面和正式 prompt 的两个 SHA，却没有证明该封面由该正式 prompt 生成。实测出现“Approved After 好看、入库 JSON 无法复现”的系统性断点。

默认保真合同还把源画幅、姿态、裁切和构图当作全局不变量。Approved After 已明确改变这些边界时，后续编译会覆盖人工实际通过的视觉 revision。

## 决定

1. manifest 6.0.0 的每个审核包新增 `effect-reproduction-contract.json`，逐项声明十四项变换边界和必现模板常量。
2. Approved After 进入人工 Pass 后成为该 revision 的最高视觉权威；默认保真规则只对复现合同未授权的内容生效。
3. 封面生成回执升级为 2.0.0，记录实际提交 prompt、唯一源图、输入数量和 Approved After 未参与运行输入。
4. 新审核包只有在封面、最终 prompt、测试图和复现合同四方 SHA 一致时才能进入人工 Pass。
5. 原始 Before 回放与随机换图迁移共同作为复现验证；像素随机性不作为失败，边界、构图比例、模板常量和标志性机制漂移作为失败。
6. 5.x 历史包保持只读兼容；任何返工 revision 使用 6.0.0 新合同。

## 影响

- 编译器和自生产 proposer 必须输出复现合同草案。
- 生成适配器必须回传实际提交 prompt 与图片输入证据。
- 画幅、姿态、裁切、补全、主体比例、环境和模板固定结构可以在有 Approved After 证据时覆盖默认保真规则。
- 只有候选封面、缺少同 prompt 回放证据的存量模板需要新 revision，不能继续以原 Pass 证明运行能力。
