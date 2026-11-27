"""Reference adapter（可移植版）。

与原版 `dataset/adapter_reference.py` 的差别只有一处：引擎根目录不再是写死的
`D:\\Workbuddy\\...`，而是**本文件所在目录**——任何人把这份目录解压到任意位置都能跑。
这是"任何人换目录可复算 0.9688"的前提：路径写死的那份，除作者外没人能算出同一个分。
（注意措辞：本仓验过的只是"同操作者换干净目录干跑"（T3），不是第三方实测（T1）。

逻辑（规则→标签的优先级）与原版逐字一致，未改判据、未加后门。
"""
from __future__ import annotations

import os
import sys

ENGINE_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_ROOT)
from lgd_engine.judges.judge_pccp import JudgePccpScope  # noqa: E402

_JUDGE = JudgePccpScope()

RULE_TO_TAG = [
    ("P-CRIT-03", "acceptance_not_met"),
    ("P-CRIT-02", "intended_use_change"),
    ("P-MAJ-01", "outside_scope"),
    ("L2-EVIDENCED", "evidence_missing"),
    ("P-MAJ-10", "unclassifiable"),
]


def _tag(verdict: str, reasons: list) -> str:
    fired = [str(r.get("rule", "")) if hasattr(r, "get") else str(r) for r in reasons]
    for prefix, tag in RULE_TO_TAG:
        if any(f.startswith(prefix) for f in fired):
            return tag
    if verdict == "go":
        return "ok_covered"
    return "unclassifiable"


def evaluate(ctx):
    res = _JUDGE.evaluate(dict(ctx))
    verdict = res.get("verdict")
    return {"verdict": verdict, "tag": _tag(verdict, res.get("reasons", [])),
            "reasons": res.get("reasons", [])}
