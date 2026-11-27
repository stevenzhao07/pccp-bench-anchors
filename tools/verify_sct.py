#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
verify_sct.py —— 把"CT/SCT 未验"这句话说准，而不是含糊带过。

之前的状态页写的是"CT 日志与 SCT 未校验"。这句话太粗：证书里到底有没有 SCT？
有几个？属于哪家 CT 日志？先把事实列出来，再决定"未验"的边界在哪。

本工具做（能确定的部分）：
  1) 解析 leaf 的 SCT 扩展，列出每个 SCT 的版本、log_id、时间戳
  2) 判断 SCT 数量是否 ≥1（Fulcio 通常嵌 2 个）
  3) 尝试从 Sigstore 官方信任根取 CT 日志公钥，核对 log_id 是否属于已登记日志

本工具**不做**（明确不冒充）：
  - 不验 SCT 签名。RFC 6962 的 SCT 签名是对"预证书 TBS"算叶子哈希后签的，
    而最终证书里 poison 扩展已被替换成 SCT 扩展，TBS 字节变了；要验必须重建预证书 TBS。
    本机未做重建，因此签名一律标 NOT_VERIFIED。
  - 不拉 CT 日志做 Merkle 包含性证明（CT 是 append-only 的另一棵树，不在 Rekor 里）。

用法：
  python verify_sct.py --bundle out\anchor_A0002.sigstore.json
"""
import argparse
import base64
import json
import sys

from cryptography import x509
from cryptography.hazmat.primitives import serialization  # noqa: F401  (仅用于类型完整)


def ct_keys_from_tuf():
    """尝试从 TUF 信任根取 CT 日志公钥（失败就返回空，并让调用方如实报告）。"""
    import os
    import shutil
    _o = os.symlink

    def _f(s, d, target_is_directory=False, **k):
        try:
            return _o(s, d, target_is_directory=target_is_directory)
        except (OSError, NotImplementedError):
            sa = s if os.path.isabs(s) else os.path.join(os.path.dirname(d), s)
            if os.path.lexists(d):
                os.unlink(d)
            shutil.copyfile(sa, d)
            return None

    os.symlink = _f
    try:
        from sigstore._internal.trust import TrustedRoot
        tr = TrustedRoot.production()
        ring = tr.ct_keyring
        # 不同版本签名不同，逐个试
        keys = []
        for call in (lambda: ring(), lambda: ring("ctfe"), lambda: ring("CTFE")):
            try:
                keys = list(call())
                if keys:
                    break
            except TypeError:
                continue
        out = []
        for k in keys:
            try:
                der = k.public_bytes(encoding=serialization.Encoding.DER,
                                     format=serialization.PublicFormat.SubjectPublicKeyInfo)
                out.append(der)
            except Exception:
                pass
        return out
    except Exception:
        return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    a = ap.parse_args()

    b = json.load(open(a.bundle, encoding="utf-8"))
    vm = b.get("verificationMaterial") or {}
    raw = vm.get("certificate", {}).get("rawBytes") or \
        vm.get("x509CertificateChain", {}).get("certificates", [{}])[0].get("rawBytes")
    if not raw:
        print(json.dumps({"status": "NO_CERT"}, ensure_ascii=False)); return 2
    cert = x509.load_der_x509_certificate(base64.b64decode(raw))

    try:
        ext = cert.extensions.get_extension_for_class(
            x509.PrecertificateSignedCertificateTimestamps).value
        scts = list(ext)
    except x509.ExtensionNotFound:
        print(json.dumps({"status": "NO_SCT", "note": "证书未嵌 SCT"}, ensure_ascii=False))
        return 1

    items = []
    for s in scts:
        try:
            log_id = s.log_id.hex()
        except Exception:
            log_id = "?"
        v = getattr(s, "version", None)
        items.append({"version": getattr(v, "name", str(v)),
                      "log_id": log_id,
                      "timestamp": str(getattr(s, "timestamp", None))})

    keys = ct_keys_from_tuf()
    recognized = []
    if keys:
        import hashlib
        known = {hashlib.sha256(k).hexdigest(): i for i, k in enumerate(keys)}
        for it in items:
            hit = next((v for h, v in known.items() if it["log_id"].startswith(h[:8])), None)
            recognized.append({"log_id": it["log_id"][:16], "tuf_match": hit is not None})

    out = {
        "status": "SCT_PRESENT_SIGNATURE_NOT_VERIFIED",
        "sct_count": len(items),
        "scts": items,
        "tuf_ct_keys_found": len(keys),
        "tuf_match": recognized or "未取到 TUF CT 公钥，无法核对归属",
        "not_verified": [
            "SCT 签名（需重建预证书 TBS；本机未做）",
            "CT 日志里的 Merkle 包含性（CT 是独立的一棵树）",
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
