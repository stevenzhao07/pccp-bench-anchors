# T1 邀请函（草稿 · 未发送）

状态：**未发送**。按规矩，任何对外发送须由本人明确许可；这份草稿只是把"发什么"先写好，
你点头（或指定收件人）之后才发。

---

## 邮件 / Issue 正文（可直接粘贴）

标题：`请求一次 10 分钟的技术复核（不需要你认同结论）`

> 你好，
>
> 我在做一个很小的事：把"医疗器械软件的预定变更控制计划（PCCP）变更是否在授权范围内"
> 这类判断，做成第三方能自己验的形式。做法不复杂——产物打 sha256、用 GitHub Actions 的
> keyless 身份签名、写进公共 Rekor 日志；验算工具是纯 Python 标准库写的，不需要装任何依赖。
>
> 我想请你做的只有一件事：**在你自己的机器上跑三条命令**，看能不能验出来。
> 不需要你认同我的判据、不需要你读代码、不需要你给结论背书。
>
> ```bash
> mkdir -p t1 && cd t1
> curl -sSLO https://raw.githubusercontent.com/stevenzhao07/pccp-bench-anchors/main/tools/verify_zero_dep.py
> mkdir -p certs
> curl -sSL  https://raw.githubusercontent.com/stevenzhao07/pccp-bench-anchors/main/certs/fulcio_intermediate.pem -o certs/fulcio_intermediate.pem
> curl -sSL  https://raw.githubusercontent.com/stevenzhao07/pccp-bench-anchors/main/certs/fulcio_root.pem -o certs/fulcio_root.pem
> curl -sSL 'https://rekor.sigstore.dev/api/v1/log/entries?logIndex=4143787841' -o entry.json
> curl -sSL 'https://rekor.sigstore.dev/api/v1/log/publicKey' -o rekor_publicKey.json
> python tools/verify_zero_dep.py --entry entry.json --rekor-key rekor_publicKey.json \
>   --intermediate certs/fulcio_intermediate.pem --root certs/fulcio_root.pem
> ```
>
> 期望最后一行是 `ZERO_DEP_ALL_PASS`（六项：BINDING / LOGID_BINDING / INCLUSION / CHECKPOINT / SET / CHAIN）。
> 任一项 FAIL 就是 FAIL，我不会把它算成通过。
>
> 跑完如果你愿意，把下面这段填好回给我（或者直接说"跑通了"也行）：
>
> ```json
> {"reviewer":"<你>","independent":true,"relationship":"<与项目无关的说明>",
>  "machine":"<OS + Python 版本>","checked_at":"<时间>",
>  "results":{"zero_dep_verify":"ZERO_DEP_ALL_PASS 或 HAS_FAIL"},
>  "disagreements":"<对不上的地方，没有就写 none>"}
> ```
>
> 边界先说清：这验的是"字节有没有进公共日志、能不能独立验出来"，**不验判断对不对**。
> 你不需要认同我的任何结论，也不需要为它背书。你若跑不通，我会把跑不通这件事原样记进台账，
> 不会写成"已验证"。
>
> 谢谢。

---

## 发之前必须确认的三件事

1. **收件人是谁**（具体的人，不是"发到群里"）。用你真认识、且与项目无关的人最好。
2. **渠道**（邮件 / 微信 / 仓库 Issue）。仓库 Issue 会公开可见，邮件不会。
3. **要不要附上"我们没做到什么"**（我建议附：T1 = 0、判器只读编码、没有真实变更回放。附上去，比被人翻出来强）。

## 收到回传之后我怎么记

只记原话进 `T1_LEDGER.md`：reviewer / 关系自述 / 时间 / 结果 / 差异项。
**不润色、不合并、不替对方解释。** 跑不通就记跑不通。
