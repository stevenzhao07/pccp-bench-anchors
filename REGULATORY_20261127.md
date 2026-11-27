# 监管窗口复核 · 2026-11-27

上一轮查了竞品，这一轮查监管。只回答一个问题：**现在有没有开着、值得我们投的口子？** 顺带记下三条会改变我们做法的事实。

## 一、FDA：PCCP 已经在"决定记录"层面留下公开语料

这不是新闻稿层面的说法，是 PMA 补充的正式记录里写着 `Predetermined Change Control Plan Authorized: Yes`，并在批准说明里写明 PCCP 覆盖的变更范围：

| 器械 | 补充号 | 决定日 | PCCP 覆盖什么 | 直链 |
|---|---|---|---|---|
| Abbott Volt PFA 导管 | P250022/S001 | 2026-03-23 | 二供件供应商变更（球囊、骨架、中心腔），前提是不影响规格与资格标准 | [FDA 记录](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?ID=P250022S001) |
| Biosense Webster VARIPULSE / TRUPULSE | P240006/S016 | 2026-06-30 | 发生器硬件与软件的预定变更 + 标签更新（"PCCP TRUPULSE Generator System v1.0"） | [FDA 记录](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?id=P240006S016) |
| Abbott 起搏电极 | P960030/S084 | 2026-06-11 | 包装线与洁净区改造（工艺侧） | [FDA 记录](https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?ID=P960030S084) |

**这条事实的含义比数字重要**：PCCP 早已不只在"AI 软件"上跑，工艺变更、二供件、硬件也在用。所以"变更是否越界"的判定对象**不是只有模型**。我们现阶段的题集全在算法侧，这是一个真实的覆盖缺口——不是风格问题。

## 二、放射学 ML 定量成像：法规条文级落地（2026-06-17）

21 CFR 892.2055 成文（Docket FDA-2026-N-6535），特殊控制把"计划内修改"写成了硬要求：设计验证要记录修改与验证方法、风险管理要识别修改风险、标签要给出性能摘要（含置信区间与亚组）、失败情形、以及 **PCCP 版本历史与"如何告知用户"**。

对应到我们这边：**"版本历史 + 如何告知用户"是可被机器判定的字段**，而现有题库没有考它。

## 三、TGA：AI 审查结论出了，但 PCCP 口子仍关

- AI 审查共 **14 项发现、5 个优先方向**（支持相关方、稳健监管、厘清职责、提升透明度等），结论是"现行软件监管大体适当"<RichMediaReference>["https://www.tga.gov.au/products/regulations-all-products/tga-reforms/medical-devices-reforms/medical-devices-reforms-software-regulation"]</RichMediaReference>
- 唯一**在开**的咨询是"数字心理健康工具豁免审查"，**2026-12-07 截止**——主题是心理健康工具，不是 PCCP，投不进去
- CDSS 豁免的修订已于 **2026-11-01 生效**（官方称"更清楚界定豁免何时适用"）
- 我方此前关注的 TGA PCCP 草案（2026-04-10 开、06-05 关）已关闭，未见新开

## 四、四条监管者在 10–11 月集中发东西（需打一个"未直验"的标记）

一份德语综述（2026-11-17）称：FDA 上线了 PCCP 专页，含**授权产品清单 + 两个 AI 软件的假设案例**；TGA 澄清数字抄写员何时算医疗器械；PMDA 于 2026-11-02 发布《监管活动中使用 AI 的基本准则》；英国政府接受其 AI 医疗监管委员会全部 44 项建议<RichMediaReference>["https://theentourage.it/insights/ki-software-medizinprodukte-pccp-fda-tga-pmda-uk"]</RichMediaReference>。

其中"FDA PCCP 专页 + 授权产品清单 + 两个假设案例"这条**我没能直验**：fda.gov 的两个候选路径均返回 link dead（可能是路径不对，也可能是网络）。所以在本文件里只作二手线索登记，不当事实用。

## 五、结论：窗口仍关，但打法可以升级一格

**投稿**：没有对我们开放的 PCCP 口子，策略不变——引用与落地，不投稿。

**但有一件可做且不需要外部输入的事**：既然 FDA 的 PMA 补充记录里公开写着每条 PCCP 的范围与前提，就可以把这些**真实决定记录**做成"回归用例"——不是拿它们当评分题，而是拿它们当**边界样本**：PCCP 授权范围写到什么颗粒度才算"具体"、什么条件下允许"不影响规格"这类兜底表述。

这件事的价值：它把题集从"我造的合成题"往"监管者真批过的边界"挪了一格；代价是得逐条抓记录、抽批准说明文本。目前只手工核了 3 条，够证明可行，不够叫语料。

## 六、能说 / 不能说（本轮更新）

- **能说**：PCCP 的公开语料存在于"决定记录"层面（PMA 补充批准说明），并有法规条文级（21 CFR 892.2055）要求；我们的题集目前只覆盖算法侧，工艺/二供件/硬件侧**未覆盖**。
- **不能说**：不能说"PCCP 没有公开语料"；也不能说我们的题集覆盖了 PCCP 的全部形态。
