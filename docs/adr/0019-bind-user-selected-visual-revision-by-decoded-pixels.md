# ADR 0019：按解码像素绑定用户选中的视觉 revision

## 状态

Accepted，2026-08-27。

## 背景

用户附件可能来自首版、retry、replacement、总览副本或经过重新编码的 PNG。同一像素内容可以具有不同文件 SHA；同 key 的不同候选也可能被现有“最新文件”逻辑折叠。由此会出现视觉选择、运行 Prompt 和正式交付错绑。

## 决策

1. 附件与候选使用宽高、RGBA 模式和解码像素内容计算稳定哈希。
2. 批准专用编译规格同时冻结文件 SHA、像素 SHA、实际生成 Prompt SHA、最终 Prompt SHA、源图 SHA、效果合同 SHA 和版本专属 X/Y/B/C。
3. `generationPromptSha256` 必须等于最终 `promptSha256`。
4. 选择旧视觉 revision 时恢复其真实 Prompt，并重新闭合生成证据后再记录 Pass。
5. 文件名、索引和“当前最新”只参与检索。

## 后果

PNG 元数据和压缩差异不会造成误判；同 key 的多次生成保持独立。历史批准文件升级到新绑定合同时需要补充像素与生成 Prompt 证据。
