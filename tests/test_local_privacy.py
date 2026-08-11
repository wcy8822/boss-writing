import importlib.util
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL_ROOT / "tools" / "check_local_privacy.py"
SPEC = importlib.util.spec_from_file_location("check_local_privacy", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class LocalPrivacyHookTest(unittest.TestCase):
    def test_blocks_local_runtime_even_if_force_added(self):
        findings = MODULE.inspect_item(
            ".agents/skills/boss-writing/.runtime/dc-scan.jsonl",
            '{"content":"示例"}',
        )
        self.assertTrue(any("本地私密区" in item.reason for item in findings))

    def test_blocks_personal_assessment_marker(self):
        findings = MODULE.inspect_item(
            "docs/knowledge.yaml",
            "personal_assessment: true\nsummary: 示例",
        )
        self.assertTrue(any("个人判断" in item.reason for item in findings))

    def test_blocks_chat_record_structure(self):
        content = '{"content":"示例","source":"群聊","speaker":"某人","timestamp":"2026-08-06"}'
        findings = MODULE.inspect_item("docs/corpus.jsonl", content)
        self.assertTrue(any("聊天记录结构" in item.reason for item in findings))

    def test_blocks_dc_supported_knowledge(self):
        findings = MODULE.inspect_item("docs/knowledge.yaml", "kind: dc_supported")
        self.assertTrue(any("聊天扫描" in item.reason for item in findings))

    def test_does_not_block_ordinary_writing_discussion(self):
        content = "这句话涉及个人感受，需要调整表达，但不是聊天扫描记录。"
        self.assertEqual(MODULE.inspect_item("docs/writing-method.md", content), [])


if __name__ == "__main__":
    unittest.main()
