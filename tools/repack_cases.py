#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repack_cases.py —— 用给定 cases json 替换数据集包里的 cases_public.json，其余字节原样保留。"""
import argparse
import os
import zipfile


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    with zipfile.ZipFile(a.zip) as zin, zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.endswith("cases_public.json"):
                with open(a.cases, "rb") as f:
                    data = f.read()
            zout.writestr(info, data)
        keep = set(i.filename for i in zin.infolist())
        if not any(n.endswith("cases_public.json") for n in keep):
            raise SystemExit("包里没有 cases_public.json")
    print("out:", a.out, os.path.getsize(a.out), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
