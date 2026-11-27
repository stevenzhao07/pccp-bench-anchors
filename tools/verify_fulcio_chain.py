#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
verify_fulcio_chain.py —— 把"身份可信"从"我们说了算"变成"链上可验"。

之前 verify_bundle.py 只看了证书里的 issuer / SAN 字段，没有验签发链。
也就是说：拿一张自己伪造、字段照抄的证书，也能过。这是真实的口子。

这里做三件事：
  1) 拉 Sigstore 的 TUF 信任根（用官方 sigstore-python 的 TrustedRoot，它自己做 TUF 校验），
     取出 Fulcio 的 root / intermediate 证书
  2) 用 cryptography 逐级验签：leaf ← intermediate ← root，并检查
     - 时间：integratedTime 必须落在 leaf 的 notBefore..notAfter（Fulcio 只签 10 分钟）
     - 用途：leaf 必须带 CodeSigning EKU
     - 基本约束：CA 证书必须 CA=true，leaf 必须 CA=false
  3) 打印 leaf 的 issuer / SAN，供与 bundle 里的身份字段交叉核对

不做：CT 日志（Fulcio 会把证书写进 CT，本工具未拉 CT 证明）、SCT 校验。
这两项在输出里明确标成未做，不冒充已验。

用法：
  python verify_fulcio_chain.py --bundle out\anchor_A0002.sigstore.json --integrated-time 1795756228
"""
import argparse
import base64
import json
import os
import shutil
import sys
from datetime import datetime, timezone

# --- Windows 无符号链接特权时，把 python-tuf 的 os.symlink 降级为复制 ----------
_orig_symlink = os.symlink


def _symlink_or_copy(src, dst, target_is_directory=False, **kw):
    try:
        return _orig_symlink(src, dst, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError):
        src_abs = src if os.path.isabs(src) else os.path.join(os.path.dirname(dst), src)
        if os.path.lexists(dst):
            os.unlink(dst)
        shutil.copyfile(src_abs, dst)
        return None


os.symlink = _symlink_or_copy
# --------------------------------------------------------------------------------

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtendedKeyUsageOID


def load_fulcio_certs():
    """从 Sigstore 官方信任根取 Fulcio 证书链。TUF 校验由 sigstore-python 负责；
    如果本机没装，直接报错而不是悄悄退回自签根（那等于没验）。"""
    try:
        from sigstore._internal.trust import TrustedRoot
    except Exception as e:  # pragma: no cover
        raise SystemExit(f"需要 sigstore 包（TUF 校验在这里发生）：{e}")

    tr = TrustedRoot.production()
    return list(tr.get_fulcio_certs())


def verify_sig(issuer_cert, subject_cert):
    pub = issuer_cert.public_key()
    sig = subject_cert.signature
    tbs = subject_cert.tbs_certificate_bytes
    h = subject_cert.signature_hash_algorithm
    if isinstance(pub, ec.EllipticCurvePublicKey):
        pub.verify(sig, tbs, ec.ECDSA(h))
        return True
    if isinstance(pub, rsa.RSAPublicKey):
        pub.verify(sig, tbs, padding.PKCS1v15(), h)
        return True
    raise ValueError("未知公钥类型")


def eku(cert):
    """返回 EKU 的 OID 字符串列表。cryptography 新版里 OID 对象没有 .name，
    只有 .dotted_string，所以按 OID 比，别按名字比。"""
    try:
        ext = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        return [oid.dotted_string for oid in ext]
    except x509.ExtensionNotFound:
        return []


def is_ca(cert):
    try:
        return cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--integrated-time", type=int, default=None,
                    help="条目 integratedTime（epoch 秒）；给了才做有效期检查")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    b = json.load(open(a.bundle, encoding="utf-8"))
    vm = b.get("verificationMaterial") or {}
    if vm.get("certificate"):
        leaf_der = base64.b64decode(vm["certificate"]["rawBytes"])
    elif vm.get("x509CertificateChain"):
        leaf_der = base64.b64decode(vm["x509CertificateChain"]["certificates"][0]["rawBytes"])
    else:
        print("NO_CERT_IN_BUNDLE"); return 2
    leaf = x509.load_der_x509_certificate(leaf_der)

    cas = load_fulcio_certs()
    fails, notes, chain = [], [], []

    # 在信任根里找 leaf 的签发者
    issuer_cert = None
    for ca in cas:
        if leaf.issuer == ca.subject:
            try:
                verify_sig(ca, leaf)
                issuer_cert = ca
                break
            except Exception:
                continue
    if issuer_cert is None:
        # 也许 leaf 直接由某个 root 签（Fulcio 有三段链时中间层在别处）
        fails.append("ISSUER_NOT_IN_TRUST_ROOT")
    else:
        chain.append(("leaf<-issuer", True))

    # 签发者自身的上级
    if issuer_cert is not None:
        root = None
        for ca in cas:
            if ca.subject == issuer_cert.issuer and ca.subject != issuer_cert.subject:
                try:
                    verify_sig(ca, issuer_cert)
                    root = ca
                    break
                except Exception:
                    continue
        if root is not None:
            chain.append(("issuer<-root", True))
        elif issuer_cert.subject == issuer_cert.issuer:
            notes.append("签发者即自签根（两段链）")
        else:
            fails.append("CHAIN_STOPPED_NO_ROOT")

    # 有效期
    if a.integrated_time:
        t = datetime.fromtimestamp(a.integrated_time, tz=timezone.utc)
        nb, na = leaf.not_valid_before_utc, leaf.not_valid_after_utc
        if not (nb <= t <= na):
            fails.append(f"CERT_NOT_VALID_AT_INTEGRATED_TIME ({nb}..{na} vs {t})")
        else:
            notes.append(f"有效期覆盖 integratedTime（窗口 {(na-nb).total_seconds():.0f} 秒）")

    # 用途与约束
    e = eku(leaf)
    if ExtendedKeyUsageOID.CODE_SIGNING.dotted_string not in e:
        fails.append(f"LEAF_EKU_MISSING_CODE_SIGNING ({e})")
    if is_ca(leaf) is True:
        fails.append("LEAF_IS_CA")   # 叶证书不得是 CA；"无此扩展"是正常叶子，不算错
    elif is_ca(leaf) is None:
        notes.append("leaf 无 BasicConstraints（端点证书常态，按非 CA 处理）")
    for ca in [c for c in [issuer_cert] if c] :
        if is_ca(ca) is not True:
            fails.append("ISSUER_NOT_CA")

    # 身份字段（供交叉核对）
    san = ""
    try:
        for gn in leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value:
            if gn.value:
                san = str(gn.value)
                break
    except x509.ExtensionNotFound:
        pass

    out = {
        "status": "FULCIO_CHAIN_VERIFIED" if not fails else "CHAIN_INVALID",
        "chain": [list(c) for c in chain],
        "leaf_subject": leaf.subject.rfc4514_string(),
        "leaf_san": san,
        "leaf_not_before": leaf.not_valid_before_utc.isoformat(),
        "leaf_not_after": leaf.not_valid_after_utc.isoformat(),
        "leaf_eku": e,
        "fails": fails,
        "notes": notes + ["CT 日志与 SCT 未校验（本项目未实现，不冒充已验）"],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
