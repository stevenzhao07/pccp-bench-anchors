#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""muse_outreach.py —— 把当前情况交给 Muse 通道（SiliconFlow / DeepSeek-V3），请它帮两件事。

用户的指令：推广这块，把情况告诉 Muse，让它去找人。

所以本脚本发出去的不是"宣传稿"，是**事实包 + 三个具体请求**：
  1  以它见过的生态，指出"哪些具体去处能找到与项目无关的复核者"（不要泛泛而谈）；
  2  给一段可直接用的招募文案（邮件 / Issue / 社群帖各一版），要求含"跑不通也照记"这句；
  3  直说我们还没做到什么，并判断"做到最好了吗"。

原则（沿用既有纪律）：
  * 只发可核验事实：哈希、logIndex、命令、我们自己承认的缺口；不发结论性形容词；
  * 明确告诉它：它的回复只记 T2（外部模型复核），**不能**充当 T1 第三方实测；
  * key 只在内存里，不打印、不落盘。

用法：
  python muse_outreach.py --out out\\muse_outreach_20261127.json --md Muse通道_20261127.md
"""
import argparse
import json
import os
import re
import sys
import urllib.request

KEY_PATH = r"D:\标准\新建文本文档.txt"
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL = "deepseek-ai/DeepSeek-V3"

FACTS = """我们需要你帮的是"找人"，不是"评审"。先把我们有什么、没什么摆清楚。

【是什么】
一个公开的小基础设施：把"医疗器械软件的预定变更控制计划（PCCP）变更是否在授权范围内"
这类判断，做成第三方能自己验的形式。公开题集 51 题 + 一个确定性判器 + 可独立验算的公共锚定回执。

【已经做到的（可核验）】
- 公共透明日志里 4 条记录（Sigstore Rekor），最新 A-0003：logIndex 4143787841，
  锚定字节 sha256 d684eaca7b2ba32483c23a1474815bf0314dd2cdf8770648eb7b6e2c1826ed99（69,421 B）。
- 零依赖验算器（只用 Python 标准库，手写 P-256/P-384 与 DER 解析），一条命令出六项 PASS/FAIL，
  任一项 FAIL 即 FAIL，不加权不平均。对手工实现的 CT(SCT) 验签做过 16 种组合与日志 404 复核，
  结论是"不可由终证书重建"，我们把这条也写在正文里。
- 题集 v0.3.2：51 题（30 go / 14 hold / 7 reject），"永远答 go"基线 0.5882；
  判器在题上 51/51（**同作者**，属天花板，不作为独立证据）；
  外部模型盲判（DeepSeek-V3 早前一轮）50/51。
- 数据集包可自跑：空目录 + 隔离解释器 python -I 下 51/51、标签率 1.0；包内自带判器依赖与自检脚本。
- 判器负向可控：663 个布尔字段对，翻一位就改判 0.6682；零敏感题 0 条、全翻不变 0 条。
- 真实语料（47 条 FDA 批准说明）探针：字面只能填满 5 个必填里的 1 个，判器可用 0/47。
  我们据此写了"14 格最小编码表"，并承认：真实回放缺的是人，不是数据。

【还没做到的（这几条我们自己列）】
- 第三方实测 T1 = 0 件。所有"跑通"都是同操作者本机（T4）。
- 判器依赖的 base.py 不是作者原字节（按唯一调用点重建，文件内标注 RECONSTRUCTED）。
- 真实 PCCP 变更回放 = 0 条。
- SCITT：只做到 COSE_Sign1 形状可对接 + 可独立验签，**没有** Transparency Service 原生 Receipt，
  也不声明任何规范符合性。
- 隐藏题 10 条不在包内；发布前审查仍有多门 REFUSE/NOT RUN。

【我们不发的东西】
不发"首创/最强/全面超越"这类话；不把"待补"写成"通过"；不把"我自己换目录重跑"算作外人实测。

---

请回答三件事，务实、具体、可执行，不要鼓励性套话：

一、以你了解的生态，**具体去处**（写清名称/渠道/入口/为什么要去），能找到一个愿意花 10 分钟
    在本人机器上跑三条命令、且与本项目无关的人。给 6-10 个，按成功率排序，并说明每个去处的门槛
    （是否需要会员/是否公开可见/是否会被当成自我推广）。

二、给三段可直接用的招募文案：① 一对一邮件（≤180 词）；② 公开仓库 Issue（≤220 词）；
    ③ 一个技术社群帖（≤260 词）。要求：
    - 明写"你不需要认同结论，只需跑三条命令"；
    - 明写"跑不通也照原样记进台账"；
    - 不出现"首创/最强/领先/超越"这类词；
    - 附上可直达的公共入口（我们给：https://github.com/stevenzhao07/pccp-bench-anchors ，
      以及 Rekor 条目 https://rekor.sigstore.dev/api/v1/log/entries?logIndex=4143787841 ）。

三、你判断：这件事"做到最好了吗"？如果没到，按"还差什么 → 补它的最小动作 → 大约成本"列 5 条以内。
    请特别回答：一个只有 1 个人、没有机构背书的小项目，在"让别人愿意花时间验证"这件事上，
    最容易犯的错是什么。
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("out", "muse_outreach_20261127.json"))
    ap.add_argument("--md", default="Muse通道_20261127.md")
    ap.add_argument("--model", default=MODEL)
    a = ap.parse_args()

    key = open(KEY_PATH, "r", encoding="utf-8").read().strip()
    if not key.startswith("sk-"):
        print("KEY_NOT_FOUND_OR_BAD_FORMAT")
        return 2

    body = {
        "model": a.model,
        "messages": [
            {"role": "system", "content": "你是一个务实的技术评审与社群运营顾问。回答要具体到名字和入口，"
                                          "不要套话，不要替对方夸自己。"},
            {"role": "user", "content": FACTS},
        ],
        "temperature": 0.3,
        "max_tokens": 2600,
    }
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as f:
            resp = json.loads(f.read().decode("utf-8"))
    except Exception as exc:
        print("CALL_FAILED", type(exc).__name__, str(exc)[:200])
        return 3

    text = resp["choices"][0]["message"]["content"]
    usage = resp.get("usage", {})
    doc = {
        "_channel": "SiliconFlow / " + a.model,
        "_tier": "T2 外部模型复核（**不是** T1 第三方实测）",
        "_sent_at": "2026-11-27",
        "usage": usage,
        "packet_chars": len(FACTS),
        "answer": text,
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(doc, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    md = ["# Muse 通道回复（T2，外部模型复核）", "",
          "通道：" + doc["_channel"] + "　用量：" + json.dumps(usage, ensure_ascii=False), "",
          "> 这是外部模型给的建议，**不是**第三方实测。它不能拿去充当 T1。", "",
          "---", "", text, ""]
    open(a.md, "w", encoding="utf-8").write("\n".join(md))

    print("ANSWER_CHARS", len(text))
    print("OUT", a.out)
    print("MD ", a.md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
