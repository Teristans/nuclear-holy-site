-- ============================================================================
-- 皇帝之威 · 法令一统 (nhs_12_edicts.sql)
--
-- 【v7.8】新增第八项特征「法令一统」：自游戏开始即额外 +1 通配符政策槽。
--
-- 实现方式（克隆原版希腊的写法，不自己发明 Modifier）：
--   原版希腊「柏拉图理想国」= TRAIT_CIVILIZATION_PLATOS_REPUBLIC
--     → TraitModifiers: TRAIT_WILDCARD_GOVERNMENT_SLOT
--     → ModifierType: MODIFIER_PLAYER_CULTURE_ADJUST_GOVERNMENT_SLOTS_MODIFIER
--     → EffectType:   EFFECT_ADJUST_PLAYER_GOVERNMENT_SLOT_TYPE
--     → CollectionType: COLLECTION_OWNER（作用于玩家本人，天然不扩散到 AI）
--   该 Modifier 只吃一个参数 GovernmentSlotType=SLOT_WILDCARD，数量默认 1，
--   所以不需要 Amount（原版「紫禁城」也是这么写的）。
--   我们只做两件事：
--     ① 复制一个 ModifierId（NHS_WILDCARD_SLOT），复用原版 ModifierType；
--     ② 挂到本 mod 第八个 trait 上，并加 PLAYER_IS_HUMAN 人类门槛。
--   不写 DynamicModifiers —— 原版已注册该 ModifierType，重复写会撞主键。
--
-- 效果口径：
--   政策槽位来自 Effects 层而非政府表（Government_SlotCounts），因此不受
--   政府更替影响：换任何政体都多这一格。开局酋邦原本只有 1 军事 + 1 经济、
--   没有通配符，所以第一回合打开政府面板就能看见多出来的这一格。
--   注意：槽位与政策卡是两件事——槽位开局就有，可插哪些卡仍受已解锁
--   政策限制（这是原版规则，本层不绕过）。
--
-- 与其它层的关系：
--   独立 trait、独立文件。不想要这条就删掉本文件在 modinfo 里的那一个动作，
--   其余七层不受影响。
-- ============================================================================

-- 1. 注册 trait 类型
INSERT INTO Types (Type, Kind) VALUES
  ('TRAIT_NHS_EDICTS', 'KIND_TRAIT');

-- 2. Trait 本体（界面显示名与描述在 text/nhs_text.xml）
INSERT INTO Traits (TraitType, Name, Description) VALUES
  ('TRAIT_NHS_EDICTS',
   'LOC_TRAIT_NHS_EDICT_NAME',
   'LOC_TRAIT_NHS_EDICT_DESC');

-- 3. 克隆希腊的 Modifier：复用原版 ModifierType，只换 Id 并加人类门槛
INSERT INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId) VALUES
  ('NHS_WILDCARD_SLOT',
   'MODIFIER_PLAYER_CULTURE_ADJUST_GOVERNMENT_SLOTS_MODIFIER',
   'PLAYER_IS_HUMAN');

-- 4. 参数：只要通配符这一类，数量取该 Effect 的默认值 1
INSERT INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_WILDCARD_SLOT', 'GovernmentSlotType', 'SLOT_WILDCARD');

-- 5. 挂到 trait
INSERT INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_EDICTS', 'NHS_WILDCARD_SLOT');

-- 6. 只发给秦始皇（与其余七层一致：走 LeaderTraits，不碰 CivilizationTraits）
INSERT OR IGNORE INTO LeaderTraits (LeaderType, TraitType) VALUES
  ('LEADER_QIN', 'TRAIT_NHS_EDICTS');
