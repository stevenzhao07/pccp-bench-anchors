#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_blocked_hosts.py —— 把两项「网络阻塞」从 UNKNOWN 拆到具体层。

为什么值得做：之前只记了 "URLError" / "RemoteDisconnected"，那是症状不是原因。
只有拆到 DNS / TCP / TLS / HTTP 哪一层断的，才知道"等网络恢复"这句话到底等的是什么，
也才知道能不能换个端点（例如 HF 的 API 与 CDN 常常一条通一条不通）。
"""
from __future__ import annotations

import json
import socket
import ssl
import sys
import time

import httpx

HOSTS = [
    ("huggingface.co", 443, "https://huggingface.co/api/datasets?limit=1"),
    ("hf.co", 443, "https://hf.co"),
    ("cdn-lfs.huggingface.co", 443, None),
    ("cdn-lfs-us-1.hf.co", 443, None),
    ("zenodo.org", 443, "https://zenodo.org/api/records?size=1"),
    ("sandbox.zenodo.org", 443, "https://sandbox.zenodo.org/api/records?size=1"),
]


def dns(host: str) -> dict:
    t0 = time.time()
    try:
        infos = socket.getaddrinfo(host, None)
        ips = sorted({i[4][0] for i in infos})
        return {"ok": True, "ips": ips[:4], "ms": round((time.time() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": type(e).__name__ + ": " + str(e)[:80],
                "ms": round((time.time() - t0) * 1000)}


def tcp(host: str, port: int) -> dict:
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=8) as s:
            peer = s.getpeername()
        return {"ok": True, "peer": str(peer), "ms": round((time.time() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": type(e).__name__ + ": " + str(e)[:80],
                "ms": round((time.time() - t0) * 1000)}


def tls(host: str, port: int) -> dict:
    ctx = ssl.create_default_context()
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=8) as s:
            with ctx.wrap_socket(s, server_hostname=host) as ss:
                cert = ss.getpeercert()
                return {"ok": True, "subject": str(cert.get("subject", "")[:60]),
                        "issuer": str(cert.get("issuer", "")[:60]),
                        "ms": round((time.time() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": type(e).__name__ + ": " + str(e)[:80],
                "ms": round((time.time() - t0) * 1000)}


def http(url: str) -> dict:
    t0 = time.time()
    try:
        r = httpx.get(url, timeout=10, follow_redirects=True)
        return {"status": r.status_code, "ms": round((time.time() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001
        return {"err": type(e).__name__ + ": " + str(e)[:100],
                "ms": round((time.time() - t0) * 1000)}


def classify(d: dict, t: dict, s: dict, h: dict | None) -> str:
    if not d.get("ok"):
        return "DNS_FAIL"
    if not t.get("ok"):
        return "TCP_BLOCKED"
    if not s.get("ok"):
        return "TLS_FAIL"
    if h is None:
        return "TCP+TLS_OK"
    if "status" in h:
        return "HTTP_%s" % h["status"]
    return "HTTP_FAIL"


def main() -> int:
    out = []
    for host, port, url in HOSTS:
        d, t, s = dns(host), tcp(host, port), tls(host, port)
        h = http(url) if (url and t.get("ok")) else None
        row = {"host": host, "dns": d, "tcp": t, "tls": s, "http": h,
               "verdict": classify(d, t, s, h)}
        out.append(row)
        print("%-26s %-14s dns=%s tcp=%s tls=%s http=%s"
              % (host, row["verdict"],
                 "OK" if d.get("ok") else "X",
                 "OK" if t.get("ok") else "X",
                 "OK" if s.get("ok") else "X",
                 (h or {}).get("status", (h or {}).get("err", "-"))))
    import os
    os.makedirs("out", exist_ok=True)
    json.dump(out, open("out/blocked_hosts_probe.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n写入 out/blocked_hosts_probe.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
