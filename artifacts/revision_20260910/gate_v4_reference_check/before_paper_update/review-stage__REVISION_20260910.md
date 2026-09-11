# Reviewer revision programme — 2026-09-10

目标：完成用户提供的审稿提分建议，以可复核证据达到 6–7 分门槛，再争取 8 分级别的方法可迁移性与实践价值。不能以显著正结果、文字改写或本地测试替代这些验收条件。

起点：用户审稿意见锁定 `1fd2b3fd91e393cb8553812f77638855439900da`；本轮实际起点为 `89eb4e4`，工作区当时干净。本轮修改属于 post-review revision，旧 gate、旧采集文件、旧统计 JSON 保留。原审稿 score 4/10，verdict **not ready**；目前尚未完成决定性的 A–D 新证据，不能据本轮修正宣称已达到提分门槛。

原文：[REVIEWER_FEEDBACK_20260910.md](REVIEWER_FEEDBACK_20260910.md)。本文件是当前修订状态入口；历史 CURRENT_STATE/NEXT_STEPS 与 PHASE2_PROTOCOL 的 freeze 时点状态不可当作今天状态。

## 已实际完成的工作

| 审稿问题 | 本轮动作与证据 | 验收状态 |
|---|---|---|
| 主统计代码与描述不符 | 新增 `experiment/revision/replay.py`；数据库和库内题目共同抽样，所有 arm/cell 共享；六个 builder 固定，seed 在 builder 内抽样；10,000 bootstrap | 新版主分析、factorial 与敏感性分析完成；事后修正，非原始预设实现 |
| 重复记录规则不一 | 使用两个已冻结 manifest 的文件顺序，再按行 first-write-wins；SHA256/长度检查；缓存与 repeat 不混合；输出逐行来源索引 | 主分析/factorial、K-matched、R2、W1/W3 已统一；W1 完整选择推断待完成 |
| core 分解混入全量数据与 baseline | 同一 400 题、同一 AD bare 记录重建 A–D；AD 与 BC 的 bare 有 2 个题目判定冲突，即使均值相同也不能视为同一记录 | 已修复，新表明示比较集合 |
| gate 意义错误 | 正文明确为非平凡机制筛选＋conformance；确认两个 prompt 类不能通过，日志共 25 次 neutral-valid 后因 NO_MECHANISM_declared 拒绝 | 旧 treatment 解释完成；修正 gate 实验仍待完成 |
| 固定三次预算虚报 | A/B/C/D 实际 raw attempts=269/255/273/324，均以每槽三次为上限，成功即停；实际 token 消耗尚未恢复 | 尝试次数、数量及逻辑调用账本已完成；计费成本证据缺失 |
| 图形单位、星号、主结果范围 | 新图按 pp 绘制；无显著性星号；范围从全量18格计算为 −4.36 至 +2.74 pp | 已修复 |
| 原始/校正 p 混用 | 同表报告未校正 CI、双侧 exact sign-flip p、Holm p；主对照单侧 p；说明检验条件范围不同于 bootstrap | 已修复；不是随机化因果检验 |
| oracle/best-fixed 解释反向 | 全量 D−A：oracle −0.44，best-fixed −0.28，H −0.16 pp；后者抵消前者部分下降 | 已修复 |
| K 含义不一 | 新表同时提供 K_candidate 与 K_total=K_candidate+1；bare 始终保留 | 主分析/factorial 已修复 |
| flip rate 被称噪声地板 | 摘要、引言、结果、讨论撤回这项推断；定义 H_stable 但不声称已估计 | 已修正文案；A 的科学证据未完成 |
| R2 contrast 不变与 T2 归因过强 | R2 canonical 全18格 +0.42→+0.81 pp；旧16格 −0.11→+0.36 pp；T2 改为机制存在但本次未触发 | R2 重算和主文/附录完成；T2 反馈作用仍需故障注入验证 |
| W1 的 0.82 被写成实际能力 | 明示 oracle +0.39、best-fixed −0.43 pp；保留历史探索标签及 loader 局限；撤回迁移/实际路由结论 | canonical 描述性重算完成并撤回旧 CI；完整选择推断及独立 D 未完成 |
| 只有 bare 的跨域验证 | 当前 HEAD 已有 MATH-500 35 harness/400 eval 结果，早于本轮；保留，但明确无 clone、无 repaired gate、单 seed、同 target | 旧审稿该事实已过时；独立稳定性验证仍不足 |
| 外部运行时不可追溯 | 已核对385份结果源码哈希全部匹配；归档391份源码（含控制）、5个外部 tracked 修改、上游 SHA、补丁与逐成员哈希 | 本地 snapshot/补丁应用检查完成；全新环境完整运行未验收 |
| 论文数字由人工复制 | revision 主分析/敏感性/成本/W1/W3 JSON→7个TeX数值/表文件＋结果图，另存 paper_assets_manifest.json | 新主分析/factorial 已连接；非全论文所有历史数字 |
| 提交 PDF | 英文稿编译成功，主文 endofmain 位于第9页；更新图表页逐页检查 | 是修订工作稿，不是最终投稿包 |

## 修正分析的实测结果

来源：`artifacts/revision_20260910/corrected_analysis.json`。点估计使用未舍入的矩阵，区间端点下列按 pp 舍入。

| 结果 | 点估计 pp | 95% bootstrap CI pp | p / Holm |
|---|---:|---|---|
| 主对照 D−A，1169题 | −0.16 | [−0.83, +0.87] | 单侧 exact sign-flip 0.647 |
| gate 主效应，400题 | −0.69 | [−1.56, +0.20] | 双侧 0.026；Holm 0.079 |
| strategy 主效应，400题 | +0.42 | [−0.32, +1.51] | 双侧 0.263；Holm 0.428 |
| interaction，400题 | −0.87 | [−2.83, +0.65] | 双侧 0.214；Holm 0.428 |

这些区间对六个固定 builder 和已有 execution records 有条件性；没有通过 bootstrap 凭空补出执行重复、目标模型或未来 builder 的变异。sign-flip 以 cell contrast 符号对称为参考假设，不能冒充随机分配 treatment 的因果检验。

主分析 AD/BC 两组的双 judge 任一判定冲突记录分别为3683/1197；这不同于仅统计 official judge 的旧数字。文件順序取冻存 manifest；BC 的 manifest 顺序与旧 factorial 脚本顺序不同，因此新值不是静默替换原预设结果。缺失/错位 task、缺失成员、畸形 JSON、哈希变动都会拒绝重算，不会以减少 K 或题目数补齐。

## 必须继续完成的验收项

1. P0 剩余：W1 正式不确定性推断及其覆盖率/偏差校准（canonical描述性重算和共享数据库/题目权重的完整重选择敏感性已完成，旧cell-only CI已撤回；扰动分位数不是CI）；补充可核对的真实 token/计费成本来源（旧 trace 无 token 字段）；真实提供方完整运行核验。中文稿已完整同步；K-matched、R2、逻辑调用账本、隔离 venv 的离线 replay，以及本机任务隔离/故障测试已完成。后者均不替代真实提供方证据。
2. A：同代码 clone 与真实 population，cache-off 独立重复、时间交错、固定成本比较，独立重复保留优势；不能只重复 bare 后宣称已排除噪声。
3. B：覆盖8种合法策略的新版 gate 合同，独立正例/负变体校准，同一预生成 raw pool 对比离线准入；旧数据不改写。
4. C：固定 builder/target/题集/judge/缓存/时间块的旧新生成流程桥接；不可用跨阶段差异替代。
5. D：冻结规则后在新生成批次或新数据上验证绝对 oracle、best-fixed、实际选择准确率及成本，对比 random、top-accuracy、同代码重复。
6. 投稿包：新数据/代码 freeze SHA 与 submission tag、全部 claims–evidence 对齐、匿名与凭据状态确认、完整PDF视觉验收。未建立tag，未提交、未发布。

详细实验方案：[REVISED_EXPERIMENT_PLAN.md](REVISED_EXPERIMENT_PLAN.md)。API预算上限仍待用户提供；这是量化采样设计所需信息，本轮没有启动新收费模型实验。旧协议中凭据状态是历史记录，未获提供方撤销证明，不能写“已撤销”。

## 复核边界与节点

本轮做了两路代码规范/需求检查，以及统计不变量测试；它们是机械检查，不等于跨模型独立科研审查。执行者/审核者的跨模型验收仍须在正式放行前完成。

官方节点已于2026-09-10核对：摘要2026-09-18 23:59 AoE，全文2026-09-25 23:59 AoE；主文不超过9页，AI use statement 必需，附件亦须匿名。来源：[ICLR 2027 Author Guidelines](https://iclr.cc/Conferences/2027/AuthorGuidelines)。

提分顺序：先恢复 P0 的完全可重放性，再完成 A+B 的决定性证据；随后最小 C 与独立 D。新增一次性 builder 和未闭环支线不优先。最终结果允许为负，但只有精度足以排除预定的实践相关效应时，才考虑“没有有意义的额外收益”。

## 前一阶段验证记录（后续快照见下）

2026-09-10：9项单元测试通过；revision模块Ruff通过；规范/需求两路机械检查无阻断项。`python -m experiment.revision.verify` 验证31项源码/结果/生成产物哈希、样本量、分解恒等式及已检查PDF快照，结果PASS。PDF总15页、主文9页；无未定义引用、无overfull；查看了更新后的主结果页与全稿缩略图。`verification.json`保存具体SHA。机械检查最终score 9/10、verdict ready仅适用于该代码/产物范围；论文的整体高分验收尚未完成。

当前改动留在工作区供后续工作使用，未做提交、submission tag或发布。中文旧稿已增加`paper/latex_zh/REVISION_STATUS.md`显式提示未同步。


## 第二阶段：敏感性分析、成本与隔离环境复跑

- K-matched 使用精确子集枚举，bare 始终保留，两侧匹配候选数量并保留 K=0 格。gate 主效应 −0.31 pp，95% CI [−1.07,+0.40]。这是旧 gate 的事后敏感性分析，不是 gate-v2 效果。
- R2 保留全部18格及 singleton population，候选子集 H 在 cached 和 cache-off 均不纳入 bare，因为没有对应的 bare cache-off 测量。D−A 从 +0.42 变为 +0.81 pp，变化 +0.39 pp，95% CI [−0.95,+1.63]。不能声称 contrast 不变。旧16格诊断 −0.11→+0.36 pp 单列解释。
- canonical 首次 cache-off 与 cached 比较2391/28000条翻转；D 的两次 cache-off 比较1245/14400条翻转。翻转比例不是均值差的噪声地板。两轮采集即使均存 repeat=0，也保留不同 acquisition group。
- 成本账本覆盖153600条候选记录、259304次逻辑 solver 调用，含缓存命中；0条记录具有 token usage 字段。因此不能把逻辑调用计数换算成已支付 API 请求或美元成本。新增成本表明确 population/candidate 与 cell/row 权重差别。
- 新建无 system-site-packages 的 Python 3.13.9 venv，以锁定依赖完成两套10000次重采样；主分析/factorial、K-matched/R2 的完整结果对象逐项一致，canonical 行索引 SHA 一致。它仍使用同一 checkout 和数据，并不等于另一台机器或完整 TTHE/API 运行时复原。
- 18项测试在该 venv 通过，Ruff 通过；新增测试覆盖数据入口集成、成本分母及共享依赖版本冲突。两路机械复核发现的 provenance 覆盖漏洞和 clone-only 表述边界已修正。最新 PDF 和源文件哈希以 `artifacts/revision_20260910/verification.json` 为准。

论文整体仍为 **score 4/10、verdict not ready（沿用外部审稿结论，尚未重新独立评分）**。A–D 的决定性新实验尚未完成，不能用以上机械验收代替提分证据。

本阶段最终快照：`python -m experiment.revision.verify` 通过37项源码/结果/产物哈希检查；PDF共16页、主文9页，无undefined reference/overfull。已检查第7、8、9、12、13页（更新结果、稳定性定义和新增附录表格）。两路复核中的问题均已关闭；机械代码复核score 9/10、verdict ready，限定数学表述复核score 10/10、verdict ready；均不是全论文提分验收。

## 第三阶段：W1/W3 canonical 描述性重算

- 新脚本 `experiment/revision/fingerprint.py` 和 `selection.py` 共用已验证的 loader、准入 membership、400题清单；W3 的 R2 仍使用同一 acquisition group/源码哈希检查。全部384候选、18格、4386个格内pair保留，不因缺题静默缩小样本。
- W3：全部pair相关系数0.596967，within-arm 0.587952。364428个非空相同变换SQL的pair-task观察中判定冲突为0；这是观察结果，有损文本变换不是SQL语义等价。SQL翻转19569/27936=70.05%，64项缺少两份非空SQL只从该分母排除；调用和判定仍各用28000项。
- W1 保留旧 seed/100 splits/200 draws/选择规则，但旧集合遍历顺序未存档，不能精确恢复旧随机序列。新版记录确定顺序和实际数据库切分，明确这是新版本的事后重算。
- k=8、共同bare始终保留：div-only−top-acc 的oracle +0.3536 pp、best-fixed −0.4221 pp、headroom +0.7757 pp；开发集选定单个成员的准确率变化 −0.0010 pp。该新增单成员对照使用统一的成员名并列规则；各方法仍可能保留不同的并列最优成员。不能解释为多样性带来的实际路由收益。
- 候选-only 与 bare-inclusive 的完整绝对指标分别保存在 `selection.json`，k4/k8、7种方法均有；英文附录新增表报告核心3种方法。旧0.82点和cell-only区间已从当前主文/附录撤回；旧文件不改写。完整选择推断仍待完成，不用取消CI冒充解决统计任务。
- 25项测试在已建立的隔离venv通过，Ruff通过。新增覆盖dev/heldout隔离、固定选择与test-best区别、bare保留、并列顺序不变、缺失SQL分母、重复源码不符。源码/JSON→论文宏与表格的绑定同步扩展。

本阶段最终验收：隔离venv重跑W1/W3输出逐字节一致，见`clean_environment_exploratory.json`；42项源码/结果/产物哈希验证PASS。PDF16页、主文9页，检查第9、13、14页，无undefined reference/overfull。两路有限范围复核通过（机械9/10 ready，代码—产物—正文一致性10/10 ready）；全论文仍未满足A–D提分门槛。下一优先工作是gate-v2八类机制合同与离线独立控制，避免继续扩展事后相关分析。

## 第四阶段：gate-v2 开发仪器与对抗反例

当前B仍为 **not ready**。新增 `GATE_V2_CONTRACTS.md` 定义八类声明的可执行观察与独立语义裁决规则；`gate_v2.py` 是开发仪器，不替换旧gate，也未用于新种群准入。

- 第一版同作者正/负控制全部符合预期，但两轮对抗复核仍找出10个会误放的实现，涵盖字符串投票/固定tie fallback、类别罗列/标点差异/共享错误动作、批量额外样本、空格视图、否定提示要求、根据步骤名伪造partial answer。前两轮反例轨迹分别归档；全部纳入当前回归。
- 改正投票的同候选/同顺序执行结果反事实（AC/BC/AB多数，没有共同可选fallback），decompose固定计划/改变opaque partial answers，repair按sample而非请求对象计数，分类模板累积并两两比较。
- 不把词命中当语义证明：hint/format、two_view表述独立性、error_classify修复动作语义均必须独立裁决，正控制也保持review_required。因此不是“八类自动校准已通过”。
- 28个开发case：8正例中4结构pass、4待语义复核；8基本负例中6fail、2待复核；10对抗负例中8fail、2待复核；2异常控制为execution_failure。待复核不计为正确拒绝，以上不是独立误放/误拒率。
- 真实SQLHarness基类的5个受信本地控制已接入spy：repair/vote正控制pass，两类负控制fail，bare/format待语义复核。真实bridge/配置/模型客户端未导入；这只证明该接口切片，不是完整provider/cache/database/judge环境恢复。
- 生成14例语义裁决材料 `gate_v2_semantic_review_packet.json`，去掉期望标签、当前verdict/reasons并中性化函数名；完整trace和声明仍保留。这些是开发case，不是未见过的独立校准集，尚未送交或完成独立裁决。
- 隔离venv下36项revision测试通过，其中11项gate/adapter测试；Ruff通过；开发报告16项输入哈希校验通过。论文原有42项产物一致性检查仍PASS，PDF本阶段未改写。

入口：[GATE_V2_CONTRACTS.md](GATE_V2_CONTRACTS.md)。证据：`artifacts/revision_20260910/gate_v2_development.json`、`gate_v2_development_verification.json`。B余项仍包括独立fixture/跨模型语义裁决、边界场景、完整runtime、共同raw pool、成本与freeze；A/C/D也未完成，不据本阶段开发检查提高整篇评分。

## 第五阶段：A项重复/clone设计模拟

完成6种情形×4种设计×1000次，共24000个模拟数据集。模型包括相同概率null、固定强弱、任务交互、共同时间冲击、交互加冲击和代码键缓存复用；bare缓存跨cell共享，非bare代码按cell区分。参数仅用R2翻转比例作说明性moment match，不据此声称真实噪声模型已经拟合。

结果区分可用稳定headroom、有限重复所拟合策略的fresh概率得分、实际模拟跨重复优势。在任务交互情形，200题×4重复的real−dev-fixed-clone保留优势均值0.696 pp，模拟分布2.5–97.5%范围[−0.620,+2.016] pp；400题×8重复均值1.067，[+0.350,+1.861]。这些是规划分布，不是实验CI或power。缓存null的可用稳定差为0，却能产生约2.64–2.86 pp的表观保留优势。不能据模拟归因已有实验，只说明独立执行/缓存校验的必要性。

结论：不将200×4直接冻结为正式样本量。正式设计还需数据库依赖、无发现/验证记录交叉的推断方法、假阳性/coverage/CI宽度检验和真实成本上限。相关图表作为设计材料，没有写成论文的新实验结果。A仍not ready。

证据：[REPEAT_PLANNING.md](REPEAT_PLANNING.md)、`repeat_planning.json`、`repeat_planning.png/pdf`、`repeat_planning_verification.json`。隔离venv复跑产物逐字节一致；41项revision测试通过，其中5项模拟行为测试；Ruff通过；原论文42项源码/产物哈希检查仍PASS。

## 第六阶段：中英文全文同步与残留矛盾清理

中文参考译本现覆盖正文、AI使用声明及全部附录，共19页、正文结束第11页；英文仍为16页、正文9页。中文十个TeX文件共用英文35个数值宏、6张结果表、3幅图和参考文献。图表内部英文标签保留。入口：[中文PDF](../paper/latex_zh/main.pdf)及[同步说明](../paper/latex_zh/REVISION_STATUS.md)。

逐段核对还发现并修正了英文残留：“相同代码必然产生相同结果”、正headroom即稳定信号、所有结果均用官方BIRD评分器、未说明smoke例外的数据库表述，以及SQL计数解释。BIRD采集窗口与数学探查分开；压缩相关工作重复定位以维持主文9页。没有改写存档实验结果，也没有增加或重跑API实验。

- 中文UTF-8无BOM、21个引用键和全部标签有效；编译实际依赖确认未读取中文目录的旧图。无缺字、undefined reference/citation或overfull；宋体small-caps回退普通字形，已记录。全文缩略与主要结果/附录页检查完成。
- 机械依赖审核9/10 ready，语义一致性审核10/10 ready；纠正non-vacuity误译为“非空性”，现为“非空洞性”，并明确bare必须违反合同属性。这些是有限范围机械/翻译审核，非跨模型科学验收。
- 新的`chinese_sync_verification.json`绑定十个中文源码、26个实际构建输入、英文源码和两版PDF。英文`verification.json`经重新编译检查后刷新，前快照保留为`verification_before_chinese_sync.json`；42项源码/产物检查PASS。
- 本轮只改TeX/文档，统计代码与结果未变，没有重跑统计测试。英文快照的25项测试沿用此前已通过记录，不能声称本轮新增25项测试；全revision套件仍为前阶段验证的41项。

全论文仍not ready，沿用外部初始4/10作为未重评基线。中文同步不替代A–D提分证据。下一实质工作仍是A的数据库依赖/推断校准与正式成本设计，B的独立控制及完整runtime，随后受控桥接与独立效用验证。

## 第七阶段：A数据库/重复推断校准，候选方法不通过

新增`repeat_inference.py`及5项行为测试，冻结每设计一次独立开发集所选anchor，参考MC与校准数据随机流分开。九个等大数据库，180×4或360×8，比较数据库/题目/重复与iid题目/重复两套percentile重选择bootstrap；每次重选逐题成员及固定比较器。索引检查确保每方向原始存储重复记录不跨半部，缓存情形仍可共享底层内容。

完成8setting×(3000参考+300校准)=26400个模拟数据集，以及1915200次bootstrap重算。六个无缓存setting的两方法均300/300覆盖；DB区间全宽3.17–5.10pp，四个替代setting均0/300正区间，表现过度保守。缓存null fresh目标0，但bias+4.40/+3.17pp，两方法均0/300覆盖且300/300正区间。均为指定合成分布下的校准结果，不估计历史实验缓存偏差，不等于真实功效。

**候选percentile推断方案not ready，不放行正式A或样本量。** 下一步需明确独立发现后固定策略的条件验证目标，并单独校准；不以缩小推断对象代替原科学问题。协议/调用成本/实际独立执行/B–D仍待完成。

证据：[校准报告](REPEAT_INFERENCE_CALIBRATION.md)、`repeat_inference.json`、`repeat_inference.png/pdf`、`repeat_inference_verification.json`。隔离venv完整运行一次；46项revision测试及Ruff通过。两路代码/数学复核9/10 ready仅允许进入校准；绘图边界舍入错误已修，图已检查。未声称第二次完整MC复跑；原论文42项检查仍PASS，两版PDF未改。本阶段仍未取得整篇独立提分评分。

## 第八阶段：稳定能力识别检查与论文比较对象修正

上一阶段校准报告的最终复核9/10 ready仅批准结果呈现；修正一处Markdown表格空行。其候选推断方法仍not ready。

本轮没有继续围绕更窄条件收益扩展模拟，而是完成两个识别反例及数学边界的可执行检查：

- 三个成员对所有题的概率恒为0.2/0.8/0.5，发现选错fixed后fresh策略收益+22.5pp，但H_stable=0；对真正best-fixed的witness为−37.5pp。
- 真实/混合bare-clone种群的witness差可为+0.4而真正H_stable差为−0.4；下界不能直接相减。
- 实现固定发现策略、逐验证块保留对所有fixed成员的差、同时概率带向H_stable及real-clone差传播，以及独立同分布时间块前提下的Hoeffding保守基准。K含bare，K1精确为0；块内允许相关。代码不证明时间独立、成本相等或外推。

证据：[STABLE_IDENTIFICATION.md](STABLE_IDENTIFICATION.md)、`stable_identification.json`、`stable_identification_verification.json`。6项新增行为测试，隔离venv下全部52项revision测试通过；Ruff通过；两路有限代码/数学审核及中英文措辞复核均9/10 ready。这里只批准固定种群的数学/机械交付，A仍not ready。

中英文结果段落已改为：独立重复衡量指定比较器下的策略价值，超过发现选定的次优fixed不足以确立稳定互补或未见任务效用。英文仍正文9页/全稿16页，中文19页；重编译与受影响页面检查完成，无新undefined/overfull/缺字，42项论文源码/产物检查PASS。此前验证快照保留，本轮刷新两版绑定；没有改动实测统计结果或调用API。

下一实质工作先完成完整运行接口、独立执行/缓存检查和真实成本材料，再推进能够回答原A问题的正式推断选择；B共同raw pool、C受控桥接、D独立效用与投稿验收仍未完成，整体仍not ready，未取得新的独立全论文评分。

## 第九阶段：完整本机采集链路与缓存/成本缺陷的动态证据

在新的隔离 runtime 环境跑通真实 SDK、bridge、原 collector、临时 BIRD 格式数据库、SQLite 及项目 official_scorer 的回环 HTTP 合成链路。没有使用替身 bridge，没有读取新真实题目或调用付费模型；上游源码与历史产物未修改。

六项新增集成测试动态确认：repeat 标签不保证新请求；同文件同 repeat 切换 no-cache 被恢复逻辑跳过；尚未刷盘的 seq1 请求可被重复发送；n=3 和 SDK 重试分别造成1条逻辑trace对应3/2次HTTP；响应 usage 没有保存在采集行；thinking 分支没有发送指定的 temperature。源码身份变化也被恢复键遗漏，这一项仅作静态确认，没有修改历史 harness 来做实验。

全部58项revision测试（原52+6）在新runtime环境通过，Ruff及pip check通过。新测试的PASS包含“成功复现缺陷”，不等于缺陷已修复。源码运行前后hash一致性、每轮stdout、HTTP账本及4条合成采集行已归档。原论文42项一致性检查仍PASS，两版PDF未改写。

报告：[RUNTIME_RESTORATION.md](RUNTIME_RESTORATION.md)。证据：`runtime_probe.json`、`runtime_probe_verification.json`、`requirements-runtime.lock.txt`。下一工作是保留旧运行版本，落实fresh采集的完整执行身份、恢复条件校验和物理请求/usage账本，再进行经授权的真实提供方小规模检查。A–D及整篇提分要求仍未完成，整体not ready。

## 第十阶段：新的 fresh 采集版本与持久请求账本

新增 `fresh_runtime.py` / `fresh_collect.py`，保留历史运行版本。完整运行manifest拒绝条件变化下的恢复；应用层缓存关闭；逻辑调用、sample、HTTP尝试、响应ID和usage分开留存。缺失usage和金额保持unknown。每cell使用不可换绑solver，未知/未闭合请求不得标为完成，输入变化或遗留线程产生持久invalid。

两轮代码复核发现并修复“捕获超时后误标完成”“延迟线程串入下一任务”“恢复原文件洗掉数据变化失败”三个漏洞。8项新增行为/集成测试通过，包括仓库真实race harness的遗留线程停止与拒绝恢复；这种harness仍需进程隔离支持，不能静默剔除它来缩小A总体。

新留存示例运行真实bare及其同源码clone、两个repeat、一个合成题目，4个cell产生4次回环HTTP，跨进程恢复新增0次；508份源码绑定。人工usage合计20tokens，只验证记录链路，不是实际提供方成本。完整66项revision测试、Ruff、论文42项一致性检查通过，两版PDF未改。两路限定机械/Spec审核各9/10 ready，不是独立科学放行。

报告：[FRESH_ACQUISITION.md](FRESH_ACQUISITION.md)。证据：`fresh_runtime_smoke.json`、`fresh_runtime_tests.txt`、`fresh_runtime_verification.json`。下一实质工作是对遗留线程/进程实行任务级隔离并保留未决请求，再完成真实提供方核验、预算和正式推断/协议冻结。新版本重试、超时、顺序和只读评分政策须进入C桥接；A–D及投稿提分要求仍未完成，整体not ready。

## 第十一阶段：race harness 的任务进程隔离与崩溃证据恢复

新增 `isolated_collect.py` 和 Windows Job 辅助模块。每cell的worker先挂起创建、归入Job后启动，solve返回立即固定答案，再在同一任务身份下等待后台请求；父进程确认整个Job活动数为0后才导入账本并接受完成状态。子事件的logical/attempt引用重映射保留归属。

真实原有race harness两个repeat已跑通：4次回环HTTP、2个完成cell、不同worker、慢回复在答案返回后仍计入同cell，恢复新增0请求。短drain留下答案与1已完/1未完请求，wall超时留下未决请求；两者均停止而非剔除候选或自动补采。本地进程树结束不等于提供方停止计算或统计独立。

修复强制终止后SQLite hot journal无法只读恢复的问题：Job清空后以mode=rw恢复既有数据库；不可读时记录unknown和pending快照。新增5项测试，包含实际写事务中断后恢复200条已提交事件。完整71项revision测试、Ruff与论文42项一致性检查通过，论文PDF未修改。两路有限审核各9/10 ready，不是科学放行。

报告：[TASK_PROCESS_ISOLATION.md](TASK_PROCESS_ISOLATION.md)。证据：`isolation_smoke.json`、`isolation_tests.txt`、`isolation_verification.json`。后续必须冻结pending/失败处理规则，避免只分析completed产生延迟/成本相关选择；完成真实提供方小规模核验、预算和A推断，B–D仍待完成，整体not ready。
# 阶段12补充：真实提供方先导审阅包（尚未执行）

已形成 `PROVIDER_PILOT.md` 与12cell配置/任务清单，使用已曝光开发题，断网prepare通过并绑定510份源码。原凭据仅用于一次只读模型列表请求，返回200且含目标模型；未发送生成请求。已将具体支出上限建议、当前无法核实的账户价格/额度以及pending停止规则写入包，避免继续以本机回环代替提供方验证。A–D仍未完成，论文无新增实测结果。


## 阶段13：AI使用披露与当前验收状态

中英文稿的AI使用声明已更正：审后同模型子代理审核属于机械检查，不称跨模型独立科学验证；AI参与分析、实验设计和修订，不再称所有科学决策均由人类逐项作出。作者最终责任保留。实测数字和运行代码未变。英文重新编译16页、主文9页；中文19页、正文结束第11页。声明页（英10、中11）视觉检查通过，论文原42项一致性检查通过。

旧稿与旧verification在`artifacts/revision_20260910/before_ai_disclosure/`保留；`ai_disclosure/verification.json`列出旧验证中被本次论文更新取代的文件绑定。历史测试记录不是针对新PDF的再次验收，不静默更新其旧哈希。当前论文验证入口仍是`verification.json`与`chinese_sync_verification.json`。

尚不能关闭：A独立重复/clone/成本匹配；B独立校准与共同raw pool；C受控桥接；D冻结后的独立效用；W1完整选择不确定性；真实提供方及最终投稿包。阶段12的20元预算问题仍待答复，没有新增生成请求。论文整体沿用原审稿4/10、not ready，未以文稿修改冒充提分证据。


## 阶段14：W1共享权重与完整重选择开发分析

`W1_WEIGHT_SENSITIVITY.md`记录全部7方法、k4/8、候选only/含bare视图的199次联合正权重扰动。原100个重叠split和18cells共用同一题目权重，开发侧重新选候选及dev-fixed；完整存档运行通过全部全一权重选择及原点估计恢复检查。10项新旧selection测试和Ruff通过，原论文42项检查通过。

精确证实普通全局multinomial会有22.1801%的重复出现至少一个原split空侧，因此未用丢弃空侧的方法伪造bootstrap区间。正权重结果只称扰动分布：主k8含bare的oracle 2.5%–97.5%分位数为−0.0583至+0.6119 pp，headroom为+0.1965至+1.0523 pp，而dev-fixed全部199次差值为0；不能据此判显著、等效或实际部署收益。

旧论文数值/PDF不变。W1正式覆盖率/偏差推断仍未验收，A–D新证据及20元真实先导预算仍待完成；未发新模型生成请求。开发测试/同模型复核不构成跨模型科研放行。


## 阶段15：提供方计费与账户只读核验

`PROVIDER_ACCOUNT_READINESS.md`记录官方MaaS产品页、控制台Loading状态及未取得的账户价格/额度证据。官方说明包含内部fallback/异常重发，故客户端HTTP尝试不能当成提供方内部全部尝试或结算条目。未进行账户修改或模型生成；阶段12先导仍not ready to launch，20元支出上限问题仍待答复。

## 阶段16：跨模型复核与先导启动缺口修复

gpt-5.5对GPT-6执行产出作不同模型审核，最初给先导包7/10、not ready：DRAFT仅为标签、usage缺失后仍可继续两个软件缺口。v2已在父/worker入口拒绝DRAFT，缺失usage时保留答案与父pending、停止后续cell并拒绝自动续跑。旧v1源码快照保留，旧验证不改写；新草案及断网prepare另存`launch_guards/`。

完整revision测试81项通过，Ruff通过。跨模型审核独立重跑8项隔离测试，通过后给两项软件修复9/10、ready；真实launch仍not ready。该分数不是论文评分，也不是预算或正式科研放行。报告见`PROVIDER_LAUNCH_GUARDS.md`。

无新增真实生成请求；论文源码、数据和两版PDF未变。账户费用界、用户金额授权、最终冻结以及A–D/W1科研证据仍待完成，整体沿用原审稿4/10、not ready。

## 阶段17：Gate-v2开发集完成不同模型语义裁决

先冻结裁决材料、来源、预算及结构/语义合并规则，再由gpt-5.5审核GPT-6开发的14例无标签材料。四类合计4例conforms、10例nonconforms、0例indeterminate；原8例review_required据固定规则成为4例开发语义符合和4例不符合，另6例保留结构fail。40条证据逐字/逐字段回指、14例源码和轨迹映射均核验。

原裁决保留；唯一一次澄清修正证据格式，未改裁决。详细分布与边界见`GATE_SEMANTIC_ADJUDICATION.md`，证据在`gate_semantic_adjudication/`。本批语义审核已完成，但控制例均已曝光，不能报告独立误放率/误拒率或关闭B。下一项仍是独立控制集、接口覆盖与共同raw pool。没有新增真实模型实验，论文数据/PDF未改，整体4/10、not ready。

## 阶段18：独立构造控制揭示仪器误拒，并写入两版论文

冻结Gate-v2后，由未接触其实现/旧控制的新上下文gpt-5.5编写32例；gpt-5.6-sol作独立源码与语义裁决。首次测量5结构pass、18fail、9review_required，无执行失败。72条证据回指通过。三例作者预期正例有源码合同争议，原标签保留；29例无争议控制中，13例符合控制被拒3例，16例不符合控制均拒绝。有限控制验收not ready，不能外推种群错误率。

误拒来自分解spy重复匹配先前步骤，以及错误分类探针把普通Schema标题计为错误类别。没有修改仪器/控制或按结果重跑。报告见`GATE_INDEPENDENT_CALIBRATION.md`；13项记录/旧gate测试通过。schema_link缺少双方认可的正控制，完整独立校准和B仍未完成。

英文新增附录G/表9，中文同步并完成编译、视觉检查；英文17页、正文9页，中文20页、正文结束第11页。旧论文及验证快照保留，历史Phase-II数字不变。A–D/W1与真实先导的预算/费用界仍待完成，整体not ready。

## 阶段19：v3修复完成已曝光回归，独立校准仍待完成

新增独立版本gate-v3，修复分解请求归属并将分类词/模板比较归为审阅线索。32例已曝光回归为6 pass、13 fail、13待审；ic021误拒转pass，ic025/ic026及旧负例ic027/ic028均转待审，不作自动准入。23项相关测试通过、跨模型代码合同9/10 ready。旧仪器、首次32例证据及论文不改；详见`GATE_V3_REGRESSION.md`。新独立控制及新版语义裁决未完成，A–D/W1与真实先导授权仍待闭环。

## 阶段20：v3新独立控制首测和论文更新

固定v3后由新上下文独立作者构造32例，新独立审核者完成32源码/20语义裁决。唯一证据澄清后101条引用校验通过；31无争议参考为14接受、16拒绝、1未决，另vc026参考争议。vc025暴露中间分类请求收到SQL的fixture类型不匹配，不能归因于真实solver错误；error_classify正控制覆盖不足，finite not ready。双语附录G纳入新结果，旧首测保留，英文18页、中文20页。见`GATE_V3_INDEPENDENT.md`；没有新增真实生成或benchmark，A–D/W1及预算门槛保留。

## 阶段21：分类响应角色修复与已曝光回归

先由独立模型只读源码冻结四例响应角色，再完成84个主/诊断调用序列。vc025恢复按三类类别选择动作，其他控制的本地误分类、通用重试及丢弃类别行为保留。该组件只测注入类别消费，不自动准入，也不回写旧首测。11项测试及Ruff通过；报告恢复缺陷修复经两轴复核，实际测量所用旧runner与完整结果保留。见`CLASSIFICATION_RESPONSE_PROFILES.md`；新增中英文待整合说明，当前论文/PDF未改。完整独立校准、接口与共同raw pool仍待完成；A–D/W1及真实先导授权不变，整体not ready。

## 阶段22：上游代码提取审计并修订双语论文

真实候选源码检查发现强制C臂没有format_guard可调用文件。固定36份C/D日志核对108次尝试：均未中性有效或准入，71条未闭合字符串、36条无围栏、1条超时。归档extract_block在三个合成合法Python示例中被内嵌SQL围栏截断且未标truncated。74份现存提取文件中3份与对应无围栏日志冲突，不能归属该次尝试。历史完整回复及运行源码身份不足，不把相容性写成全部历史失败归因。

见`GENERATION_EXTRACTION_AUDIT.md`。审计声明跨模型9.4/10 ready、机械9/10 ready，3项专项测试通过；论文主文及附录B中英同步，英文18页（正文9）、中文21页（主文结束11），编译和视觉检查通过。旧源码/PDF及构建日志已先保存，原主分析不变。先修新生成回复保存／提取，再完成真实接口和共同raw pool；整体not ready，无新增provider生成或benchmark。

## 阶段23：新共同pool生成软件完成本机验收

新入口先保存content-encoding解码前的HTTP响应体，再提取Python；修复内嵌SQL围栏截断，固定每槽3次，不因首份有效或坏代码改变计划。异常回复或usage不完整保留未决并停机；生成端不执行候选或准入。13项专项测试及Ruff通过，本机HTTP演练6请求、2语法失败保留、完成后恢复0请求、压缩响应体逐字节一致。机械9/10、跨模型合同9.5/10 ready仅限软件；不代表论文提分或科学验收。见COMMON_POOL_GENERATION.md及common_pool_generation/verification.json。旧生成器、历史结果与本轮论文/PDF不改；真实共同池、八类接口、独立校准与A/C/D/W1仍待完成，费用授权未扩大。

## 阶段24：七份真实候选接口首测

固定名册七份C候选运行27个合成场景：10结构pass、4fail、13待审，无执行异常，另1条派生cross-class记录；format_guard仍缺失。two_view在首个结果非空的两场景中只执行第一份，违反原execute both声明。schema_link存在JSON响应类型不匹配；decompose完整计划使spy归属歧义；error_classify合成错误措辞触发默认semantics。后面三项首先是测量边界，不作真实分类准确率或机制失败归因。见RUNTIME_GATE_DIAGNOSTIC.md及runtime_gate_bridge/stage24/。旧gate/候选/论文不改，无provider或benchmark调用；B及A/C/D/W1仍未完成。

## 阶段25：响应格式与SQLite错误输入修正，更新两版附录

三份固定源码候选的11个新开发场景完成，4项测试及Ruff通过。合法schema JSON确实进入显式表列约束但完整schema仍保留；不能仅据上下文残留判原声明不符合。专用子问题字段恢复分解目标与SQL载荷组装，四项真实SQLite错误触发对应syntax/schema动作。跨模型证据解释9.6/10 ready仅限诊断，非独立校准。英中附录G同步新发现，英文18页/正文9、中文21页；编译、视觉检查与42项论文一致性检查通过。见RUNTIME_RESPONSE_PROFILES.md。B及A/C/D/W1未完成，历史统计数字不改，无provider/benchmark调用。

## 阶段26：统一Gate-v4并完成39场景开发回归

五类复用冻结v3，三类合并typed响应接口，未知profile待审不执行，schema上下文残留不再自动拒绝。分类支持本地/LLM中间类别，所有typed结果保持待审。8项测试通过；机械9/10、跨模型合同9.4/10 ready仅限开发代码。固定归档候选和旧控制39场景无执行异常，two_view及两个负控仍失败，format原候选缺失。见GATE_V4_REGRESSION.md，仪器只为后续独立参考检验冻结。论文/PDF沿用阶段25，完整校准、共同pool及A/C/D/W1未完成，无provider/benchmark调用。

## 阶段27：独立参考在首测前发现接口与合同偏差

32项新参考由gpt-5.6-sol构造，gpt-5.5盲静态审核，初始14符合/14不符合/4未决；补充原vote采样合同裁决后12符合/16不符合/4未决，与作者26/32一致。根审核核验43条逐字证据。四schema接口形状不兼容，两vote拟正例违反n=3、temperature=0.7，均在仪器首测前发现；未运行参考测量。首批来源/标签/审核完整保存，作者只修正这两类，修后需重新盲审。见GATE_V4_REFERENCE_PREFLIGHT.md，参考6/10 not ready；runner3测试及机械9/10仅为软件验收。旧阶段49绑定核验一致，论文/PDF不改，无provider或benchmark调用，整体提分目标仍未完成。
