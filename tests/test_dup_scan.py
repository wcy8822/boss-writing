import difflib
import importlib.util
import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL_ROOT / "tools" / "dup-scan.py"
SPEC = importlib.util.spec_from_file_location("dup_scan", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def run(text: str, *args: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as fh:
        fh.write(text)
        path = fh.name
    argv = sys.argv
    sys.argv = ["dup-scan.py", path, *args]
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            MODULE.main()
        return buf.getvalue()
    finally:
        sys.argv = argv
        Path(path).unlink()


class DupScanTest(unittest.TestCase):
    def test_duplicate_line_is_reported(self):
        text = "名单存下来过三个月还能翻出来对。\n中间隔一段别的内容。\n名单存下来过三个月还能翻出来对。\n"
        self.assertIn("2×", run(text))

    def test_heading_repetition_is_not_reported(self):
        """设计上对称的同名小节是结构要求，不是冗余 —— 报它等于把设计当缺陷。"""
        text = "## 主线一 · 试点\n正文甲内容足够长可以参与判断。\n## 主线一 · 试点\n正文乙内容也足够长。\n"
        self.assertIn("① 逐字重复的整行：0 组", run(text))

    def test_code_block_is_ignored(self):
        text = "```\n重复的命令行内容需要被忽略掉\n重复的命令行内容需要被忽略掉\n```\n正文只有一句话在这里。\n"
        self.assertIn("① 逐字重复的整行：0 组", run(text))


class PruningEquivalenceTest(unittest.TestCase):
    """⚠️ 回归锁：剪枝优化不许改变结果。

    difflib 只对 b 侧做 junk 分析，ratio() 因此不对称——
    ratio(A,B) 与 ratio(B,A) 可以差 0.03 以上。把不变的那句放 seq2
    能复用索引、快一倍多，但会漏掉/多出句对。这个坑踩过一次。
    """

    SENTS = [
        "以前选点靠个人经验换个区域就用不上了",
        "以前选点靠个人判断换个城市就用不上了",
        "现在按标签批量圈选在地图上集中判断",
        "现在按标签批量筛选在地图上统一判断",
        "完全无关的一句话用来做对照组使用",
    ]

    def _brute(self, ratio):
        out = []
        for i in range(len(self.SENTS)):
            for j in range(i + 1, len(self.SENTS)):
                r = difflib.SequenceMatcher(None, self.SENTS[i], self.SENTS[j]).ratio()
                if r >= ratio:
                    out.append((i, j, round(r, 6)))
        return out

    def _pruned(self, ratio):
        out = []
        m = difflib.SequenceMatcher()
        for i, first in enumerate(self.SENTS):
            m.set_seq1(first)
            for j, second in enumerate(self.SENTS[i + 1:], start=i + 1):
                m.set_seq2(second)
                if m.real_quick_ratio() < ratio or m.quick_ratio() < ratio:
                    continue
                r = m.ratio()
                if r >= ratio:
                    out.append((i, j, round(r, 6)))
        return out

    def test_pruned_matches_brute_force(self):
        for ratio in (0.3, 0.55, 0.8):
            self.assertEqual(self._brute(ratio), self._pruned(ratio), f"ratio={ratio} 结果不一致")

    # 从真实材料里捞出来的一对——不是构造的。短句往往触发不了不对称，
    # 差值最大的这对相差 0.14（0.3721 vs 0.5116）。
    ASYM_A = "| 来源 | 有刺写法 | 温和写法 | 问题 |"
    ASYM_B = "| 矛盾类型 | 实例 | 修法 |"

    def test_ratio_is_not_symmetric(self):
        """记录 difflib 这个反直觉行为，防止后人再"顺手优化"。"""
        forward = difflib.SequenceMatcher(None, self.ASYM_A, self.ASYM_B).ratio()
        backward = difflib.SequenceMatcher(None, self.ASYM_B, self.ASYM_A).ratio()
        self.assertNotEqual(round(forward, 4), round(backward, 4),
                            "difflib.ratio() 在这对上应当不对称；相等说明 difflib 行为变了，"
                            "届时可以重新评估 seq1/seq2 顺序能不能换")

    def test_swapping_seq_order_would_change_results(self):
        """直接证明「换顺序会改结果」——这是那条回归锁存在的理由。"""
        sents = [self.ASYM_A, self.ASYM_B]
        ratio = 0.40
        keep_order = difflib.SequenceMatcher(None, sents[0], sents[1]).ratio() >= ratio
        swapped = difflib.SequenceMatcher(None, sents[1], sents[0]).ratio() >= ratio
        self.assertNotEqual(keep_order, swapped, "这对句子在阈值 0.40 上应当一边达标一边不达标")

    def test_source_keeps_correct_seq_order(self):
        """源码里必须是外层 set_seq1、内层 set_seq2，反了结果会变。"""
        src = MODULE_PATH.read_text(encoding="utf-8")
        body = re.search(r"for i, first in enumerate\(sents\):.*?pairs\.append", src, re.S).group(0)
        self.assertLess(body.index("set_seq1"), body.index("set_seq2"))


if __name__ == "__main__":
    unittest.main()
