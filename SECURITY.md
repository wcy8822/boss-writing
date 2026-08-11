# 安全说明

这个包会读你的材料、跑正则、调 `git`，所以它的安全边界值得写清楚——也方便你在扫描报告里看到告警时，能自己核实而不是猜。

## 一句话

**全包不联网、不执行外部代码、不把任何内容发出去。** 所有处理都在本机完成，输出只落在你指定的路径。

## 常见静态扫描告警逐条说明

静态扫描工具通常按模式匹配，不区分上下文。下面是这个包会被扫出来的项，以及它们为什么不构成风险——每条都给了你可以自己跑的核实命令。

### `subprocess.run` — 不构成命令注入

`tools/check_local_privacy.py` 调用 `git` 读取暂存区内容：

```python
subprocess.run(["git", "-C", repo, *args], check=False, capture_output=True)
```

**列表传参、不经 shell。** 参数即使含 `;` `|` `$()` 也只会被当成 git 的字面参数，不会被解释执行。命令注入的必要条件是 `shell=True` 或字符串拼接，两者都没有。

自己核实：

```bash
grep -rn "shell=True\|os.system\|os.popen\|eval(\|exec(" tools/
# 应无输出
```

### `re.compile` — 全部是字面量常量，无 ReDoS

包内所有正则都写死在源码里，**不接受用户输入拼接构造**（无 f-string、无字符串加法）。

所有量词都有明确上界（`.{1,30}?` / `.{2,60}?` / `{2,8}`），且无嵌套量词——不存在灾难性回溯的结构条件。

实测（含阳性对照，证明测法本身有效）：

| 输入 | 耗时 |
|---|---|
| 已知会回溯的 `(a+)+$` 打 24 个 `a`（阳性对照） | 0.580s |
| 8.7 万字符恶意构造输入打本包全部正则 | **0.007s** |

差三个数量级。自己核实：

```bash
python3 - <<'EOF'
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location('bl','tools/business_language.py')
m = importlib.util.module_from_spec(spec); sys.modules['bl']=m; spec.loader.exec_module(m)
payload = ("以前"+"x"*60+"现在"+"9"*20+"这说明")*1000
t=time.time(); m.extract_technique_candidates([{"content":payload,"source":"x"}])
print(f"{len(payload)} 字符耗时 {time.time()-t:.3f}s")
EOF
```

### GitHub Actions 表达式插值 — 已刻意规避

`.github/workflows/tests.yml` **不使用 matrix 和 `${{ }}` 插值**，三个 Python 版本写成三个独立 job，版本号是字面量。

script injection 的真实触发条件是把攻击者可控的输入（如 issue 标题、PR 正文）插进 `run:` 的 shell 脚本。本工作流的 `run:` 块里零表达式插值。为了让扫描器也能一眼看出这点，我们用重复换取了零插值。

自己核实：

```bash
grep -c '\${{' .github/workflows/tests.yml
# 应输出 0
```

## 这个包会碰什么

| 行为 | 说明 |
|---|---|
| 读文件 | 只读你在命令行显式传入的路径 |
| 写文件 | 只写你用 `--output` / `--report` 指定的路径，以及 `.runtime/`（已在 `.gitignore`） |
| 调外部命令 | 只有 `git`（列表传参），仅用于读暂存区 |
| 网络 | **无**。全包没有 `requests` / `urllib` / `http` / `socket` 的任何调用 |
| 依赖 | 仅 Python 标准库 + PyYAML；`yaml.safe_load`，不用 `yaml.load` |

网络与反序列化自己核实：

```bash
grep -rn "import requests\|import urllib\|import http\|import socket\|urlopen" tools/   # 应无输出
grep -rn "yaml.load(" tools/                                                            # 应无输出（只用 safe_load）
```

## 需要你注意的一件事

`tools/check_local_privacy.py` 是防止聊天语料、个人评价材料进版本库的闸门。**它只检查 git 暂存区，管不了「打包整个目录发出去」。**

如果你往 `.runtime/` 存过内部语料，对外分发前请手动确认它不在包里：

```bash
tar tzf <你的包>.tar.gz | grep -E "\.runtime|sources\.local"
# 应无输出
```

## 报告安全问题

发现真实问题请开 issue（不涉及未公开细节时），或在 issue 里说明你希望私下沟通。

请附上：受影响文件与行号、触发条件、可复现的最小输入。
