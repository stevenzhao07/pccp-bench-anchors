#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_zero_dep.py —— 零第三方依赖的锚定验算器（只用 Python 标准库）。

为什么要有它：此前整套判据依赖 `cryptography`（也曾依赖 cosign / sigstore SDK）。
"外人可独立验算"若隐含"先 pip install 一堆东西"，门槛仍是我给的。本文件把六件事自己算完：

  BINDING       产物字节 sha256 == 条目 body 里的摘要（hastrekord: spec.data.hash.value）
  LOGID_BINDING logID == SHA-256(Rekor 公钥 SPKI DER)
  INCLUSION     leaf → Merkle path → root == 条目自带 rootHash（RFC 6962 审计路径）
  CHECKPOINT    Rekor 公钥对 checkpoint 正文 ECDSA/SHA-256 验签
  SET           日志对这条记录四字段规范化 JSON 的签名
  CHAIN         leaf ← Fulcio intermediate ← root（P-384/SHA-384，自写 X.509 DER 解析）

SCT 只报存在与归属，不报签名（见 verify_sct_sig.py：预证书字节不可由终证书还原）。

用法：
  python verify_zero_dep.py --bundle b.json --artifact a.bin --entry e.json \\
      --rekor-key rekor_publicKey.json \\
      --intermediate fulcio_intermediate.pem --root fulcio_root.pem
"""
import argparse
import base64
import hashlib
import json
import sys

# ---------------- 曲线参数 ----------------
CURVES = {
    "p256": (
        0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF,
        (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
         0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5),
        0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551,
    ),
    "p384": (
        0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFFFF0000000000000000FFFFFFFF,
        (0xAA87CA22BE8B05378EB1C71EF320AD746E1D3B628BA79B9859F741E082542A385502F25DBF55296C3A545E3872760AB7,
         0x3617DE4A96262C6F5D9E98BF9292DC29F8F41DBD289A147CE9DA3113B5F0B8C00A60B1CE1D7E819D7A431D7C90EA0E5F),
        0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFC7634D81F4372DDF581A0DB248B0A77AECEC196ACCC52973,
    ),
}

SIGALG = {  # OID DER -> (curve, hashname)
    bytes.fromhex("2a8648ce3d040302"): ("p256", "sha256"),
    bytes.fromhex("2a8648ce3d040303"): ("p384", "sha384"),
}


def _add(p, p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % p == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1 + (p - 3)) * pow(2 * y1, -1, p) % p
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, p) % p
    x3 = (lam * lam - x1 - x2) % p
    return x3, (lam * (x1 - x3) - y1) % p


def _mul(p, pt, k):
    r = None
    while k:
        if k & 1:
            r = _add(p, r, pt)
        pt = _add(p, pt, pt)
        k >>= 1
    return r


def _der_sig(b):
    i = 1
    ln = b[i]
    i += 1
    if ln & 0x80:
        i += ln & 0x7F
    assert b[i] == 0x02
    i += 1
    rl = b[i]
    i += 1
    r = int.from_bytes(b[i:i + rl], "big")
    i += rl
    assert b[i] == 0x02
    i += 1
    sl = b[i]
    i += 1
    s = int.from_bytes(b[i:i + sl], "big")
    return r, s


def ecdsa_verify(pub, msg, sig, curve="p256", hashname="sha256"):
    p, G, n = CURVES[curve]
    try:
        r, s = _der_sig(sig)
    except Exception:
        return False
    if not (1 <= r < n and 1 <= s < n):
        return False
    e = int.from_bytes(hashlib.new(hashname, msg).digest(), "big")
    w = pow(s, -1, n)
    pt = _add(p, _mul(p, G, e * w % n), _mul(p, pub, r * w % n))
    return pt is not None and pt[0] % n == r


# ---------------- DER ----------------
def tlv(b, i=0):
    tag = b[i]
    ln = b[i + 1]
    i += 2
    if ln & 0x80:
        nn = ln & 0x7F
        ln = int.from_bytes(b[i:i + nn], "big")
        i += nn
    return tag, b[i:i + ln], i + ln


def _len(b, i):
    ln = b[i + 1]
    s = i + 2
    if ln & 0x80:
        nn = ln & 0x7F
        ln = int.from_bytes(b[s:s + nn], "big")
        s += nn
    return ln, s


def _raw(b, i):
    ln, s = _len(b, i)
    return b[i:s + ln]


def _kids(b):
    out, i = [], 0
    while i < len(b):
        t, c, i = tlv(b, i)
        out.append((t, c))
    return out


def _raw_child(container, k):
    i = 0
    for _ in range(k):
        ln, s = _len(container, i)
        i = s + ln
    return _raw(container, i)


def pem_to_der(pem):
    body = "".join(l for l in pem.strip().splitlines() if "-----" not in l and l.strip())
    return base64.b64decode(body)


def point_from_spki(spki: bytes):
    _, i = _len(spki, 0)
    ln2, s2 = _len(spki, i)
    j = s2 + ln2
    ln3, s3 = _len(spki, j)
    raw = spki[s3:s3 + ln3]
    if raw[0] != 0x00 or raw[1] != 0x04:
        raise ValueError("非未压缩 EC 点")
    half = (len(raw) - 2) // 2
    return (int.from_bytes(raw[2:2 + half], "big"),
            int.from_bytes(raw[2 + half:], "big"))


def cert_parts(der):
    """(tbs_der, spki_der, sig_der, sigalg_oid)"""
    _, content, _ = tlv(der)
    seq = _kids(content)
    tbs_der = _raw(der, _len(der, 0)[1])
    kids_tbs = _kids(seq[0][1])
    idx = 6 if kids_tbs[0][0] == 0xA0 else 5
    spki = _raw_child(seq[0][1], idx)
    sig = seq[2][1]
    if seq[2][0] == 0x03:
        sig = sig[1:]
    oid = _kids(seq[1][1])[0][1]
    return tbs_der, spki, sig, oid


def pub_from_rekor_pem(pem):
    return point_from_spki(pem_to_der(pem))


# ---------------- 判据 ----------------
def check_binding(artifact_path, entry):
    body = json.loads(base64.b64decode(entry["body"]))
    spec = body.get("spec") or {}
    want = ((spec.get("data") or {}).get("hash") or {}).get("value") \
        or ((spec.get("payloadHash") or {}).get("value")) or ""
    got = hashlib.sha256(open(artifact_path, "rb").read()).hexdigest()
    return {"ok": want.lower() == got, "entry": want.lower(), "artifact": got}


def check_logid(rekor_pem, bundle):
    lid = hashlib.sha256(pem_to_der(rekor_pem)).hexdigest()
    tle = ((bundle.get("verificationMaterial") or {}).get("tlogEntries") or [{}])[0]
    declared = ((tle.get("logId") or {}).get("keyId") or "")
    dhex = base64.b64decode(declared + "=" * (-len(declared) % 4))[:32].hex() if declared else ""
    return {"ok": dhex == lid, "logid": lid, "declared": dhex}


def check_inclusion(entry):
    pr = entry["verification"]["inclusionProof"]
    r = hashlib.sha256(b"\x00" + base64.b64decode(entry["body"])).digest()
    fn, sn = int(pr["logIndex"]), int(pr["treeSize"]) - 1
    for h in [bytes.fromhex(x) for x in pr["hashes"]]:
        if fn % 2 == 1 or fn == sn:
            r = hashlib.sha256(b"\x01" + h + r).digest()
            while fn % 2 == 0 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            r = hashlib.sha256(b"\x01" + r + h).digest()
        fn >>= 1
        sn >>= 1
    return {"ok": r == bytes.fromhex(pr["rootHash"]), "depth": len(pr["hashes"]),
            "logIndex": int(pr["logIndex"]), "treeSize": int(pr["treeSize"])}


def check_checkpoint(entry, pub):
    cp = entry["verification"]["inclusionProof"]["checkpoint"]
    if "\n\n— " not in cp:
        return {"ok": False, "reason": "NO_SIG_BLOCK"}
    body, blk = cp.split("\n\n— ", 1)
    raw = base64.b64decode(blk.strip().split()[-1])
    for name, text in (("body+LF", body + "\n"), ("body", body), ("body+LF+LF", body + "\n\n")):
        if ecdsa_verify(pub, text.encode(), raw[4:], "p256", "sha256"):
            return {"ok": True, "variant": name, "keyhash": raw[:4].hex()}
    return {"ok": False, "reason": "SIGNATURE_MISMATCH"}


def check_set(entry, pub):
    obj = {"body": entry["body"], "integratedTime": int(entry["integratedTime"]),
           "logID": entry["logID"], "logIndex": int(entry["logIndex"])}
    der = base64.b64decode(entry["verification"]["signedEntryTimestamp"])
    for name, s in (("sorted-compact", json.dumps(obj, sort_keys=True, separators=(",", ":"))),
                    ("insertion-compact", json.dumps(obj, separators=(",", ":"))),
                    ("sorted-spaced", json.dumps(obj, sort_keys=True))):
        if ecdsa_verify(pub, s.encode(), der, "p256", "sha256"):
            return {"ok": True, "variant": name}
    return {"ok": False, "reason": "SET_MISMATCH"}


def check_chain(leaf_der, im_der, root_der):
    steps, ok = [], True
    for name, child, parent in (("leaf<-intermediate", leaf_der, im_der),
                                ("intermediate<-root", im_der, root_der)):
        tbs, _, sig, oid = cert_parts(child)
        _, ps, _, _ = cert_parts(parent)
        curve, hname = SIGALG.get(oid, ("p256", "sha256"))
        good = ecdsa_verify(point_from_spki(ps), tbs, sig, curve, hname)
        steps.append(f"{name}={good}")
        ok = ok and good
    return {"ok": ok, "detail": "; ".join(steps)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--entry", required=True)
    ap.add_argument("--rekor-key", required=True)
    ap.add_argument("--intermediate", required=True)
    ap.add_argument("--root", required=True)
    a = ap.parse_args()

    bundle = json.load(open(a.bundle, encoding="utf-8"))
    raw = json.load(open(a.entry, encoding="utf-8"))
    entry = raw[next(iter(raw))] if "body" not in raw else raw
    rk = open(a.rekor_key, encoding="utf-8").read()
    rpub = pub_from_rekor_pem(rk)

    vm = bundle.get("verificationMaterial") or {}
    certs = (vm.get("x509CertificateChain") or {}).get("certificates")
    leaf = base64.b64decode(certs[0]["rawBytes"] if certs else vm["certificate"]["rawBytes"])

    rows = []
    b = check_binding(a.artifact, entry)
    rows.append(("BINDING", "OK" if b["ok"] else f"FAIL {b['entry'][:12]}≠{b['artifact'][:12]}", ""))
    lg = check_logid(rk, bundle)
    rows.append(("LOGID_BINDING", "OK" if lg["ok"] else f"FAIL {lg['declared'][:12]}≠{lg['logid'][:12]}", ""))
    inc = check_inclusion(entry)
    rows.append(("INCLUSION", "OK" if inc["ok"] else "FAIL", f"idx={inc['logIndex']} depth={inc['depth']}"))
    cp = check_checkpoint(entry, rpub)
    rows.append(("CHECKPOINT", "OK" if cp["ok"] else f"FAIL {cp.get('reason')}", cp.get("variant", "")))
    st = check_set(entry, rpub)
    rows.append(("SET", "OK" if st["ok"] else f"FAIL {st.get('reason')}", st.get("variant", "")))
    ch = check_chain(leaf, pem_to_der(open(a.intermediate, encoding="utf-8").read()),
                     pem_to_der(open(a.root, encoding="utf-8").read()))
    rows.append(("CHAIN", "OK" if ch["ok"] else "FAIL", ch["detail"]))

    print("ZERO_DEP_VERIFY")
    for name, verdict, note in rows:
        print("  %-14s %-8s %s" % (name, verdict, note))
    ok = all(r[1] == "OK" for r in rows)
    print("\nZERO_DEP_" + ("ALL_PASS" if ok else "HAS_FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
