-- ============================================================================
-- 核动力圣地 · 国王的修道院层 (nhs_05_monasteries.sql)
-- 游戏数值平衡专家 设计产物
--
-- 加入「国王的修道院」能力（TRAIT_LEADER_MONASTERIES_KING，阇耶跋摩七世领袖特性）：
--   * 圣地与河流相邻时获得「大相邻加成」（+2 信仰）
--   * 圣地的食物产出 = 其相邻加成数值
--   * 圣地在河流旁时 +2 住房
--   * 建造圣地时触发文化炸弹（顺带圈地，正好配合俄罗斯母亲的额外领土）
--
-- ⚠ 注意这是【领袖特性】不是文明特性（原版挂在 LEADER_JAYAVARMAN 上）。
--   本层依然用 CivilizationTraits 发放——trait 本身只关心 KIND_TRAIT 与它挂的
--   Modifier，不关心来源是领袖还是文明；这样做能和 nhs_04 保持同一套写法。
--   若实机发现不生效，改用 LeaderTraits 发放即可（见文末备选段）。
--
-- 为什么它很强（数值视角）：
--   「食物 = 相邻加成」**没有固定上限**，圣地质量越高食物越多。这与固定 +N 食物
--   是两种完全不同的强度曲线：固定值线性、会被时代稀释；相邻型随选址放大。
--   因此 v4 已把核心固定食物从 +4 下调到 +1，把食物这条链路交还给本特性。
--
-- 同样的克隆策略：不重写效果，从 TraitModifiers 克隆原版挂的 Modifier。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. 自定义 Trait
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Types (Type, Kind) VALUES
  ('TRAIT_NHS_MONASTERIES_KING', 'KIND_TRAIT');

INSERT OR IGNORE INTO Traits (TraitType, Name, Description) VALUES
  ('TRAIT_NHS_MONASTERIES_KING',
   'LOC_TRAIT_NHS_MK_NAME',
   'LOC_TRAIT_NHS_MK_DESC');

-- ---------------------------------------------------------------------------
-- 2. 克隆原版 Modifier（带人类门槛）
--    只保留 4 个必要列，其余走表默认值。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId)
SELECT 'NHS_MK_' || m.ModifierId,
       m.ModifierType,
       'PLAYER_IS_HUMAN',
       m.SubjectRequirementSetId
FROM Modifiers m
JOIN TraitModifiers tm ON tm.ModifierId = m.ModifierId
WHERE tm.TraitType = 'TRAIT_LEADER_MONASTERIES_KING';

-- ---------------------------------------------------------------------------
-- 3. 克隆参数（只补克隆成功的）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value)
SELECT 'NHS_MK_' || a.ModifierId, a.Name, a.Value
FROM ModifierArguments a
WHERE EXISTS (
  SELECT 1 FROM Modifiers m WHERE m.ModifierId = 'NHS_MK_' || a.ModifierId
);

-- ---------------------------------------------------------------------------
-- 4. 挂到自定义 Trait
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId)
SELECT 'TRAIT_NHS_MONASTERIES_KING', m.ModifierId
FROM Modifiers m
WHERE m.ModifierId LIKE 'NHS_MK_%';

-- ---------------------------------------------------------------------------
-- 5. 只发给秦始皇（LEADER_QIN）
--    v7 起本 mod 是「秦始皇专属」。不再需要排除高棉——秦始皇身上
--    本来就没有阇耶跋摩七世的原版特性，不存在双份。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO LeaderTraits (LeaderType, TraitType) VALUES
  ('LEADER_QIN', 'TRAIT_NHS_MONASTERIES_KING');

-- ---------------------------------------------------------------------------
-- 备选发放方式（若上面第 5 段实机不生效，改用这段，注释掉第 5 段）
-- INSERT OR IGNORE INTO LeaderTraits (LeaderType, TraitType)
-- SELECT LeaderType, 'TRAIT_NHS_MONASTERIES_KING' FROM Leaders
-- WHERE LeaderType <> 'LEADER_JAYAVARMAN';
-- ---------------------------------------------------------------------------
