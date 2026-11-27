## 背景
拿 `scitt-community/scitt-api-emulator` 做了一次 SCITT 形状的互通测试（自己签一条 `COSE_Sign1` 陈述 → `POST /entries` → 用服务端与自写验算器双方各自验回执）。撞到两类问题：

1. **实现侧硬缺陷**（会导致同一条合法陈述时好时坏）；
2. **错误码语义**：陈述解不出来时，服务端以 `400 invalidInput "Claim is not a valid COSE message"` 回应，实现者无法区分"格式坏 / 字段缺 / 签名不合 / 依赖版本错"。

第 2 点我认为值得在 SCRAPI 层面讨论，所以发在这里；第 1 点只是作为事实与复现附上，供其他实现者避开。

## 一、现象（可复现）
```
POST /entries  (Content-Type: application/scitt-statement+cose, 一条带 tag18 的 COSE_Sign1)
→ HTTP 400 {"detail": "Claim is not a valid COSE message",
            "type": "urn:ietf:params:scitt:error:invalidInput"}
```
同一条字节换个环境（cbor2 5.6.5）立刻受理并出回执，说明陈述本身合法。

根因：模拟器 `scitt.py` 里
```python
try:
    msg = Sign1Message.decode(claim, tag=True)
except ...:
    raise ClaimInvalidError("Claim is not a valid COSE message")
```
而 `pycose 1.1.0` 的 `decode()`（`cosemessage.py:54-74`）
```python
cose_obj = cbor2.loads(received).value
if isinstance(cose_obj, list): ...      # 只认 list
else: raise TypeError(...)
```
`cbor2 >= 6` 对带 tag 的数组返回 **tuple**（`CBORTag(18, (…))`），`cbor2 5.x` 返回 **list**。
于是只要 `cbor2>=6`（`cwt 4.0` 的要求就是 `cbor2>=6.1`），模拟器**自己 create-claim 产出的陈述也会被自己的服务端拒收**。

三种不冲突的修法：钉 `cbor2<6`；在解码入口 `list(cose_obj) if isinstance(cose_obj, tuple)`；或不经 pycose、按 `[phdr, uhdr, payload, sig]` 自行解析。

## 二、想让 WG 确认的问题（规范层面）
1. **错误码粒度**：现在 `invalidInput` 一个码覆盖"解不出来 / 缺 `cwt_claims` / 缺 `content type` / 签名缺失"四种完全不同的原因。规范是否应至少区分
   - 消息不可解码（结构层）
   - 必需头缺失（`label 3` Content-Type、`label 14` CWT Claims 的 `iss`/`sub`）
   - 签名缺失或不匹配
   否则客户端无法给出有用诊断，只能整条重传。这是我在互通里唯一一次"报错信息本身把我带偏"的地方。
2. **必需字段是否就是这三项**：tag 18、`label 3`、`label 14`（`iss`/`sub`）。我是从实现源码反推出来的；如果规范已有明文，指个章节即可，我把这条撤回。
3. **`label 14` 位置**：实现要求 CWT Claims 在 **protected** 头里。若放在 unprotected 头应接受还是拒绝？两种实现都见过，规范最好点明。

## 三、另外两个实现者会踩的坑（只是事实，不要求处理）
- `pip install` 直接失败：依赖 `rkvst-archivist` 已不在 PyPI；需 `--no-deps` + 自建 `archivist` 桩才能 import（即使只用 CCF 后端）。
- `server -p 8000` 在 Windows 上 `WSAEACCES`（Flask 起 socket 被系统拒），换 8088 正常。若默认端口是 8000，新手会卡在这一步。

## 四、边界（免得被当成互通证明）
- 服务跑在 `127.0.0.1`，**不是第三方运营的 TS**；模拟器源码自述不验证述签名、不执行注册策略。
- 我们的验算器（不依赖 pycose，自算 tbi→leaf→root、自验 ECDSA、自验证书链）与对方 verifier 在 cbor2 5.6.5 下得出**同 leaf、同 root**；恢复 cbor2 6.3.0 后对方失效而我们的仍通过——据此判断缺陷在解码入口，不在回执数据。
- 我们不主张"已符合 SCITT"，只报形状对齐与这条缺陷。
