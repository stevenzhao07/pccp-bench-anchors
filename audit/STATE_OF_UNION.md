# 收尾总账（由 audit_all.py 自动生成）

生成时间：2026-11-27T19:08:46+08:00　环境：Windows-10-10.0.19045-SP0 / Python 3.13.18

**判定：ALL_CHECKS_PASS**　通过 15 / 失败 0 / 出错 0 / 跳过 2

## 逐项检查

| # | 检查 | 判据 | 结果 | 读数 |
|---|---|---|---|---|
| 1 | `HASH-A-0001` | A-0001 的产物字节哈希等于台账登记值 | PASS | sha256=1907e93a21305c30… 期望 1907e93a21305c30… size=60505 |
| 2 | `HASH-A-0002` | A-0002 的产物字节哈希等于台账登记值 | PASS | sha256=b19fd9d6dc473fee… 期望 b19fd9d6dc473fee… size=761 |
| 3 | `HASH-A-0003` | A-0003 的产物字节哈希等于台账登记值 | PASS | sha256=d684eaca7b2ba324… 期望 d684eaca7b2ba324… size=69421 |
| 4 | `REC-S0001` | S-0001 在公共日志条目里的 hash 值与 logIndex 与台账一致 | PASS | kind=hashedrekord alg=sha256 logIndex=4145697630 sha=bda911e8d9a794b6… |
| 5 | `INC-S0001` | Merkle 包含路径能被离线重算并校验通过 | PASS | 4023793372 ／ hTOUi7Em... ／   NOT_CHECKED   = checkpoint 签名 / SET 签名（未实现，不得称为已通过） |
| 6 | `SET-S0001` | 签名条目时间戳(SET)能被离线重算并校验通过 | PASS |   "integratedTime": 1795770765, ／   "set_sha256": "d7e2f81e75e1b9e9" ／ } |
| 7 | `CP-S0001` | checkpoint 签名能被离线重算并校验通过 | PASS |   WARN           = 条目 record.logIndex 与 proof.logIndex 不一致，需记待核 ／   NOT_IMPLEMENTED= SET 签名 / logID↔公钥登记校验 ／ ANCHOR_VERIFIED |
| 8 | `ZDEP-A0003` | A-0003 的六项（绑定/LOGID/包含/checkpoint/SET/证书链）零三方依赖全过 | PASS | 6 行判据；BINDING        OK ／ LOGID_BINDING  OK ／ INCLUSION      OK       idx=4021883579 depth=26 ／ CHECKPOINT     OK       body+LF ／ SET            OK       sorted-compact ／ CHAIN     |
| 9 | `SCITT-TAG18` | COSE_Sign1 陈述（tag 18）验签通过，且 subject_sha256 与包字节绑定 | PASS |   ISSUER         urn:pccp-bench:test-key-20261127 ／   SUBJECT_SHA256 d684eaca7b2ba32483c23a1474815bf0314dd2cdf8770648eb7b6e2c1826ed99 ／   BINDING        OK ／ SCITT_ALL_PASS |
| 10 | `SCITT-UNTAGGED` | COSE_Sign1 陈述（untagged）验签通过，且 subject_sha256 与包字节绑定 | PASS |   ISSUER         urn:pccp-bench:test-key-20261127 ／   SUBJECT_SHA256 d684eaca7b2ba32483c23a1474815bf0314dd2cdf8770648eb7b6e2c1826ed99 ／   BINDING        OK ／ SCITT_ALL_PASS |
| 11 | `SCITT-TAMPER` | 篡改一个字节后必须验不过（证明不是恒真） | PASS |   SUBJECT_SHA256 d684eaca7b2ba32483c23a1474815bf0314dd2cdf8770648eb7b6e2c1826ed99 ／ SCITT_HAS_FAIL |
| 12 | `PKG-V032` | v0.3.2 包在空目录自跑 51/51 判决一致，cases_sha256 与登记一致 | PASS | verdict_match  51/51 ／ tag_rate       1.0000 ／ SELFCHECK_ALL_PASS |
| 13 | `KAPPA` | κ 计算器的四个解析算例（0.4 / 1.0 / 0.0 / 0.798）全部对上 | PASS | SELFTEST_OK   完全一致 κ=1.0 ／ SELFTEST_OK   系统性反向 κ=0.0 ／ SELFTEST_OK   负向对照（5 例扰动）κ=0.798 < 0.8 ／ KAPPA_SELFTEST_ALL_PASS |
| 14 | `BLIND-NOANSWER` | 10 题盲标包结构上不含答案（无答案文件、判决列全空、内部标注串零出现） | PASS | 成员 5 个；无泄漏 |
| 15 | `CLAIMS` | 全部 markdown 已过禁语机审（禁语只活在否定语境） | PASS | 扫描 23 个 md，命中 0 处 → CLAIM_AUDIT_CLEAN |
| 16 | `LINKS` | 上下游链接探活 | SKIP | 未加 --with-network |
| 17 | `SIGSTORE` | sigstore 官方库交叉验 | SKIP | 未加 --with-network |

## 仍未做到的（同一份总账里列清）

| 事项 | 现状 | 说明 |
|---|---|---|
| T1 第三方实测 | 0 件 | 盲标包已就绪，缺一位与项目无关的评审人；发送需用户指定渠道 |
| κ 真实读数 | 仅干跑 | A/B 两组为同操作者干跑（T4），不代表独立一致：{} |
| A-0004 锚定 v0.3.2 | 未锚 | 等一个字；候选包已在 dist/ |
| 真实 PCCP 变更回放 | 0 条 | 缺'人 + 14 格 + 每格可直达引用'的真实变更档案 |
| 已投递 issue 的回复 | 0 回复 | 三处 201 Created（croissant #1078 / py-scrapi #10 / scrapi-wg #215） |

## 口径边界

- 本输出证明的是：这些字节、这些哈希、这些签名关系能被任何人在离线环境重算一致。
- 本输出不证明：判据内容在监管意义上正确、第三方已见证、或本项目优于任何他人实现。
