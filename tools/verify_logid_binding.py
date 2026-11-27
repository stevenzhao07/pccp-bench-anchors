#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
verify_logid_binding.py —— 补最后一个技术口子：logID 到底是不是"这把钥匙"。

Rekor/Trillian 的约定：logID = SHA-256(DER 编码的 SubjectPublicKeyInfo)，十六进制。
所以"logID 与公钥对得上"是可以纯算术验的，不该靠"我记得是这个值"。

之前我们的判器用固定 PEM、把 logID 当字符串比，没验这个关系；
于是"换一把钥匙、把 logID 照抄"这种替换是拦不住的。本工具补这一环。

判据：
  1) 用给定 PEM 算 SHA-256(SPKI DER)，与条目里的 logID 逐字符比（小写）
  2) 用 --live 时，再从 /api/v1/log/publicKey 现取一次，比 PEM 正文是否同一把钥匙
     （拦"本地 PEM 被替换、但远端没换"的情况）
  3) 打印 checkpoint/keyhash 前 8 位，与 logID 前 8 位对照（本工具不把 8 位当判据，只作提示）

用法：
  python verify_logid_binding.py --entry out\anchor_entry_A0002.json \
      --public-key out\rekor_publicKey.json --live
"""
import argparse
import hashlib
import json
import sys
import urllib.request

from cryptography.hazmat.primitives import serialization


def spki_der_sha256(pem_text: str) -> str:
    pub = serialization.load_pem_public_key(pem_text.encode())
    der = pub.public_bytes(encoding=serialization.Encoding.DER,
                           format=serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", required=True)
    ap.add_argument("--public-key", required=True)
    ap.add_argument("--live", action="store_true", help="再从 Rekor API 现取公钥比对")
    a = ap.parse_args()

    pem = open(a.public_key, encoding="utf-8").read()
    raw = json.load(open(a.entry, encoding="utf-8"))
    rec = raw[next(iter(raw))]
    log_id = str(rec.get("logID", "")).lower()
    fails, notes = [], []

    computed = spki_der_sha256(pem)
    if computed != log_id:
        fails.append(f"LOGID_MISMATCH computed={computed[:16]} entry={log_id[:16]}")
    else:
        notes.append(f"logID == SHA-256(SPKI DER)（{computed[:16]}…）")

    if a.live:
        try:
            r = urllib.request.urlopen("https://rekor.sigstore.dev/api/v1/log/publicKey", timeout=20)
            live_pem = r.read().decode()
            live_h = spki_der_sha256(live_pem)
            if live_h != computed:
                fails.append(f"LIVE_KEY_DIFFERS live={live_h[:16]} local={computed[:16]}")
            else:
                notes.append("现取公钥与本地 PEM 同一把钥匙")
            if live_h != log_id:
                fails.append(f"LIVE_KEY_NOT_LOGID live={live_h[:16]} entry={log_id[:16]}")
        except Exception as e:
            fails.append(f"LIVE_FETCH_ERROR:{e}")

    cp = (((rec.get("verification") or {}).get("inclusionProof") or {}).get("checkpoint") or "")
    out = {
        "status": "LOGID_BOUND" if not fails else "LOGID_UNBOUND",
        "computed_logid": computed,
        "entry_logid": log_id,
        "checkpoint_keyhash_hint": next((ln.split()[-1] for ln in cp.splitlines()
                                         if ln.startswith("— ") or ln.startswith("- ")), None),
        "fails": fails,
        "notes": notes,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
