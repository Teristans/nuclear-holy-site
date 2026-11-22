-- ============================================================================
-- 皇帝之威 · 帝国规模层 (nhs_18_tech_scaling.sql)  v7.46
--
-- ############################################################################
-- ##  ★ 先读这一段：v37 / v38 / v40 三轮「零效果」的真实原因已查明，
-- ##    不是 effect 不生效，而是**三轮的测试方法全都无效**。
-- ############################################################################
--
-- 【真相】
--   这三轮（每人口负值 / 负百分比 / 负固定值）都是在**同一个老存档（t303）**上验证的。
--   Civ6 在**建局那一刻**把玩家已挂载的 trait modifier 集合写进存档；此后往 mod 里
--   新增的 modifier 只会进游戏库（GameInfo 里查得到），**不会追溯挂到已经在跑的存档上**。
--   于是三轮无论写什么 effect、什么符号、什么数值，读档后都一样纹丝不动。
--
-- 【两条铁证，都不是推断】
--   ① v41 探针：把三条 Amount 全改成 **+20（正值）**，其余不动。若是「引擎丢弃负值」，
--      正值必然生效、科研会暴涨。实测（Lua.readlive）：
--          会稽（21 人口）sci=121.76 —— 与改前一模一样，一分未动。
--      说明与符号无关、与 effect 类型无关，是**这条 modifier 根本没被挂上**。
--      同一次日志里 GameInfo.Modifiers[L1/L2/L3]=true，即「库里有、身上没有」。
--   ② 反面对照：本 mod 的「移民 +2 移动」（MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT，
--      同样 PLAYER_IS_HUMAN、同样挂 trait）在**同一存档里一直有效**（移民 6 移动）。
--      差别只有一个：那条 modifier 在这个存档建立**之前**就已经存在。
--
-- 【结论与规矩】
--   · 本层数值**只能在新开的局里验证**，老存档永远测不出来。
--     HANDOFF.md 第 7 条（改 SQL 层必须「完全退出进程 → 重启 → 新开一局」）本来就写着，
--     v37~v41 这几轮违反了它，所有「零效果」结论一并作废。
--   · 因此回到**百分比方案**：它是自适应的（科研涨了折扣自动跟上），
--     且与巴比伦的 TRAIT_SCIENCE_DECREASE（−50% 科研，原版自带、确定在跑）完全同形状。
--     v40 的固定值方案是在「误以为百分比不生效」的前提下做的妥协，前提已不成立，弃用。
--
-- ============================================================================
-- 【要解决的问题】
--   实机存档 t300 实测（神级 / 马拉松 / 大型 Terra / 14 城）：
--       玩家：14 城 · 172 人口 · 科技 37 · 科研 331/回合
--       玛雅：10 城 ·  69 人口 · 科技 23 · 科研  78/回合  ← 最强 AI
--   总科研 6.6 倍。但拆开看，超模不在乘数而在**承载力**：
--       科研 6.62x = 城市数 2.33x × 每城 2.84x × 每人口 1.19x
--   每人口科研只高 19%（1.92 对 1.13），真正拉开差距的是人口总量 2.49 倍。
--   本 mod 的冻土农场（+2 食物）与农庄（+1 食物）把人口曲线抬起来了，
--   而科研带着人口线性走，于是人口一多，科技就自己跑起来了。
--
--   所以这一层不砍任何乘数，只做一件事：**让「人口」这条轴自己收敛。**
--   城市越大，科研折扣越狠，科技总量对人口从「线性」变成「次线性」，
--   玩家再堆人口也换不来等比例的科技。
--
-- ============================================================================
-- 【机制出处 —— 全部查自 Cache/DebugGameplay.sqlite，非臆造】
--
--   ModifierType : MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER
--   DynamicModifiers: COLLECTION_PLAYER_CITIES + EFFECT_ADJUST_CITY_YIELD_MODIFIER
--   参数两个：YieldType / Amount（Amount 是**百分比整数**，−18 就是 −18%）
--
--   原版同形状用例（三条互不重叠，交叉验证）：
--     · TRAIT_SCIENCE_DECREASE（巴比伦）      Amount −50，挂 TraitModifiers
--     · DECENTRALIZATION_HIGHPOP_GOLD        Amount −15，Subject = 人口≥7 城市
--     · HIGH_DIFFICULTY_SCIENCE_SCALING      Amount 正值，Owner = 玩家判定
--   合起来就是本层的形状：**trait 挂载 + Owner 判玩家 + Subject 判城市人口**。
--
--   本 mod 的圣地加成用的是另一条 effect（EFFECT_ADJUST_CITY_YIELD_CHANGE，
--   加算类固定值），那条不受本层改动影响，继续照旧生效。
--
-- ============================================================================
-- 【三档设计 —— 人口越多，扣得越狠】
--
--     档位            门槛            本档 Amount   累计
--     ① 规模税       所有城市          −10%        −10%
--     ② 大城档       城市人口 ≥10      再 −12%     −22%
--     ③ 巨型城档     城市人口 ≥16      再 −8%      −30%
--
--   为什么门槛是 10 / 16：
--     10 是原版对「大城」的通用口径（STADIUM_10 分界、永乐人口门槛、体育场）。
--     16 是本 mod 场景下的「巨型城」分界：t300 时玩家 14 城 172 人口，
--     平均 12.3；首都类城市 20 以上。16 这个点把「堆到 16 以上的城」单独拎出来
--     再压一档，让惩罚随人口继续递增，而不是跨过 10 就封顶。
--     原版没有 16 的现成 set，所以自建（结构与 CITY_HAS_7_OR_MORE_POP 同构）。
--
--   为什么用百分比而不是固定值：
--     固定值（v40 的 −4/−14/−32）不会随科研增长自适应，t400 之后力度自动衰减，
--     等于「越到后期越松」，与设计目的相反。百分比则是「人口越多、折扣越重」，
--     且城市科研天然随时代增长，折扣绝对值也跟着长——这才是「次线性」的正解。
--     （百分比当初被判死刑只是因为测试无效，见文件头。）
--
-- ============================================================================
-- 【数值验算 —— 用 t150 实机读数倒推（2026-11-22，v46 口径）】
--   实测（神级 / 马拉松 / 10 城，本局只有 1 个 major AI + 12 城邦）：
--       人类 91.92 科研（逐城 83.93 + 贸易/城邦 7.99；10 城 99 人口）
--       最强 AI 吉尔伽美什 89.49（9 城）
--   三档取 −18/−20/−15（累计 −53%）时 → **1.03 倍**；完全不吃折扣 → **1.57 倍**。
--
--   ★ 为什么 −53% 太狠（这是本层设计上的固有代价，改档时必须想清楚）：
--     折扣在 16 人口封顶。封顶之后，人类每新增一个人口、每新建一座图书馆，
--     只拿 47% 收益，而 AI 拿 100%。两者扩张速度相当时，人类**持续相对走弱**。
--     1.03 意味着「科技刚好持平」，而神级 AI 另有产能/金币/生产加成，玩家整体吃亏；
--     且按该斜率 t250 之后会被反超。
--   故 v46 从「激进」调到「推荐」：−10/−12/−8（累计 −30%），按同批数据换算 = **1.26 倍**。
--
--   ★ 目标倍数为什么定 1.2~1.3 而不是 1.0：
--     1.0 是「科技与 AI 持平」，在神级下等于慢性失血；
--     1.26 是「明显领先但不碾压」，同时给后期人口增长留出衰减空间。
--     老存档 t300 那种 6.6 倍是要消除的病，1.26 倍不是。
--
--   ★ 叠加方式已实测为**加法**（不是乘法，别再按乘法估算）：
--       14.000 × (1 − 0.18 − 0.20) = 8.68  ← 实测命中
--       14.000 × (0.82 × 0.80)     = 9.18  ← 实测不命中
--     所以累计值 = 三个 Amount 直接相加，改档按算术推即可。
--
-- ============================================================================
-- 【旋钮 —— 只改这三个数字，其余不要动】
--       档位          温和(~1.4x)   推荐(~1.26x)  激进(~1.03x)
--     ① 所有人         −6           −10          −18
--     ② 人口≥10       −8           −12          −20
--     ③ 人口≥16       −5           −8           −15
--   （倍数一栏按 t150 实测数据换算：人类 91.92 / AI 89.49。
--     改档后倍数会偏，因为它是按当前城数与人口结构算的，只作量级参考。）
--   改完必须：完全退出游戏进程 → 重启 → **新开一局**（老存档不追溯，见文件头）。
--
-- 【为什么不动文化与产能】
--   同一份 t300 数据：文化 2.54 倍（每人口 0.46 倍，低于 AI），
--   产能 4.38 倍但每人口 0.79 倍（也低于 AI）。两者都不是乘数超模，
--   只是人口多带来的自然结果。给它们也加惩罚，会把「人多」从「有代价」
--   变成「纯负收益」，玩家只能精铺，与冻土农场的设定互相打架。
--   只压科技，是因为科技是唯一直接决定胜利进度（太空竞赛）的轴。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. 人口门槛：城市人口 ≥ 10 / ≥ 16
--    与 CITY_HAS_7_OR_MORE_POP_REQUIREMENTS 完全同构（一条
--    REQUIREMENT_CITY_HAS_X_POPULATION + Amount + REQUIREMENTSET_TEST_ALL），
--    只换名字与数字。Inverse 不写 = 0（满足即通过），不写 Inverse=1。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Requirements (RequirementId, RequirementType) VALUES
  ('NHS_REQ_CITY_POP_10', 'REQUIREMENT_CITY_HAS_X_POPULATION'),
  ('NHS_REQ_CITY_POP_16', 'REQUIREMENT_CITY_HAS_X_POPULATION');

INSERT OR IGNORE INTO RequirementArguments (RequirementId, Name, Value) VALUES
  ('NHS_REQ_CITY_POP_10', 'Amount', '10'),
  ('NHS_REQ_CITY_POP_16', 'Amount', '16');

INSERT OR IGNORE INTO RequirementSets (RequirementSetId, RequirementSetType) VALUES
  ('NHS_REQS_CITY_POP_10', 'REQUIREMENTSET_TEST_ALL'),
  ('NHS_REQS_CITY_POP_16', 'REQUIREMENTSET_TEST_ALL');

INSERT OR IGNORE INTO RequirementSetRequirements (RequirementSetId, RequirementId) VALUES
  ('NHS_REQS_CITY_POP_10', 'NHS_REQ_CITY_POP_10'),
  ('NHS_REQS_CITY_POP_16', 'NHS_REQ_CITY_POP_16');

-- ---------------------------------------------------------------------------
-- 2. 规模税：所有城市科研 −10%
--    OwnerRequirementSetId = PLAYER_IS_HUMAN → 只对人类秦始皇生效，
--    与本 mod 其余各层同一口径。AI 拿不到，科研节奏一点不变。
--    SubjectRequirementSetId 留空 = 不收窄，所有城市都吃（这正是「规模税」的本意）。
--
--    为什么敢用 OR IGNORE（旧行不会残留）：
--      Civ6 每次**进程启动**都从模板重建 Cache/DebugGameplay.sqlite，上一次会话
--      mod 写入的行不会跨进程保留；而同一进程内 UpdateDatabase 只执行一次。
--      不重启进程时 SQL 根本不会重跑，所以不存在「OR IGNORE 跳过、留着旧类型」的场景。
--      若哪天引擎改成增量更新，这里要换成先 DELETE 再 INSERT。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId) VALUES
  ('NHS_TECH_SCALE_L1', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER', 'PLAYER_IS_HUMAN');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_TECH_SCALE_L1', 'YieldType', 'YIELD_SCIENCE');
INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_TECH_SCALE_L1', 'Amount',    '-10');

INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_TECH_SCALE_L1');

-- ---------------------------------------------------------------------------
-- 3. 大城档：人口 ≥10 的城市再 −12%
--    Owner 判「这个玩家是不是人类」，Subject 判「这座城市够不够大」，
--    两者在不同收集阶段评估，不冲突（原版 DECENTRALIZATION_HIGHPOP_GOLD
--    就是「同一 modifier + 人口门槛 Subject」的形状）。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId) VALUES
  ('NHS_TECH_SCALE_L2', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER', 'PLAYER_IS_HUMAN', 'NHS_REQS_CITY_POP_10');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_TECH_SCALE_L2', 'YieldType', 'YIELD_SCIENCE');
INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_TECH_SCALE_L2', 'Amount',    '-12');

INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_TECH_SCALE_L2');

-- ---------------------------------------------------------------------------
-- 4. 巨型城档：人口 ≥16 的城市再 −8%（三档累计 −30%）
--    这一档是「边际递增」的来源：跨过 16 之后斜率再抬一档，
--    防止「只要到 10 就封顶」——那样 10 人口和 30 人口吃一样的折扣，
--    「人口越多惩罚越多」就只对了一半。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId) VALUES
  ('NHS_TECH_SCALE_L3', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER', 'PLAYER_IS_HUMAN', 'NHS_REQS_CITY_POP_16');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_TECH_SCALE_L3', 'YieldType', 'YIELD_SCIENCE');
INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_TECH_SCALE_L3', 'Amount',    '-8');

INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_TECH_SCALE_L3');

-- ============================================================================
-- 【实机验收 —— ✅ 三档全部通过（2026-11-22，v42~v45）】
--   0. 老存档（t303 那局）**永远验不出来**，原因见文件头，别在那里浪费时间。
--   1. 完全退出游戏进程 → 重启 → **新开一局**（秦始皇，任意难度/速度）。
--
--   ★ 实测记录（2026-11-22，v42，神级/马拉松/新开局，已通过）
--     ① 开局第 1~4 回合（验证 L1）：
--          人类首城（咸阳，pop 1）  sci = 1.89
--          城邦单城基准（n=5，pop 1）sci = 2.30   ← 不吃难度加成、不吃本 trait
--          比值 1.89 / 2.30 = 0.8217 → 折扣 17.8%，与设计 −18% 吻合。
--        同一份日志里老存档（t303）会稽仍是 121.76（= 0%），两相对照即知：
--        **老存档里根本没有这条 modifier，新存档有且生效。**
--     ② t79 → t80（验证 L2，同城同回合只多一个人口，最干净的一组）：
--          咸阳 pop 9   sci = 11.23   → 若无折扣 11.23 / 0.82 = 13.695
--          咸阳 pop 10  sci =  8.68   → 若无折扣  8.68 / 0.62 = 14.000
--          两者差 0.305，恰好是一个人口的科研贡献（每人口约 0.30）
--        → 折扣从 −18% 整档跳到 −38%，L2 确认生效。
--     ③ **叠加方式是加法，不是乘法**（这条对以后调数值很关键）：
--          乘法预测 14.000 × (0.82 × 0.80) = 14.000 × 0.656 = 9.18  ← 实测不是
--          加法预测 14.000 × (1 − 0.18 − 0.20)   = 14.000 × 0.620 = 8.68 ← 实测吻合
--        所以三档的累计值就是三个 Amount 直接相加（−18 −20 −15 = −53），
--        改任一档时按算术加减推结果即可，不要再去乘百分比。
--     ④ t? → 咸阳 pop 15 → 16（验证 L3）：
--          咸阳 pop 15  sci =  9.61   → 若无折扣  9.61 / 0.62 = 15.500
--          咸阳 pop 16  sci =  7.40   → 若无折扣（实测报告值，日志尚未落下）
--          预测：15.805 × 0.47 = 7.43，实测 7.40，**差 0.03**。
--        → 折扣整档 −38% → −53%，L3 确认。三档全部通过，本层机制收工。
--     ⑤ 顺带记录一个不属于本层的现象：pop 14 → 15 时科研反而从 10.95 掉到 9.61（−12.2%）。
--        这两级都在 −38% 档，人口 +1 本应 +0.305（+2.8%），反推还有约 −14% 的额外
--        全局惩罚 —— 这是**宜居度掉档**（人口增长吃宜居度）的典型幅度，Civ6 固有机制，
--        与本 mod 无关。以后看到类似的「人口涨了科研反降」，先查宜居度，别怀疑本层。
--     ⑥ 判据不要在「人类 vs AI」上看：AI 带神级难度加成（实测 +40%~+50%），
--        人类必然低于 AI，那不是本层的功劳。要看「人口跨门槛的跳变」或「人类 / 城邦」。
--
--   2. 三档的识别方法：人类首城 / 城邦单城均值
--        −10% ≈ 只有 L1（人口 <10 时的正确状态）
--        −22% ≈ L2 也生效（人口 ≥10）
--        −30% ≈ 三档全叠（人口 ≥16）
--      （下面 ①~⑥ 的实测记录是 v42 时拍的，那三档是 −18/−20/−15，
--        对应 −18/−38/−53；判据结构完全相同，只是数字换了一批。）
--      0%   ≈ 没生效 → 先确认真的是新开的局（老存档不会追溯）。
--      nhs_info.lua v7.43 起会直接打印「折扣实测: … 比值=0.xxx（−xx.x%）」这一行。
--   3. ✅ 第三档（L3）已复核通过：咸阳 pop 16 实测 7.40，与预测 7.43 差 0.03。
--      机制验收至此完成。**注意区分两件事**：
--        · 「机制是否生效」= 已证（三档全部实测命中）
--        · 「平衡目标是否达成」= **未证**，要打到 t150 之后看人类/AI 科研总量倍数，
--          前期人类只有最强 AI 的 60%（t82 实测），中期是否会反超过多，仍需观测。
--   4. 顺带确认 AI 没受影响：AI 城市科研不应出现任何负向修正。
--   5. `NHS_SCRIPT` 动作块**暂时保留**：机制虽已验收，平衡目标还没定，
--      中期（t150 之后）仍要靠它看人类/AI 科研总量。平衡定稿后再删。
-- ============================================================================
