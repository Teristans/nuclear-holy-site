-- ============================================================================
-- 皇帝之威 · 冻土农场层 (nhs_17_last_best_west.sql)  v7.30
--
-- 【来源：加拿大领袖劳雷尔的特性】
--   原版唯一允许「在冻土上建农场」的能力是
--     TRAIT_LEADER_LAST_BEST_WEST  （The Last Best West / 挂 LEADER_LAURIER）
--   游戏内英文原文（DLC/Expansion2/Text/en_US/Expansion2_ConfigText.xml:149）：
--     "Allows Farms to be built on Tundra terrain. After Civil Engineering is
--      unlocked Farms can be built on Tundra Hills. In Snow, Tundra, Snow Hills,
--      and Tundra Hills all Mines provide +2 Production, Lumber Mills provide
--      +2 Production, Camps provide +2 Food, Farms provide +2 Food, and
--      strategic resource accumulation rate is +100%. Reduces the purchase cost
--      of tiles in these terrain types by 50%."
--   —— 注意「Civil Engineering」是**市政**（CIVIC_CIVIL_ENGINEERING，
--      EraType=ERA_INDUSTRIAL，Cost=920），不是科技。别按科技去找。
--
-- 【机制：为什么它能做到，而不是改全局表】
--   农场的地形白名单 Improvement_ValidTerrains 只有四行：
--     GRASS / GRASS_HILLS / PLAINS / PLAINS_HILLS   —— 没有冻土。
--   直接往这张表插 TERRAIN_TUNDRA 是**全局**生效：所有文明（含 AI）立刻都能
--   在冻土建农场，与本 mod「只对秦始皇生效」的硬约束冲突。
--
--   加拿大走的是另一条路，全库仅此一例：
--     MODIFIER_PLAYER_CITIES_ADJUST_IMPROVEMENT_VALID_TERRAIN
--       = EFFECT_ADJUST_IMPROVEMENT_VALID_TERRAIN
--       CollectionType = COLLECTION_PLAYER_CITIES   ← 天生只收自己城市的玩家
--       参数：ImprovementType = IMPROVEMENT_FARM
--             TerrainType     = TERRAIN_TUNDRA / TERRAIN_TUNDRA_HILLS
--   丘陵那条额外挂 SubjectRequirementSetId = PLAYER_HAS_CIVIL_ENGINEERING
--   （= REQUIREMENT_PLAYER_HAS_CIVIC + CIVIC_CIVIL_ENGINEERING）。
--   因为是 Modifier，所以能被 Trait 门控、能挂人类门槛——这正是我们要的。
--
-- 【实现：克隆，不重写】
--   与本项目 nhs_04（俄罗斯母亲）同一套做法：把原版该 Trait 挂的全部 Modifier
--   连同参数整批克隆，前缀 NHS_LBW_，OwnerRequirementSetId 改为 PLAYER_IS_HUMAN，
--   再挂到「披荆斩棘」（TRAIT_NHS_MOTHER_RUSSIA，冻土那条威仪）上。
--
--   好处：零猜测（不手抄 26 条 ModifierId）、自动跟随原版数值、天然人类门槛。
--   代价：若原版没有这个 Trait（缺 GS），克隆结果为空且**不报错**，
--         退化为没有这一层。已经在 run_mod_sql.py 里加了条数断言兜住。
--
--   「全套」= 原版 26 条全克隆，含雪原那 12 条（本 mod 出生偏置只给冻土，
--   雪原项实际只在占领 AI 极地城市时才有意义，留着不占什么，一并收下）。
--
-- 【依赖与执行序】
--   必须排在 nhs_04 之后：本文件把克隆体挂到 TRAIT_NHS_MOTHER_RUSSIA，
--   而那个 Trait 是 nhs_04 建的。排前面会因外键失败（或被 OR IGNORE 静默吞掉）。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. 克隆 Modifier（带人类门槛）
--    只保留 4 个必要列，其余列走表默认值，避免依赖列名猜错。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId)
SELECT 'NHS_LBW_' || m.ModifierId,
       m.ModifierType,
       'PLAYER_IS_HUMAN',
       m.SubjectRequirementSetId
FROM Modifiers m
JOIN TraitModifiers tm ON tm.ModifierId = m.ModifierId
WHERE tm.TraitType = 'TRAIT_LEADER_LAST_BEST_WEST';

-- ---------------------------------------------------------------------------
-- 2. 克隆参数：只补上第 1 步真正克隆成功的那些
--    （用 EXISTS 反查克隆表，避免再次扫描正在被写入的表）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value)
SELECT 'NHS_LBW_' || a.ModifierId, a.Name, a.Value
FROM ModifierArguments a
WHERE EXISTS (
  SELECT 1 FROM Modifiers m WHERE m.ModifierId = 'NHS_LBW_' || a.ModifierId
);

-- ---------------------------------------------------------------------------
-- 3. 挂到「披荆斩棘」（冻土威仪）
--    下划线在 LIKE 中是通配符，故用 ESCAPE 转义（与 nhs_04 同写法）。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId)
SELECT 'TRAIT_NHS_MOTHER_RUSSIA', m.ModifierId
FROM Modifiers m
WHERE m.ModifierId LIKE 'NHS\_LBW\_%' ESCAPE '\';

-- ============================================================================
-- 【可选的减法】去掉「买地半价」与「战略资源累积 +100%」 —— 默认开启，全部生效
--
--   这两组是加拿大「拓荒」味道最重的部分，与「皇帝之威」的题材关系最弱，
--   而且买地 -50% 对前期扩张是实打实的加速。想收回去就把下面六行取消注释。
--   删的顺序必须是 关联表 → 参数 → 主表，否则外键残留。
--
--   涉及的 Modifier（克隆体名）：
--     NHS_LBW_TUNDRA_PLOT_COST / NHS_LBW_TUNDRA_HILLS_PLOT_COST
--     NHS_LBW_SNOW_PLOT_COST   / NHS_LBW_SNOW_HILLS_PLOT_COST
--     NHS_LBW_TUNDRA_RESOURCE_EXTRACTION / NHS_LBW_TUNDRA_HILLS_RESOURCE_EXTRACTION
--     NHS_LBW_SNOW_RESOURCE_EXTRACTION   / NHS_LBW_SNOW_HILLS_RESOURCE_EXTRACTION
-- ---------------------------------------------------------------------------
-- DELETE FROM TraitModifiers    WHERE ModifierId LIKE 'NHS\_LBW\_%PLOT\_COST' ESCAPE '\';
-- DELETE FROM ModifierArguments WHERE ModifierId LIKE 'NHS\_LBW\_%PLOT\_COST' ESCAPE '\';
-- DELETE FROM Modifiers         WHERE ModifierId LIKE 'NHS\_LBW\_%PLOT\_COST' ESCAPE '\';
-- DELETE FROM TraitModifiers    WHERE ModifierId LIKE 'NHS\_LBW\_%RESOURCE\_EXTRACTION' ESCAPE '\';
-- DELETE FROM ModifierArguments WHERE ModifierId LIKE 'NHS\_LBW\_%RESOURCE\_EXTRACTION' ESCAPE '\';
-- DELETE FROM Modifiers         WHERE ModifierId LIKE 'NHS\_LBW\_%RESOURCE\_EXTRACTION' ESCAPE '\';
