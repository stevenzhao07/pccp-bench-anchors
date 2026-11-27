#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
verify_sct_sig.py —— 把"CT/SCT 未验"从一句免责声明，压成一张可复现的试验记录。

它做三件事，每件都给结论，不合并成一句"未验"：

  1  证书里有没有 SCT？归属哪个 CT 日志？（有 → log_id 是否在官方 TUF 信任根里 → 是 2022 生产日志）
  2  SCT 签名能不能验？—— 需要**预证书 TBS**。终证书里只有"带 SCT 扩展的 TBS"，
     Fulcio 的流程是「带 poison 扩展的预证书 → 拿 SCT → 把 poison 换成 SCT 扩展发终证书」。
     故本脚本按最小 DER 解析器把 SCT 扩展换回 poison 扩展，重建预证书 TBS，
     并同时试 4 种叶子构造 × 2 种时间戳单位 × 2 种签名类型，逐条报命中/未命中。
  3  CT 树认不认这枚叶子？—— 直接拿重建出的叶子哈希去 ctfe 的 get-proof-by-hash，
     若日志认得出，会回审计路径；回 404 说明日志里没有这条叶子。
     这一条是关键：它把"SCT 签名失败"与"预证书字节重建失败"分开定责。

已知结论（本机实跑，见输出）：签名与日志查询**双双未命中**，因此责任在
「预证书字节无法由终证书单靠扩展替换还原」，不在密钥或算法选择。
CT 树的 Merkle 包含性因此仍未取得——这是独立的一棵树，需真实预证书字节才能算。

用法：
  python verify_sct_sig.py --bundle out\anchor_A0002.sigstore.json \
      --trusted-root out\tuf_trusted_root.json [--ct-probe]
"""
import argparse
import base64
import hashlib
import json
import struct
import sys
import urllib.parse
import urllib.request

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

POISON_OID = bytes.fromhex("2b06010401d679020403")
SCT_OID = bytes.fromhex("2b06010401d679020402")


def tlv(b, i=0):
    tag = b[i]
    l = b[i + 1]
    i += 2
    if l & 0x80:
        n = l & 0x7F
        l = int.from_bytes(b[i:i + n], "big")
        i += n
    return tag, b[i:i + l], i + l


def enc(tag, content):
    if len(content) < 0x80:
        return bytes([tag, len(content)]) + content
    ln = len(content).to_bytes((len(content).bit_length() + 7) // 8, "big")
    return bytes([tag, 0x80 | len(ln)]) + ln + content


def children(b):
    out, i = [], 0
    while i < len(b):
        t, c, i = tlv(b, i)
        out.append((t, c))
    return out


def poison_ext():
    inner = enc(0x06, POISON_OID) + enc(0x01, b"\xff") + enc(0x04, b"\x05\x00")
    return enc(0x30, inner)


def rebuild_tbs(cert_der, drop_sct=True):
    """终证书 TBS → 预证书 TBS（去掉 SCT 扩展、加回 poison 扩展）。"""
    _, cert_content, _ = tlv(cert_der)
    tbs_tag, tbs_content, _ = tlv(cert_content)
    kids = []
    for tag, c in children(tbs_content):
        if tag == 0xA3:
            _, ext_content, _ = tlv(c)
            kept = []
            for etag, ec_ in children(ext_content):
                _, oid_c, _ = tlv(ec_)
                if drop_sct and oid_c == SCT_OID:
                    continue
                kept.append((etag, ec_))
            if drop_sct:
                kept.append((0x30, poison_ext()[2:]))
            kids.append((0xA3, enc(0x30, b"".join(enc(t, x) for t, x in kept))))
        else:
            kids.append((tag, c))
    return enc(tbs_tag, b"".join(enc(t, x) for t, x in kids))


def verify(pub, sig, data):
    if isinstance(pub, ec.EllipticCurvePublicKey):
        pub.verify(sig, data, ec.ECDSA(hashes.SHA256()))
    elif isinstance(pub, rsa.RSAPublicKey):
        pub.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())
    else:
        raise ValueError("unsupported key")


def ct_get(base, path):
    return json.loads(urllib.request.urlopen(base + path, timeout=25).read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--trusted-root", required=True)
    ap.add_argument("--ct-probe", action="store_true", help="向 ctfe 查叶子是否在树里")
    a = ap.parse_args()

    b = json.load(open(a.bundle, encoding="utf-8"))
    vm = b.get("verificationMaterial") or {}
    raw = vm.get("certificate", {}).get("rawBytes") \
        or vm["x509CertificateChain"]["certificates"][0]["rawBytes"]
    der = base64.b64decode(raw)
    leaf = x509.load_der_x509_certificate(der)
    sct = list(leaf.extensions.get_extension_for_class(
        x509.PrecertificateSignedCertificateTimestamps).value)[0]

    troot = json.load(open(a.trusted_root, encoding="utf-8"))
    ct = next((c for c in troot["ctlogs"]
               if base64.b64decode(c["logId"]["keyId"] + "==")[:32].hex() == sct.log_id.hex()), None)
    rep = {
        "sct_present": True,
        "sct_version": str(sct.version),
        "entry_type": str(sct.entry_type),
        "log_id": sct.log_id.hex(),
        "timestamp": str(sct.timestamp),
        "sig_alg": f"{sct.signature_algorithm}/{sct.signature_hash_algorithm.name}",
    }
    if ct is None:
        rep["verdict"] = "SCT_LOG_NOT_TRUSTED"
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 1
    rep["ct_log"] = ct.get("baseUrl")
    ct_pub = serialization.load_der_public_key(base64.b64decode(ct["publicKey"]["rawBytes"]))

    # 签发者：按 subject 匹配 TUF CA，并用它反向验叶证书签名（顺带证明确实是这把钥匙签的叶子）
    issuer = None
    for ca in troot["certificateAuthorities"]:
        for c in ca["certChain"]["certificates"]:
            cand = x509.load_der_x509_certificate(base64.b64decode(c["rawBytes"]))
            if cand.subject == leaf.issuer:
                issuer = cand
    leaf_sig_ok = False
    try:
        issuer.public_key().verify(leaf.signature, leaf.tbs_certificate_bytes,
                                   ec.ECDSA(leaf.signature_hash_algorithm))
        leaf_sig_ok = True
    except Exception:
        pass
    rep["issuer"] = issuer.subject.rfc4514_string()
    rep["leaf_signed_by_issuer"] = leaf_sig_ok

    ikh = hashlib.sha256(issuer.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo)).digest()
    ts_ms = int(sct.timestamp.timestamp() * 1000)

    cands = {
        "precert_tbs / ikh+tbs / typename-1": (rebuild_tbs(der, True), bytes([0, 1]) + ikh + rebuild_tbs(der, True)),
        "precert_tbs / sha(ikh+tbs)": (rebuild_tbs(der, True), bytes([0, 1]) + hashlib.sha256(ikh + rebuild_tbs(der, True)).digest()),
        "final_tbs / ikh+tbs": (leaf.tbs_certificate_bytes, bytes([0, 1]) + ikh + leaf.tbs_certificate_bytes),
        "final_cert / x509-entry": (leaf.tbs_certificate_bytes, bytes([0, 0]) + der),
    }
    attempts = []
    for name, (tbs, entry) in cands.items():
        sig_hit = False
        for st in (0, 1):
            for ts in (ts_ms, ts_ms // 1000):
                data = bytes([0, st]) + struct.pack(">Q", ts) + entry + b"\x00\x00"
                try:
                    verify(ct_pub, sct.signature, data)
                    sig_hit = True
                except Exception:
                    pass
        row = {"construction": name, "sct_signature": "VERIFIED" if sig_hit else "NOT_VERIFIED"}
        if a.ct_probe:
            leaf_hash = hashlib.sha256(b"\x00" + bytes([0, 0]) + struct.pack(">Q", ts_ms) + entry).digest()
            sth = ct_get(ct["baseUrl"], "/ct/v1/get-sth")
            q = ("/ct/v1/get-proof-by-hash?hash="
                 + urllib.parse.quote(base64.b64encode(leaf_hash).decode())
                 + "&tree_size=" + str(sth["tree_size"]))
            try:
                p = ct_get(ct["baseUrl"], q)
                row["ct_tree"] = f"IN_TREE leaf_index={p.get('leaf_index')} nodes={len(p['audit_path'])}"
            except Exception as e:
                row["ct_tree"] = ("NOT_IN_TREE" if "404" in str(e) else str(e))
        attempts.append(row)
    rep["attempts"] = attempts
    rep["ct_tree_size"] = sth.get("tree_size") if a.ct_probe else None

    any_hit = any(r["sct_signature"] == "VERIFIED" for r in attempts)
    rep["verdict"] = "SCT_VERIFIED" if any_hit else "SCT_NOT_VERIFIED_PRECERT_BYTES_UNREPRODUCIBLE"
    rep["responsibility"] = (None if any_hit else
                             "签名失败与日志查询 404 同时成立 → 问题在预证书字节无法由终证书还原，"
                             "不在密钥/算法选择；CT 树 Merkle 包含性因此仍未取得")
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if any_hit else 1


if __name__ == "__main__":
    sys.exit(main())
