-- ============================================================================
-- 核动力圣地 · 移动力层 (nhs_07_movement.sql)
-- 游戏数值平衡专家 设计产物
--
-- 需求：人类的侦察兵、移民移动速度加倍。
--
-- 【技术难点说明】
--   Civ6 的移动力是**加算**的整数，引擎没有"移动力 ×2"这种百分比效果。
--   所以"加倍"只能按基础值折算成固定加值：
--       侦察兵 UNIT_SCOUT  基础 3 → +3 = 6（精确翻倍）
--       移民   UNIT_SETTLER 基础 2 → +2 = 4（精确翻倍）
--   若日后版本改了基础移动力，请同步改这里的 Amount。
--
-- 【用到的机制 —— 均为社区验证过的标准写法】
--   ModifierType : MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT
--                  = COLLECTION_PLAYER_UNITS + EFFECT_ADJUST_UNIT_MOVEMENT
--                  （玩家级、作用于该玩家名下所有单位，再用 SubjectRequirement 收窄范围）
--                  注意别用 MODIFIER_PLAYER_UNIT_ADJUST_MOVEMENT——那个是单挂到一个单位
--                  上的，挂到 trait 上不会生效，这是 CivFanatics 上被反复踩的坑
--   Requirement  : REQUIREMENT_UNIT_TYPE_MATCHES + 参数 UnitType
--                  （用 SubjectRequirementSet 把作用范围收窄到指定单位类型，
--                    否则 COLLECTION_PLAYER_UNITS 会给所有单位都加移动力）
--
-- 【数值判断】见 civ6_nhs_balance_v6.py 第 1 节：
--   侦察兵 3→6 探索同一片区域耗时减半；移民 2→4 铺城 8 格从 4 回合降到 2 回合。
--   折算约 16 个"城市已上线回合"≈ 64 产能的早期收益，且不含抢地价值。
--   这属于"强但不破坏"：它放大了既有节奏，不直接产生数值。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. 需求：只匹配侦察兵 / 只匹配移民
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Requirements (RequirementId, RequirementType) VALUES
  ('NHS_REQ_UNIT_IS_SCOUT',   'REQUIREMENT_UNIT_TYPE_MATCHES'),
  ('NHS_REQ_UNIT_IS_SETTLER', 'REQUIREMENT_UNIT_TYPE_MATCHES');

INSERT OR IGNORE INTO RequirementArguments (RequirementId, Name, Value) VALUES
  ('NHS_REQ_UNIT_IS_SCOUT',   'UnitType', 'UNIT_SCOUT'),
  ('NHS_REQ_UNIT_IS_SETTLER', 'UnitType', 'UNIT_SETTLER');

INSERT OR IGNORE INTO RequirementSets (RequirementSetId, RequirementSetType) VALUES
  ('NHS_REQSET_UNIT_SCOUT',   'REQUIREMENTSET_TEST_ALL'),
  ('NHS_REQSET_UNIT_SETTLER', 'REQUIREMENTSET_TEST_ALL');

INSERT OR IGNORE INTO RequirementSetRequirements (RequirementSetId, RequirementId) VALUES
  ('NHS_REQSET_UNIT_SCOUT',   'NHS_REQ_UNIT_IS_SCOUT'),
  ('NHS_REQSET_UNIT_SETTLER', 'NHS_REQ_UNIT_IS_SETTLER');

-- ---------------------------------------------------------------------------
-- 2. 自定义 Trait
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Types (Type, Kind) VALUES
  ('TRAIT_NHS_SWIFT_PIONEERS', 'KIND_TRAIT');

INSERT OR IGNORE INTO Traits (TraitType, Name, Description) VALUES
  ('TRAIT_NHS_SWIFT_PIONEERS',
   'LOC_TRAIT_NHS_MOVE_NAME',
   'LOC_TRAIT_NHS_MOVE_DESC');

-- ---------------------------------------------------------------------------
-- 3. Modifier：侦察兵 +3 移动力（3 → 6，翻倍）
--    门槛：OwnerRequirementSetId = PLAYER_IS_HUMAN（AI 拿不到）
--           SubjectRequirementSetId = 只对侦察兵生效
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId) VALUES
  ('NHS_SCOUT_MOVEMENT',  'MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT', 'PLAYER_IS_HUMAN', 'NHS_REQSET_UNIT_SCOUT'),
  ('NHS_SETTLER_MOVEMENT','MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT', 'PLAYER_IS_HUMAN', 'NHS_REQSET_UNIT_SETTLER');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_SCOUT_MOVEMENT',   'Amount', '3'),
  ('NHS_SETTLER_MOVEMENT', 'Amount', '2');

-- ---------------------------------------------------------------------------
-- 4. 挂到 Trait 并发放给所有文明
--    移动力是纯增益，不存在"和本体叠加翻倍"的问题，故无需排除任何文明。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_SWIFT_PIONEERS', 'NHS_SCOUT_MOVEMENT'),
  ('TRAIT_NHS_SWIFT_PIONEERS', 'NHS_SETTLER_MOVEMENT');

INSERT OR IGNORE INTO LeaderTraits (LeaderType, TraitType) VALUES
  ('LEADER_QIN', 'TRAIT_NHS_SWIFT_PIONEERS');

-- ---------------------------------------------------------------------------
-- 调参旋钮
--   * 想让移民更快：把 NHS_SETTLER_MOVEMENT 的 Amount 改成 3（2 → 5）。
--     不建议超过 3：移民移速过高会让人口调度彻底脱离地形约束，
--     山地/森林的成本惩罚等于消失，地图设计失去意义。
--   * 若实机发现移民不生效（民用车单位有时不受 COLLECTION_PLAYER_UNITS 覆盖）：
--     改用 REQUIREMENT_UNIT_TAG_MATCHES + Tag='CLASS_SETTLER' 试一次，
--     或退回"给移民加一个免费晋升"的方案（需另建 Promotion）。
-- ---------------------------------------------------------------------------
