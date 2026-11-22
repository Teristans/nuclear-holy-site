-- ============================================================================
-- 核动力圣地 · 俄罗斯母亲层 (nhs_04_mother_russia.sql)
-- 游戏数值平衡专家 设计产物
--
-- 加入「俄罗斯母亲」能力（TRAIT_CIVILIZATION_MOTHER_RUSSIA）：
--   * 建成城市时额外 8 格领土
--   * 苔原地块 +1 信仰 +1 产能（市中心除外）
--   * 单位免疫暴风雪 / 敌方在俄领土受双倍暴风雪伤害  ← 本 mod 不移植（见下）
--
-- 实现思路（这是本文件最关键的工程决策）：
--   不重新实现效果，而是从游戏数据库"克隆"原版该 Trait 挂载的 Modifier：
--     克隆体 = 'NHS_MR_' + 原 ModifierId，并把 OwnerRequirementSetId 改为
--     PLAYER_IS_HUMAN，再挂到自定义 Trait TRAIT_NHS_MOTHER_RUSSIA 上。
--
--   为什么这么做：
--     1) 零猜测 —— 不需要知道任何具体 ModifierId / EffectType / 参数名。
--        原版怎么写，这里就跟着怎么写，不会因为 ID 敲错而变废纸。
--     2) 自动跟随版本 —— 官方改了数值，克隆体同步。
--     3) 天然的人类门槛 —— 加在 Owner 上，AI 拿到 Trait 也不生效。
--
--   代价 / 风险（如实标注）：
--     a) 依赖原版行存在。若你的版本没有这个 Trait，克隆结果为空——不会报错，
--        但也不会有任何苔原加成（退化为只有核心层）。
--     b) 通过 'BLIZZARD' 关键字排除暴风雪相关 Modifier：暴风雪免疫/易伤是
--        GS 的天气系统内容，与"帮助新手发展"无关，且移植后语义诡异，故剔除。
--     c) 原版若把某效果做在 C++ 层（不走数据库），克隆无法覆盖（如额外领土
--        若为硬编码，则本层拿不到该效果）。这属于无法离线验证项。
--
-- 核对方法见 README 第 4 节。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. 自定义 Trait
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Types (Type, Kind) VALUES
  ('TRAIT_NHS_MOTHER_RUSSIA', 'KIND_TRAIT');

INSERT OR IGNORE INTO Traits (TraitType, Name, Description) VALUES
  ('TRAIT_NHS_MOTHER_RUSSIA',
   'LOC_TRAIT_NHS_MR_NAME',
   'LOC_TRAIT_NHS_MR_DESC');

-- ---------------------------------------------------------------------------
-- 2. 克隆原版 Modifier（带人类门槛）
--    只保留 4 个必要列，其余列走表默认值，避免依赖列名猜错。
--    排除含 BLIZZARD 的 Modifier（天气系统内容，与本题无关）。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId)
SELECT 'NHS_MR_' || m.ModifierId,
       m.ModifierType,
       'PLAYER_IS_HUMAN',
       m.SubjectRequirementSetId
FROM Modifiers m
JOIN TraitModifiers tm ON tm.ModifierId = m.ModifierId
WHERE tm.TraitType = 'TRAIT_CIVILIZATION_MOTHER_RUSSIA'
  AND NOT EXISTS (
        -- 用 NOT EXISTS 而非 NOT IN：Value 存在 NULL 时 NOT IN 会整体失效
        SELECT 1 FROM ModifierArguments a
        WHERE a.ModifierId = m.ModifierId AND a.Value LIKE '%BLIZZARD%'
      );

-- ---------------------------------------------------------------------------
-- 3. 克隆参数：只补上第 2 步真正克隆成功的那些
--    （用 EXISTS 反查克隆表，避免再次扫描正在被写入的表）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value)
SELECT 'NHS_MR_' || a.ModifierId, a.Name, a.Value
FROM ModifierArguments a
WHERE EXISTS (
  SELECT 1 FROM Modifiers m WHERE m.ModifierId = 'NHS_MR_' || a.ModifierId
);

-- ---------------------------------------------------------------------------
-- 4. 挂到自定义 Trait
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId)
SELECT 'TRAIT_NHS_MOTHER_RUSSIA', m.ModifierId
FROM Modifiers m
WHERE m.ModifierId LIKE 'NHS\_MR\_%' ESCAPE '\';
-- 注：下划线在 LIKE 中是通配符，故用 ESCAPE 转义；若你的 SQLite 版本报错，
--     可直接换成 WHERE m.ModifierId LIKE 'NHS_MR_%'（本 mod 内无歧义 ID）。


-- ---------------------------------------------------------------------------
-- 5. 只发给秦始皇（LEADER_QIN）
--    v7 起本 mod 是「秦始皇专属」，见 nhs_01 的说明。
--
--    不再需要排除俄罗斯：秦始皇的文明是中国，原版俄罗斯母亲的 trait
--    根本不在秦始皇身上，不存在双份叠加的可能。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO LeaderTraits (LeaderType, TraitType) VALUES
  ('LEADER_QIN', 'TRAIT_NHS_MOTHER_RUSSIA');
