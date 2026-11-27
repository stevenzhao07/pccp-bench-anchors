#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_t1_pack.py —— 打一个"给人用"的 T1 复核包。

内容（全部自包含，对方不需要访问我们的项目目录）：
  README_T1.md            使用说明（A 路径三条命令 / A+ 跑包 / B 路径 14 格）
  t1_encode_template.csv  14 格模板（每格带填法 + 引用列）
  t1_return_template.json 回传模板
  verify_t1_return.py     回传完整性检查（只查完整性，不代补、不代解释）
  tools/verify_zero_dep.py  零依赖验算器
  certs/fulcio_intermediate.pem, certs/fulcio_root.pem
  pkg/pccp-bench_v0.3.2_candidate.zip   数据集包本体（A+ 路径与 B 路径都要用）

用法：
  python build_t1_pack.py --pkg dist\\pccp-bench_v0.3.2_candidate.zip --out dist\\pccp-t1-review-pack_20261127.zip
"""
import argparse
import hashlib
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
T1 = os.path.join(HERE, "t1_pack")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    items = [
        (os.path.join(T1, "README_T1.md"), "README_T1.md"),
        (os.path.join(T1, "t1_encode_template.csv"), "t1_encode_template.csv"),
        (os.path.join(T1, "t1_return_template.json"), "t1_return_template.json"),
        (os.path.join(T1, "verify_t1_return.py"), "verify_t1_return.py"),
        (os.path.join(HERE, "verify_zero_dep.py"), "tools/verify_zero_dep.py"),
        (os.path.join(HERE, "out", "fulcio_intermediate.pem"), "certs/fulcio_intermediate.pem"),
        (os.path.join(HERE, "out", "fulcio_root.pem"), "certs/fulcio_root.pem"),
        (a.pkg, "pkg/" + os.path.basename(a.pkg)),
    ]

    missing = [src for src, _ in items if not os.path.exists(src)]
    if missing:
        print("缺文件，不打包：")
        for m in missing:
            print("  " + m)
        return 2

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    manifest = []
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in items:
            z.write(src, arc)
            manifest.append({"path": arc, "sha256": sha(src), "bytes": os.path.getsize(src)})
        z.writestr("PACK_MANIFEST.json", __import__("json").dumps(
            {"files": manifest, "built_at": "2026-11-27",
             "_note": "每个文件的 sha256 都在这里；对方可自行复核。包内不含任何私钥。"},
            ensure_ascii=False, indent=1))

    print("out   ", a.out, os.path.getsize(a.out), "bytes")
    print("sha256", sha(a.out))
    for m in manifest:
        print("  %-44s %8d  %s" % (m["path"], m["bytes"], m["sha256"][:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
