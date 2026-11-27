# 竞品复核快照 · 2026-11-27

口令要求"全面调研竞品"。这一份不做抒情，只做三件事：**谁在做什么、最新变化、三个空位是否仍然空着。**
每条都带直链，读完能自己点进去核。

## 一、六个对手，六种"信任模型"

| 谁 | 现在提供的 | 信任模型 | 直链 |
|---|---|---|---|
| **Ketryx** | PCCP 模板 + 变更控制 + CI/CD 一致性报告；2026-10 向 FDA 递交评论，明确要求"接受**厂商自己的**受控发布流程生成的自动化 re-benchmark 证据" | 厂商自证 + 平台留痕 | [Ketryx 对 FDA 的评论（2026-10-19）](https://www.ketryx.com/blog/ketryx-comments-to-fda-on-the-regulation-of-generative-ai-enabled-medical-devices) · [AI/ML 功能页](https://www.ketryx.com/function/ai-ml) · [PCCP & CI/CD  webinar](https://www.ketryx.com/learn/webinars/on-demand/implementing-a-pccp-ci-cd-for-ai-ml-enabled-medical-devices) |
| **AEGIS** | 厂商内部四类部署决策（APPROVE / CONDITIONAL / CLINICAL REVIEW / REJECT）+ 独立 ALARM 信号；2026-10 的 arXiv 版在脓毒症与脑瘤分割两个域上跑通 | 厂商内部治理 | [arXiv 2603.22322](https://arxiv.org/html/2603.22322v1) · [npj Digital Medicine 版](http://www.shturl.cc/97874b7ca2b23a4efe8a3cce89e033e6) |
| **VIGILANT（DIDSR）** | 三把量：learning / potential / retention——把"模型变好了"与"数据分布变了"拆开；有 Python 包（仓库直链实测 200） | 方法学工具，无题集、无回执 | [论文（含 Code Availability）](https://arxiv.org/html/2604.04878) · [GitHub DIDSR/VIGILANT](https://github.com/DIDSR/VIGILANT) |
| **MedPerf（MLCommons）** | 联邦评测 + 2026-07 接入 Google Cloud 机密计算（TEE 证明换取解密权）；结果由数据方**人工审批后**才上传 | 硬件证明 + 数据方审批 | [MedPerf + Google Cloud（2026-07-22）](https://mlcommons.org/2026/07/medperf-google-cloud-confidential/) · [MedPerf 原始论文](https://arxiv.org/pdf/2110.01406.pdf) |
| **RRI-MI** | 部署方 11 域 × 22 项自评表，自称 conceptual framework 待验证 | 自评 | 见前期调研记录（无公开可验产物） |
| **MedAIBench** | 35 万题 / 22 测评集 / 64 专科的评测集合 | 榜单式，模型能力而非变更合规 | 见前期调研记录 |

## 二、本轮相对上次调研，新增的四件事

1. **Ketryx 把话说到明处了**（2026-10-19）：它请求 FDA 接受"manufacturer's controlled release process 生成的自动化 re-benchmark 证据"。这意味着"厂商自跑证据"已是公开主张，**不再是我们的差异化点**；我们的差异化只能是"非厂商第三方可独立复算 + 可验证的锚定"。
2. **AEGIS 出了期刊+arXiv 双版**（2026-10），仍是厂商内部治理工具，不含对外可验产物。
3. **MedPerf 上了机密计算**（2026-07-22）：用 TEE 证明换取解密权，这是目前最强的"过程可信"路线，但结果仍需数据方人工批准才分享——**它解决的是"数据出不去"，不是"分数可被外人重算"**。
4. **VIGILANT 真的开源了**（Python 包 + 浏览器版）：这是与我方最近的一支，属于"量"的层面（learning/potential/retention），缺的是"题集 + 回执 + 可验锚定"这一整条链。

## 三、三个空位：仍然是空的

以 2026-11-27 的检索为准（query 见下），三项都没找到公开对应物：

| 空位 | 检索结论 |
|---|---|
| PCCP 变更范围判定的**公开题集** | 未找到。检索到的是指南解读、模板、厂商工具与自评表，没有可下载、可复算的题集 |
| 变更合规的**公开榜单** | 未找到。现有的榜单（MedAIBench、各种 challenge）评的是模型能力，不是"这次变更是否越界" |
| **第三方可独立验算的运行回执格式** | 未找到。最接近的是 MedPerf 的 TEE 证明与数据方审批，属"过程证明"，非"结果可被任意第三方重算" |

检索用的 query（可复现）：
`predetermined change control plan PCCP benchmark public test set leaderboard medical device AI 2026`；`Ketryx PCCP evidence automated re-benchmark third party verification receipt`；`"PCCP" public test set dataset open source medical AI change validation benchmark`；`MedPerf federated benchmark medical AI container submission result 2026`；`DIDSR VIGILANT measurements for adaptive AI PCCP github performance assessment`。

## 四、据此能说与不能说

**能说**：在"变更是否越界"这个具体判定上，目前没有公开题集、没有榜单、没有第三方可验回执；我们提供了其中两样半（题集 32 公开题 + 回执 + 零依赖可验），并以公共 Rekor 锚定。

**不能说**：不能说整体最强、不能说首创、不能说已被第三方见证；也不能说比 Ketryx 更"合规"——它做的是厂商侧流程，我们做的是第三方可验的判定，两者不在同一层。

顺带一句：VIGILANT 的出现说明这个方向正在有人做，且是官方机构背景。这是好事——**说明这条路不是孤岛，但也说明留给"只有度量、没有回执"的时间不多了。**
