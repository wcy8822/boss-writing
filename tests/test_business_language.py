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


class BusinessSenseTest(unittest.TestCase):
    """业务感 = 业务对象 + 动作 + 场景的密度（SKILL §三·五）。"""

    @classmethod
    def setUpClass(cls):
        cls.packs = MODULE.load_packs(SKILL_ROOT / "language-packs")

    def test_empty_paragraph_is_reported(self):
        text = ("本季度我们持续推进能力建设，通过体系化的方法完善整体框架，形成了较为完整的机制，"
                "为后续工作奠定了坚实基础，各项指标均有所改善，整体运行情况良好。")
        hits = [f for f in MODULE.business_sense_findings(text, self.packs)
                if f.category == "business_sense"]
        self.assertEqual(len(hits), 1)
        self.assertIn("读者脑子里是空的", hits[0].reason)

    def test_paragraph_with_business_words_is_not_reported(self):
        text = ("拜访客户前，一线以前要翻三个系统才能查清周边有几家竞对。现在按标签批量圈选，"
                "在地图上集中判断，名单保存后还能继续跟踪和回溯。两区试点跑通后仍可复用。")
        self.assertEqual(MODULE.business_sense_findings(text, self.packs), [])

    def test_short_paragraph_is_not_judged(self):
        """标题、过渡句太短，判不出来也不该判。"""
        self.assertEqual(MODULE.business_sense_findings("本季度进展良好。", self.packs), [])

    def test_scenario_alone_is_enough(self):
        """三要素任一即可 —— 场景是最被低估的那个。"""
        text = "月底对账时，" + "这件事需要反复确认才能推进下去因此耗时较长" * 2
        self.assertEqual(MODULE.business_sense_findings(text, self.packs), [])

    def test_uses_all_packs_not_only_routed(self):
        """⚠️ 回归锁：必须对照全部词包。

        用 routed 会产生鸡生蛋——越没有业务感的材料越路由不到业务词包，
        结果最该被报的段落反而不被检查。这个坑踩过一次。
        """
        empty = ("本季度我们持续推进能力建设，通过体系化的方法完善整体框架，形成了较为完整的机制，"
                 "为后续工作奠定了坚实基础，各项指标均有所改善，整体运行情况良好。")
        routed = MODULE.route_packs(empty, self.packs)
        self.assertEqual([p["id"] for p in routed], ["common"])   # 确实只路由到 common
        self.assertEqual(MODULE.business_words(routed), {})       # common 里没有业务感词
        findings, _ = MODULE.lint_text(empty, self.packs)         # 但整体 lint 必须报出来
        self.assertTrue(any(f.category == "business_sense" for f in findings))


class CaseExtractionTest(unittest.TestCase):
    """把润色变成能积累的一步：从原稿 vs 改写稿抽 case 候选。"""

    ORIGIN = "本季度完成能力建设，通过整合多源数据构建完整体系，为团队\n提供决策支持，赋能业务增长。"
    REVISED = "以前选点靠个人经验，换个区域用不上。现在按标签批量圈选，一键导出成名单。"

    def test_extracts_rewrite_pair(self):
        items = MODULE.extract_case_candidates(self.ORIGIN, self.REVISED)
        self.assertTrue(items)
        self.assertIn("能力建设", items[0]["before"])
        self.assertIn("圈选", items[0]["after"])

    def test_judgement_fields_left_empty(self):
        """为什么这么改是判断，diff 产不出 —— 三项必须留空。"""
        item = MODULE.extract_case_candidates(self.ORIGIN, self.REVISED)[0]
        for field in ("reason", "audience", "material_type"):
            self.assertEqual(item[field], MODULE.CASE_TODO)
        self.assertEqual(item["result"], "pending_confirmation")

    def test_near_identical_is_skipped(self):
        """只动标点不值得记。"""
        a = "以前选点靠个人经验，换个区域就用不上了。"
        b = "以前选点靠个人经验，换个区域就用不上了"
        self.assertEqual(MODULE.extract_case_candidates(a, b), [])

    def test_soft_wrap_does_not_split_sentence(self):
        """⚠️ 回归锁：markdown 软换行不是句子边界。踩过一次。"""
        sents = MODULE.split_sentences("为区域和一线团队\n提供决策支持，赋能业务增长。")
        self.assertEqual(len(sents), 1)
        self.assertIn("为区域和一线团队提供决策支持", sents[0])

    def test_heading_does_not_glue_to_body(self):
        """⚠️ 回归锁：修软换行时引入过一个副作用——标题末尾没句号，
        合并软换行会把标题和正文粘成一句。"""
        sents = MODULE.split_sentences("## 三、行动推荐能力建设方案\n本季度完成了整合工作，效果良好。")
        self.assertGreaterEqual(len(sents), 2, f"标题与正文没分开: {sents}")
        self.assertNotIn("本季度", sents[0])

    def test_heading_inside_blockquote_also_splits(self):
        """引用块里的标题同样要分开 —— examples/ 里的改前改后就在引用块中。"""
        sents = MODULE.split_sentences("> ## 三、行动推荐能力建设方案\n>\n> 本季度完成了整合工作。")
        self.assertNotIn("本季度", sents[0])

    def test_low_similarity_pairs_are_kept(self):
        """⚠️ 回归锁：整句重写字面几乎不重合（实测 0.06~0.28），
        早期版本用相似度下限筛，把最有价值的改写全过滤掉了。"""
        items = MODULE.extract_case_candidates(
            "形成了从数据到决策的闭环，赋能业务持续增长。",
            "拜访客户前打开就能看到周边有几家竞对，不用再翻三个系统。")
        self.assertTrue(items, "低相似度的整句重写必须保留")


class TermLearningTest(unittest.TestCase):
    """让它认识你：业务词的候选抽取与入库闭环。"""

    MATERIAL = ("## 履约健康度看板本周进展\n\n"
                "本周完成**履约健康度看板**的第一版。看板的核心是把「超时履约率」讲清楚。\n"
                "另外把《大区履约白皮书》里的判据同步进来。\n")

    @classmethod
    def setUpClass(cls):
        cls.packs = MODULE.load_packs(SKILL_ROOT / "language-packs")

    def test_marked_expressions_are_captured(self):
        """加粗 / 引号 / 书名号是作者自己标出来的，精确可信。"""
        got = {c["text"]: c["signal"] for c in MODULE.suggest_terms(self.MATERIAL, self.packs)}
        self.assertEqual(got.get("履约健康度看板"), "加粗")
        self.assertEqual(got.get("超时履约率"), "引号")
        self.assertEqual(got.get("大区履约白皮书"), "书名号")

    def test_already_known_terms_are_not_suggested(self):
        """已收录的不该再问用户第二遍。"""
        text = "本周把客户洞察报告发给了三个区域，反馈都不错，下一步继续推进这件事。"
        self.assertNotIn("客户洞察报告",
                         [c["text"] for c in MODULE.suggest_terms(text, self.packs)])

    def test_rejected_terms_are_remembered(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rejected.yaml"
            MODULE.reject_terms(path, ["大区履约白皮书"])
            self.assertIn("大区履约白皮书", MODULE.load_rejected(path))
            got = [c["text"] for c in
                   MODULE.suggest_terms(self.MATERIAL, self.packs, MODULE.load_rejected(path))]
            self.assertNotIn("大区履约白皮书", got)

    def test_append_term_writes_valid_pack(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / "mine.yaml"
            entry = MODULE.append_term(pack, "履约健康度看板", "product", "汇总履约达成的看板", "对话确认")
            self.assertTrue(entry["id"].startswith("mine-"))
            self.assertNotIn("--", entry["id"])          # 曾生成过 xxx-- 这种 id
            data = MODULE.load_yaml(pack)
            # 产品名必须同时成为路由触发词，否则这个包对含该产品名的材料不会被加载
            self.assertIn("履约健康度看板", data["triggers"])
            self.assertEqual(data["terms"][0]["type"], "product")

    def test_append_term_rejects_duplicate_and_bad_type(self):
        with tempfile.TemporaryDirectory() as d:
            pack = Path(d) / "mine.yaml"
            MODULE.append_term(pack, "晨会前", "scenario", "晨会开始前的时刻", "对话确认")
            with self.assertRaises(ValueError):
                MODULE.append_term(pack, "晨会前", "scenario", "重复", "对话确认")
            with self.assertRaises(ValueError):
                MODULE.append_term(pack, "别的词", "not-a-type", "释义", "对话确认")

    def test_new_term_immediately_lifts_business_sense(self):
        """入库后业务感检查要立刻认得 —— 这是整个闭环的意义。"""
        with tempfile.TemporaryDirectory() as d:
            pack_dir = Path(d)
            MODULE.append_term(pack_dir / "mine.yaml", "履约健康度看板", "product",
                               "汇总履约达成的看板", "对话确认")
            packs = MODULE.load_packs(pack_dir)
            text = "晨会前先看一眼履约健康度看板，派单时心里更有底，各大区口径也能保持一致。"
            self.assertEqual(MODULE.business_sense_findings(text, packs), [])


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
