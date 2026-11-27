#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_blind_kit.py —— 从 v0.3.2 里抽 10 题做成"盲标小包"。

纪律：包里**不能有答案**。答案另行存到 out/blind_kit_key.json（不随包发出），
否则"独立标注"一开始就废了。抽题按 go/hold/reject 分层，避免全是一个类。
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
import sys
import zipfile

PKG = "dist/pccp-bench_v0.3.2_candidate.zip"
KIT = pathlib.Path("t1_pack/blind_kit")
FACT_FIELDS = [
    "pccp_authorized", "change_within_pccp_scope", "affects_intended_use",
    "change_class_described", "acceptance_criteria_met", "remains_se_to_predicate",
    "validation_documented", "labeling_version_history", "udi_updated",
]
WANT = {"go": 4, "hold": 3, "reject": 3}


def main() -> int:
    cases = json.loads(zipfile.ZipFile(PKG).read("dataset/cases_public.json")
                       .decode("utf-8"))["cases"]
    picked, key = [], {}
    for want, n in WANT.items():
        got = [c for c in cases if c.get("expected_verdict") == want][:n]
        picked += got
    if len(picked) < sum(WANT.values()):
        print("题量不足：只抽到", len(picked))
        return 1

    KIT.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in picked:
        refs = c.get("source_refs") or []
        refs_txt = " | ".join("%s: %s" % (r.get("kind"), r.get("ref")) for r in refs)
        row = {"case_id": c["case_id"],
               "device_description": c["device_description"],
               "change_type": c.get("change_type", ""),
               "jurisdiction": c.get("jurisdiction", ""),
               "source_refs": refs_txt}
        for f in FACT_FIELDS:
            row[f] = "" if c.get(f) is None else str(c.get(f)).lower()
        row["evidence_sufficiency"] = c.get("evidence_sufficiency", "")
        row["你的判决(go/hold/reject)"] = ""
        row["理由(一句话,可留空)"] = ""
        rows.append(row)
        key[c["case_id"]] = {"verdict": c["expected_verdict"], "tag": c.get("expected_tag"),
                             "kind": c.get("kind"), "provenance": c.get("label_provenance")}

    with open(KIT / "cases_blind_10.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    with open(KIT / "rater_verdicts.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "verdict", "confidence(1-3)", "note"])
        for c in picked:
            w.writerow([c["case_id"], "", "", ""])

    (KIT / "README_盲标.md").write_text("""# 盲标小包（10 题，20 分钟）

包里**没有答案**。我不是要你背我的结论，是要拿你的判断和判器的判断算一个一致性系数。

## 怎么做
1. 打开 `cases_blind_10.csv`。每题有器械描述、9 个事实字段（TRUE/FALSE）、变更类型、来源引用。
2. 按下面的定义填 `你的判决` 列，**只看事实和来源，不要猜我要什么**：
   - `go`：该变更可以按已授权的 PCCP 实施，不需要另行申报；
   - `hold`：有事实没写清 / 证据不够，判不了——**留白不等于没问题**；
   - `reject`：超出 PCCP 覆盖、改变了预期用途，或该变更版本不能再当谓词器械。
3. 填完把 `rater_verdicts.csv` 的 `verdict` 列填上（每个 case_id 一行），两文件一起回传。

## 我会拿它算什么
Cohen's κ（把"碰巧一致"扣掉之后的一致性）。算法在本项目 `kappa.py` 里，带三个解析可验的算例
（教科书例 κ=0.4、完全一致 κ=1.0、系统性反向 κ=0.0），你自己也能跑。

## 边界（先说清，免得误会）
- 10 题、n 小，κ 的区间会很宽，只作参考，我不会拿它当"独立验证完成"的证据；
- 你填的判决**不会**被改写成"与作者一致"；有差异我原样列出；
- 这不是法律意见，你的判断也不必与 FDA 一致——我要的是**独立**，不是**相同**。
""" , encoding="utf-8")

    json.dump(key, open("out/blind_kit_key.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("抽出 %d 题：%s" % (len(picked), " ".join(WANT)))
    print("包：%s（不含答案）" % (KIT / "cases_blind_10.csv"))
    print("答案另存：out/blind_kit_key.json（不随包发出）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
