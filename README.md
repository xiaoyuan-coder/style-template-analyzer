# style-template-analyzer

`style-template-analyzer` 是风格化模板生产 Skill 的独立源码仓库。仓库根目录同时也是 Skill 根目录，当前版本为 `4.5.0`。

## 目录职责

- `SKILL.md`：运行入口与完整生产流程。
- `references/`：合同、审美学习、评测与迁移规范。
- `contracts/`：正式 Schema 与模板包合同。
- `scripts/`：编译、校验、最终化、发布辅助与回归测试。
- `agents/`：Agent 配置。
- `docs/adr/`：与本 Skill 直接相关的架构决策。
- `skill-manifest.json`：版本和运行时文件清单。

## 开发与校验

```bash
corepack pnpm install --frozen-lockfile
corepack pnpm test
python /Users/xiaoyuan/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

单包校验可以使用：

```bash
corepack pnpm validate -- <模板包目录>
```

## 业务产出路由

本仓库只管理 Skill 源码、合同、测试和工程文档。业务产物继续写入工作总库的固定目录：

- 风格化模板生产：`../../05-风格化模板生产`
- 模板质量评测：`../../06-模板质量评测`
- 数据验收与上线：`../../07-数据验收与上线`

本地运行生成的临时文件可写入 `artifacts/`，该目录不进入 Git。

## 运行时副本

Codex 自动发现的运行时副本通常位于 `$CODEX_HOME/skills/style-template-analyzer`。研发与提交始终以本仓库为准；只有需要立即验证安装效果时，才把仓库版本同步到全局运行目录。全局副本不属于本仓库，也不参与提交。

## Git 边界

该目录拥有自己的 `.git` 和独立提交历史，不依赖原 `memebuy-skills` 仓库。默认不提交业务产物、凭据、OSS 密钥、个人覆盖数据或预发布临时目录；远端由维护者单独配置。
