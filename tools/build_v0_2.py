#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_v0_2.py —— 把 v0.1 的 32 条与新增 20 条合成 v0.2 公开题集，并做一致性校验。

只做一件事：**不动原 32 条**，只追加。追加的 20 条专为修补 v0.1 的判别力缺陷：
  6 个零方差标志各出现至少一次 False；go 基线从 0.875 降到约 0.577。

同时用一条显式的推导规则复核每条案例的 expected_verdict 是否自洽，
不自洽的逐条报出来，不悄悄改标签。

用法：
  python build_v0_2.py --zip pcb010.zip --add cases_v0_2_additions.json \
      --out out/cases_public_v0_2.json
"""
import argparse
import json
import zipfile
from collections import Counter


def derive(c):
    """判据推导顺序（写死在代码里，可被任何人核）：
    无授权 PCCP → 改预期用途 → 破坏 SE → 出描述范围 → 类别未描述
    → 验收未达 → 验证未做 → 标签版本缺失 → UDI 未更新 → 其余 go。
    出范围一项取 hold（fail-safe），理由见 v0.1 的 K260973-N1-UNDESCRIBED-ORGAN 注释。
    """
    if not c["pccp_authorized"]:
        return "reject", "no_pccp_authorized"
    if c["affects_intended_use"]:
        return "reject", "intended_use_change"
    if not c["remains_se_to_predicate"]:
        return "reject", "se_not_maintained"
    if not c["change_within_pccp_scope"]:
        return "hold", "outside_scope"
    if not c["change_class_described"]:
        return "hold", "unclassifiable"
    if not c["acceptance_criteria_met"]:
        return "hold", "acceptance_not_met"
    if not c["validation_documented"]:
        return "hold", "validation_missing"
    if not c["labeling_version_history"]:
        return "hold", "labeling_version_missing"
    if not c["udi_updated"]:
        return "hold", "udi_not_updated"
    return "go", "ok_covered"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--add", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    v01 = json.loads(zipfile.ZipFile(a.zip).read("dataset/cases_public.json"))["cases"]
    v02_add = json.load(open(a.add, encoding="utf-8"))["cases"]
    ids = {c["case_id"] for c in v01}
    for c in v02_add:
        assert c["case_id"] not in ids, "case_id 重复: " + c["case_id"]
    all_cases = v01 + v02_add

    mism = []
    for c in all_cases:
        want_v, want_t = derive(c)
        if c["expected_verdict"] != want_v or c["expected_tag"] != want_t:
            mism.append((c["case_id"], c["expected_verdict"], c["expected_tag"], want_v, want_t))

    json.dump({"cases": all_cases}, open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("total cases:", len(all_cases), "(v0.1 %d + new %d)" % (len(v01), len(v02_add)))
    print("verdicts:", Counter(c["expected_verdict"] for c in all_cases).most_common())
    print("baseline(always-go) = %d/%d = %.4f"
          % (sum(1 for c in all_cases if c["expected_verdict"] == "go"), len(all_cases),
             sum(1 for c in all_cases if c["expected_verdict"] == "go") / len(all_cases)))
    flags = [k for k in all_cases[0] if isinstance(all_cases[0][k], bool)]
    print("\n%-32s %-6s %-6s" % ("flag", "True", "False"))
    zero = []
    for k in flags:
        t = sum(1 for c in all_cases if c.get(k) is True)
        f = sum(1 for c in all_cases if c.get(k) is False)
        print("%-32s %-6d %-6d" % (k, t, f))
        if t == 0 or f == 0:
            zero.append(k)
    print("\n仍为零方差:", zero or "无")
    print("推导自查不一致:", len(mism), "条")
    for m in mism:
        print("  ", m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
