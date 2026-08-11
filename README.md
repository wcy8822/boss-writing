# boss-writing

[![tests](https://github.com/wcy8822/boss-writing/actions/workflows/tests.yml/badge.svg)](https://github.com/wcy8822/boss-writing/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**让 AI 写出的中文汇报材料，能直接在会上讲出口——并且越用越准。**

一份可直接装进 Claude Code 的写作规范（Agent Skill），管的是「句子怎么写」：季度规划、区域汇报、项目复盘、周报、立项、PPT 母稿、演讲稿、管理层简报。

它不是一份死文档。每一次「这句不行、改成那样」都会被记下来，下次自动提示。

---

## 解决什么问题

用 AI 写汇报材料，产出通常掉进两个坑：

- 往上飘：满篇「赋能、闭环、抓手、护城河」，听完记不住一件事；
- 往下滑：为了「说人话」滑成大白话，把事说小了，失去专业性。

两者是同一个病——**没想清楚这句话到底在说什么事**。改到最后往往还是自己重写一遍。

更麻烦的是第三件事：**改过的毛病会再犯**。这轮说清楚了「别用『愿不愿用』这种考核口气」，下一份材料、换个人写，它又回来了。

## 提供什么

### 一、写作规范（`SKILL.md`）

| 内容 | 说明 |
|---|---|
| 八条核心方法 | 标题即观点、不是A而是B、数字带解读、诚实分层、落到可执行动词等 |
| 四段论证结构 | 讲一件事默认套「解决什么问题 → 提供什么 → 相对优势 → 当前进展」 |
| 去术语 + 画面感测试 | 术语与口语双向黑名单；判据是「句子里的名词，听的人脑子里能不能浮现出东西」 |
| 归责闸门 | 把问题归给流程和工具，不归给人——对一线团队讲话尤其重要 |
| 事实纪律 | 团队构成、目标数字、组织关系等信息，AI 一律不许自填 |

### 二、会长大的学习内核（`tools/business_language.py`）

```
采集 → 识别业务表达 → 保留来源 → 辅助写作 → 分级检查 → 收集反馈 → 更新词包、案例与作者偏好
```

七个命令：`route`（自动选词包）、`lint`（影子检查）、`knowledge-query`（检索已确认知识）、`learn`（记录反馈事件）、`ingest`（语料抽候选）、`sanitize`（一致性脱敏）、`blind-packet`（多模型匿名评测）。

四份随用随长的资产：通用语言包、业务词包、作者偏好档案、正反案例库。

**状态流转是命门**：`candidate → supported → pending_confirmation → approved`。只有人确认过的才能转正——聊天里说得最多的词，往往正是最没被推敲过的词。

### 三、两套 HTML 汇报模板（`visual/`）

季度汇报版式，暖色版与清新版，纯 CSS 交互（无 JS 依赖）。正文是虚构示例，替换即用。

## 相对现状的优势

跟「直接让 AI 改一遍」比：

- **改写有边界**——成熟句子默认不动，删改必须能指出原句的问题；
- **事实有闸门**——量化词逐个回原文核算，AI 自行补的因果会被拦下；
- **听感有检查**——问题对事不对人，朗读讲不出口就不要；
- **教训能累积**——反馈事件带听众、场合和原因一起存，不同场景下的冲突偏好并存而不互相覆盖。

跟「自己重写一遍」比：起草仍归人，模型只做局部精进。自己写会求稳，怕编造就不敢加解读，写出的是「不犯错的 60 分稿」；模型没有这个包袱，敢往前推一步——其中一部分越界，另一部分正是自己不敢写的那句。

## 当前进展与边界

在季度规划、区域汇报、周报三类材料上跑过多轮，材料评分从 60 提到 85。20 个单测覆盖路由、检查、脱敏、反馈与隐私闸门。

**明确说清楚三条边界，别误解它的能力：**

1. **不联网**。全包零联网代码，设计上就不联网。`ingest` 的输入是你准备好的 JSONL，采集器由调用端提供。
2. **外部写作资料通道是半成品**。`--kind external` 只做到了命名空间隔离和「禁止转正」标记；抽取逻辑与内部采集共用同一套业务名词正则，**抽不出「这段为什么写得好」**。要真正做到，得先定义「一条写作技巧」的结构化字段。
3. **知识检索是关键词匹配**，不是语义检索。没命中会明确返回未命中，不会编。

视觉模板中的「顶部阅读进度条」一条尚未实现（`VISUAL-STANDARD.md` 已注明）。

---

## 安装

```bash
git clone <本仓库> ~/.claude/skills/boss-writing
```

或直接把整个目录放进 `~/.claude/skills/`（项目级放 `.claude/skills/`）。

装好后说「写汇报」「改写这段材料」「说人话」「给老板看」即可触发。

依赖：Python 3.9+ 与 PyYAML（只有学习内核需要；两个校验脚本零依赖）。

```bash
pip install pyyaml
python3 -m pytest tests/ -q      # 20 passed
```

## 首次使用先做五件事

1. **建你自己的业务词包**——复制 `language-packs/example-domain.yaml`。**特别是把名字里带禁词的产品名登记进去**（`type: product` + `approved`），否则模型会擅自给你的产品改名。
2. **建作者档案**——复制 `profiles/example.yaml`，让它随反馈长大。
3. **补术语表**——`tools/style-lint.py` 的 `TERMS`，按你团队的技术栈增删。表里没有的内部黑话（自研系统名、平台名、项目代号）才是最该加的。
4. **调禁词表**——`tools/rewrite-check.py` 的 `BAN_JARGON` 与 `WHITELIST`。
5. **换品牌色**——两个 HTML 模板 CSS 顶部的 `--orange-*` 一组是占位色。

如果你打算往里存聊天语料，**装上 pre-commit 闸门**：

```bash
echo 'python3 tools/check_local_privacy.py || exit 1' >> .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

它拦住四类东西进版本库：本地私密路径、聊天扫描产物文件名、含 `content/source/speaker/timestamp` 结构的文件、标了 `privacy: local_only` 的内容。

> ⚠️ 这个闸门只管 git 暂存区，**管不了「打包整个目录发出去」**。对外分发前手动确认 `.runtime/` 与 `references/sources.local.yaml` 不在包里。

## 目录

```
SKILL.md                        写什么、怎么写（主文档）
tools/
  style-lint.py                 句长 / 并列过载 / 术语命中 / 归责表达
  rewrite-check.py              改写稿验收：数字增删 / 禁词 / 篇幅 / SMART 覆盖
  business_language.py          学习内核（七个子命令）
  check_local_privacy.py        pre-commit 隐私闸门
  smart-polish-prompt.md        交给模型润色时的 prompt 模板
language-packs/
  common.yaml                   通用写作语言包
  example-domain.yaml           业务词包模板
profiles/example.yaml           作者偏好档案模板
cases/example.yaml              正反案例库模板
references/
  DESIGN.md                     学习内核的需求、边界与验收标准
  sources.example.yaml          采集来源配置模板
tests/                          20 个单测
.github/workflows/tests.yml     CI：3.9 / 3.11 / 3.12 三个版本跑测试
visual/
  VISUAL-STANDARD.md            HTML 汇报材料八条视觉规格
  template-warm.html            暖色版模板
  template-fresh.html           清新版模板
  ORIGINAL-STANDARD-v6.2.md     视觉标准的原始出处
```

## 常用命令

```bash
# 文风机检
python3 tools/style-lint.py draft.md

# 改写稿验收（基准原文 vs 一到多个候选）
python3 tools/rewrite-check.py origin.md cand-1.md cand-2.md

# 影子检查（分级提示，不阻断）
python3 tools/business_language.py lint draft.md --report report.json

# 记录一次反馈 —— 这一步不做，学习闭环就是断的
python3 tools/business_language.py learn \
  --before "共同承诺" --after "一起把这件事做成" \
  --reason "对合作团队有压力" --audience region --material-type speech
```

**机检只证明格式与事实纪律，不证明听感。** 量化词、越界解读、全局矛盾三项必须人工过一遍，判据见 `SKILL.md` §八。

## 说明

- 文中所有示例、数字、业务场景、词包内容均为虚构，仅用于演示。
- 两个 HTML 模板的正文是示例材料，使用时整段替换。

## 参与贡献

最有价值的 PR 往往是几行 YAML——一条真实的改稿案例，比抽象规则有用得多。
详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

⛔ **提交前请确认改动里没有你公司的真实姓名、内部系统名、未公开业务数据或聊天记录。**

## 许可证

[Apache License 2.0](LICENSE) · Copyright 2026 wcy8822

若本项目被认定为职务成果，版权归属可能属于所属单位。对外公开发布前请按所在单位的开源合规流程确认，必要时更新 `LICENSE` 与 `NOTICE` 中的版权人。
