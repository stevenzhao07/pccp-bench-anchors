#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_t1_return.py —— 检查 T1 回传是否完整。只查完整性，不改写、不补全、不解释。

为什么只查完整性：T1 的价值在于"第三方本人说的原话"。任何"代为补全"或"替他解释"的动作，
都会把 T1 降级成我们的话。所以这里只判断三件事：

  1  必填项在不在（reviewer / independent / relationship / machine / checked_at / path / raw_output）
  2  结果字段是不是合法取值（ZERO_DEP_ALL_PASS / HAS_FAIL，不给中间态）
  3  raw_output 里是否真的出现对应结论字符串（防空口回传）

不做什么：不重跑、不判对错、不写台账。

用法：
  python verify_t1_return.py --file t1_return.json
  # T1_RECORD_OK（退出码 0） / T1_RECORD_INCOMPLETE（退出码 1，逐条列出缺什么）
"""
import argparse
import json
import sys

REQUIRED = ["reviewer", "independent", "relationship", "machine", "checked_at", "path", "raw_output"]
RESULT_FIELD = {"A": ("a_results", "zero_dep_verify", {"ZERO_DEP_ALL_PASS", "HAS_FAIL"})}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    a = ap.parse_args()

    doc = json.load(open(a.file, encoding="utf-8"))
    problems = []

    for k in REQUIRED:
        v = doc.get(k)
        if v is None or (isinstance(v, str) and (not v.strip() or v.strip().startswith("<"))) or v is False:
            problems.append("缺或未填：" + k)

    if doc.get("independent") is not True:
        problems.append("independent 必须是 true（本协议不接受'半独立'）")

    path = (doc.get("path") or "").upper()
    if path not in ("A", "A+", "B"):
        problems.append("path 只能是 A / A+ / B")
    else:
        key = "a_results"
        block = doc.get(key) or {}
        field, name, allowed = RESULT_FIELD.get("A")
        val = block.get(name)
        if val not in allowed:
            problems.append("%s.%s 必须是 %s 之一（不给中间态）"
                            % (key, name, "/".join(sorted(allowed))))
        raw = doc.get("raw_output") or ""
        if val and val.split()[0] not in raw:
            problems.append("raw_output 里找不到结论字符串 %r —— 空口回传不算" % val)

    if problems:
        print("T1_RECORD_INCOMPLETE")
        for p in problems:
            print("  - " + p)
        print("（退回让本人补；不代补、不代解释）")
        return 1

    print("T1_RECORD_OK")
    print("  reviewer    " + str(doc.get("reviewer")))
    print("  relationship " + str(doc.get("relationship")))
    print("  checked_at  " + str(doc.get("checked_at")))
    print("  result      " + str((doc.get("a_results") or {}).get("zero_dep_verify")))
    print("  → 下一步：原样记进 T1_LEDGER.md，不改写、不合并")
    return 0


if __name__ == "__main__":
    sys.exit(main())
