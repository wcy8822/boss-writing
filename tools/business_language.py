#!/usr/bin/env python3
"""业务语言持续学习内核：路由、影子检查、采集、反馈、脱敏与盲测包。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


SKILL_ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = SKILL_ROOT / "language-packs"
RUNTIME_DIR = SKILL_ROOT / ".runtime"
KNOWLEDGE_DIR = RUNTIME_DIR / "knowledge-base"
TECHNIQUE_DIR = SKILL_ROOT / "techniques"


@dataclass
class Finding:
    line: int
    position: str
    level: str
    category: str
    text: str
    reason: str
    suggestions: list[str]
    sources: list[dict[str, Any]]
    mode: str = "shadow"


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_packs(pack_dir: Path = PACK_DIR) -> list[dict[str, Any]]:
    return [load_yaml(path) for path in sorted(pack_dir.glob("*.yaml"))]


def load_knowledge(knowledge_dir: Path = KNOWLEDGE_DIR) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for path in sorted(knowledge_dir.glob("*.yaml")):
        payload = load_yaml(path)
        for card in payload.get("cards", []):
            item = dict(card)
            item["knowledge_file"] = path.name
            cards.append(item)
    return cards


def searchable_text(card: dict[str, Any]) -> str:
    fields = [
        card.get("title", ""),
        card.get("summary", ""),
        " ".join(card.get("topics", [])),
        " ".join(card.get("audiences", [])),
        " ".join(card.get("actions", [])),
        " ".join(card.get("use_when", [])),
        " ".join(card.get("avoid", [])),
    ]
    return "\n".join(str(value) for value in fields)


def query_knowledge(query: str, cards: Iterable[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    terms: list[str] = []
    for chunk in re.findall(r"[一-鿿]+|[A-Za-z0-9_-]{2,}", query.lower()):
        if re.fullmatch(r"[一-鿿]+", chunk):
            terms.append(chunk)
            for size in range(2, min(6, len(chunk)) + 1):
                terms.extend(chunk[index:index + size] for index in range(len(chunk) - size + 1))
        else:
            terms.append(chunk)
    terms = list(dict.fromkeys(terms))
    if not terms and query.strip():
        terms = [query.strip().lower()]
    ranked: list[tuple[int, dict[str, Any]]] = []
    for card in cards:
        if card.get("status") != "approved":
            continue
        haystack = searchable_text(card).lower()
        score = 0
        for term in terms:
            if term not in haystack:
                continue
            score += 3 if term in str(card.get("title", "")).lower() else 1
            score += min(haystack.count(term), 3)
        if score:
            ranked.append((score, card))
    ranked.sort(key=lambda item: (-item[0], item[1].get("id", "")))
    return [item for _, item in ranked[:limit]]


def route_packs(text: str, packs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    routed: list[dict[str, Any]] = []
    for pack in packs:
        triggers = pack.get("triggers", [])
        hits = [trigger for trigger in triggers if trigger and trigger in text]
        if pack.get("id") == "common" or hits:
            item = dict(pack)
            item["route_hits"] = hits
            routed.append(item)
    return routed


def approved_expressions(packs: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    approved: dict[str, dict[str, Any]] = {}
    for pack in packs:
        for term in pack.get("terms", []):
            if term.get("status") != "approved":
                continue
            approved[term["text"]] = term
            for variant in term.get("variants", []):
                approved[variant] = term
        for phrase in pack.get("phrases", []):
            if phrase.get("status") == "approved":
                approved[phrase["text"]] = phrase
    return approved


def line_position(line: str, current: str) -> str:
    stripped = line.strip()
    if re.match(r"^#\s+", stripped) or re.search(r"<h1(?:\s|>)", stripped, re.I):
        return "title"
    if re.match(r"^#{2,6}\s+", stripped) or re.search(r"<h[2-6](?:\s|>)", stripped, re.I):
        return "summary"
    if any(marker in stripped for marker in ("核心结论", "核心定位", "关键结论", "core-conclusion", "key-claim")):
        return "claim"
    if stripped.startswith("**") and stripped.endswith("**"):
        return "claim"
    return current if current in {"title", "claim"} and not stripped else "body"


def mask_approved(text: str, approved: dict[str, dict[str, Any]]) -> str:
    masked = text
    protected = [
        expression for expression, metadata in approved.items()
        if metadata.get("type") == "product"
    ]
    for expression in sorted(protected, key=len, reverse=True):
        masked = masked.replace(expression, "〓" * len(expression))
    return masked


def lint_text(text: str, packs: list[dict[str, Any]]) -> tuple[list[Finding], list[dict[str, Any]]]:
    routed = route_packs(text, packs)
    approved = approved_expressions(routed)
    findings: list[Finding] = []
    position = "body"
    seen: set[tuple[int, str, str]] = set()
    novel_suffixes = "引擎|载体|飞轮|底座|抓手|矩阵|闭环"

    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.strip().startswith("```"):
            continue
        position = line_position(raw, position)
        visible = re.sub(r"<[^>]+>|`[^`]*`", "", raw)
        masked = mask_approved(visible, approved)

        for pack in routed:
            for rule in pack.get("discouraged", []):
                term = rule["text"]
                if term not in masked or position not in rule.get("positions", [position]):
                    continue
                key = (lineno, "discouraged", term)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(Finding(
                    lineno, position, rule.get("level", "medium"), "business_language",
                    term, rule.get("reason", "来源或适用场景不足"),
                    rule.get("suggestions", []), [],
                ))
            for item in pack.get("technical_terms", []):
                term = item["text"]
                if term and term in visible:
                    findings.append(Finding(
                        lineno, position, "medium", "technical_term", term,
                        "面向业务听众时需要换成业务解释",
                        [item["replacement"]] if item.get("replacement") else [], [],
                    ))
            for item in pack.get("tone_patterns", []):
                if item["text"] in visible:
                    findings.append(Finding(
                        lineno, position, "medium", "tone", item["text"],
                        item["reason"], [], [],
                    ))

        if position in {"title", "claim", "summary"}:
            for match in re.finditer(rf"[一-鿿]{{2,12}}(?:{novel_suffixes})", masked):
                phrase = match.group(0)
                key = (lineno, "novel_claim", phrase)
                if key not in seen:
                    seen.add(key)
                    findings.append(Finding(
                        lineno, position, "high", "unverified_claim", phrase,
                        "标题或核心主张中出现未在业务词包登记的抽象概念",
                        [], [],
                    ))

    return findings, routed


def write_report(path: Path, findings: list[Finding], routed: list[dict[str, Any]]) -> None:
    payload = {
        "mode": "shadow",
        "blocked": False,
        "packs": [{"id": p.get("id"), "hits": p.get("route_hits", [])} for p in routed],
        "findings": [asdict(item) for item in findings],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


REUSABLE_FEEDBACK_RESULTS = {"owner_feedback", "owner_selected", "accepted_final"}
FEEDBACK_CONTEXT_WILDCARDS = {"", "all", "any", "*"}


def feedback_terms(text: str) -> set[str]:
    """Return explainable Latin words and short CJK n-grams for scene matching."""
    terms = set(re.findall(r"[a-z0-9][a-z0-9_-]+", text.lower()))
    for chunk in re.findall(r"[一-鿿]+", text):
        if len(chunk) <= 4:
            terms.add(chunk)
            continue
        for size in (2, 3, 4):
            terms.update(chunk[index:index + size] for index in range(len(chunk) - size + 1))
    return terms


def feedback_context_matches(event_value: str, requested: str) -> bool:
    event_normalized = str(event_value or "").strip().lower()
    requested_normalized = str(requested or "").strip().lower()
    if requested_normalized in FEEDBACK_CONTEXT_WILDCARDS:
        return True
    return event_normalized == requested_normalized


def is_owner_feedback(event: dict[str, Any]) -> bool:
    source = event.get("source")
    return isinstance(source, dict) and source.get("kind") == "owner"


def check_feedback_application(
    text: str, applicable: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Verify that exact replacement feedback did not regress in a finished draft."""
    violations: list[dict[str, Any]] = []
    checked = 0
    for event in applicable:
        before = str(event.get("before", "")).strip()
        after = str(event.get("after", "")).strip()
        if not before or not after:
            continue
        checked += 1
        after_present = after in text
        residual_text = text.replace(after, "") if after_present else text
        before_present = before in residual_text
        if before_present:
            violations.append({
                "before": before,
                "after": after,
                "reason": event.get("reason", ""),
                "before_present": before_present,
                "after_present": after_present,
            })
    return {"passed": not violations, "checked": checked, "violations": violations}


def query_feedback(
    query: str,
    events: Iterable[dict[str, Any]],
    audience: str,
    material_type: str,
    limit: int = 5,
) -> dict[str, Any]:
    """Find owner-confirmed feedback that is reusable in the requested scene."""
    query_terms = feedback_terms(query)
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, raw_event in enumerate(events):
        event = dict(raw_event)
        if event.get("result") not in REUSABLE_FEEDBACK_RESULTS:
            continue
        if not is_owner_feedback(event):
            continue
        if event.get("reuse_scope", "once") == "once":
            continue
        reuse_scope = event.get("reuse_scope")
        if reuse_scope == "similar":
            if str(event.get("audience", "")).strip().lower() != audience.strip().lower():
                continue
            if str(event.get("material_type", "")).strip().lower() != material_type.strip().lower():
                continue
        else:
            if not feedback_context_matches(event.get("audience", ""), audience):
                continue
            if not feedback_context_matches(event.get("material_type", ""), material_type):
                continue
        evidence = " ".join(str(event.get(field, "")) for field in
                            ("topic", "before", "after", "reason"))
        overlap = sorted(query_terms & feedback_terms(evidence))
        if reuse_scope == "similar" and not overlap:
            continue

        score = len(overlap)
        score += 3 if str(event.get("audience", "")).lower() == audience.lower() else 0
        score += 3 if str(event.get("material_type", "")).lower() == material_type.lower() else 0
        score += 2 if reuse_scope == "stable" else 0
        event["match"] = {
            "audience": event.get("audience", ""),
            "material_type": event.get("material_type", ""),
            "terms": overlap,
            "score": score,
        }
        ranked.append((score, index, event))

    conflict_keys: set[str] = set()
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for _, index, event in ranked:
        key = re.sub(r"\s+", "", str(event.get("before", ""))).lower()
        if key:
            grouped.setdefault(key, []).append((index, event))

    conflicts: list[dict[str, Any]] = []
    for key, members in grouped.items():
        alternatives = {
            str(event.get("after", "")).strip()
            for _, event in members
            if str(event.get("after", "")).strip()
        }
        if len(alternatives) < 2:
            continue
        conflict_keys.add(key)
        ordered = [event for _, event in sorted(members, key=lambda item: item[0])]
        conflicts.append({
            "before": ordered[0].get("before", ""),
            "alternatives": list(dict.fromkeys(event.get("after", "") for event in ordered)),
            "events": ordered,
            "requires_owner_choice": True,
        })

    ranked.sort(key=lambda item: (-item[0], -item[1]))
    applicable = [
        event for _, _, event in ranked
        if re.sub(r"\s+", "", str(event.get("before", ""))).lower() not in conflict_keys
    ]
    return {
        "query": query,
        "audience": audience,
        "material_type": material_type,
        "applicable": applicable[:limit],
        "conflicts": conflicts,
    }


def feedback_event(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "before": args.before,
        "after": args.after,
        "reason": args.reason,
        "audience": args.audience,
        "material_type": args.material_type,
        "topic": getattr(args, "topic", ""),
        "reuse_scope": getattr(args, "reuse_scope", "once"),
        "result": args.result,
        "source": {"kind": getattr(args, "source_kind", "owner")},
        "status": "candidate",
    }


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def load_feedback(path: Path = RUNTIME_DIR / "feedback.jsonl") -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def extract_candidates(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    pattern = re.compile(r"[一-鿿A-Za-z0-9]{2,8}(?:名单|工具|策略|方法|流程|规则|地图|能力)")
    leading_noise = ("今天核对", "再次核对", "需要核对", "核对", "看看", "讨论")
    for record in records:
        content = str(record.get("content", ""))
        for phrase in pattern.findall(content):
            for prefix in leading_noise:
                if phrase.startswith(prefix) and len(phrase) > len(prefix) + 1:
                    phrase = phrase[len(prefix):]
                    break
            item = counts.setdefault(phrase, {"text": phrase, "count": 0, "sources": []})
            item["count"] += 1
            if len(item["sources"]) < 5:
                item["sources"].append({
                    "source": record.get("source", "unknown"),
                    "timestamp": record.get("timestamp"),
                    "speaker": record.get("speaker", "anonymous"),
                })
    return sorted(counts.values(), key=lambda item: (-item["count"], item["text"]))


# 写作技巧的候选定位器。
#
# ⚠️ 关键设计：**这里不生成技巧，只定位「值得人看一眼」的段落。**
# 一条技巧的核心是 problem / technique / avoid_when 三个字段，它们是判断，
# 正则产不出判断。早期版本让外部资料走业务名词正则，抽出来的全是
# 「XX方法」「XX能力」这类短语 —— 看着像结果，其实没有任何可复用信息。
# 所以这里只做机械可靠的事：认出带对照结构的句子，输出待补全的骨架。
TECHNIQUE_PATTERNS = (
    ("contrast",       re.compile(r"不是.{1,30}?[，,]?\s*而是|与其.{1,30}?[，,]?\s*不如")),
    ("before_after",   re.compile(r"(?:以前|过去|原来|此前).{2,60}?(?:现在|如今|改成|now)")),
    ("number_reading", re.compile(r"\d+(?:\.\d+)?%?.{0,12}?(?:这说明|意味着|所以|因此|说明)")),
    ("myth_break",     re.compile(r"(?:看起来|通常认为|直觉上|表面上).{2,60}?(?:实际|其实|但)")),
)

TECHNIQUE_SKELETON_TODO = "TODO 由人或模型补全"


def extract_technique_candidates(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """定位带对照结构的段落，产出待补全的技巧骨架（不产出技巧本身）。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        content = str(record.get("content", ""))
        for sentence in re.split(r"[。！？\n]", content):
            sentence = sentence.strip()
            if len(sentence) < 8:
                continue
            for name, pattern in TECHNIQUE_PATTERNS:
                if not pattern.search(sentence):
                    continue
                key = f"{name}:{sentence}"
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "id": f"cand-{len(out) + 1:03d}",
                    "pattern_hit": name,
                    "excerpt": sentence,
                    "source": {
                        "kind": "external",
                        "ref": record.get("source", "unknown"),
                        "timestamp": record.get("timestamp"),
                    },
                    # 以下四项是一条技巧的真正内容，正则给不出，留空待补
                    "title": TECHNIQUE_SKELETON_TODO,
                    "problem": TECHNIQUE_SKELETON_TODO,
                    "technique": TECHNIQUE_SKELETON_TODO,
                    "avoid_when": TECHNIQUE_SKELETON_TODO,
                    "status": "candidate",
                    "promotion": "forbidden",
                })
                break
    return out


def load_techniques(technique_dir: Path = TECHNIQUE_DIR) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(technique_dir.glob("*.yaml")):
        for item in load_yaml(path).get("techniques", []):
            entry = dict(item)
            entry["technique_file"] = path.name
            items.append(entry)
    return items


def query_techniques(query: str, items: Iterable[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """按场景检索技巧。候选态一并返回，但保留 status 供调用方判断。"""
    terms = [t for t in re.findall(r"[一-鿿]{2,}|[A-Za-z]{2,}", query.lower()) if t]
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        hay = " ".join(str(item.get(k, "")) for k in
                       ("title", "category", "problem", "technique")).lower()
        hay += " " + " ".join(item.get("use_when", []) or [])
        score = sum(3 if t in str(item.get("title", "")).lower() else 1
                    for t in terms if t in hay)
        if score:
            ranked.append((score, item))
    ranked.sort(key=lambda x: (-x[0], x[1].get("id", "")))
    return [i for _, i in ranked[:limit]]


def ingest_payload(records: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    external = kind == "external"
    return {
        "namespace": "external-writing-methods" if external else "business-language-candidates",
        "status": "candidate",
        "promotion_to_business_pack": "forbidden" if external else "owner_confirmation_required",
        # 外部资料学的是写法，不是业务词 —— 走技巧定位器，产出待补全骨架
        "items": extract_technique_candidates(records) if external else extract_candidates(records),
    }


def sanitize_text(text: str, entities: list[str], number_scale: float | None = None) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    labels = ["实体甲", "实体乙", "实体丙", "实体丁", "实体戊", "实体己"]
    sanitized = text
    for index, entity in enumerate(sorted(set(entities), key=len, reverse=True)):
        if not entity:
            continue
        label = labels[index] if index < len(labels) else f"实体{index + 1}"
        mapping[entity] = label
        sanitized = sanitized.replace(entity, label)
    if number_scale is not None:
        sanitized = re.sub(
            r"(?<![A-Za-z])\d+(?:\.\d+)?(?![A-Za-z])",
            lambda m: f"{float(m.group(0)) * number_scale:g}",
            sanitized,
        )
    return sanitized, mapping


def content_digest(text: str, entities: list[str], scale: float | None) -> str:
    raw = json.dumps([text, sorted(entities), scale], ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


DEFAULT_REVEAL = {
    # 评完再揭晓谁是谁 —— 换成你实际使用的模型名。
    # candidate-c 是唯一拿到原稿的角色，请指定可信通道内的模型。
    "candidate-a": "model-a",
    "candidate-b": "model-b",
    "candidate-c": "model-c-trusted-channel",
}


def build_blind_packet(
    sanitized: str,
    digest: str,
    raw_internal_ref: str,
    reveal: dict[str, str] | None = None,
) -> dict[str, Any]:
    questions = [
        "听众听完能复述出什么核心判断",
        "哪些表达有真实业务指纹",
        "哪些句子像自创概念或通用套话",
        "哪些地方有现场感 哪些地方作者消失了",
        "哪些修改会伤害原稿已经成熟的表达",
    ]
    return {
        "id": digest,
        "anonymous_reviewers": {
            "candidate-a": {"role": "synthesis", "input": "sanitized", "questions": questions},
            "candidate-b": {"role": "logic", "input": "sanitized", "questions": questions},
            "candidate-c": {"role": "challenge", "input": "raw_internal_ref", "questions": questions},
        },
        "inputs": {"sanitized": sanitized, "raw_internal_ref": raw_internal_ref},
        "reveal": dict(reveal or DEFAULT_REVEAL),
        "decision": "owner_evidence_not_vote",
    }


def command_lint(args: argparse.Namespace) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    findings, routed = lint_text(text, load_packs(Path(args.pack_dir)))
    if args.report:
        write_report(Path(args.report), findings, routed)
    for item in findings:
        suggestions = f" 建议: {' / '.join(item.suggestions)}" if item.suggestions else ""
        print(f"L{item.line} [{item.level}/{item.position}] {item.text}: {item.reason}{suggestions}")
    print(f"影子检查：{len(findings)} 条提示，0 条阻断；词包：{', '.join(p['id'] for p in routed)}")
    return 0


def command_route(args: argparse.Namespace) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    routed = route_packs(text, load_packs(Path(args.pack_dir)))
    print(json.dumps([{"id": p["id"], "hits": p["route_hits"]} for p in routed], ensure_ascii=False, indent=2))
    return 0


def command_learn(args: argparse.Namespace) -> int:
    item = feedback_event(args)
    append_jsonl(Path(args.output), item)
    print(json.dumps(item, ensure_ascii=False))
    return 0


def command_feedback_query(args: argparse.Namespace) -> int:
    payload = query_feedback(
        args.query,
        load_feedback(Path(args.feedback_file)),
        audience=args.audience,
        material_type=args.material_type,
        limit=args.limit,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_feedback_check(args: argparse.Namespace) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    selected = query_feedback(
        args.query,
        load_feedback(Path(args.feedback_file)),
        audience=args.audience,
        material_type=args.material_type,
        limit=args.limit,
    )
    result = check_feedback_application(text, selected["applicable"])
    payload = {**result, "conflicts": selected["conflicts"]}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] and not payload["conflicts"] else 1


def command_ingest(args: argparse.Namespace) -> int:
    records = [json.loads(line) for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    payload = ingest_payload(records, args.kind)
    Path(args.output).write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"采集 {len(records)} 条记录，提取 {len(payload['items'])} 个候选；命名空间={payload['namespace']}；未自动转正")
    return 0


def command_knowledge_query(args: argparse.Namespace) -> int:
    cards = query_knowledge(args.query, load_knowledge(Path(args.knowledge_dir)), args.limit)
    payload = {
        "query": args.query,
        "matched": len(cards),
        "items": cards,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_technique_query(args: argparse.Namespace) -> int:
    items = query_techniques(args.query, load_techniques(Path(args.technique_dir)), args.limit)
    print(json.dumps({"query": args.query, "matched": len(items), "items": items},
                     ensure_ascii=False, indent=2))
    return 0


def command_sanitize(args: argparse.Namespace) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    sanitized, mapping = sanitize_text(text, args.entity or [], args.number_scale)
    digest = content_digest(text, args.entity or [], args.number_scale)
    output = Path(args.output) if args.output else RUNTIME_DIR / "sanitized" / f"{digest}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(sanitized, encoding="utf-8")
    map_path = output.with_suffix(output.suffix + ".mapping.json")
    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"digest": digest, "output": str(output), "mapping": str(map_path)}, ensure_ascii=False))
    return 0


def command_blind(args: argparse.Namespace) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    sanitized, _ = sanitize_text(text, args.entity or [], args.number_scale)
    digest = content_digest(text, args.entity or [], args.number_scale)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    internal_output = output.with_suffix(output.suffix + ".internal.md")
    internal_output.write_text(text, encoding="utf-8")
    packet = build_blind_packet(sanitized, digest, str(internal_output))
    output.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"匿名评测包已生成：{output}；仅 candidate-c 可见的原稿：{internal_output}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--pack-dir", default=str(PACK_DIR))
    sub = root.add_subparsers(dest="command", required=True)

    lint = sub.add_parser("lint")
    lint.add_argument("file")
    lint.add_argument("--report")
    lint.set_defaults(func=command_lint)

    route = sub.add_parser("route")
    route.add_argument("file")
    route.set_defaults(func=command_route)

    learn = sub.add_parser("learn")
    learn.add_argument("--before", required=True)
    learn.add_argument("--after", required=True)
    learn.add_argument("--reason", required=True)
    learn.add_argument("--audience", required=True)
    learn.add_argument("--material-type", required=True)
    learn.add_argument("--topic", default="")
    learn.add_argument("--reuse-scope", choices=["once", "similar", "stable"], default="similar")
    learn.add_argument("--result", default="owner_feedback")
    learn.add_argument("--source-kind", choices=["owner", "model", "chat", "document"], default="owner")
    learn.add_argument("--output", default=str(RUNTIME_DIR / "feedback.jsonl"))
    learn.set_defaults(func=command_learn)

    feedback = sub.add_parser("feedback-query")
    feedback.add_argument("query")
    feedback.add_argument("--audience", required=True)
    feedback.add_argument("--material-type", required=True)
    feedback.add_argument("--feedback-file", default=str(RUNTIME_DIR / "feedback.jsonl"))
    feedback.add_argument("--limit", type=int, default=5)
    feedback.set_defaults(func=command_feedback_query)

    feedback_check = sub.add_parser("feedback-check")
    feedback_check.add_argument("file")
    feedback_check.add_argument("query")
    feedback_check.add_argument("--audience", required=True)
    feedback_check.add_argument("--material-type", required=True)
    feedback_check.add_argument("--feedback-file", default=str(RUNTIME_DIR / "feedback.jsonl"))
    feedback_check.add_argument("--limit", type=int, default=5)
    feedback_check.set_defaults(func=command_feedback_check)

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--input", required=True, help="DC或外部采集器输出的JSONL")
    ingest.add_argument("--output", required=True)
    ingest.add_argument("--kind", choices=["dc", "external"], default="dc")
    ingest.set_defaults(func=command_ingest)

    knowledge = sub.add_parser("knowledge-query")
    knowledge.add_argument("query")
    knowledge.add_argument("--knowledge-dir", default=str(KNOWLEDGE_DIR))
    knowledge.add_argument("--limit", type=int, default=5)
    knowledge.set_defaults(func=command_knowledge_query)

    technique = sub.add_parser("technique-query")
    technique.add_argument("query")
    technique.add_argument("--technique-dir", default=str(TECHNIQUE_DIR))
    technique.add_argument("--limit", type=int, default=5)
    technique.set_defaults(func=command_technique_query)

    sanitize = sub.add_parser("sanitize")
    sanitize.add_argument("file")
    sanitize.add_argument("--entity", action="append")
    sanitize.add_argument("--number-scale", type=float)
    sanitize.add_argument("--output")
    sanitize.set_defaults(func=command_sanitize)

    blind = sub.add_parser("blind-packet")
    blind.add_argument("file")
    blind.add_argument("--entity", action="append")
    blind.add_argument("--number-scale", type=float)
    blind.add_argument("--output", required=True)
    blind.set_defaults(func=command_blind)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
