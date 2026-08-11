#!/usr/bin/env python3
"""boss-writing style-lint — 老板级材料文风机检
用法: python3 style-lint.py <file.md> [--terms-only|--len-only|--tone-only]
检查: ①长句(>40汉字) ②并列过载(单句≥3顿号) ③术语命中 ④可能归责听众的表达
"""
import re
import sys

# 术语表: 正文命中=FAIL, 折叠区命中=WARN
# ⚠️ 这是一份通用起点，请按你所在团队的技术栈增删——
#    表里没有的内部黑话（自研系统名、内部平台名、项目代号）才是最该加进来的。
TERMS = [
    # 研发流程
    "灰度", "灰度名单", "合入主干", "合 master", "合master", "trunk", "回绿", "回滚",
    # 数据与存储
    "ClickHouse", "mapper", "取数内核", "ETL", "血缘", "事实表", "维表", "宽表",
    "数据湖", "数仓", "分区", "落库", "回填",
    # 工程实现
    "下推", "并发", "缓存", "中间件", "配置中心", "熔断", "限流",
    "schema", "API", "SDK", "SPI", "route", "fetcher", "mock", "Mock",
    # 权限与身份
    "SSO", "scope", "钳制", "鉴权",
    # 文档与口径
    "BRD", "PRD", "DRD", "周环比", " pp",
]
# 只能提示人工复核，不能脱离上下文机械替换。
# 归责式表达：把流程/工具的局限写成了对人的评价。按你的组织角色词增补。
TONE_PATTERNS = [
    "只留在个人手里", "愿不愿用", "不会用",
    "好方法复制不了", "只靠个人判断", "必须让", "要求各",
]
MAX_LEN = 40      # 单句最大汉字数
MAX_COMMAS = 3    # 单句顿号并列上限(达到即报)


def cjk_len(s: str) -> int:
    return len(re.findall(r"[一-鿿]", s))


def main(path: str, mode: str = "all") -> int:
    lines = open(path, encoding="utf-8").read().splitlines()
    in_details = False
    in_code = False
    issues = []
    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line:
            continue
        if "<details" in line:
            in_details = True
        if "</details>" in line:
            in_details = False
            continue
        # 去 markdown/HTML 噪音后再检
        text = re.sub(r"<[^>]+>", "", line)          # HTML 标签
        text = re.sub(r"`[^`]*`", "", text)           # 行内代码
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # 链接
        text = re.sub(r"[#>*_|\-]{1,}", " ", text)   # md 记号/表格线
        # ① / ② 长句与并列: 按句末标点切句
        if mode in ("all", "--len-only"):
            for sent in re.split(r"[。！？；;]", text):
                n = cjk_len(sent)
                if n > MAX_LEN:
                    issues.append((i, "长句", f"{n} 字: {sent.strip()[:40]}…"))
                if sent.count("、") >= MAX_COMMAS:
                    issues.append((i, "并列", f"{sent.count('、')} 个顿号: {sent.strip()[:40]}…"))
        # ③ 术语
        if mode in ("all", "--terms-only"):
            for t in TERMS:
                if t in text:
                    level = "术语·折叠区(WARN)" if in_details else "术语·正文(FAIL)"
                    issues.append((i, level, t))
        # ④ 归责感只能由人判断，机器只报提示。
        if mode in ("all", "--tone-only"):
            for p in TONE_PATTERNS:
                if p in text:
                    issues.append((i, "听感·归责(WARN)", p))
    fails = [x for x in issues if "WARN" not in x[1]]
    for ln, kind, detail in issues:
        print(f"  L{ln:>4} [{kind}] {detail}")
    print(f"\n=== style-lint: {len(fails)} FAIL / {len(issues) - len(fails)} WARN "
          f"({'PASS ✅' if not fails else '需治理 ❌'}) ===")
    return 1 if fails else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "all"))
