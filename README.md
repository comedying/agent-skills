# agent-skills

一组可安装、可复用的 Agent Skill。

## 解决什么问题

很多"我希望 AI 每次都这么做"的经验，只存在于一次性的对话里，下次还得重新解释一遍。
把这类经验固化成技能，就能跨会话复用。

本仓库第一个技能 `make-skill-and-publish` 更进一步：把一句自然语言需求，一路做到
**符合 Agent Skills 规范、可直接发布到 GitHub** 的成品技能。

## 主要功能

**`make-skill-and-publish`** —— 从需求到发布的全流程

- 把需求/文档/截图整理成技能规格（名称、用途、输入输出、边界、约束），有歧义先问，不猜。
- 按官方规范生成并校验技能：`name` 与目录一致、`description` 写成"何时使用"、正文精简并做渐进披露。
- 用一个真实例子自测，而不是只描述结果。
- **发布前扫描**：检查密钥、私钥、Token、个人隐私、本机绝对路径、临时文件、测试垃圾与大文件；
  命中值自动打码，输出可直接贴出来。
- 提交与发布：`gh repo create ... --push` 建仓推送，`gh skill publish` 按规范校验并创建 Release。

技能内置的安全边界：**不接触任何凭据**（不索要、不回显、不写入文件），
遇到浏览器授权/验证码/2FA 一律暂停交回本人；发布动作前必须先报告扫描结果并等确认。

## 仓库结构

```text
agent-skills/
|-- README.md
├── LICENSE
├── .gitignore
└── skills/
    └── make-skill-and-publish/
        ├── SKILL.md
        ├── agents/openai.yaml
        ├── references/
        │   ├── stage-prompts.md       # 分阶段提示词模板（含一键版）
        │   └── publish-github.md      # gh 安装/认证/建仓/发版与排错
        └── scripts/
            └── scan_publish_ready.py  # 发布前扫描（可当 CI 闸门）
```

## 安装方法

方式一，GitHub CLI：

```bash
gh skill install comedying/agent-skills make-skill-and-publish
```

方式二，Codex 内用 `$skill-installer`：

```text
$skill-installer install https://github.com/comedying/agent-skills/tree/main/skills/make-skill-and-publish
```

方式三，手动：

```bash
git clone https://github.com/comedying/agent-skills.git
# 把 skills/make-skill-and-publish 复制到 ~/.codex/skills/（Windows: %USERPROFILE%\.codex\skills\）
```

装完重启 Codex 即可生效。

## 使用方法

在 Codex 里直接调用，或贴需求让它接管：

```text
$make-skill-and-publish 我想让 AI 把我的会议纪要自动整理成行动项清单，做成技能并发到 GitHub。
```

只想用其中一段（例如只做"发布前检查"）可以复制 `references/stage-prompts.md` 里的对应模板。

单独跑发布前扫描：

```bash
python skills/make-skill-and-publish/scripts/scan_publish_ready.py <目标目录>
python skills/make-skill-and-publish/scripts/scan_publish_ready.py <目标目录> --json --fail-on medium
```

它会返回非零退出码（默认遇到 HIGH 即失败），可以直接挂到 CI 或 pre-commit 上。

## 输入输出示例

输入（一句话需求）：

```text
把我们团队的代码评审清单做成一个技能，让 AI 每次 review 都按这个清单走，并发布到 GitHub。
```

输出（目录结构）：

```text
my-skills/
├── README.md
└── skills/
    └── team-code-review/
        ├── SKILL.md              # 含"何时使用"的 description 与评审流程/清单
        ├── agents/openai.yaml
        └── references/
            └── checklist.md
```

并附带：扫描报告（无 HIGH）、本地 git 提交、GitHub 仓库地址与 Release 链接。

## 许可

MIT，见 [LICENSE](LICENSE)。
