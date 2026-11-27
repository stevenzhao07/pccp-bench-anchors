#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""relabel_v0_2.py —— 按 R1 判决语义重标 v0.2 候选集。

R1（2026-11-27 定）：判"可补救性"而不是判"严重程度"。
  不可补救 → reject：预期用途变更 / 破 SE / 主张 PCCP 覆盖却无授权 PCCP /
                     实测验收指标未达 / 以改动版当谓词
  可补救   → hold  ：出范围（含"根本没有授权 PCCP"且未主张走 PCCP 路线）/
                     类别未描述 / 验证未留档 / 标签无版本历史 / UDI 未更新 /
                     验收未测 / 授权状态未述 / 证据不足
  其余     → go

只改 expected_verdict / expected_tag，题面与九个标志一字不动。
所有被改的记录写进 diff 日志，并打 label_provenance: rule_r1_20261127。
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# (verdict, tag, 说明) —— 顺序即优先级，先命中先返回
RULES = [
    ("reject", "intended_use_change",
     lambda c: c.get("affects_intended_use") is True),
    ("reject", "not_se_to_predicate",
     lambda c: c.get("remains_se_to_predicate") is False),
    ("reject", "modified_version_as_predicate",
     lambda c: c.get("pccp_modified_version_used_as_predicate") is True),
    ("reject", "no_pccp_authorized",
     lambda c: c.get("pccp_authorized") is False
     and c.get("change_within_pccp_scope") is True),
    ("reject", "acceptance_not_met",
     lambda c: c.get("acceptance_criteria_met") is False),
    ("hold", "pccp_status_unknown",
     lambda c: c.get("pccp_authorized") is None),
    ("hold", "outside_scope",
     lambda c: c.get("change_within_pccp_scope") is False),
    ("hold", "class_not_described",
     lambda c: c.get("change_class_described") is not True),
    ("hold", "validation_missing",
     lambda c: c.get("validation_documented") is not True),
    ("hold", "labeling_version_history_missing",
     lambda c: c.get("labeling_version_history") is not True),
    ("hold", "udi_not_regenerated",
     lambda c: c.get("udi_updated") is not True),
    ("hold", "acceptance_unproven",
     lambda c: c.get("acceptance_criteria_met") is None),
    ("hold", "evidence_insufficient",
     lambda c: c.get("evidence_sufficiency") in {"needs_supplement", "none"}),
]


def derive(c):
    for verdict, tag, fn in RULES:
        if fn(c):
            return verdict, tag
    return "go", "go_covered"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=os.path.join(HERE, "out", "cases_public_v0_2.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "cases_public_v0_2b.json"))
    ap.add_argument("--diff", default=os.path.join(HERE, "out", "relabel_diff.json"))
    a = ap.parse_args()

    data = json.load(open(a.cases, encoding="utf-8"))
    cases = data.get("cases", data) if isinstance(data, dict) else data

    diff, out = [], []
    for c in cases:
        c = dict(c)
        v, tag = derive(c)
        # 只动合成题：v0.1 的 32 条保持字节级不动，保可比性
        if not str(c.get("label_provenance", "")).startswith("synthetic"):
            out.append(c)
            continue
        if v != c.get("expected_verdict"):
            diff.append({
                "case_id": c["case_id"],
                "from": [c.get("expected_verdict"), c.get("expected_tag")],
                "to": [v, tag],
            })
            c["expected_verdict"], c["expected_tag"] = v, tag
            prev = c.get("label_provenance", "")
            c["label_provenance"] = (prev + "+rule_r1_20261127").strip("+")
        out.append(c)

    payload = data if isinstance(data, dict) and "cases" in data else {"cases": out}
    if isinstance(payload, dict) and "cases" in payload:
        payload["cases"] = out
    json.dump(payload, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(diff, open(a.diff, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    n = len(out)
    dist = {}
    for c in out:
        dist[c["expected_verdict"]] = dist.get(c["expected_verdict"], 0) + 1
    print(json.dumps({"n": n, "changed": len(diff), "dist": dist,
                      "baseline_majority": max(dist.values()) / n,
                      "diff": diff}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
