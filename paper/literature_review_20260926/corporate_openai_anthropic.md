# OpenAI 与 Anthropic 企业报告：叙事和文风精读

检索及精读日期：2026-09-26。任务限定为写法借鉴，接受用户已确定的研究定位；不讨论内容相似性、新颖性或补引义务。四份文件都是企业原始发布，不能称为顶会录用论文。下列观察来自正文的指定段落，不以宣传页代替精读。

## 来源身份与精读范围

| 来源 | 原始身份 | 本次精读位置 |
|---|---|---|
| [GPT-4 Technical Report](https://cdn.openai.com/papers/gpt-4.pdf)（2023） | 技术报告；后附独立 system card | Abstract；§1 Introduction；§2 Scope and Limitations；§3 Predictable Scaling；§4 Capabilities；§5 Limitations |
| [GPT-4o System Card](https://cdn.openai.com/gpt-4o-system-card.pdf)（2024-08-08） | 安全 system card | §1 Introduction；§3.2 Evaluation Methodology；§3.3 Observed safety challenges, evaluations and mitigations；§6 Conclusion |
| [The Claude 3 Model Family: Opus, Sonnet, Haiku](https://assets.anthropic.com/m/61e7d27f8c8f5919/original/Claude-3-Model-Card.pdf)（2024） | Model card；能力评估与安全评估并列 | Abstract；§1；§5开头；§5.1；§5.3；§5.4；§5.5，PDF第1–12页 |
| [System Card: Claude Opus 4 & Claude Sonnet 4](https://www-cdn.anthropic.com/07b2a3f9902ee19fe39a36ca638e5ae987bc64dd.pdf)（2025-05） | 安全 system card | Abstract；目录；§1；§2.1；§4.1/§4.2结构；§7.1/§7.3 |

Anthropic身份和月份另由[官方system-card目录](https://www.anthropic.com/system-cards)核验。Claude 3现行PDF附有2024年6月与10月增补；本次只分析原Claude 3主体的上述页码。

## 逐篇写法

### GPT-4：先让读者知道结果，再让读者理解工程问题

摘要先界定对象与能力，再给代表性表现，最后转到训练和可预测缩放。Introduction逐步扩大读者视野：具体例子、跨任务表现、工程挑战。§3把挑战组织成可检查的问题，随后给方法和图；§4先交代如何测，再报告表现。§5集中讨论限制，§2则只界定报告范围。可借鉴的是信息次序与分工：开篇交付一个完整发现，正文逐层解释；测量限定就近说清，综合限制集中处理。

### GPT-4o：短概述建立对象与阅读契约

§1先解释输入输出能力，以响应速度和性能比较把能力具体化，再明确本文的安全评估目的。§3.3先给汇总表，个案保持问题、处理、观测的稳定节奏。§3.2将方法限制放在相应测量旁，读者不用跨节寻找解释条件。可借鉴短段落、清楚的文档目的和重复的结果段落结构。其安全审计目录服务于部署责任，不宜整体移植成研究论文的故事框架。

### Claude 3：主结果、代表案例、技术细节逐级展开

摘要用模型家族中各成员的角色解释产品取舍，再给能力与报告范围。§5先列能力维度；§5.1先报告总体表现，再重点展开GPQA及重复采样设置。§5.3先概括视觉能力，再给AI2D代表结果和处理细节；Figure 1图注按完成任务所需动作解释案例。§5.5先给偏好结果，再讲评估过程和局部限制。可借鉴“总体判断—一个数值锚点—解释”的段落节奏，避免每段同时承担动机、方法、所有结果与辩护。

### Claude 4：结论概览和详细评估分层

摘要明确两款模型及文档所覆盖的评估，目录让读者快速定位。§4.1先汇报发现，§4.2再展开主要评估细节；§2.1以结果概述引导表格，再解释对比与剩余行为。§7同样先说明评估流程，再分领域报告。可借鉴主文中结论与细节的层次，以及让表格承担完整枚举、段落只讲关键解释的做法。其用途主要是安全评估，移植时只取局部叙述技巧。

## 对当前稿件的具体编辑动作

1. 结果标题直接写发现，避免让所有标题都停留在研究对象名称。
2. 每段第一句只承担一个判断，下一句给关键数值，末句解释它怎样推进下一问题。
3. 用同一组名词贯穿叙事：coverage、repeatability、selection、execution budget。每次出现说明其在当前段落的角色。
4. 保留限定实际测量含义的一句话；把重复的“没有证明”“没有执行”等清单压缩，避免打断核心发现。
5. 完整表格与正文分工：表格列全部结果，正文挑能推动论证的比较。图注先告诉读者应看到什么，再交代读取条件。
6. 负向和零增益结果使用直接的结果句。统计区间和适用条件紧接证据，不把整段写成逐条防御。
7. 中文与英文保持同样的故事顺序；中文不额外增加判断，英文不省略关键限定。

原创句法示意（并非来源原句）：`The population covers more tasks than any single member. ...` → `Identical programs also yield positive oracle estimates. ...` → `The tested selector adds no gain. ...`。它们展示的是清楚陈述发现的节奏；最终措辞仍取决于稿内既有证据。

## 检索记录与阅读边界

完整查询：
- `site.openai.com GPT-4 technical report pdf 2023`
- `site.openai.com index gpt-4o system card`
- `site.anthropic.com Claude 3 model card pdf`
- `site.anthropic.com Claude 4 system card pdf`

网页工具可解析GPT-4、GPT-4o和Claude4 PDF。Claude3官方链接被网页工具因文件过大拒绝，最终以官方assets链接直接读取46,824,360字节、64页PDF，用pypdf在内存中提取第1–12页。旧CDN直连一次返回403，未绕过登录或访问控制；公开assets链接正常返回。只做指定段落精读，未审计全部附录，也未声称完成视觉版式检查。无逐字长引文，无未核实引文数、评审分数或奖项。
