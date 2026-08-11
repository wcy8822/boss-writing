# 参与贡献

这个包的价值不在代码，在**积累**：词包、案例库和作者档案会随着每一次「这句不行、改成那样」长大。所以最有价值的 PR 往往是几行 YAML，不是几百行 Python。

---

## ⛔ 先看这一条：不要把你公司的东西提上来

这是公开仓库。提交前请确认你的改动**不包含**：

- 真实姓名、工号、手机号、邮箱、账号
- 内部系统名、平台名、项目代号、服务器地址、内网域名
- 未公开的业务数据（真实的量级、金额、覆盖率、目标值）
- 聊天记录、会议纪要原文、内部文档链接
- 任何密钥、token、连接串

**词包和案例请用脱敏或虚构的表达提交。** 一条案例的价值在于「为什么这么改」，不在于它出自哪家公司的哪份材料——把主语换成「示例团队」「某产品」完全不影响它的教学价值。

仓库自带一道闸门，装上它能挡掉大部分意外：

```bash
echo 'python3 tools/check_local_privacy.py || exit 1' >> .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

它拦四类：本地私密路径（`.runtime/`、`sources.local.yaml`）、聊天扫描产物文件名、含 `content/source/speaker/timestamp` 结构的文件、标了 `privacy: local_only` 的内容。

> ⚠️ 闸门只管 git 暂存区，不管你手动打包。它也不认得你公司的产品名——**最后一道防线是你自己读一遍 diff**。

---

## 最需要的三类贡献

### 一、正反案例（`cases/*.yaml`）— 最欢迎

一条案例 = 一次真实的改稿。比任何抽象规则都有用。

```yaml
- id: tone-003
  kind: negative                  # negative 改前有问题 / positive 改后是范本
  before: 各部门要尽快完成对接
  after: 我们会在本周提供接口文档，也希望能一起把联调时间定下来
  reason: 原句是单向要求，没给对方可执行的下一步
  audience: cross_team            # management / region / cross_team / internal
  material_type: presentation     # presentation / speech / weekly / review
  result: owner_rejected_before   # owner_rejected_before / owner_approved_after
```

**`reason` 是这条案例的灵魂。** 只写"改得更好了"等于没写——要说清原句**具体哪里**出了问题：是归责了人、是数字没解读、还是名词浮不出画面。

### 二、通用语言包条目（`language-packs/common.yaml`）

只收**跨业务稳定成立**的表达。判据是：换一个完全不同的行业，这条还成立吗？

```yaml
discouraged:
  - text: 深度赋能
    level: medium                 # high 标题/主张必改 / medium 提示
    positions: [title, claim, summary, body]
    reason: 抽象且缺少具体交付物
    suggestions: [名单, 规则, 工具]   # 给替代词，别只说"不许用"
```

**不收**：你们公司的产品名、行业专有名词、只在某个组织内成立的用词约定。这些属于业务词包（`language-packs/<你的域>.yaml`），留在你自己的 fork 里。

### 三、写作方法（`SKILL.md`）

改主文档前请先想清楚：**这条方法有没有一次具体的失败作为依据？**

现有的每一条都有出处——「去术语不许滑到口语」来自一次被判"太低端"的返工，「量化词人工必检」来自校验器全绿但 9/14 被写成"近半数"。没有具体失败支撑的方法论，通常是正确的废话。

PR 描述里请写清：**你踩了什么坑，这条规则能拦住它吗。**

---

## 提交前跑一遍

```bash
pip install pyyaml pytest
python3 -m pytest tests/ -q          # 应为 20 passed
python3 tools/check_local_privacy.py # 应无输出、退出码 0
```

改了词包的话，顺手验证路由和检查还正常：

```bash
python3 tools/business_language.py route <你的材料.md>
python3 tools/business_language.py lint <你的材料.md>
```

新增词包条目建议补一条测试，放在 `tests/test_business_language.py`。

---

## 几条约定

**状态别乱填。** 词包条目的 `status` 流转是 `candidate → supported → pending_confirmation → approved`。
外部贡献的条目请填 `candidate` 或 `supported`，**不要直接写 `approved`**——`approved` 意味着"有人以自己的判断为它背书"，那是维护者合并时的动作。

**产品名要登记成 `type: product`。** 名字里含通用禁词（如「赋能」）的产品名，只有登记为 `product` + `approved` 才会被保护，否则检查器会把它当黑话报出来，模型也可能擅自给它改名。

**Commit message** 用 `<type>(<scope>): <原因>`，type 取 `feat` / `fix` / `docs` / `refactor` / `chore` / `test`。

**别为了让检查全绿而改内容。** 这套工具会误报——它认不得你的专有名词，也判断不了听感。误报应该反馈成 issue（帮我们修判据），而不是把好句子改坏。`SKILL.md` 里那句话同样适用于工具本身：**机检只证明格式与事实纪律，不证明听感。**

---

## 报 issue

误报和漏报都值得报，尤其是误报——它直接决定这套检查能不能长期用下去。请附上：

- 触发的原文片段（脱敏后）
- 你期望的行为
- `python3 tools/business_language.py lint <文件> --report r.json` 的输出

## 许可证

提交即表示你同意你的贡献以 [Apache License 2.0](LICENSE) 授权。
