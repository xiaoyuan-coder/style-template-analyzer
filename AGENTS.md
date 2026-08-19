# AGENTS.md

## 仓库定位

本仓库是 `style-template-analyzer` 的独立版本管理源，仓库根目录同时是 Skill 根目录。处理本 Skill 的研发、测试、文档或提交任务时，必须优先读取仓库内 `SKILL.md` 及其引用文件，不使用同名全局副本替代当前工作版本。

## 写入边界

- Skill 源码、合同、脚本、测试、ADR 和工程说明写入本仓库。
- 风格化模板业务产物写入总库相对目录 `../../05-风格化模板生产`。
- 评测标准、测试集和正式评测报告写入 `../../06-模板质量评测`。
- UAT、待导入数据、人工验收和上线记录写入 `../../07-数据验收与上线`。
- 仓库内 `artifacts/` 仅用于本地临时产物，默认不提交。
- 密钥、Token、密码、个人覆盖数据与预发布临时目录禁止提交。

## Skill 维护

- 修改行为、Schema、命令、输出文件或用户可见规则时，同步更新 `skill-manifest.json` 的版本号、更新时间和文件清单。
- 正式交接物必须声明 `artifactType`、`schemaVersion` 和 `producer`；保持官方业务 JSON 形状时，使用相邻 `artifact-manifest.json` 承载内部元数据。
- 删除字段、字段改名或改变字段语义时递增 Schema `MAJOR`；新增向后兼容的可选字段时递增 `MINOR`；不改变兼容性的修正递增 `PATCH`。
- 研发与提交以仓库副本为准。只有用户明确要求验证全局安装效果时，才同步到 `$CODEX_HOME/skills/style-template-analyzer`。

## 完成检查

提交前至少运行：

```bash
corepack pnpm test
python /Users/xiaoyuan/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
git status --short
git diff --check
```

如修改正式合同或交接 Schema，还需运行对应合同测试和完整回归测试，并核对生产方、消费方兼容声明及 manifest。

## Git

- 未经用户明确要求，不主动提交、创建 Tag 或推送。
- 用户要求提交时使用 Conventional Commits，主题优先使用中文。
- 一次提交聚焦单一主题，业务产物与 Skill 源码分开处理。
- 配置远端前先执行 `git remote -v`；推送前必须再次确认目标远端。
