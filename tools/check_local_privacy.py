#!/usr/bin/env python3
"""阻止本地聊天扫描与个人评价材料进入 Git 暂存区。

装成 pre-commit hook 即可：
    python3 tools/check_local_privacy.py || exit 1
命中时返回 1 并列出违规文件，不做任何自动修改。
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class Violation:
    path: str
    reason: str


# 本地私密区：路径出现在仓库任何层级都算命中
LOCAL_ONLY_PATHS = (
    re.compile(r"(?:^|/)\.runtime(?:/|$)"),
    re.compile(r"(?:^|/)references/sources\.local\.yaml$"),
)

# 文件名一看就是聊天扫描产物
SCAN_ARTIFACT_NAMES = (
    re.compile(r"(?:^|[-_.])(?:dc|chat|im)[-_.]?scan(?:[-_.]|$)", re.I),
    re.compile(r"(?:^|[-_.])(?:dc|chat|im)[-_.]?candidates?(?:[-_.]|$)", re.I),
    re.compile(r"(?:^|[-_.])chat[-_.]?(?:export|corpus|dump)(?:[-_.]|$)", re.I),
)

CONTENT_RULES = (
    (re.compile(r"(?m)^\s*(?:privacy|visibility)\s*:\s*local_only\s*$", re.I), "标记为仅限本地"),
    (re.compile(r"(?m)^\s*(?:contains_)?personal_(?:assessment|evaluation)\s*:\s*true\s*$", re.I), "包含个人判断或评价标记"),
    (re.compile(r"(?m)^\s*(?:source_type|kind)\s*:\s*(?:personal_chat|chat_supported|dc_supported)\s*$", re.I), "知识来源于个人聊天扫描"),
    (re.compile(r"(?m)^\s*ref\s*:\s*.*聊天扫描.*$", re.I), "引用聊天扫描结论"),
    (re.compile(r'(?s)(?=.*"content"\s*:)(?=.*"source(?:_id)?"\s*:)(?=.*"speaker"\s*:)(?=.*"timestamp"\s*:)'), "包含聊天记录结构"),
)

CONTENT_EXTENSIONS = {".yaml", ".yml", ".json", ".jsonl", ".md", ".txt"}


def inspect_item(path: str, content: str) -> list[Violation]:
    normalized = PurePosixPath(path).as_posix()
    violations: list[Violation] = []
    if any(pattern.search(normalized) for pattern in LOCAL_ONLY_PATHS):
        violations.append(Violation(normalized, "路径属于本地私密区"))
    if any(pattern.search(PurePosixPath(normalized).name) for pattern in SCAN_ARTIFACT_NAMES):
        violations.append(Violation(normalized, "文件名表明它是聊天扫描产物"))
    if PurePosixPath(normalized).suffix.lower() in CONTENT_EXTENSIONS:
        for pattern, reason in CONTENT_RULES:
            if pattern.search(content):
                violations.append(Violation(normalized, reason))
    return violations


def git(repo: str, *args: str, text: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", repo, *args],
        check=False,
        capture_output=True,
        text=text,
    )


def staged_paths(repo: str = ".") -> list[str]:
    result = git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return [item.decode("utf-8", errors="replace") for item in result.stdout.split(b"\0") if item]


def staged_content(repo: str, path: str) -> str:
    result = git(repo, "show", f":{path}")
    if result.returncode != 0:
        return ""
    if b"\0" in result.stdout:
        return ""
    return result.stdout.decode("utf-8", errors="replace")


def scan_staged(repo: str = ".") -> list[Violation]:
    violations: list[Violation] = []
    for path in staged_paths(repo):
        violations.extend(inspect_item(path, staged_content(repo, path)))
    return violations


def main() -> int:
    try:
        violations = scan_staged()
    except RuntimeError as error:
        print(f"个人聊天材料检查失败：{error}", file=sys.stderr)
        return 2
    if not violations:
        return 0
    print("提交已阻断：以下内容涉及本地聊天扫描或个人评价，不应进入 Git：", file=sys.stderr)
    for item in violations:
        print(f"- {item.path}：{item.reason}", file=sys.stderr)
    print("请将内容移到 .runtime/（已被 .gitignore 排除），并取消暂存。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
