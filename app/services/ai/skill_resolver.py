"""从用户自然语言中解析并匹配可用技能（按 name/id 模糊匹配）。"""
from __future__ import annotations

import os
import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SKILL_USE_PATTERNS = [
    re.compile(r"使用(?:一下|下)?[「\"']?(.+?)[」\"']?(?:技能|skill)", re.I),
    re.compile(r"用(?:一下|下)?[「\"']?(.+?)[」\"']?(?:技能|skill)", re.I),
    re.compile(r"(?:执行|运行|触发|加载|套用|按照)(?:一下|下)?[「\"']?(.+?)[」\"']?(?:技能|skill)", re.I),
    re.compile(r"(?:技能|skill)[「\"']?(.+?)[」\"']?(?:执行|运行|查|查询)", re.I),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _validate_skill_id(skill_id: str) -> bool:
    if not skill_id or "/" in skill_id or "\\" in skill_id or ".." in skill_id:
        return False
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", skill_id))


def _parse_skill_frontmatter(skill_id: str, skill_md_path: str) -> Dict[str, str]:
    from app.utils.skill_metadata import parse_skill_frontmatter

    return parse_skill_frontmatter(skill_id, skill_md_path)


def list_skill_metas() -> List[Dict[str, str]]:
    """扫描技能目录，返回 id/name/description 摘要列表。"""
    try:
        from app.core.config import settings

        skills_dir = settings.SKILLS_DIR
    except Exception:
        return []

    if not skills_dir or not os.path.exists(skills_dir):
        return []

    metas: List[Dict[str, str]] = []
    for item in sorted(os.listdir(skills_dir)):
        if item.startswith("."):
            continue
        item_path = os.path.join(skills_dir, item)
        if not os.path.isdir(item_path):
            continue
        if not _validate_skill_id(item):
            continue
        skill_md_path = os.path.join(item_path, "SKILL.md")
        meta = _parse_skill_frontmatter(item, skill_md_path)
        meta["skill_md_path"] = skill_md_path
        metas.append(meta)
    return metas


def load_skill_md_content(skill_id: str, max_bytes: int = 262144) -> Optional[str]:
    """读取技能 SKILL.md 全文；失败返回 None。"""
    if not _validate_skill_id(skill_id):
        return None
    try:
        from app.core.config import settings

        skills_dir = os.path.abspath(settings.SKILLS_DIR)
        skill_md_path = os.path.abspath(os.path.join(skills_dir, skill_id, "SKILL.md"))
        if os.path.commonpath([skills_dir, skill_md_path]) != skills_dir:
            return None
        if not os.path.exists(skill_md_path):
            return None
        with open(skill_md_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(max_bytes)
    except Exception as e:
        logger.warning("[Skills] Failed to read SKILL.md for %s: %s", skill_id, e)
        return None


def _extract_skill_hints(user_query: str) -> List[str]:
    hints: List[str] = []
    for pattern in _SKILL_USE_PATTERNS:
        match = pattern.search(user_query)
        if not match:
            continue
        hint = (match.group(1) or "").strip("「」\"' \t，,。.")
        if hint and len(hint) >= 2:
            hints.append(hint)
    return hints


def _score_skill_match(hint: str, meta: Dict[str, str]) -> float:
    hint_n = _normalize(hint)
    if not hint_n:
        return 0.0
    name_n = _normalize(meta.get("name", ""))
    id_n = _normalize(meta.get("id", ""))
    desc_n = _normalize(meta.get("description", ""))

    if hint_n == name_n or hint_n == id_n:
        return 1.0
    if hint_n in name_n or name_n in hint_n:
        return 0.9
    if hint_n in id_n or id_n in hint_n:
        return 0.85
    if hint_n in desc_n:
        return 0.7
    return 0.0


def resolve_skills_from_query(user_query: str, max_results: int = 2) -> List[Dict[str, Any]]:
    """从用户问题中解析技能引用并按 name/id 匹配可用技能。

    例如「使用用户列表查询技能查询一次」→ 匹配 name 含「用户列表查询」的技能。
    """
    query = (user_query or "").strip()
    if not query:
        return []

    hints = _extract_skill_hints(query)
    if not hints and not any(token in query.lower() for token in ("技能", "skill")):
        return []

    metas = list_skill_metas()
    if not metas:
        return []

    scored: List[tuple[float, Dict[str, str]]] = []
    for hint in hints:
        for meta in metas:
            score = _score_skill_match(hint, meta)
            if score >= 0.7:
                scored.append((score, meta))

    # 兜底：用户直接在句子里提到技能 display_name
    if not scored:
        for meta in metas:
            name = (meta.get("name") or "").strip()
            if len(name) >= 2 and name in query:
                scored.append((0.75, meta))

    scored.sort(key=lambda item: item[0], reverse=True)
    seen_ids: set[str] = set()
    results: List[Dict[str, Any]] = []
    for _, meta in scored:
        skill_id = meta["id"]
        if skill_id in seen_ids:
            continue
        seen_ids.add(skill_id)
        results.append(dict(meta))
        if len(results) >= max_results:
            break
    return results
