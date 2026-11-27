"""DomainJudge Protocol + JudgeVerdict data structures.

Fixed schema (shared with parallel Demo2 line):
    JudgeVerdict = {
        "verdict": "go" | "hold" | "reject",
        "reasons": [{"rule": str, "level": "critical|major|minor", "detail": str}],
        "evidence": [{"kind": str, "ref": str}],
    }
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Protocol, runtime_checkable


VALID_VERDICTS = ("go", "hold", "reject")
VALID_LEVELS = ("critical", "major", "minor")


@dataclass
class Reason:
    rule: str
    level: str
    detail: str

    def __post_init__(self) -> None:
        if self.level not in VALID_LEVELS:
            raise ValueError(f"invalid reason level: {self.level}")


@dataclass
class Evidence:
    kind: str   # e.g. "fda_recall", "fda_510k", "nmpa_recall", "internal_verification"
    ref: str    # e.g. "Z-1924-2025", "K190204", URL, or local doc id


@dataclass
class JudgeVerdict:
    verdict: str                       # go | hold | reject
    reasons: List[Reason] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(f"invalid verdict: {self.verdict}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reasons": [asdict(r) for r in self.reasons],
            "evidence": [asdict(e) for e in self.evidence],
        }

    @property
    def has_critical(self) -> bool:
        return any(r.level == "critical" for r in self.reasons)


@runtime_checkable
class DomainJudge(Protocol):
    """Every domain adapter implements this. ctx is an input JSON dict."""

    domain: str

    def evaluate(self, ctx: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover - protocol
        ...

# ===== RECONSTRUCTED ADDITIONS (non-original) =====
# judge_pccp.py 里 `from .base import ... is_unusable, misused` 依赖这两个函数，
# 但本机引擎树里的 base.py 没有它们（发布快照与本地引擎树不同源）。
# 下面两个函数是**按判器用法重建**的，不是原字节。重建依据是它的唯一调用点：
#   _CONTRACT["when"] = lambda c: bool(is_unusable(c, REQUIRED_FIELDS) or misused(c, BOOL_FIELDS))
# 语义取"台账口径"：必填缺失/为空 → unusable；布尔字段给了非布尔值 → misused。
# 复用前必须知道：这两个函数的原始实现未公开，本重建不保证与作者版逐字一致。

def is_unusable(ctx, required_fields):
    """Required fields missing or empty -> the record cannot be judged."""
    for k, t in required_fields.items():
        if k not in ctx or ctx[k] is None:
            return True
        v = ctx[k]
        if isinstance(v, str) and not v.strip():
            return True
        if t is str and not isinstance(v, str):
            return True
    return False


def misused(ctx, bool_fields):
    """A field that should be a boolean carries something else (e.g. "true")."""
    for k in bool_fields:
        if k in ctx and ctx[k] is not None and not isinstance(ctx[k], bool):
            return True
    return False
