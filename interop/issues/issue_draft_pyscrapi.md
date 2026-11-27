## 摘要
`install_requires = ["cbor2", "pycose", "rfc9290"]` 两处都没钉版本。装到 **cbor2 6.x** 后，
`pycose` 解带 tag 的 COSE 消息会直接失败——因为 `cbor2>=6` 把带 tag 的 CBOR 数组解成 **tuple**，
而 `pycose 1.1.0` 的 `decode()` 只认 **list**：

```python
# pycose/messages/cosemessage.py:54-74
cbor_msg  = cbor2.loads(received)
cose_obj  = cbor_msg.value          # ← cbor2 6.x 给 tuple
if isinstance(cose_obj, list): ...  # ← 只认 list
else: raise TypeError("Bytes cannot be decoded as COSE message")
```

最小复现：
```python
import cbor2, pycose
print(cbor2.loads(b"\xd2\x84\x01\x02\x03\x04"))   # CBORTag(18, (1, 2, 3, 4))  ← tuple
from pycose.messages import Sign1Message
Sign1Message.decode(b"\xd2\x84\x01\x02\x03\x04")  # TypeError: Bytes cannot be decoded as COSE message
```
降到 `cbor2==5.6.5` 同一句即正常（`CBORTag(18, [1,2,3,4])`，decode 通过）。

## 影响面
任何"签发 → 再读回"的路径都会踩：登记前把陈述从磁盘读回、验回执时重建 `phdr/payload/sig`、
CI 里 round-trip 测试。**mojibake 不在陈述本身**，同一份字节在 cbor2 5.6.5 下完全合法。

## 我们是怎么撞到的
用 `scitt-community/scitt-api-emulator`（已 archived）做一次 SCITT 形状的互通测试：
- 该模拟器同样 `Sign1Message.decode(claim, tag=True)` + 宽 `except`，于是**它自己 create-claim 产出的陈述也被自己的服务端以
  `400 invalidInput "Claim is not a valid COSE message"` 拒收**；
- 根因定位到 cbor2 版本；降到 5.6.5 后立刻受理（entryId 1，receipt verified）。
- 顺带：恢复 cbor2 6.3.0 后，模拟器自己的 `verify-receipt` 又失效，而我们另写的不依赖 pycose 的验算器仍能验过同一份回执——
  这说明缺陷在"解码入口"，不在回执数据。

## 建议
1. `install_requires` 钉住 `cbor2>=6.1,<7` 的同时，把解码入口归一化：
   ```python
   cose_obj = list(cose_obj) if isinstance(cose_obj, tuple) else cose_obj
   ```
2. 或者干脆不经 `pycose.decode`：`cbor2.loads` 后按 `[phdr, uhdr, payload, sig]` 自行解析（本场景不需要 pycose 的验签）。
3. 若上游确需 `cbor2>=6.1`（`cwt 4.0` 的要求），第 1 条是唯一不冲突的解法。

## 环境
Windows 11 / Python 3.13 / `pycose 1.1.0` / `cbor2 6.3.0`（pip）
