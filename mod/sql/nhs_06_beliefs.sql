-- ============================================================================
-- 核动力圣地 · 信条/政策层 (nhs_06_beliefs.sql)
-- 游戏数值平衡专家 设计产物
--
-- 本层克隆四个"加强圣地"的原版条目（全部走同一套克隆策略）：
--   1) BELIEF_DANCE_OF_THE_AURORA   极光之舞（万神殿）  圣地 +1 信仰/相邻冻土
--   2) BELIEF_WORK_ETHIC            职业道德（追随者）  圣地相邻信仰 → 等量产锤 ★引擎
--   3) BELIEF_JESUIT_EDUCATION      耶稣会教育（追随者）可用信仰购买学院/剧院建筑
--   4) POLICY_SCRIPTURE             经文（政策卡，神学解锁）+100% 圣地相邻加成 ★翻倍
--
-- ⚠ 三条必须先读的风险提示（信条克隆比特性克隆不确定得多）：
--
--   (a) 【宗教门槛】信条类 Modifier 通常自带"城市信奉本宗教"的 SubjectRequirementSet。
--       我保留了这个门槛（更忠于原版），也就是说：**必须先创教、且城市信你的教**，
--       才吃得到职业道德/耶稣会教育。以本 mod 的信仰产出，创教是很快的事，但不是开局即有。
--       若你想跳过宗教门槛（变成一个纯被动），把下面 1 段的 SubjectRequirementSetId
--       改成 NULL 即可 —— 但这属于魔改，效果可能与原版不等价。
--
--   (b) 【重复叠加】游戏无法在数据库层判断玩家"是否自己已经选了这条信条"。
--       如果你自己又选了极光之舞/职业道德，会拿到两份。**建议不要重复选。**
--
--   (c) 【经文是政策卡】POLICY_SCRIPTURE 从 PolicyModifiers 克隆，等于"常驻一张政策卡"，
--       不占政策位。这是本层最强的改动：它把原版中古（神学）才有的杠杆提前到开局，
--       数学后果是远古产能比冲到 1.5+。若觉得远古太无脑，注释掉第 2 段即可。
--
-- 核对方法见 README 第 4 节。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 0. 自定义 Trait
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Types (Type, Kind) VALUES
  ('TRAIT_NHS_BELIEFS', 'KIND_TRAIT');

INSERT OR IGNORE INTO Traits (TraitType, Name, Description) VALUES
  ('TRAIT_NHS_BELIEFS',
   'LOC_TRAIT_NHS_BEL_NAME',
   'LOC_TRAIT_NHS_BEL_DESC');

-- ---------------------------------------------------------------------------
-- 1. 克隆信条（极光之舞 + 职业道德 + 耶稣会教育）
-- ---------------------------------------------------------------------------
--
-- ★ v33：克隆时排除 WORK_ETHIC_FOLLOWER_PRODUCTION（每信徒 +1 产能）。
--   原版 BELIEF_WORK_ETHIC 由两条 Modifier 组成：
--     WORK_ETHIC_ADJACENCY_PRODUCTION_2   相邻信仰 → 等量产锤（保留，随选址收敛）
--     WORK_ETHIC_FOLLOWER_PRODUCTION      每信徒 +1 产能（剔除，随人口线性、无上限）
--   后者是 MODIFIER_ALL_CITIES_ATTACH_MODIFIER，挂的是
--   COLLECTION_ALL_CITIES + CITY_FOLLOWS_RELIGION_REQUIREMENTS，
--   所以同教的 AI 城市也会吃。中后期人口一涨，产能就失控，
--   而前期它给得极少 —— 正是"前期弱、后期爆"的元凶。
--   只留相邻那条：选址好才有收益，且收益被城市质量锁死。
--
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId)
SELECT 'NHS_BL_' || m.ModifierId,
       m.ModifierType,
       'PLAYER_IS_HUMAN',
       m.SubjectRequirementSetId
FROM Modifiers m
JOIN BeliefModifiers bm ON bm.ModifierId = m.ModifierId
WHERE bm.BeliefType IN ('BELIEF_DANCE_OF_THE_AURORA',
                        'BELIEF_WORK_ETHIC',
                        'BELIEF_JESUIT_EDUCATION')
  AND m.ModifierId <> 'WORK_ETHIC_FOLLOWER_PRODUCTION';

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value)
SELECT 'NHS_BL_' || a.ModifierId, a.Name, a.Value
FROM ModifierArguments a
WHERE EXISTS (
  SELECT 1 FROM Modifiers m WHERE m.ModifierId = 'NHS_BL_' || a.ModifierId
);

-- ---------------------------------------------------------------------------
-- 1b. 极光之舞：改写为「无条件生效 + 只作用于自己的城市」（v24）
--   实机反馈「勤则不匮的冻土加信仰看不见」。根因不在「有没有选极光之舞」——
--   我们从来不是给你挂信条，而是把信条的 Modifier 直接克隆到 trait 上，
--   所以你选不选那条万神殿都与它无关。真正的两处卡点在下面：
--
--   (1) 克隆体原样继承了 SubjectRequirementSetId = CITY_FOLLOWS_PANTHEON_REQUIREMENTS。
--       这条要求的内容是「城市跟随你的万神殿」——**没立万神殿时判定为假**，
--       整条加成就静默失效（不报错、日志干净）。也就是说开局到花 25 信仰立
--       万神殿之前，冻土对圣地一点用都没有。
--   (2) 原版之所以敢用 COLLECTION_ALL_CITIES（全世界所有城市）这个收集器，
--       正是靠上面那条门槛把范围收回到「自己的城市」。所以**不能只删门槛**，
--       否则加成就发给 AI 的圣地。
--
--   改法：换成原版现成的 MODIFIER_PLAYER_CITIES_TERRAIN_ADJACENCY
--   （COLLECTION_PLAYER_CITIES + EFFECT_TERRAIN_ADJACENCY，参数完全相同，
--     印尼「香料群岛」特性 TRAIT_NUSANTARA_COAST_* 就是 35 条这个写法，
--     全部不带任何 SubjectRequirement），再把门槛置空。
--   效果：开局即有，圣地每相邻一格冻土 +1 信仰；与你是否立万神殿无关。
--
--   ⚠ 副作用（刻意接受）：若你自己又选了「极光之舞」作万神殿，
--   原版那条 modifier 会再叠一份 → 相邻冻土变成 +2。文案已提示不要重复选。
-- ---------------------------------------------------------------------------
UPDATE Modifiers
   SET ModifierType           = 'MODIFIER_PLAYER_CITIES_TERRAIN_ADJACENCY',
       SubjectRequirementSetId = NULL
 WHERE ModifierId LIKE 'NHS_BL_DANCE_OF_THE_AURORA%';

-- ---------------------------------------------------------------------------
-- 2. 克隆经文政策卡（POLICY_SCRIPTURE：+100% 圣地相邻加成）
--    ★ 这是最强也最危险的一段。注释掉整个第 2 段即可退回温和版本。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId)
SELECT 'NHS_PL_' || m.ModifierId,
       m.ModifierType,
       'PLAYER_IS_HUMAN',
       m.SubjectRequirementSetId
FROM Modifiers m
JOIN PolicyModifiers pm ON pm.ModifierId = m.ModifierId
WHERE pm.PolicyType = 'POLICY_SCRIPTURE';

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value)
SELECT 'NHS_PL_' || a.ModifierId, a.Name, a.Value
FROM ModifierArguments a
WHERE EXISTS (
  SELECT 1 FROM Modifiers m WHERE m.ModifierId = 'NHS_PL_' || a.ModifierId
);
-- ↑↑↑ 第 2 段结束（要关闭经文，只需把上面四条语句注释掉）↑↑↑

-- ---------------------------------------------------------------------------
-- 3. 全部挂到自定义 Trait
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId)
SELECT 'TRAIT_NHS_BELIEFS', m.ModifierId
FROM Modifiers m
WHERE m.ModifierId LIKE 'NHS_BL_%' OR m.ModifierId LIKE 'NHS_PL_%';

-- ---------------------------------------------------------------------------
-- 4. 只发给秦始皇（LEADER_QIN）
--    v7 起本 mod 是「秦始皇专属」。信条不是任何文明的固有特性，
--    所以不需要排除谁；限定领袖即可。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO LeaderTraits (LeaderType, TraitType) VALUES
  ('LEADER_QIN', 'TRAIT_NHS_BELIEFS');
