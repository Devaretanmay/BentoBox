import re

TASK_PROFILES = {
    "code": ["upgrade", "update", "bump", "add", "install", "generate", "create", "write", "refactor", "restructure"],
    "debugging": ["fix", "bug", "error", "crash", "broken", "issue"],
    "research": ["explore", "investigate", "understand", "what", "how", "why", "list", "show", "find", "search"],
    "testing": ["test"],
    "security": ["security", "auth", "permission", "vulnerability", "injection"],
    "writing": ["document", "readme", "comment", "docstring", "docs"],
}


def classify(text: str) -> str:
    text_lower = text.strip().lower()
    for profile, keywords in TASK_PROFILES.items():
        for kw in keywords:
            if re.match(rf"^{kw}\b", text_lower):
                return profile
    return "code"
