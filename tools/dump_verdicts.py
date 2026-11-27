#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dump_verdicts.py —— 逐案打印判器判决，用于核对标签与判器的分歧点。

用法：python tools/dump_verdicts.py --dataset-zip pcb_v02_full.zip
"""
import argparse
import importlib.util
import json
import os
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))


def load_bench(dataset_dir):
    path = os.path.join(dataset_dir, "bench.py")
    spec = importlib.util.spec_from_file_location("pccp_bench", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pccp_bench"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-zip", required=True)
    ap.add_argument("--adapter", default=os.path.join(HERE, "repro", "adapter_reference.py"))
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="pccp_dump_")
    with zipfile.ZipFile(a.dataset_zip) as z:
        z.extractall(tmp)
    dd = os.path.join(tmp, "dataset")
    bench = load_bench(dd)
    adapter = bench.load_adapter(os.path.abspath(a.adapter))
    cases = json.load(open(os.path.join(dd, "cases_public.json"), encoding="utf-8"))
    cases = cases.get("cases", cases) if isinstance(cases, dict) else cases

    print("%-34s %-8s %-8s %-24s %-24s" % ("case_id", "expected", "actual", "expected_tag", "tag"))
    for c in cases:
        v, tag = bench.ask(adapter, dict(c))
        mark = "" if v == c["expected_verdict"] else "  <<< MISMATCH"
        print("%-34s %-8s %-8s %-24s %-24s%s" %
              (c["case_id"], c["expected_verdict"], v, c.get("expected_tag"), tag, mark))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
