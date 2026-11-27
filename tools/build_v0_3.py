#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_v0_3.py —— 生成 v0.3 数据集包（拆标志 + 11 字词表）。

改动清单（相对 v0.2 候选）：
  1. cases 增加四个字段：claimed_pccp_coverage / actually_within_scope /
     criteria_measured / criteria_met，并保留老九标志以向后兼容；
  2. bench.py 的 TAGS 由 6 字扩到 11 字（词表不足的现场证据见
     语义与标志审计_20261127.md 第三节）；
  3. adapter_reference.py 换为 v0.3 版：先在编码层展开，再用同一判器；
  4. DATASET_CARD.md 追加 v0.3 段（含"哪些是合成、哪些有一手引用"）。
判器字节一字不改（snapshot/judge_pccp.py 保持原样）。
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

# 直接从判器取已知变更类型集合，避免我这边抄一份走样
sys.path.insert(0, os.path.join(HERE, "repro"))
try:
    from lgd_engine.judges.judge_pccp import KNOWN_CHANGE_TYPES  # noqa: E402
except Exception:  # pragma: no cover
    KNOWN_CHANGE_TYPES = set()

TAGS_V03 = '''TAGS = ("ok_covered", "outside_scope", "acceptance_not_met",
        "evidence_missing", "intended_use_change", "unclassifiable",
        "no_pccp_authorized", "not_se_to_predicate", "validation_missing",
        "labeling_version_history_missing", "udi_not_regenerated")
# v0.3：原 6 字扩到 11 字。理由不是"想细分"，而是原词表里有三条判决理由
# 根本说不出来（P-CRIT-01 无授权 PCCP、P-CRIT-04 破 SE、P-MAJ-03/05/06
# 三类可补救缺失在词表里全落到 unclassifiable）。'''
TAGS_OLD = '''TAGS = ("ok_covered", "outside_scope", "acceptance_not_met",
        "evidence_missing", "intended_use_change", "unclassifiable")'''

ADAPTER_V03 = '''"""Reference adapter（v0.3）：先展开编码，再用同一个判器。

v0.3 事实把两个被压扁的标志拆成四个：
  claimed_pccp_coverage / actually_within_scope   （主张 vs 事实）
  criteria_measured / criteria_met                （测没测 vs 达没达）
本文件在编码层把它们展开回判器认识的九标志，判器一行未改。

展开式（四种组合逐一验过，见 v03编码层修复_20261127.md）：
  change_within_pccp_scope = claimed AND (actual OR NOT authorized)
  acceptance_criteria_met  = None 若未按类型测；否则 = met

标签优先级 = R1 语义（可补救 → hold，不可补救 → reject），11 字词表。
"""
from __future__ import annotations

import os
import sys

ENGINE_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_ROOT)
from lgd_engine.judges.judge_pccp import JudgePccpScope  # noqa: E402

_JUDGE = JudgePccpScope()

RULE_TO_TAG = [
    ("P-CRIT-04", "not_se_to_predicate"),
    ("P-CRIT-05", "not_se_to_predicate"),
    ("P-CRIT-02", "intended_use_change"),
    ("P-CRIT-01", "no_pccp_authorized"),
    ("P-CRIT-03", "acceptance_not_met"),
    ("P-MAJ-01", "outside_scope"),
    ("P-MAJ-03", "validation_missing"),
    ("P-MAJ-05", "labeling_version_history_missing"),
    ("P-MAJ-06", "udi_not_regenerated"),
    ("P-MAJ-04", "unclassifiable"),
    ("P-MAJ-07", "evidence_missing"),
    ("L2-EVIDENCED", "evidence_missing"),
]


def expand(ctx):
    ctx = dict(ctx)
    auth = ctx.get("pccp_authorized")
    claim = ctx.get("claimed_pccp_coverage")
    actual = ctx.get("actually_within_scope")
    if claim is None:
        claim = ctx.get("change_within_pccp_scope")
    if actual is None:
        actual = ctx.get("change_within_pccp_scope")
    ctx["change_within_pccp_scope"] = bool(claim) and (bool(actual) or auth is False)

    measured = ctx.get("criteria_measured")
    if measured is None:
        pass
    elif measured is not True:
        ctx["acceptance_criteria_met"] = None
    else:
        ctx["acceptance_criteria_met"] = ctx.get("criteria_met")
    return ctx


def _tag(verdict, reasons):
    fired = [str(r.get("rule", "")) if hasattr(r, "get") else str(r) for r in reasons]
    for prefix, tag in RULE_TO_TAG:
        if any(f.startswith(prefix) for f in fired):
            return tag
    if verdict == "go":
        return "ok_covered"
    return "unclassifiable"


def evaluate(ctx):
    res = _JUDGE.evaluate(expand(ctx))
    verdict = res.get("verdict")
    return {"verdict": verdict, "tag": _tag(verdict, res.get("reasons", [])),
            "reasons": res.get("reasons", [])}
'''


def derive_v03(c):
    """R1 语义，直接在 v0.3 事实上推导。"""
    if c.get("affects_intended_use") is True:
        return "reject", "intended_use_change"
    if c.get("remains_se_to_predicate") is False:
        return "reject", "not_se_to_predicate"
    if c.get("pccp_modified_version_used_as_predicate") is True:
        return "reject", "not_se_to_predicate"
    if c.get("claimed_pccp_coverage") is True and c.get("pccp_authorized") is False:
        return "reject", "no_pccp_authorized"
    if c.get("criteria_measured") is True and c.get("criteria_met") is False:
        return "reject", "acceptance_not_met"
    if c.get("pccp_authorized") is None:
        return "hold", "unclassifiable"
    if c.get("claimed_pccp_coverage") is True and c.get("actually_within_scope") is False:
        return "hold", "outside_scope"
    if c.get("claimed_pccp_coverage") is False and c.get("actually_within_scope") is False:
        return "hold", "outside_scope"
    if c.get("change_class_described") is not True:
        return "hold", "unclassifiable"
    if c.get("validation_documented") is not True:
        return "hold", "validation_missing"
    if c.get("labeling_version_history") is not True:
        return "hold", "labeling_version_history_missing"
    if c.get("udi_updated") is not True:
        return "hold", "udi_not_regenerated"
    if c.get("criteria_measured") is not True:
        return "hold", "unclassifiable"
    if c.get("evidence_sufficiency") in {"needs_supplement", "none"}:
        return "hold", "evidence_missing"
    if KNOWN_CHANGE_TYPES and c.get("change_type") not in KNOWN_CHANGE_TYPES:
        # 判器的 P-MAJ-10：change_type 不能分类 → hold（unknown 不是 safe default）
        return "hold", "unclassifiable"
    return "go", "ok_covered"


def to_v03(c, overrides=None):
    c = dict(c)
    if overrides:
        c.update(overrides)
    if "claimed_pccp_coverage" not in c:
        c["claimed_pccp_coverage"] = c.get("change_within_pccp_scope")
    if "actually_within_scope" not in c:
        c["actually_within_scope"] = c.get("change_within_pccp_scope")
    if "criteria_measured" not in c:
        c["criteria_measured"] = None if c.get("acceptance_criteria_met") is None else True
    if "criteria_met" not in c:
        c["criteria_met"] = c.get("acceptance_criteria_met")
    v, t = derive_v03(c)
    c["expected_verdict"], c["expected_tag"] = v, t
    return c


CARD_V03 = """

## v0.3（2026-11-27，候选，未发布）

- 事实层：新增 `claimed_pccp_coverage` / `actually_within_scope` / `criteria_measured` / `criteria_met` 四个字段，
  把 v0.2 里"一颗标志兼两义"的缺陷拆开。老九标志全部保留（向后兼容）。
- 词表：`TAGS` 由 6 字扩到 11 字。原因有实例——`SYN-NO-PCCP-ROADMAP` 判出 reject，
  而六字词表没有"没有授权 PCCP"这个词，只能落 `unclassifiable`。
- 判器：`snapshot/judge_pccp.py` **一字未改**。编码展开在 adapter 里做，
  兼容性回归 51 条 0 判决变化。
- 标签语义：R1（可补救 → hold，不可补救 → reject），逐条由写死的规则表推导，来源字段标 `label_provenance`。
- 仍存在的缺口：题面长度中位仍低于 FDA `ao_statement` 中位 463 字符；`reject` 与 `affects_intended_use=True`
  覆盖偏少；10 条隐藏题不随包发布；无真实 PCCP 变更回放。
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-zip", required=True)
    ap.add_argument("--cases", default=os.path.join(HERE, "out", "cases_public_v0_2c.json"))
    ap.add_argument("--out-zip", required=True)
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="pccp_v03_")
    with zipfile.ZipFile(a.base_zip) as z:
        z.extractall(tmp)
    dd = os.path.join(tmp, "dataset")

    src = json.load(open(a.cases, encoding="utf-8"))
    cases = src.get("cases", src)
    v03 = [to_v03(c) for c in cases]
    json.dump({"cases": v03}, open(os.path.join(dd, "cases_public.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    bench_p = os.path.join(dd, "bench.py")
    s = open(bench_p, encoding="utf-8").read()
    assert TAGS_OLD in s, "bench.py 里找不到原 TAGS，包结构变了？"
    open(bench_p, "w", encoding="utf-8").write(s.replace(TAGS_OLD, TAGS_V03))

    open(os.path.join(dd, "adapter_reference.py"), "w", encoding="utf-8").write(ADAPTER_V03)

    card_p = os.path.join(dd, "DATASET_CARD.md")
    open(card_p, "a", encoding="utf-8").write(CARD_V03)

    with zipfile.ZipFile(a.out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(tmp):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, tmp).replace("\\", "/"))

    print("out:", a.out_zip, os.path.getsize(a.out_zip), "bytes")
    mix = {}
    for c in v03:
        mix[c["expected_verdict"]] = mix.get(c["expected_verdict"], 0) + 1
    print("cases:", len(v03), "mix:", mix,
          "baseline:", round(max(mix.values()) / len(v03), 4))
    tags = sorted({c["expected_tag"] for c in v03})
    print("tags used:", tags)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
