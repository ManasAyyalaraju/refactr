import re
from typing import List


def normalize_skill(skill: str) -> str:
    """Lowercase and collapse whitespace for matching."""
    return re.sub(r"\s+", " ", skill.strip().lower())


def parse_skill_line(raw_skills: str) -> List[str]:
    """Split a pipe/comma/semicolon-separated skill line into a list."""
    if not raw_skills:
        return []
    normalized = raw_skills
    for sep in ["|", ";"]:
        normalized = normalized.replace(sep, ",")
    return [s.strip() for s in normalized.split(",") if s.strip()]


def merge_and_dedupe_skills(*skill_lists: List[str]) -> List[str]:
    merged: List[str] = []
    seen = set()
    for skills in skill_lists:
        for skill in skills or []:
            clean = skill.strip()
            if not clean:
                continue
            key = normalize_skill(clean)
            if key not in seen:
                seen.add(key)
                merged.append(clean)
    return merged
