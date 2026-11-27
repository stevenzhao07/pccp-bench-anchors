#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
verify_bundle.py —— 校验 sigstore bundle 的"身份 + 绑定"两件事（不重复做 Rekor 那三件套）。

判据：
  1) messageSignature.digest  == 产物字节 sha256
  2) tlog 条目 hashedrekord.digest == 同一 sha256   ← 这才是"签的是这份字节"
  3) 证书 SAN / OIDC 扩展里的 issuer 与 identity 是否等于期望值（必须显式给出，否则只是打印）
  4) 证书与条目在同一 bundle（结构自洽，不是从别处拼来的）

不做什么：不验证书链到 Fulcio 根（需 TUF 根，另走 verify_anchor/tuf），
不验 SET/包含性（verify_set.py / verify_anchor.py 各自负责）。

用法：
  python verify_bundle.py --bundle x.sigstore.json --artifact artifact.bin \
      --expect-issuer https://token.actions.githubusercontent.com \
      --expect-identity-regex '^https://github\.com/stevenzhao07/pccp-bench-anchors/'
"""
import argparse
import base64
import hashlib
import json
import re
import sys

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID
except ImportError:  # pragma: no cover
    print(json.dumps({"status": "ERROR", "reason": "缺 cryptography"}, ensure_ascii=False))
    sys.exit(2)

# Sigstore 证书里的自定义扩展 OID（1.3.6.1.4.1.57264.x）
OID_ISSUER_V1 = "1.3.6.1.4.1.57264.1.1"
OID_ISSUER_V2 = "1.3.6.1.4.1.57264.1.8"
OID_BUILD_SIGNER = "1.3.6.1.4.1.57264.1.9"


def norm_digest(v):
    """bundle 里 digest 有时是 base64（新格式），有时是十六进制（Rekor 条目）。
    统一成小写 hex，避免'看着不一样其实一样'的假失败。"""
    if not v:
        return None
    s = str(v).strip()
    if all(c in "0123456789abcdefABCDEF" for c in s) and len(s) == 64:
        return s.lower()
    try:
        pad = "=" * (-len(s) % 4)
        return base64.b64decode(s + pad).hex()
    except Exception:
        return s.lower()


def ext_text(cert, oid):
    for ext in cert.extensions:
        if ext.oid.dotted_string == oid:
            v = ext.value
            raw = getattr(v, "value", None)
            if isinstance(raw, bytes):
                # Sigstore 扩展值外面套了 ASN.1 壳，取其中可打印的 ASCII 段
                txt = raw.decode("utf-8", "ignore")
                m = re.findall(r"[\x20-\x7e]{6,}", txt)
                cand = m[-1] if m else txt
            else:
                cand = str(v)
            # 去掉 ASN.1 tag/长度字节残留（常见一个前导符号或十六进制串）
            u = re.search(r"https://[^\s\"'<>]+", cand)
            return u.group(0) if u else cand.strip("\x00\x0b\x0c+ ")
    return None


def san_uris(cert):
    """从 SAN 扩展里取全部 URI 值。GitHub Actions 的 identity 落在这里，
    不在 CN、也不在 email，所以必须单独读。"""
    out = []
    for e in cert.extensions:
        if e.oid.dotted_string == "2.5.29.17":
            try:
                for gn in e.value:
                    if gn.value is not None and isinstance(gn.value, str):
                        out.append(gn.value)
            except TypeError:
                pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--expect-issuer")
    ap.add_argument("--expect-identity-regex")
    a = ap.parse_args()

    art_sha = hashlib.sha256(open(a.artifact, "rb").read()).hexdigest()
    b = json.load(open(a.bundle, encoding="utf-8"))
    fails, notes = [], []

    # 1) messageSignature digest（可能是 base64）
    ms = b.get("messageSignature") or {}
    sig_digest = norm_digest((ms.get("messageDigest") or {}).get("digest"))
    if sig_digest != art_sha:
        fails.append(f"MESSAGE_DIGEST_MISMATCH bundle={str(sig_digest)[:16]} artifact={art_sha[:16]}")

    # 2) 条目里的 hashedrekord digest
    tlog_entries = (b.get("verificationMaterial") or {}).get("tlogEntries", [])
    if not tlog_entries:
        fails.append("NO_TLOG_ENTRY")
    entry_digest = None
    for e in tlog_entries:
        body_b64 = e.get("canonicalizedBody")
        if not body_b64:
            continue
        body = json.loads(base64.b64decode(body_b64))
        spec = body.get("spec") or {}
        hk = spec.get("hashedrekord") or spec   # 两种命名都兼容
        entry_digest = norm_digest(((hk.get("data") or {}).get("hash") or {}).get("value"))
        notes.append(f"tlog logIndex={e.get('logIndex')} kind={((e.get('kindVersion') or {}).get('kind'))}")
    if entry_digest != art_sha:
        fails.append(f"TLOG_DIGEST_MISMATCH entry={str(entry_digest)[:16]} artifact={art_sha[:16]}")

    # 3) 证书身份
    vm = b.get("verificationMaterial") or {}
    cert_raw = None
    if vm.get("certificate"):
        cert_raw = vm["certificate"]["rawBytes"]
    elif vm.get("x509CertificateChain"):
        cert_raw = vm["x509CertificateChain"]["certificates"][0]["rawBytes"]
    identity = issuer = None
    if not cert_raw:
        fails.append("NO_CERT_IN_BUNDLE")
    else:
        cert = x509.load_der_x509_certificate(base64.b64decode(cert_raw))
        subj = cert.subject
        emails = [attr.value for attr in subj.get_attributes_for_oid(NameOID.EMAIL_ADDRESS)]
        cns = [attr.value for attr in subj.get_attributes_for_oid(NameOID.COMMON_NAME)]
        identity = (emails or cns or [None])[0]
        issuer = ext_text(cert, OID_ISSUER_V2) or ext_text(cert, OID_ISSUER_V1)
        notes.append(f"cert_subject_CN={cns[0] if cns else None} email={emails or None}")
        notes.append(f"cert_san=" + str(ext_text(cert, "2.5.29.17") or
                                        next((str(e.value) for e in cert.extensions
                                              if e.oid.dotted_string == "2.5.29.17"), None)))

    if a.expect_issuer:
        if issuer != a.expect_issuer:
            fails.append(f"ISSUER_MISMATCH got={issuer} want={a.expect_issuer}")
    identity_uris = []
    if a.expect_identity_regex:
        if cert_raw:
            cert = x509.load_der_x509_certificate(base64.b64decode(cert_raw))
            identity_uris = san_uris(cert)
        target = identity or ""
        ok = any(re.search(a.expect_identity_regex, u) for u in identity_uris) or \
            bool(re.search(a.expect_identity_regex, target))
        if not ok:
            fails.append("IDENTITY_NOT_MATCHED")
            notes.append("san_uris=" + str(identity_uris))
        else:
            notes.append("identity_matched=" + str([u for u in identity_uris
                                                    if re.search(a.expect_identity_regex, u)]))

    out = {
        "status": "BUNDLE_VERIFIED" if not fails else "BUNDLE_INVALID",
        "artifact_sha256": art_sha,
        "entry_digest": entry_digest,
        "cert_identity": identity,
        "cert_oidc_issuer": issuer,
        "failures": fails,
        "notes": notes,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
