-- ============================================================================
-- 核动力圣地 · 工人加速奇观层 (nhs_08_wonder_boost.sql)
-- 游戏数值平衡专家 设计产物
--
-- 需求（v7.36 起）：人类工人可以加速**任意时代**的奇观；
--   远古～中世纪每次 30%，**进入文艺复兴时代后降为 15%**。
--
-- 【v7.36 变更：时代全开 + 后期幅度减半】
--   上一版（v7.28）是把 MaxEra 收到 3（中世纪），文艺复兴之后干脆不能加速。
--   现在改成「时代不设限、后期只推一半」：进度随时能推，但文艺复兴起一次只推 15%
--   （正好等于原版秦始皇的幅度），避免"一个工人包圆现代奇观"。
--
--   实现：本层那 +15% 挂上需求「玩家尚未进入文艺复兴」（第 1b 节），
--   进文艺复兴后该需求失效 → 只剩原版 15%。
--   时代全开在 nhs_09_wonder_era.sql（MaxEra = -1）。
--
--   ⚠ 两处必须成对：只改 nhs_09 不改本文件 = 全程 30%（失衡）；
--     只改本文件不改 nhs_09 = 文艺复兴之后按钮消失，15% 永远看不到。
--
-- 【v7 重大变更：只给秦始皇，且改成「叠加到 30%」而不是「另给 30%」】
--   原版：秦始皇的工人加速 = 15%（TRAIT_BUILDER_WONDER_PERCENT, Amount=15）
--   本层：再给一个 +15%，两者相加 = 30% → 正好是你的目标值
--   原来写 30% 是因为要绕开中国（怕 15+30=45 叠加失控）；
--   现在既然 mod 就是给秦始皇用的，就不该再叠加出 45%，直接各出 15%。
--
--   百分比类 modifier 在同为 MODIFIER_PLAYER_ADJUST_UNIT_WONDER_PERCENT 时
--   是按玩家累加的，所以 15 + 15 = 30 是确定行为，不是推测。
--
-- 【原版机制的确切实现 —— 已查实，非猜测】
--   秦始皇（TRAIT_LEADER_THE_FIRST_EMPEROR → FIRST_EMPEROR_TRAIT）的加速由两段组成：
--     1) 百分比：ModifierId = 'TRAIT_BUILDER_WONDER_PERCENT'
--                 ModifierType = 'MODIFIER_PLAYER_ADJUST_UNIT_WONDER_PERCENT'
--                 ModifierArguments: Name='Amount', Value='15'
--                 （Leaders.xml:1531 定义、3652 处 Amount=15、1087 挂在 trait 上）
--     2) 时代限制：不在 modifier 里，而在 UnitCommands 表的
--                 'UNITCOMMAND_WONDER_PRODUCTION' 行的 MaxEra 列（默认 2 = 古典）
--        → 解禁全时代见 nhs_09_wonder_era.sql
--
--   【关键事实：这个能力本来就是秦始皇独占】
--     多个来源一致确认"秦始皇是唯一能用建造者加速奇观的领袖"。
--     也就是说 —— 引擎判定"能不能用加速指令"的依据，就是玩家有没有
--     MODIFIER_PLAYER_ADJUST_UNIT_WONDER_PERCENT 的效果。
--     这正是本方案能成立的技术前提：既然 mod 只给秦始皇，
--     AI 里没有这份效果（人类占了秦始皇）→ AI 连加速按钮都没有。
--
-- 【⚠ 数值警告 —— 这一层依然是全 mod 最破坏平衡的部分】
--   见 civ6_nhs_balance_v6.py 第 2~5 节（按每次 30% 估算）：
--     · 投入产出比：远古 3.00x、工业 7.12x、现代 8.04x（正常投资回报 1.0~1.5x）
--     · 前期：秦始皇自带工人 +1 次（4 次）→ 30% × 4 = 120%
--       **一个工人直接把奇观从 0 干到完工**（v7.36 起仅限文艺复兴之前）
--     · 后期：15% × 4 = 60% —— 一个工人最多推掉六成，必须配合城市产能
--       （换算成投入产出比约为上表的一半：工业 7.12x → 3.56x、现代 8.04x → 4.02x）
--     · 金币买工人再加速：前期 1.50~4.02 产能/金币（正常购买 0.5），后期减半
--   想再降温就把下面 Amount 改成 10（前期总 25%、后期 10%），或把
--   时代分档的门槛从文艺复兴提前到中世纪（改 NHS_REQ_NOT_RENAISSANCE 的 EraType）。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. 自定义 Trait
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Types (Type, Kind) VALUES
  ('TRAIT_NHS_MASTER_BUILDER', 'KIND_TRAIT');

INSERT OR IGNORE INTO Traits (TraitType, Name, Description) VALUES
  ('TRAIT_NHS_MASTER_BUILDER',
   'LOC_TRAIT_NHS_BUILDER_NAME',
   'LOC_TRAIT_NHS_BUILDER_DESC');

-- ---------------------------------------------------------------------------
-- 1b. 时代分档需求（v7.36）：本层那 +15% 只在「还没进文艺复兴」时生效
--
--     写法：REQUIREMENT_PLAYER_ERA_AT_LEAST + Inverse = 1
--           语义 = NOT(玩家时代 >= 文艺复兴) = 远古 / 古典 / 中世纪
--
--     【为什么用 Inverse，而不是「进文艺复兴后减 15」】
--       减法要依赖「百分比累加接受负数」。若引擎在单条 modifier 上做
--       clamp(>=0)，那条 -15 会被吞掉，结果静默变回全程 30%，不报错、查不出来。
--       Inverse 只需要引擎认 Inverse 列，而且**失败方向更安全**：
--       万一 Inverse 不生效，结果是全程 30%（回到 v7.28 手感），
--       而不是掉到 0%。失败要往"还能玩"的方向掉，这是有意的取舍。
--
--     【已核实的四件事（都不是凭记忆）】
--       · RequirementType 真实存在：REQUIREMENT_PLAYER_ERA_AT_LEAST
--       · 原版同类用例：REQUIRES_PLAYER_IS_INDUSTRIAL_ERA（EraType=ERA_INDUSTRIAL）
--       · 时代名与序号：ERA_RENAISSANCE = 4（Eras 表逐行读出）
--       · PLAYER_IS_HUMAN 这个 Set 里只有一条 REQUIREMENT_PLAYER_IS_HUMAN，
--         其 RequirementId 就是 'REQUIRES_PLAYER_IS_HUMAN'，可直接搬进新 Set
--         （RequirementSetRequirements 是多对多，原版也大量复用同一条需求）
--       · RequirementArguments 的 Type 列建议显式写 'ARGTYPE_IDENTITY'。
--         注意：这一列在 schema 里**有默认值**（DEFAULT "ARGTYPE_IDENTITY"），
--         所以漏写不会出错、落库值也一样；显式写只是为了让审阅的人一眼看清。
--         真正会出错的是把 Type 写成别的值（如 ARGTYPE_NUMBER），那才会让参数不被识别。
--
--     ⚠ 判的是**人类玩家自己的时代**，不是目标奇观的时代。
--       所以文艺复兴之后回头造一座远古奇观，也是 15%。
--       这与"时代越往后越该收敛"的设计意图一致，也和 MaxEra 判奇观时代不同维度。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Requirements (RequirementId, RequirementType, Inverse) VALUES
  ('NHS_REQ_NOT_RENAISSANCE', 'REQUIREMENT_PLAYER_ERA_AT_LEAST', 1);

INSERT OR IGNORE INTO RequirementArguments (RequirementId, Name, Type, Value) VALUES
  ('NHS_REQ_NOT_RENAISSANCE', 'EraType', 'ARGTYPE_IDENTITY', 'ERA_RENAISSANCE');

INSERT OR IGNORE INTO RequirementSets (RequirementSetId, RequirementSetType) VALUES
  ('NHS_RS_WONDER_BOOST', 'REQUIREMENTSET_TEST_ALL');

INSERT OR IGNORE INTO RequirementSetRequirements (RequirementSetId, RequirementId) VALUES
  ('NHS_RS_WONDER_BOOST', 'REQUIRES_PLAYER_IS_HUMAN'),
  ('NHS_RS_WONDER_BOOST', 'NHS_REQ_NOT_RENAISSANCE');

-- ---------------------------------------------------------------------------
-- 2. Modifier：再 +15%（与原版 15% 相加 = 30%）
--    门槛：NHS_RS_WONDER_BOOST = 人类 且 尚未进入文艺复兴
--          多人局里另一个玩家即使也选秦始皇，也因为是 AI 而拿不到
--    不设 SubjectRequirementSet：该 EffectType 只对建造者的加速指令有意义，
--    多挂一个需求反而增加 ID 出错的风险。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId) VALUES
  ('NHS_BUILDER_WONDER_PERCENT', 'MODIFIER_PLAYER_ADJUST_UNIT_WONDER_PERCENT', 'NHS_RS_WONDER_BOOST');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_BUILDER_WONDER_PERCENT', 'Amount', '15');

-- ---------------------------------------------------------------------------
-- 3. 挂到 Trait
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_MASTER_BUILDER', 'NHS_BUILDER_WONDER_PERCENT');

-- ---------------------------------------------------------------------------
-- 4. 只发给秦始皇
--    v7 起：不再排除中国，而是**只给中国（LEADER_QIN）**。
--    原版 15% + 本层 15% = 30%（文艺复兴之前）；进入文艺复兴后本层失效，只剩原版 15%。
--    （旧版写 30% 并排除中国，是因为怕 15+30=45 失控；那套逻辑已废弃。）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO LeaderTraits (LeaderType, TraitType) VALUES
  ('LEADER_QIN', 'TRAIT_NHS_MASTER_BUILDER');

-- ---------------------------------------------------------------------------
-- ---------------------------------------------------------------------------
-- 备选：若实机发现"加速按钮不出现"
--   v7 之后这一层只发给秦始皇，而秦始皇**本来就有**原版 15% 的加速能力，
--   所以按钮理论上是存在的（只是时代受限）。若仍然看不到按钮，按顺序排查：
--     1) 确认你选的是秦始皇（LEADER_QIN），不是忽必烈领导的中国
--     2) 确认建造者站在该奇观所在城市的地块上、且该城正在建该奇观
--     3) 确认建造者还有剩余使用次数与移动力
--     4) 确认奇观时代 ≤ MaxEra —— v7.36 起 MaxEra = -1（不限），此项已不成因，
--        但仍要确认 nhs_09 真的执行了（查 DebugGameplay.sqlite：
--        SELECT MaxEra FROM UnitCommands WHERE CommandType='UNITCOMMAND_WONDER_PRODUCTION';）
--
--   旧版曾建议"克隆 TRAIT_LEADER_THE_FIRST_EMPEROR 的 modifier"——
--   该方案在 v7 已废弃：秦始皇本来就有那个 trait，克隆会变成双份叠加（15+15+15）。
--
--   【若"文艺复兴之后仍是 30%"】说明 Inverse 没被引擎采纳（见第 1b 节）。
--   核对方法：DebugGameplay.sqlite 里
--     SELECT RequirementId, RequirementType, Inverse FROM Requirements WHERE RequirementId='NHS_REQ_NOT_RENAISSANCE';
--   应为 Inverse=1。若为 1 但游戏仍给 30%，则换成"文艺复兴起 -15"的减法方案
--   （改 ModifierArguments 为 -15 并去掉 Inverse），并实测是否被 clamp。
-- ---------------------------------------------------------------------------
