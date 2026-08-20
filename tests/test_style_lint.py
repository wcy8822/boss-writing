import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL_ROOT / "tools" / "style-lint.py"
SPEC = importlib.util.spec_from_file_location("style_lint", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def lint(text: str) -> int:
    """跑一遍 style-lint，返回 FAIL 数（退出码 1=有 FAIL，0=干净）。"""
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as fh:
        fh.write(text)
        path = fh.name
    try:
        return MODULE.main(path)
    finally:
        Path(path).unlink()


class TableRowExemptionTest(unittest.TestCase):
    """表格单元格里的枚举不是句子并列 —— SKILL §七·六·二 的规则落进代码。"""

    def test_table_row_enumeration_is_not_reported(self):
        table = "| 要素 | 例 |\n|---|---|\n| 业务对象 | 名单、地图、点位、客户、策略编号 |\n"
        self.assertEqual(lint(table), 0)

    def test_same_enumeration_in_prose_is_still_reported(self):
        """同样的枚举写在正文里必须照报 —— 豁免只针对表格结构，不是放过并列过载。"""
        prose = "我们提供名单、地图、点位、客户、策略编号这几样东西。\n"
        self.assertEqual(lint(prose), 1)

    def test_long_sentence_in_table_is_not_reported(self):
        long_cell = "| 项 | 说明 |\n|---|---|\n| 判据 | " + "很长的说明文字" * 8 + " |\n"
        self.assertEqual(lint(long_cell), 0)

    def test_jargon_in_table_is_still_reported(self):
        """表格豁免的只是句长与并列，术语命中照报。"""
        table = "| 名称 | 说明 |\n|---|---|\n| 数据层 | 走 ClickHouse 直连 |\n"
        self.assertEqual(lint(table), 1)


if __name__ == "__main__":
    unittest.main()
