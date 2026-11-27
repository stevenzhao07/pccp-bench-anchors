#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""corpus_replay_probe.py —— 用 47 条真实 FDA 批准说明去喂判器，看它到底能不能吃。

为什么做这个：我们一直说"真实变更回放 0 条"。这句话太笼统，容易变成免责声明。
把它拆成可测的问题：**拿真实文本直接喂判器，能不能跑出判决？**

做法（刻意保守，宁可留 None 也不替 FDA 推断）：
  从 `ao_statement` 原文里只抽**字面成立**的字段，抽不到就留 None。
  然后把这份"半编码"喂给 v0.3.1 包里的判器，看它出什么。

这份探针要回答三件事，不做第四件：
  1  47 条里，有多少条**字面**能支撑 pccp_authorized / claimed_coverage / actually_within_scope
  2  判器要求的 5 个必填里，哪几个在审批说明里**根本不出现**（= 真实回放的真正瓶颈）
  3  半编码喂进去后，判器给什么判决（预期大多是"不可用"，这正是要量出来的）
  **不做**：不假设缺失字段的取值、不把这批判决当"真实回放结果"。

用法：
  python corpus_replay_probe.py --corpus out\\pccp_corpus.json --pkg %TEMP%\\iso_v031 \
      --json out\\corpus_replay_probe.json
"""
import argparse
import importlib.util
import json
import os
import re
import sys

REQ = ["pccp_authorized", "change_within_pccp_scope", "acceptance_criteria_met",
       "remains_se_to_predicate", "evidence_sufficiency"]

EVID = re.compile(r"data|study|studies|test(ing|ed)?|validation|assessment|analysis", re.I)
NEG_CLAUSE = re.compile(r"(do not|does not|without)\s+(impact|affect|alter)", re.I)
INTENDED = re.compile(r"intended use|indication", re.I)
SE = re.compile(r"substantial(ly)? equivalen|predicate device|510\(k\)", re.I)


def load_adapter(pkg):
    p = os.path.join(pkg, "dataset", "adapter_reference.py")
    spec = importlib.util.spec_from_file_location("adapter_reference", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["adapter_reference"] = mod
    spec.loader.exec_module(mod)
    return mod


def encode(text):
    """只写字面成立的。返回 (ctx, evidence_notes)。"""
    t = text or ""
    low = t.lower()
    ctx, notes = {}, []

    if "predetermined change control plan" in low or "pccp" in low:
        ctx["pccp_authorized"] = True
        ctx["claimed_pccp_coverage"] = True
        notes.append("pccp_authorized=True: 原文出现 predetermined change control plan / PCCP")

    if low.strip().startswith("approval for a predetermined change control plan"):
        ctx["actually_within_scope"] = True
        notes.append("actually_within_scope=True: 原文以 approval for a PCCP 开头")

    if NEG_CLAUSE.search(t) and INTENDED.search(t):
        ctx["affects_intended_use"] = False
        notes.append("affects_intended_use=False: 原文有 do not impact/affect 条款且提到 intended use")

    if SE.search(t):
        # 原文提到 SE/谓词，但没有说"变更后仍保持 SE" → 不赋值
        notes.append("remains_se_to_predicate 留 None：原文只提到 SE/谓词，未陈述变更后仍保持")
    else:
        notes.append("remains_se_to_predicate 留 None：原文未提")

    ctx["evidence_sufficiency"] = "sufficient" if EVID.search(t) else "needs_supplement"
    notes.append("evidence_sufficiency=%s：按是否出现 data/study/testing/validation 字样判断（字面，不判是否充分）"
                 % ctx["evidence_sufficiency"])

    notes.append("acceptance_criteria_met 留 None：审批说明不写判据是否达成")
    # change_within_pccp_scope 由 adapter 的展开式从 claimed/actual/auth 推出，这里不直接置值
    return ctx, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--pkg", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()

    corpus = json.load(open(a.corpus, encoding="utf-8"))
    recs = corpus["records"]
    adapter = load_adapter(a.pkg)

    rows = []
    usable = 0
    verdicts = {}
    present_count = {k: 0 for k in REQ}
    for r in recs:
        ctx, notes = encode(r.get("ao_statement", ""))
        for k in REQ:
            if ctx.get(k) is not None:
                present_count[k] += 1
        full = {**ctx}
        res = adapter.evaluate(full)
        v = res.get("verdict")
        if v != "hold" or "unusable" not in json.dumps(res.get("reasons", []), ensure_ascii=False).lower():
            pass
        verdicts[v] = verdicts.get(v, 0) + 1
        reasons = [str(x.get("rule") if hasattr(x, "get") else x) for x in res.get("reasons", [])]
        unusable = any("CONTRACT" in s.upper() for s in reasons) or any("unusable" in s.lower() for s in reasons)
        if not unusable:
            usable += 1
        rows.append({
            "pma": r["pma"], "supplement": r["supplement"], "applicant": r["applicant"],
            "year": (r.get("decision_date") or "")[:4],
            "verdict": v, "tag": res.get("tag"),
            "unusable": unusable,
            "filled": {k: (ctx.get(k) if ctx.get(k) is not None else "None") for k in REQ},
            "notes": notes,
        })

    out = {
        "corpus_total": len(recs),
        "probe_rule": "只写字面成立的字段；抽不到留 None；不假设、不外推",
        "required_field_coverage": present_count,
        "judge_usable": usable,
        "verdict_distribution": verdicts,
        "rows": rows,
    }

    # 假设填法下的行为（**是假设，不是回放**）：用来看"格子填上以后判器动不动"
    scen = {
        "A_all_satisfied": dict(remains_se_to_predicate=True, acceptance_criteria_met=True),
        "B_acceptance_not_met": dict(remains_se_to_predicate=True, acceptance_criteria_met=False),
        "C_breaks_SE": dict(remains_se_to_predicate=False, acceptance_criteria_met=True),
        "D_scope_claim_only": dict(remains_se_to_predicate=True, acceptance_criteria_met=True,
                                   claimed_pccp_coverage=True, actually_within_scope=False),
    }
    scen_out = {}
    for name, extra in scen.items():
        dist = {}
        for r in recs:
            ctx, _n = encode(r.get("ao_statement", ""))
            ctx.update(extra)
            v = adapter.evaluate(ctx).get("verdict")
            dist[v] = dist.get(v, 0) + 1
        scen_out[name] = dist
    out["assumption_scenarios"] = {
        "_note": "以下是假设缺失格取值后的判决分布，用于说明判器是否有区分力；**不是真实回放结果**",
        "by_scenario": scen_out,
    }

    # 门梯：以"13 格全满"为基线，逐格降级，看判器给什么。
    # 这一步要回答的不是"判器对不对"，而是：真实回放到底要填几格、缺一格会怎样。
    full = dict(pccp_authorized=True, claimed_pccp_coverage=True, actually_within_scope=True,
                criteria_measured=True, criteria_met=True, remains_se_to_predicate=True,
                affects_intended_use=False, evidence_sufficiency="sufficient",
                change_class_described=True, validation_documented=True,
                labeling_version_history=True, udi_updated=True,
                change_type="retrain_same_distribution",
                source_refs=[{"kind": "verification_report", "ref": "RPT-PLACEHOLDER"}])
    r = adapter.evaluate(dict(full))
    ladder = [{"slot": "(基线，13 格全满)", "degraded_to": "-", "verdict": r.get("verdict"), "tag": r.get("tag")}]
    degrade = {
        "pccp_authorized": False, "actually_within_scope": False, "criteria_met": False,
        "criteria_measured": False, "remains_se_to_predicate": False, "affects_intended_use": True,
        "evidence_sufficiency": "needs_supplement", "change_class_described": False,
        "validation_documented": False, "labeling_version_history": False, "udi_updated": False,
        "change_type": "unknown_type", "source_refs": [],
    }
    for slot, bad in degrade.items():
        ctx = dict(full)
        ctx[slot] = bad
        rr = adapter.evaluate(ctx)
        ladder.append({"slot": slot, "degraded_to": repr(bad),
                       "verdict": rr.get("verdict"), "tag": rr.get("tag")})

    # 静默覆盖探针：v0.3 适配器在 criteria_measured=True 时用 criteria_met 覆盖
    # acceptance_criteria_met。于是"填了 v0.2 的名字"会被无声丢掉 —— 必须量出来。
    ctx_v2name = dict(full)
    ctx_v2name["acceptance_criteria_met"] = False      # 只改 v0.2 的名字
    rr = adapter.evaluate(ctx_v2name)
    out["silent_override"] = {
        "_note": "只把 acceptance_criteria_met 置 False（v0.2 字段名），criteria_met 仍 True",
        "verdict": rr.get("verdict"), "tag": rr.get("tag"),
        "hazard": "适配器用 criteria_met 覆盖同名结论，填 v0.2 字段名的输入被静默忽略、不报错",
    }
    ctx_v3name = dict(full)
    ctx_v3name["criteria_met"] = False                 # 改 v0.3 的名字
    rr = adapter.evaluate(ctx_v3name)
    out["silent_override"]["control_v3name"] = {"verdict": rr.get("verdict"), "tag": rr.get("tag")}
    out["gate_ladder"] = {
        "_note": "基线=13 格全填（含 source_refs 非空引用）；逐格降级看判决。用于说明'真实回放要填几格'",
        "rows": ladder,
    }
    if a.json:
        json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"语料 {len(recs)} 条（真实 FDA 批准说明）")
    print("判器必填 5 项的字面覆盖率：")
    for k in REQ:
        print(f"  {k:<28} {present_count[k]}/{len(recs)}")
    print(f"判器可用（非 CONTRACT 拒绝）：{usable}/{len(recs)}")
    print(f"判决分布：{verdicts}")
    print("假设填法下的判决分布（是假设，不是回放）：")
    for name, dist in out["assumption_scenarios"]["by_scenario"].items():
        print(f"  {name:<24} {dist}")
    print("门梯（13 格全满 → 逐格降级）：")
    for row in out["gate_ladder"]["rows"]:
        print(f"  {row['slot']:<26} {row['degraded_to']:<22} → {row['verdict']:<7} {row['tag']}")
    so = out["silent_override"]
    print("静默覆盖探针：只填 acceptance_criteria_met=False →", so["verdict"], so["tag"],
          "｜填 criteria_met=False →", so["control_v3name"]["verdict"], so["control_v3name"]["tag"])
    print("CORPUS_PROBE_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
