# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## Unreleased

### Added

- `scripts/new_skill.py`：自包含的技能脚手架（仅用标准库），不再依赖 Codex 的 `skill-creator`。
- `scripts/validate_skill.py`：离线规范校验（名称与目录一致、description 长度与字符、`allowed-tools` 形状、遗留 `[TODO:]`、断掉的 reference 链接）。没有 `gh` 也能校验。
- `assets/trigger-eval-queries.json`：触发评测用例集（20 条），含标签、判定结果与本次发现的已知缺口。
- `references/publish-github.md`：新增「更新已发布的技能」流程（换 tag、版本策略、`--pin` 锁版本）。
- `.github/workflows/validate.yml`：push / PR 时自动跑发布前扫描，并在可用时用 `gh skill publish --dry-run` 校验规范。

### Changed

- `SKILL.md`：第 2 步改为优先使用技能自带的初始化脚本。
- `SKILL.md`：**description 按触发自测结果收紧**——删掉 `install a skill from a repo`（与 `skill-installer` 职责重叠，实测误吃安装类请求），`publish it to GitHub` 收窄为 `publish that skill to GitHub`，并去掉过于宽泛的兜底从句。
- `SKILL.md`：闸门边界写死——允许写 `.gitignore` / `git init` / `git status`，禁止 `git add` / `git commit` / 建 remote / 上传，直到用户确认；第 6 步明确标注「停下等待」。
- `SKILL.md`：澄清 `--path` 是父目录、`agents/` 由脚手架自动创建、脚本支持绝对路径调用。
- `SKILL.md`：新增 `gh` 未安装时的分支；第 9 步补上「停在闸门处」的汇报方式。
- `SKILL.md`：触发自测改为可执行——无法开启第二个会话时必须标注「未执行」，不得声称已验证。
- `references/stage-prompts.md`：删除「本机未安装 gh」这类把易变机器状态写成既成事实的断言；说明 P0 与 `SKILL.md` 两种执行纪律的优先级。

## 1.0.0 - 2026-10-10

### Added

- `make-skill-and-publish` 技能：从需求到发布的完整流程。
- `scripts/scan_publish_ready.py`：发布前扫描（密钥、私钥、PII、本机绝对路径、垃圾文件、大文件），命中值打码。
- `references/stage-prompts.md`：原始提示词摘录、比对结论与修订后的分阶段提示词模板。
- `references/publish-github.md`：gh 安装、认证、建仓、`gh skill publish` 与排错。
