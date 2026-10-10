# 发布到 GitHub：命令与排错

读这个文件当你要「建仓 / 推送 / 发版」时。命令以官方手册为准，`gh skill` 系列仍是 **preview**，
不同版本可能有差异。

---

## 一、前置条件

需要两个工具：`git` 和 GitHub CLI `gh`。

```powershell
git --version
gh --version
```

没有 `gh` 时，按平台安装（Windows 优先 winget）：

```powershell
# Windows
winget install --id GitHub.cli
# 或：scoop install gh
```

```bash
# macOS
brew install gh
# Debian/Ubuntu
sudo apt install gh
# Fedora
sudo dnf install gh
```

> 装完要**新开一个终端**，让 `PATH` 生效，再运行 `gh --version` 确认。

---

## 二、认证（这一步必须由用户本人完成）

先做只读检查：

```bash
gh auth status
```

未登录时启动：

```bash
gh auth login
# 依次选择：GitHub.com -> HTTPS -> 浏览器登录 -> 允许 gh 配置 git 凭据
```

- 默认就是**浏览器流程**，token 存在系统凭据库里；
- 需要账号密码、验证码、2FA 或浏览器授权时**暂停，交给用户本人**；
- **不要**让用户把密码或 Token 发到对话里，也不要把它写进文件、命令或环境变量；
- 登录后如果 git 仍要密码，运行 `gh auth setup-git` 让 gh 充当 git 的凭据助手；
- 喜欢 SSH 的话用 `gh auth login --git-protocol ssh`；
- 需要用现成 Token 的场景（自动化）才用 `--with-token` 从标准输入读，最小 scope 为 `repo, read:org, gist`。

`gh auth status` 会显示实际登录的账号与生效的 scope，发布前务必确认账号正确。

---

## 三、仓库结构

```text
<repo>/
|-- README.md           # 一份，放仓库根目录
|-- LICENSE             # 可选
|-- .gitignore
`-- skills/
    `-- <skill-name>/
        |-- SKILL.md
        |-- agents/openai.yaml
        |-- references/
        `-- scripts/
```

`.gitignore` 起步模板：

```gitignore
# 操作系统 / 编辑器
.DS_Store
Thumbs.db
desktop.ini
*.swp
*~

# 日志与临时文件
*.log
*.tmp
*.bak
*.orig
*.rej

# Python
__pycache__/
*.py[cod]
.venv/
venv/
.env
.env.*

# Node（只有在技能里带 JS 时需要）
node_modules/

# 本地草稿
/scratch/
/work/
```

---

## 四、建仓并推送

```bash
git init -b main
git add -A
git commit -m "Add <skill-name> skill"

# 建远端 + 推送（三选一）
gh repo create <repo-name> --public --source . --remote origin --push --description "<一句话描述>"
gh repo create <owner>/<repo-name> --public --source . --remote origin --push
gh repo create <repo-name> --private --source . --remote origin --push
```

常用参数：`--public` / `--private` / `--internal`、`--source <dir>`、`--push`、
`--remote <name>`、`--description <string>`、`--license <spdx>`、`--add-readme`、`--clone`。

> 只想建空仓库、稍后再推：去掉 `--source` 与 `--push`。

---

## 五、按规范校验并发版：`gh skill publish`

它做的事：**校验**本地仓库里的技能是否符合 Agent Skills 规范，然后**创建 GitHub Release** 来发布，
这样别人可以 `gh skill install` 安装。

```bash
gh skill publish --dry-run          # 只校验，不发布
gh skill publish                    # 交互式：加 topic、选 tag、建 release
gh skill publish --tag v1.0.0       # 非交互，指定 tag（建议语义化版本）
gh skill publish --fix              # 只自动修（如剔除安装元数据），不发布
```

**技能发现规则**（放对位置才会被发现）：

```text
skills/*/SKILL.md
skills/{scope}/*/SKILL.md
*/SKILL.md            （仓库根目录一级）
plugins/{scope}/skills/*/SKILL.md
```

**校验内容**：

- 技能名符合 agentskills.io 的严格命名规则；
- 技能名与所在目录名一致；
- 必需的 frontmatter 字段（`name`、`description`）存在；
- `allowed-tools` 是字符串而不是数组；
- 若存在安装元数据（`metadata.github-*`）会被剥离。

交互式发布会引导你：给仓库加 `agent-skills` topic、选版本 tag、用自动生成的说明创建 release。

---

## 六、验证与安装

```bash
gh repo view --web                 # 打开仓库确认内容
git ls-remote --tags origin        # 确认 tag 已推送
gh release view --web              # 确认 release 与说明

# 别人怎么装
gh skill search <keyword>
gh skill install <owner>/<repo> <skill-name>
gh skill install github/awesome-copilot documentation-writer   # 官方示例
gh skill update                    # 更新已安装技能
```

在 Codex 里也可以用 `$skill-installer` 从 GitHub 仓库/目录 URL 安装（支持私有仓库）。

---

## 七、排错

| 现象 | 原因与处理 |
|---|---|
| `gh: command not found` | 未安装或 `PATH` 未刷新；装完新开终端 |
| `gh auth status` 显示未登录 | 运行 `gh auth login`，走浏览器流程；用户本人操作 |
| 推送 403 / permission denied | 登录账号或 scope 不对；`gh auth status` 核对，必要时 `gh auth refresh -s repo` |
| `remote origin already exists` | 去掉 `--remote`，或 `git remote set-url origin <url>` |
| 仓库名已被占用 | 换名字，或用 `--source .` 配合 `gh repo create <owner>/<name>` |
| `gh skill publish` 报找不到技能 | 文件没放对位置；放到 `skills/<name>/SKILL.md` |
| 校验失败：名称不一致 | 目录名与 frontmatter `name` 必须完全相同 |
| 校验失败：description | 不能包含 `<` 或 `>`，且不超过 1024 字符 |
| 校验失败：allowed-tools | 必须是空格分隔的字符串，不能写成 YAML 列表 |
| 推送体积过大 | 先看扫描结果里的大文件；补进 `.gitignore` 后重新提交 |
| 默认分支不是 main | 用 `git init -b main`；已建仓可 `git branch -M main` |
| 想把仓库设为私有 | `gh repo create ... --private`，或建后在网页改可见性 |
