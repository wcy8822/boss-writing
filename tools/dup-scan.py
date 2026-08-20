#!/usr/bin/env python3
"""跨章冗余扫描 —— 找「同一件事在不同地方重复说」。

用法:
    python3 dup-scan.py <材料.md>
    python3 dup-scan.py <材料.md> --ratio 0.6      # 句子相似度阈值，默认 0.55
    python3 dup-scan.py <材料.md> --min-times 3    # 实体短语最少出现次数，默认 3

为什么要有它:
    SKILL.md §P0 说「删除必须有重复或偏题依据」，但没给**怎么找到**重复的办法；
    §七·六 全局一致性检查治的是「同一件事两种说法（矛盾）」，
    不治「同一件事说了三遍（冗余）」—— 这是两个不同的病。
    实测一份周报：某产品名全文出现 13 次、同一条状态说明重复 3 处、
    两章判断句相似度 0.88 几乎逐字相同，肉眼通读**一处都没发现**
    （因为分散在不同章节，读到后面已经忘了前面怎么写的）。

输出三类:
    ① 高频实体短语 —— 同一个名词反复出现，通常是该用简称或该合并段落
    ② 高相似句子对 —— 同一件事重复陈述
    ③ 重复的整行 —— 逐字相同，几乎一定是冗余

⚠️ 机器只报「疑似」，删不删是人的判断。
   **同一事实在不同章节各有职责时，重复是合理的**（如 01 章讲月度进度、
   05 章讲对账，同一件事出现两次不算冗余）。别拿本工具的输出无脑删。
"""
import argparse
import difflib
import re
from collections import Counter


def strip_noise(text):
    """去掉不参与冗余判断的部分：代码块、提交清单、表格分隔线。"""
    out, skip = [], False
    for l in text.split("\n"):
        s = l.strip()
        if s.startswith("```"):
            skip = not skip
            continue
        if skip:
            continue
        if re.match(r"^-\s+`\d{4}-\d{2}-\d{2}`", s):      # 提交明细
            continue
        if re.match(r"^\|[\s\-:|]+\|$", s):                # 表格分隔线
            continue
        if re.fullmatch(r"</?\w[^>]*>(.*</\w+>)?", s):        # 纯 HTML 标记行（<summary> 等）
            continue
        out.append(l)
    return "\n".join(out)


def phrases(text, min_times, min_len=4, max_len=12):
    """高频实体短语：只保留最长的那个，避免 n-gram 套娃。"""
    c = Counter()
    for n in range(min_len, max_len + 1):
        for i in range(len(text) - n):
            s = text[i:i + n]
            if re.fullmatch(r"[一-龥A-Za-z0-9]+[一-龥A-Za-z0-9 ·]*", s) and re.search(r"[一-龥A-Za-z]", s):
                c[s] += 1
    cand = [(s, k) for s, k in c.items() if k >= min_times]
    cand.sort(key=lambda x: (-len(x[0]), -x[1]))   # 长的先入选，短子串才会被吃掉
    keep = []
    for s, k in cand:
        if any(s in x for x, _ in keep):           # 已被更长的短语覆盖
            continue
        keep.append((s, k))
    keep.sort(key=lambda x: -x[1])
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("--ratio", type=float, default=0.55)
    ap.add_argument("--min-times", type=int, default=3)
    a = ap.parse_args()

    raw = open(a.md, encoding="utf-8").read()
    text = strip_noise(raw)

    print(f"冗余扫描 · {a.md.split('/')[-1]}")
    print("=" * 64)

    # ── ① 逐字重复的整行（最硬的信号）
    # 跳过标题行：设计上对称的同名小节（如两章都有「主线一 · XXX」）在多处出现
    # 是**结构要求**，不是文案冗余。报它 = 把设计当缺陷。
    lines = [l.strip() for l in text.split("\n")
             if len(l.strip()) > 10 and not l.strip().startswith("#")]
    dup_lines = [(l, k) for l, k in Counter(lines).most_common() if k > 1]
    print(f"\n① 逐字重复的整行：{len(dup_lines)} 组")
    for l, k in dup_lines[:10]:
        print(f"   {k}× {l[:76]}")
    if not dup_lines:
        print("   无")

    # ── ② 高频实体短语
    ph = phrases(text, a.min_times)
    print(f"\n② 高频实体短语（≥{a.min_times} 次）：前 12 条")
    for s, k in ph[:12]:
        print(f"   {k:2d}× {s}")
    if not ph:
        print("   无")

    # ── ③ 高相似句子对
    sents = [s.strip() for s in re.split(r"[。；\n]", text)
             if 12 < len(s.strip()) < 140 and not s.strip().startswith("#")]
    # 先用 difflib 的两级快速上界筛掉不可能达标的句对，再算精确相似度。
    # 实测 4 万字材料（484 句 / 11.7 万个句对）：2.26s → 0.98s，结果逐条一致。
    #
    # ⚠️ set_seq1/set_seq2 的顺序不能反过来图快。
    #    difflib 只对 b 侧做 junk 分析，ratio() 因此**不对称**：
    #    同一对句子 ratio(A,B)=0.5920 而 ratio(B,A)=0.6240。
    #    把不变的那句放 seq2 能复用索引、快 5.7 倍，但结果会变
    #    （实测漏 5 对、多 2 对、14 对数值不同）—— 那是最危险的一类 bug：
    #    输出看着正常，只是悄悄少了几条。正确性优先。
    pairs = []
    matcher = difflib.SequenceMatcher()
    for i, first in enumerate(sents):
        matcher.set_seq1(first)
        for second in sents[i + 1:]:
            matcher.set_seq2(second)
            if matcher.real_quick_ratio() < a.ratio or matcher.quick_ratio() < a.ratio:
                continue
            r = matcher.ratio()
            if r >= a.ratio:
                pairs.append((r, first, second))
    pairs.sort(reverse=True, key=lambda x: x[0])
    print(f"\n③ 相似句子对（≥{a.ratio}）：{len(pairs)} 对，按相似度列前 12")
    for r, x, y in pairs[:12]:
        print(f"   [{r:.2f}] A: {x[:72]}")
        print(f"          B: {y[:72]}")

    print("\n" + "=" * 64)
    print("⚠️ 以上只是「疑似」。删之前逐条问一句：")
    print("   这两处是**同一职责在重复**，还是**不同章节各有职责**？")
    print("   后者（如月度进度 vs 数据对账）重复是合理的，不要删。")
    print("   数字、业务原词、口径边界一律不许删（SKILL.md §五 保留清单）。")

    return 1 if (dup_lines or pairs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
