import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = SKILL_ROOT / "tools" / "business_language.py"
SPEC = importlib.util.spec_from_file_location("business_language", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class BusinessLanguageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packs = MODULE.load_packs(SKILL_ROOT / "language-packs")

    def test_routes_common_and_domain_pack(self):
        routed = MODULE.route_packs("选址推荐按标签圈选点位", self.packs)
        self.assertEqual([p["id"] for p in routed], ["common", "example-domain"])
        self.assertIn("选址推荐", routed[1]["route_hits"])

    def test_approved_product_name_masks_generic_jargon(self):
        findings, _ = MODULE.lint_text("# 客户赋能工具\n## 赋能工具\n打开工具查看周边竞争。", self.packs)
        self.assertFalse(any(item.text == "赋能" for item in findings))

    def test_old_version_abstract_foundation_is_reported(self):
        findings, _ = MODULE.lint_text("生产环境与数据底座已经就绪，形成融合底座。", self.packs)
        self.assertIn("底座", [item.text for item in findings])

    def test_unverified_claim_is_high_but_never_blocks(self):
        findings, _ = MODULE.lint_text("# 打造增长复制引擎\n正文。", self.packs)
        self.assertTrue(any(item.level == "high" and item.category in {"business_language", "unverified_claim"} for item in findings))
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            MODULE.write_report(report, findings, MODULE.route_packs("打造增长复制引擎", self.packs))
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["mode"], "shadow")
            self.assertFalse(payload["blocked"])

    def test_ordinary_language_is_not_reported(self):
        text = "# Q3我们聚焦两件事\n区域可以核对名单，并把问题及时记录下来。"
        findings, _ = MODULE.lint_text(text, self.packs)
        self.assertEqual(findings, [])

    def test_extract_candidates_keeps_source_and_candidate_status_is_external(self):
        records = [
            {"content": "今天核对点位名单和拜访工具", "source": "chat-a", "speaker": "u1"},
            {"content": "点位名单还要再核一次", "source": "chat-b", "speaker": "u2"},
        ]
        candidates = MODULE.extract_candidates(records)
        station = next(item for item in candidates if item["text"] == "点位名单")
        self.assertEqual(station["count"], 2)
        self.assertEqual(len(station["sources"]), 2)

    def test_feedback_event_stays_candidate(self):
        args = type("Args", (), {
            "before": "共同承诺",
            "after": "一起把这件事做成",
            "reason": "听感有压力",
            "audience": "region",
            "material_type": "speech",
            "result": "owner_feedback",
        })()
        event = MODULE.feedback_event(args)
        self.assertEqual(event["status"], "candidate")
        self.assertEqual(event["after"], "一起把这件事做成")

    def test_external_namespace_cannot_promote_to_business_pack(self):
        payload = MODULE.ingest_payload([{"content": "用真实动作组织文章"}], "external")
        self.assertEqual(payload["namespace"], "external-writing-methods")
        self.assertEqual(payload["promotion_to_business_pack"], "forbidden")

    def test_knowledge_query_only_returns_approved_cards_with_sources(self):
        cards = [
            {
                "id": "approved",
                "title": "区域科学管理",
                "summary": "帮助区域看清目标差距并安排动作",
                "topics": ["示例业务", "区域"],
                "status": "approved",
                "sources": [{"kind": "owner", "ref": "确认"}],
            },
            {
                "id": "candidate",
                "title": "区域增长飞轮",
                "summary": "候选概念",
                "topics": ["区域"],
                "status": "candidate",
                "sources": [{"kind": "dc", "ref": "聊天"}],
            },
        ]
        results = MODULE.query_knowledge("区域 示例业务", cards)
        self.assertEqual([item["id"] for item in results], ["approved"])
        self.assertTrue(results[0]["sources"])

    def test_knowledge_query_returns_empty_for_unknown_topic(self):
        cards = MODULE.load_knowledge(SKILL_ROOT / ".runtime" / "knowledge-base")
        self.assertEqual(MODULE.query_knowledge("完全无关的量子航天", cards), [])

    def test_sanitization_is_consistent_and_structure_preserving(self):
        raw = "示例团队使用选址推荐。\n示例团队反馈名单准确。"
        sanitized, mapping = MODULE.sanitize_text(raw, ["示例团队"])
        self.assertEqual(sanitized.count("实体甲"), 2)
        self.assertEqual(raw.count("\n"), sanitized.count("\n"))
        self.assertEqual(mapping["示例团队"], "实体甲")

    def test_blind_packet_routes_raw_only_to_internal_reviewer(self):
        raw = "示例团队使用选址推荐"
        sanitized, _ = MODULE.sanitize_text(raw, ["示例团队"])
        packet = MODULE.build_blind_packet(sanitized, "abc", "/tmp/internal-only.md")
        self.assertEqual(packet["anonymous_reviewers"]["candidate-a"]["input"], "sanitized")
        self.assertEqual(packet["anonymous_reviewers"]["candidate-b"]["input"], "sanitized")
        self.assertEqual(packet["anonymous_reviewers"]["candidate-c"]["input"], "raw_internal_ref")
        self.assertNotIn("示例团队", packet["inputs"]["sanitized"])
        self.assertNotIn("示例团队", json.dumps(packet, ensure_ascii=False))
        self.assertEqual(packet["inputs"]["raw_internal_ref"], "/tmp/internal-only.md")

    def test_html_headings_receive_stricter_position(self):
        findings, _ = MODULE.lint_text("<h1>增长复制引擎</h1>", self.packs)
        self.assertTrue(any(item.position == "title" and item.level == "high" for item in findings))

    def test_accepted_material_has_no_language_findings(self):
        """定稿材料不应被误报——误报率是这套检查能不能长期用下去的关键。"""
        text = "\n".join([
            "# 这一季就做两件事",
            "选址推荐：按标签批量圈选，在地图上集中判断，名单保存后继续跟踪和回溯。",
            "客户赋能工具：说明周边竞争对手、客群分流和经营机会。",
            "两区试点跑通后，把方法带到更多区域。",
        ])
        findings, routed = MODULE.lint_text(text, self.packs)
        self.assertEqual([p["id"] for p in routed], ["common", "example-domain"])
        self.assertEqual(findings, [])

    def test_old_style_material_reports_abstract_foundation(self):
        """未经治理的旧稿：抽象比喻必须被抓出来。"""
        html = "<h2>数据底座已经就绪</h2><p>形成融合底座，打造增长复制引擎。</p>"
        findings, _ = MODULE.lint_text(html, self.packs)
        texts = [item.text for item in findings]
        self.assertIn("底座", texts)
        self.assertIn("增长复制引擎", texts)


class TechniqueTest(unittest.TestCase):
    """FR-9：外部资料学写法，不学业务词。"""

    @classmethod
    def setUpClass(cls):
        cls.items = MODULE.load_techniques(SKILL_ROOT / "techniques")

    def test_external_ingest_uses_technique_extractor_not_business_regex(self):
        records = [{"content": "以前需要逐个搜索反复核对，现在按标签批量圈选。", "source": "book-a"}]
        payload = MODULE.ingest_payload(records, "external")
        self.assertEqual(payload["namespace"], "external-writing-methods")
        self.assertEqual(payload["promotion_to_business_pack"], "forbidden")
        self.assertEqual(payload["items"][0]["pattern_hit"], "before_after")
        # 业务名词正则会抽出「拜访工具」这类词；技巧通道不该产出这种东西
        self.assertNotIn("text", payload["items"][0])

    def test_technique_skeleton_leaves_judgement_fields_empty(self):
        """正则产不出判断——problem/technique/avoid_when 必须留空待补。"""
        records = [{"content": "问题不是缺点位，而是缺值得去的点位。", "source": "talk-b"}]
        item = MODULE.extract_technique_candidates(records)[0]
        self.assertEqual(item["pattern_hit"], "contrast")
        for field in ("title", "problem", "technique", "avoid_when"):
            self.assertEqual(item[field], MODULE.TECHNIQUE_SKELETON_TODO)

    def test_external_candidate_can_never_be_approved(self):
        records = [{"content": "覆盖率 12%，这说明还有大量空白。", "source": "report-c"}]
        item = MODULE.extract_technique_candidates(records)[0]
        self.assertEqual(item["pattern_hit"], "number_reading")
        self.assertEqual(item["status"], "candidate")
        self.assertEqual(item["promotion"], "forbidden")

    def test_all_four_patterns_are_recognised(self):
        records = [{"content": "不是缺站而是缺好站。以前靠人现在靠规则。"
                               "覆盖率 12%，这说明还有空间。看起来很近，实际要绕路。",
                    "source": "mix"}]
        hits = {i["pattern_hit"] for i in MODULE.extract_technique_candidates(records)}
        self.assertEqual(hits, {"contrast", "before_after", "number_reading", "myth_break"})

    def test_every_shipped_technique_has_before_after_and_avoid(self):
        """没有对照的技巧是抽象口号，不许进库。"""
        self.assertTrue(self.items)
        for item in self.items:
            for field in ("problem", "technique", "example_before", "example_after",
                          "use_when", "avoid_when"):
                self.assertTrue(item.get(field), f"{item['id']} 缺 {field}")

    def test_external_sourced_technique_stays_candidate(self):
        for item in self.items:
            if item.get("source", {}).get("kind") == "external":
                self.assertEqual(item["status"], "candidate", item["id"])
            self.assertEqual(item.get("promotion"), "forbidden", item["id"])

    def test_technique_query_matches_by_scenario(self):
        hits = MODULE.query_techniques("标题", self.items)
        self.assertIn("tech-title-as-claim", [i["id"] for i in hits])
        self.assertEqual(MODULE.query_techniques("量子航天育种", self.items), [])


if __name__ == "__main__":
    unittest.main()
