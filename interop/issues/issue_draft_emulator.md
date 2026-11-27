## 环境
- Windows 11 / Python 3.13
- `scitt-emulator` 0.0.1，源码来自 `scitt-community/scitt-api-emulator` main 分支 tarball（PyPI 无发行版）
- `pycose 1.1.0`、`cbor2 6.3.0`（cbor2 6.x 是 `cwt 4.0` 的要求：`cbor2>=6.1.0,<7`）
- 服务端：`scitt-emulator server -p 8088 --tree-alg CCF`

## 现象一：安装即失败（`rkvst-archivist` 已停止发布）
```
pip install .            # 或在本地目录安装
ERROR: Could not find a version that satisfies the requirement rkvst-archivist (from versions: none)
```
`tree_algs.py` → `rkvst.py` → `from archivist.archivist import Archivist`，即使只用 CCF 模式也会在 import 阶段炸掉。
绕过方式：`pip install --no-deps .` 再自建一个 `archivist` 桩模块（只满足 import），CLI 才能启动。

## 现象二：任何合法 COSE_Sign1 都被拒（cbor2 >= 6）
```
scitt-emulator client submit-claim --claim claim.cose --out receipt.cbor --url http://127.0.0.1:8088
HTTP 400 {"detail": "Claim is not a valid COSE message", "type": "urn:ietf:params:scitt:error:invalidInput"}
```

根因在 `scitt.py` 的 `_create_receipt`：
```python
try:
    msg = Sign1Message.decode(claim, tag=True)
except:                                       # ← 异常被吞成 invalidInput
    raise ClaimInvalidError("Claim is not a valid COSE message")
```
`pycose/messages/cosemessage.py:54-74` 中：
```python
cbor_msg = cbor2.loads(received)
cose_obj = cbor_msg.value
...
if isinstance(cose_obj, list): ...            # ← 只认 list
else: raise TypeError("Bytes cannot be decoded as COSE message")
```
而 `cbor2 >= 6` 对带 tag 的 CBOR 数组返回的是 **tuple**：
```python
>>> cbor2.loads(b"\xd2\x84\x01\x02\x03\x04")
CBORTag(18, (1, 2, 3, 4))        # cbor2 6.3.0 → value 是 tuple
>>> cbor2.loads(b"\xd2\x84\x01\x02\x03\x04")   # cbor2 5.6.5 → value 是 list
CBORTag(18, [1, 2, 3, 4])
```
因此只要 `cbor2 >= 6`，**该模拟器自己 `create-claim` 产出的陈述也会被自己的服务端拒收**，与陈述是否合法无关。

验证：把 cbor2 降到 5.6.5 后，同一条陈述立刻受理：
```
Claim Registered: entryId 1
Receipt verified（服务端 verify-receipt 通过）
Leaf e5b9b98d0539dfc150fe52ff41bfb7833a736fbcdf85ddf4b8e0198e0e065331
```
再恢复 cbor2 6.3.0，服务端 verifier 又失效（客户端侧我们自写的独立验算器不受影响）。

## 建议（三种都行）
1. `install_requires` 里把 `cbor2<6` 钉住（会与 `cwt>=4.0` 的 `cbor2>=6.1.0` 冲突，需要一并处理）；
2. 在 `_create_receipt` 里把 `cose_obj` 归一化：`cose_obj = list(cose_obj) if isinstance(cose_obj, tuple) else cose_obj`；
3. 或不要用 `Sign1Message.decode`，直接 `cbor2.loads` 后自己按 `[phdr, uhdr, payload, sig]` 解析（本模拟器本来也不验签）。

## 附：另一处（可选）
`server -p 8000` 在本机 Windows 上直接 `WSAEACCES`（Flask 起 socket 被拒），换 8088 正常。不是大问题，但如果默认端口是 8000，新手会卡住。

## 说明
我们是拿 `scitt-api-emulator` 做一次 SCITT 形状的互通测试时撞到这两个问题的；陈述来自我们自己的产物，不含任何商业内容。
