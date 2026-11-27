#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_croissant.py —— 给 pccp-bench v0.3.2 候选包出一份 Croissant 1.1 元数据。

目的不是"贴个标签"，是让一个陌生人和一台陌生机器都能读到：
这个包是什么、许可如何、字节指纹是多少、它从哪来（PROV-O）、谁判的。

产物：dist/pccp-bench_v0.3.2_croissant.json（用 mlcroissant 校验，不合规就改到合规）。
"""
import hashlib
import json
import os

PKG = "dist/pccp-bench_v0.3.2_candidate.zip"
OUT = "dist/pccp-bench_v0.3.2_croissant.json"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def build(digest, size):
    return {
        "@context": {
            "@language": "zh",
            "@vocab": "https://schema.org/",
            "sc": "https://schema.org/",
            "cr": "http://mlcommons.org/croissant/",
            "dct": "http://purl.org/dc/terms/",
            "prov": "http://www.w3.org/ns/prov#",
            "rai": "http://mlcommons.org/croissant/RAI/"
        },
        "@type": "sc:Dataset",
        "name": "pccp-bench",
        "description": ("PCCP（预定变更控制计划）变更范围判定的公开题集与判器。"
                        "51 题、9 个布尔判据标志（v0.3 编码层另展开四字段）；"
                        "本包为 v0.3.2 候选，未锚定。判定结论由判器给出，"
                        "不表示内容正确，也不表示已通过第三方实测。"),
        "version": "0.3.2-candidate",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "url": "https://github.com/stevenzhao07/pccp-bench-anchors",
        "citeAs": ("pccp-bench v0.3.2 candidate; 包内 MANIFEST.json 记录 21 个叶子的 sha256 与 merkle 根；"
                   "已锚版本为 v0.3（A-0003，Rekor logIndex 4143787841），本包未锚"),
        "datePublished": "2026-11-27",
        "citation": "pccp-bench v0.3.2 candidate (2026-11-27); 包内 MANIFEST.json 与 dist/pccp-bench_v0.3.2_candidate.zip 同字节",
        "isLiveDataset": False,
        "inLanguage": ["zh", "en"],
        "creator": {"@type": "Person", "name": "Steven Zhao", "url": "https://github.com/stevenzhao07"},
        "publisher": {"@type": "Organization", "name": "pccp-bench-anchors"},
        "keywords": ["PCCP", "FDA", "AI-DSF", "SaMD", "conformance", "transparency-log", "receipt"],
        "conformsTo": [
            "http://mlcommons.org/croissant/1.1",
            "https://www.w3.org/TR/prov-o/"
        ],
        "distribution": [{
            "@type": "https://schema.org/FileObject",
            "@id": "pccp-bench_v0.3.2_candidate.zip",
            "name": "pccp-bench_v0.3.2_candidate.zip",
            "contentUrl": "https://github.com/stevenzhao07/pccp-bench-anchors/raw/main/dist/pccp-bench_v0.3.2_candidate.zip",
            "encodingFormat": "application/zip",
            "sha256": digest,
            "contentSize": "%d B" % size
        }],
        "prov:wasGeneratedBy": {
            "@type": "prov:Activity",
            "prov:label": "build_v0_3_2.py",
            "prov:startedAtTime": "2026-11-27",
            "prov:wasAssociatedWith": {"@id": "https://github.com/stevenzhao07"}
        },
        "prov:wasDerivedFrom": {
            "@type": "prov:Entity",
            "prov:label": "pccp-bench v0.3（已锚，A-0003）",
            "dct:identifier": "rekor:logIndex=4143787841",
            "dct:description": ("v0.3.2 在 v0.3 之上只改编码层（冲突格置 None）与包内自检/重建 base，"
                                "判器字节未变；v0.3 包内 MANIFEST 的版本号是旧值，字节已进公共日志不可改")
        },
        "rai:dataCollection": ("题集由公开 PCCP 与 FDA AI-DSF 变更语义构建；"
                               "另采 47 条真实 FDA ao_statement 做探针（只写字面成立字段）"),
        "rai:dataUseCases": ("用于判定'某次变更是否落在已授权 PCCP 范围内'并出可验回执；"
                             "不用于声称器械安全有效"),
        "rai:dataLimitations": ("判器在同作者题集 51/51 属天花板；外部模型盲判 50/51；"
                                "真实变更回放 0 条；第三方实测 0 件；base.py 为重建版，非作者原字节"),
        "rai:personalSensitiveInformation": "无个人数据；语料仅取公开监管文书",
        "rai:dataBiases": "语料集中于 2024–2026 年 FDA 公开文书，工艺类占 36/47",
        "recordSet": []
    }


def main():
    digest, size = sha256(PKG), os.path.getsize(PKG)
    doc = build(digest, size)
    json.dump(doc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出 %s；zip=%d B sha256=%s" % (OUT, size, digest[:16]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


