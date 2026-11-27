#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blind_dryrun.py —— 盲标包的干跑（**不是**独立标注）。

它做三件事，全部由我自己完成，口径上只能记作"同操作者干跑"（T4），不得记成 T1：
  1. 用包内判器对 10 题出判决（raterA.csv），与我们标签本身比对 → 应 10/10，κ=1.0；
  2. 造一个"扰动版"评审（raterB.csv，3 题翻判）→ κ 必须显著下降，用来证明 κ 会动；
  3. 把两份结果连同 κ 一起落盘，作为将来真评审回传时的对照基线。

为什么值得做：此前 κ 这个数一次都没出现过；包也没跑过通。
一个从没跑过的交接包，交给外人只会当场卡住。
"""
from __future__ import annotations

import csv
import json
import pathlib
import subprocess
import sys
import zipfile

KIT = pathlib.Path("t1_pack/blind_kit")
PKG = "dist/pccp-bench_v0.3.2_candidate.zip"
EXTRACT = pathlib.Path("out/pkg_v032_kit")


def ensure_pkg() -> pathlib.Path:
    if not (EXTRACT / "dataset/adapter_reference.py").exists():
        EXTRACT.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(PKG).extractall(EXTRACT)
    return EXTRACT


def judge_verdicts(ids: list[str]) -> dict[str, str]:
    root = ensure_pkg()
    sys.path.insert(0, str(root))
    from dataset import adapter_reference  # type: ignore
    cases = json.loads((root / "dataset/cases_public.json").read_text(encoding="utf-8"))["cases"]
    by_id = {c["case_id"]: c for c in cases}
    out = {}
    for cid in ids:
        r = adapter_reference.evaluate(by_id[cid])
        v = r["verdict"] if isinstance(r, dict) else getattr(r, "verdict", r)
        out[cid] = str(v)
    return out


def write_csv(path: pathlib.Path, rows: list[tuple[str, str]]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "verdict"])
        w.writerows(rows)


def main() -> int:
    ids = [r["case_id"] for r in csv.DictReader(
        open(KIT / "cases_blind_10.csv", encoding="utf-8-sig", newline=""))]
    truth = judge_verdicts(ids)
    write_csv(pathlib.Path("out/dryrun_raterA.csv"), list(truth.items()))

    # 扰动版：固定翻 3 题（可复现），模拟一个会犯错的评审
    keys = [k for k in ids if truth[k] == "hold"][:2] + [k for k in ids if truth[k] == "reject"][:1]
    b = dict(truth)
    for k in keys:
        b[k] = "hold" if b[k] != "hold" else "go"
    write_csv(pathlib.Path("out/dryrun_raterB.csv"), [(k, b[k]) for k in ids])

    res = {}
    for tag, other in (("A_vs_label", "out/dryrun_raterA.csv"), ("B_vs_label", "out/dryrun_raterB.csv")):
        r = subprocess.run([sys.executable, "kappa.py", "--a", "out/dryrun_raterA.csv",
                            "--b", other], capture_output=True, text=True)
        head = (r.stdout or "").strip().splitlines()
        res[tag] = head[0] if head else r.stderr.strip()[:120]
        print("%-12s %s" % (tag, res[tag]))

    # 与我们存的答案（labels）对账：这批题抽出来时分层，A 应与标签全同
    key = json.load(open("out/blind_kit_key.json", encoding="utf-8"))
    same = sum(1 for cid in ids if key[cid]["verdict"] == truth[cid])
    print("A 与原始标签一致：%d/%d" % (same, len(ids)))

    json.dump({"kit_cases": len(ids), "a_vs_label": res["A_vs_label"],
               "b_vs_label": res["B_vs_label"], "a_matches_original_label": same,
               "label": "同操作者干跑（T4），不是独立标注（T1）"},
              open("out/blind_dryrun.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\nBLIND_KIT_DRYRUN_DONE（口径：T4 干跑，非 T1）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
