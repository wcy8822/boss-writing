#!/usr/bin/env python3
"""改写稿自动验收 —— 机器管事实与纪律，人管表达。

用法: python3 score.py <基准原文> <待评稿1> [待评稿2 ...]
"""
import re
import sys
import pathlib

# 禁用黑话。末尾可按组织用词习惯追加——不少组织对个别中性词也有自己的约定。
BAN_JARGON = ['痛点', '抓手', '赋能', '生态', '护城河', '心智', '势能', '组合拳',
              '全域', '全链路', '一体化', '数字化转型', '智能化升级', '降维打击',
              '上帝视角', '进一步优化', '有效提升']
BAN_ORAL = ['拿去谈', '跑起来', '收得回来', '动得了', '对不上账', '没人说得清',
            '被骗了', '拍脑袋', '抢客', '蛋糕大', '好钢用在刀刃上', '说白了']

# SMART 四要素的语言指纹（粗判，只作提示不作硬判）
SMART_HINTS = {
    '动因': ['为', '因', '需', '对应', '约束', '否则', '前置'],
    '产出物': ['输出', '产出', '完成', '建成', '定稿', '上线', '文档', '方案'],
    '结果': ['%', '项', '座', '张', '条', '个', '已', '至'],
    '价值': ['意味', '说明', '不是', '而是', '才能', '据此', '支撑', '用于'],
}


# 专有名词豁免：既定命名内含禁词也不算违规。**把你自己的产品名填进来。**
# 起因：模型见「赋能」在禁词表，把主线正式名「XX赋能工具」删成了「XX工具」。
# 专有名词优先于禁词表 —— 命名是业务方定的，不由文风规则改写。
WHITELIST = []  # 例：['客户赋能工具', '增长引擎']


def strip(t):
    t = re.sub(r'<[^>]+>', '', t)
    return t


def mask_whitelist(t):
    """把白名单短语挖掉再查禁词，避免专有名词误报。"""
    for w in WHITELIST:
        t = t.replace(w, '〓')
    return t


def cn_len(s):
    return len(re.findall(r'[一-鿿]', s))


def analyze(path, base_nums=None):
    raw = pathlib.Path(path).read_text(encoding='utf-8')
    t = strip(raw)
    nums = sorted(set(re.findall(r'\d+(?:\.\d+)?%?', t)))
    bullets = [l.strip() for l in t.splitlines() if l.strip().startswith('-')]
    lens = [cn_len(b) for b in bullets] or [0]

    r = {
        'name': pathlib.Path(path).stem,
        'cn': cn_len(t),
        'bullets': len(bullets),
        'avg': sum(lens) / len(lens),
        'over40': sum(1 for x in lens if x > 40),
        'nums': nums,
        'jargon': [w for w in BAN_JARGON if w in mask_whitelist(t)],
        'oral': [w for w in BAN_ORAL if w in mask_whitelist(t)],
        'nab': len(re.findall(r'不是.{1,20}[，,]?\s*而是', t)),
    }
    if base_nums is not None:
        r['num_added'] = sorted(set(nums) - set(base_nums))
        r['num_lost'] = sorted(set(base_nums) - set(nums))
    # SMART 覆盖：每个 bullet 命中几类要素
    cover = []
    for b in bullets:
        hit = sum(1 for k, kws in SMART_HINTS.items() if any(w in b for w in kws))
        cover.append(hit)
    r['smart_avg'] = sum(cover) / len(cover) if cover else 0
    r['smart_full'] = sum(1 for c in cover if c >= 3)
    return r


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    base = analyze(sys.argv[1])
    print(f"基准：{base['name']}  {base['cn']} 字 · {base['bullets']} 条 · 数字 {len(base['nums'])} 个\n")

    rows = []
    for p in sys.argv[2:]:
        rows.append(analyze(p, base['nums']))

    hdr = f"{'稿件':<16}{'字数':>6}{'增幅':>7}{'均长':>6}{'超40':>6}{'禁词':>6}{'口语':>6}{'不是A而是B':>11}{'SMART全':>8}"
    print(hdr)
    print('-' * len(hdr))
    for r in rows:
        delta = (r['cn'] - base['cn']) / base['cn'] * 100
        print(f"{r['name']:<16}{r['cn']:>6}{delta:>6.0f}%{r['avg']:>6.1f}{r['over40']:>6}"
              f"{len(r['jargon']):>6}{len(r['oral']):>6}{r['nab']:>11}{r['smart_full']:>8}")

    print('\n=== 事实保真（硬红线）===')
    for r in rows:
        bad = []
        if r.get('num_added'):
            bad.append(f"新增数字 {r['num_added']}")
        if r.get('num_lost'):
            bad.append(f"丢失数字 {r['num_lost']}")
        if r['jargon']:
            bad.append(f"禁词 {r['jargon']}")
        if r['oral']:
            bad.append(f"口语 {r['oral']}")
        print(f"  {r['name']:<16} " + ('✅ 通过' if not bad else '❌ ' + ' | '.join(bad)))

    print('\n注：SMART全 = 单条命中动因/产出物/结果/价值 ≥3 类的条目数（粗判，仅供参考）')
    print('    表达力由人评分，机器只管事实与纪律。')


if __name__ == '__main__':
    main()
