#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""score_policies.py —— 同一批 51 条，在三种标签政策下各算一次分。

P0  : v0.2 原始（宽松：门通过失败 → hold）
R1  : 只按 R1 重标合成题（v0.1 32 条不动）
R1F : R1 全量（连 v0.1 那 2 条与规则冲突的也按 R1 改）——仅用于量化上限，不采纳
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def repack(base_zip, cases_path, out_zip):
    subprocess.run([PY, os.path.join(HERE, "repack_cases.py"),
                    "--zip", base_zip, "--cases", cases_path, "--out", out_zip],
                   check=True, stdout=subprocess.DEVNULL)
    return out_zip


def score(zip_path):
    out = subprocess.run([PY, os.path.join(HERE, "repro", "run_repro.py"),
                          "--dataset-zip", zip_path], capture_output=True, text=True)
    return json.loads(out.stdout)


def main():
    base = os.path.join(tempfile.gettempdir(), "pcb_v02_full.zip")
    tmp = tempfile.mkdtemp(prefix="pccp_pol_")

    # R1F：在 v0.2b 基础上，再把 v0.1 两条与规则冲突的按 R1 改（只为量化上限）
    c = json.load(open(os.path.join(HERE, "out", "cases_public_v0_2b.json"), encoding="utf-8"))
    cases = c.get("cases", c)
    changed = []
    for x in cases:
        if x["case_id"] == "K260973-H1-DICE-MISS" and x["expected_verdict"] != "reject":
            x["expected_verdict"] = "reject"
            changed.append(x["case_id"])
        if x["case_id"] == "P240006-HW-COVERAGE-GAP" and x["expected_verdict"] != "go":
            x["expected_verdict"] = "go"
            x["expected_tag"] = "ok_covered"
            changed.append(x["case_id"])
    r1f_json = os.path.join(tmp, "cases_r1f.json")
    json.dump(c if isinstance(c, dict) else {"cases": cases},
              open(r1f_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    pol = {
        "P0": os.path.join(HERE, "out", "cases_public_v0_2.json"),
        "R1": os.path.join(HERE, "out", "cases_public_v0_2b.json"),
        "R1F": r1f_json,
    }
    table = {}
    for name, path in pol.items():
        z = repack(base, path, os.path.join(tmp, "v_%s.zip" % name))
        r = score(z)
        table[name] = {
            "exact": r["public"]["exact"],
            "n": r["n_cases"],
            "exact_rate": r["public"]["exact_rate"],
            "tag_rate": r["public"]["tag_rate"],
            "misses": r["public"]["misses"],
            "case_digest": r["case_digest"],
        }
    dist = {}
    for x in json.load(open(pol["R1"], encoding="utf-8")).get("cases", []):
        dist[x["expected_verdict"]] = dist.get(x["expected_verdict"], 0) + 1
    table["_baseline_always_go"] = round(dist.get("go", 0) / sum(dist.values()), 4)
    table["_dist_R1"] = dist
    table["_r1f_changed"] = changed
    print(json.dumps(table, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
