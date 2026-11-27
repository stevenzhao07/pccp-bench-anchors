#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
run_repro.py —— 让"0.9688"这个分数可被外人重算。

不重写打分逻辑：直接 import 数据集包里的 `bench.py`，用它的
`load_adapter / ask / mask_case / score_rows / digest`，避免"我这里算得跟官榜不一样"。
本脚本只做三件事：把包解开、把 adapter 接上、把两列（public / masked）跑出来。

用法：
  python run_repro.py --dataset-zip <pccp-bench_zenodo_v0.1.0.zip>
  python run_repro.py --dataset-zip <zip> --adapter adapter_reference.py

输出：public / masked 两列的 exact_rate 与 misses（漏了哪几例），
      外加 case-set digest —— 同一份题集在任何机器上都应得同一个串。
"""
import argparse
import importlib.util
import json
import os
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))


def load_bench(dataset_dir: str):
    path = os.path.join(dataset_dir, "bench.py")
    spec = importlib.util.spec_from_file_location("pccp_bench", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pccp_bench"] = mod
    spec.loader.exec_module(mod)
    return mod


def run_column(bench, adapter, cases, mask: bool):
    rows = []
    for c in cases:
        case = bench.mask_case(c) if mask else dict(c)
        v, tag = bench.ask(adapter, case)
        rows.append({"case_id": c["case_id"], "expected": c["expected_verdict"],
                     "actual": v, "expected_tag": c.get("expected_tag"), "tag": tag})
    return bench.score_rows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-zip", required=True)
    ap.add_argument("--adapter", default=os.path.join(HERE, "adapter_reference.py"))
    ap.add_argument("--keep", action="store_true", help="保留解压目录便于检查")
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="pccp_repro_")
    with zipfile.ZipFile(a.dataset_zip) as z:
        z.extractall(tmp)
    dataset_dir = os.path.join(tmp, "dataset")
    if not os.path.isdir(dataset_dir):
        raise SystemExit(f"包结构不含 dataset/：{os.listdir(tmp)}")

    bench = load_bench(dataset_dir)
    adapter = bench.load_adapter(a.adapter)
    cases = json.load(open(os.path.join(dataset_dir, "cases_public.json"), encoding="utf-8"))
    if isinstance(cases, dict):          # 兼容 {"cases":[...]} 结构
        cases = cases.get("cases", cases)

    pub = run_column(bench, adapter, cases, mask=False)
    msk = run_column(bench, adapter, cases, mask=True)

    out = {
        "n_cases": len(cases),
        "public": {"exact_rate": pub["exact_rate"], "exact": pub["exact"],
                   "misses": pub["misses"], "tag_rate": pub["tag_rate"]},
        "masked": {"exact_rate": msk["exact_rate"], "exact": msk["exact"],
                   "misses": msk["misses"], "tag_rate": msk["tag_rate"]},
        "case_digest": bench.digest(cases, [], {"public": pub}),
        "adapter": os.path.abspath(a.adapter),
        "dataset_dir": tmp if a.keep else "(已清理)",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
