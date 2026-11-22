-- ============================================================================
-- 皇帝之威 · 驰道 (nhs_11_roads.sql)
--
-- 【v7.7】新增第七项特征「驰道」：新建城市立刻与首都连通道路。
--
-- 实现方式（克隆原版罗马的写法，不自己发明 Modifier）：
--   原版罗马「条条大路通罗马」= TRAIT_CIVILIZATION_ALL_ROADS_TO_ROME
--     → TraitModifiers: TRAIT_FREE_ROADS_TO_CAPITAL
--     → ModifierType: MODIFIER_PLAYER_CITIES_GRANT_ROAD_TO_CAPITAL
--     → EffectType:   EFFECT_GRANT_CITY_ROAD_TO_CAPITAL（Types 里注册为 KIND_EFFECT）
--   该 Modifier 无参数、无 RequirementSet。我们只做两件事：
--     ① 复制一个 ModifierId（NHS_ROAD_TO_CAPITAL），复用原版 ModifierType；
--     ② 挂到本 mod 第七个 trait 上，并加 PLAYER_IS_HUMAN 人类门槛。
--   不写 DynamicModifiers —— 原版已注册该 ModifierType，重复写会撞主键。
--
-- 效果口径：
--   城市建立（或被占领/获得）后，引擎会自动从该城向首都铺出道路，
--   与罗马特性完全一致。道路等级按原版规则随时代升级（远古土路→中世纪→
--   工业→现代），连接关系永久成立，单位移动与商队都吃这条路。
--
-- 与其它层的关系：
--   独立 trait、独立文件。不想要这条就删掉本文件在 modinfo 里的那一个动作，
--   其余六层不受影响。
-- ============================================================================

-- 1. 注册 trait 类型
INSERT INTO Types (Type, Kind) VALUES
  ('TRAIT_NHS_IMPERIAL_ROAD', 'KIND_TRAIT');

-- 2. Trait 本体（界面显示名与描述在 text/nhs_text.xml）
INSERT INTO Traits (TraitType, Name, Description) VALUES
  ('TRAIT_NHS_IMPERIAL_ROAD',
   'LOC_TRAIT_NHS_ROAD_NAME',
   'LOC_TRAIT_NHS_ROAD_DESC');

-- 3. 克隆罗马的 Modifier：复用原版 ModifierType，只换 Id 并加人类门槛
INSERT INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId) VALUES
  ('NHS_ROAD_TO_CAPITAL', 'MODIFIER_PLAYER_CITIES_GRANT_ROAD_TO_CAPITAL', 'PLAYER_IS_HUMAN');

-- 4. 挂到 trait
INSERT INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_IMPERIAL_ROAD', 'NHS_ROAD_TO_CAPITAL');

-- 5. 只发给秦始皇（与其余六层一致：走 LeaderTraits，不碰 CivilizationTraits）
INSERT OR IGNORE INTO LeaderTraits (LeaderType, TraitType) VALUES
  ('LEADER_QIN', 'TRAIT_NHS_IMPERIAL_ROAD');
