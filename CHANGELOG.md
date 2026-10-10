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
- `tests/test_skill_scripts.py`：45 条回归测试（仅标准库），把下面每个修复点都固化下来，含一条扫描耗时上限以拦住 O(n²) 回溯回归。在仓库根目录运行 `python -m unittest discover -s tests`。

### Changed

- `SKILL.md`：第 2 步改为优先使用技能自带的初始化脚本。
- `SKILL.md`：**description 按触发自测结果收紧**——删掉 `install a skill from a repo`（与 `skill-installer` 职责重叠，实测误吃安装类请求），`publish it to GitHub` 收窄为 `publish that skill to GitHub`，并去掉过于宽泛的兜底从句。
- `SKILL.md`：闸门边界写死——允许写 `.gitignore` / `git init` / `git status`，禁止 `git add` / `git commit` / 建 remote / 上传，直到用户确认；第 6 步明确标注「停下等待」。
- `SKILL.md`：澄清 `--path` 是父目录、`agents/` 由脚手架自动创建、脚本支持绝对路径调用。
- `SKILL.md`：新增 `gh` 未安装时的分支；第 9 步补上「停在闸门处」的汇报方式。
- `SKILL.md`：触发自测改为可执行——无法开启第二个会话时必须标注「未执行」，不得声称已验证。
- `references/stage-prompts.md`：删除「本机未安装 gh」这类把易变机器状态写成既成事实的断言；说明 P0 与 `SKILL.md` 两种执行纪律的优先级。

### Fixed

- `scripts/scan_publish_ready.py`：**修掉一个静默漏报**——超过 2 MB 的文件内容完全不扫，却不留任何记录，于是「报告干净」可能是在描述一个从未读过的文件。现在 `--max-file-mb` 是唯一上限，超出者额外报 `content-not-scanned`（MEDIUM，默认闸门放行，`--fail-on medium` 拦截）。
- `scripts/scan_publish_ready.py`：**修掉灾难性回溯**。两条 `generic-secret` 规则带的多余 `[\w.\-]*` 前缀让开销变成 O(n²)：单行 8 KB 就要约 3 秒，原来那个 2 MB「上限」根本保护不了任何真实文件——压缩过的 JS 或单行 JSON 在远低于 2 MB 时就已卡死。前缀本就冗余（可匹配 0 字符，且只读第 1 组），已删除，并用 6 万条随机输入验证与原行为完全等价。`email-address` 同样按 RFC 长度加上界。
- `scripts/scan_publish_ready.py`：`windows-user-path` 存在**假阴性**。`[A-Za-z]:\\` 已吃掉盘符后的反斜杠，而分支却要求 `\Users\`/`\AppData\` 等必须带前导反斜杠，导致 `<盘符>:\Users\<名字>` 这一最常见形态完全不匹配，只在更深层路径（如 `…\Users\bob\Documents\x`）才命中。分隔符改为可选。
- `scripts/scan_publish_ready.py`：修掉 `--exclude` 传目录名无效（只有 `dir/*` 生效），以及根目录传 `.` 时每条 finding 被加上多余前导斜杠（`/k.pem`）。
- `scripts/validate_skill.py`：**发现规则补齐到 `gh` 实测的 6 种**。原实现只认 3 种，对 `*/SKILL.md`、`{prefix}/skills/*/SKILL.md`、`{prefix}/skills/{scope}/*/SKILL.md`、`plugins/*/skills/*/SKILL.md` 一律报 `no SKILL.md found` 并退出 2——即对一个 `gh skill publish` 能正常发布与安装的仓库误判失败。
- `scripts/validate_skill.py`：修掉两处**误报**——未知 frontmatter 键（如 `version:`）降为 warning（`gh` 接受它），YAML 折叠标量 `description: >` 不再把 `>` 当内容而报出假的「不能包含 `<` 或 `>`」。
- `scripts/validate_skill.py`：`[TODO: ...]` 检查补上 frontmatter。原实现只查正文，于是 `new_skill.py` 写进 `description` 的占位符（决定技能会不会被调用的那个字段）能一路通过离线校验和 `gh`，直接被发布出去。
- `scripts/validate_skill.py`：BOM 报错改为可行动（原来只说「必须以 `---` 开头」，可文件明明就是）；`gh` 同样拒绝 BOM，但报的是「缺少 name」，更误导。
- `scripts/new_skill.py`：`--resources scripts,scripts` 不再抛未捕获的 `FileExistsError`；创建中途失败会整体回滚，不再留下半个技能目录（原先重试会撞上 `target already exists` 而卡死）。`--path` 指向文件时给出干净的报错而非 traceback。
- `SKILL.md`、`references/publish-github.md`：技能发现规则由 4 条订正为实测的 6 条（`gh skill publish --help` 漏了 `{prefix}/skills/...` 两条，其报错信息里才是全的）。


### Added

- `make-skill-and-publish` 技能：从需求到发布的完整流程。
- `scripts/scan_publish_ready.py`：发布前扫描（密钥、私钥、PII、本机绝对路径、垃圾文件、大文件），命中值打码。
- `references/stage-prompts.md`：原始提示词摘录、比对结论与修订后的分阶段提示词模板。
- `references/publish-github.md`：gh 安装、认证、建仓、`gh skill publish` 与排错。
