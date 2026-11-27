## 更正（自查源码后，撤回正文里两处不准确的地方）

回去逐行读了 `scitt.py` 的 `_create_receipt`，正文有两处与源码不符，先更正：

**1. 必需头是三项，且都要求出现在 protected 头（`msg.phdr`）**——我漏写了 Algorithm：
```python
if not isinstance(msg, Sign1Message): ...
if pycose.headers.Algorithm  not in msg.phdr: raise ClaimInvalidError("...algorithm header parameter")
if pycose.headers.ContentType not in msg.phdr: raise ClaimInvalidError("...content type header parameter")
if CWTClaims                 not in msg.phdr: raise ClaimInvalidError("...CWTClaims")
```

**2. 我写"签名缺失或不匹配"也在 `invalidInput` 里——不准确，撤回。**
该模拟器**根本不验签**（源码注释自述：does not verify the claim signature, does not apply registration policies）。
所以被同一个 `invalidInput` 吞掉的其实是这四类：
- CBOR/结构层解不出来
- 解得出来但不是 `COSE_Sign1`
- 缺 `Algorithm`（protected）
- 缺 `ContentType`(label 3) 或 `CWTClaims`(label 14)（protected）

**错误码粒度的诉求依旧成立**，只是原因清单要按上面这版看。

**3. 关于 label 14 放在 unprotected 头该接受还是拒绝，原文写"两种实现都见过"是我没有依据的说法，撤回。**
这条仍是我想请 WG 明确的问题：目前我只有一个实现作为样本，它要求 protected；规范若允许 unprotected，实现者会各写各的。

## 附：为什么这条值得报
这不是我调不通，而是**同一条合法字节在 cbor2 5.6.5 下受理、在 cbor2 6.3.0 下被拒**（服务端与 cbor2 版本强耦合），报错又统一是 "Claim is not a valid COSE message"。我把这条当成"错误码粒度"的证据提上来，而不是当成模拟器的 bug 报告——模拟器仓库已归档，issue 发不进去。
