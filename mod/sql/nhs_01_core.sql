-- ============================================================================
-- 核动力圣地 · 核心层 (nhs_01_core.sql)
-- 游戏数值平衡专家 设计产物
--
-- 【v7：本 mod 已改为「秦始皇专属」】
--   全部 6 层 trait 通过 LeaderTraits 只挂到 LEADER_QIN，不再发给所有文明。
--   原因：nhs_09 改的 UnitCommands 是全局表，加了人类门槛也挡不住 AI 秦始皇；
--   而"人类玩秦始皇"时 AI 不可能是秦始皇，泄漏才真正归零。
--   代价：玩别的文明时本 mod 一层都不生效（刻意的）。
--
-- 设计口径（产出曲线来自 civ6_nhs_balance_v5.py）：
--   * 人类门槛：所有 Modifier 的 OwnerRequirementSetId = PLAYER_IS_HUMAN
--     （PLAYER_IS_HUMAN 已在游戏本体 Leaders.xml:5444 核实存在，
--       原版自己就把它用作野蛮人营地金币 modifier 的 OwnerRequirementSetId）
--   * 固定产出（城市有圣地才生效）：
--       产能 +0 / 食物 +1 / 信仰 +2 / 文化 +1 / 住房 +2
--   * v14 追加：首都每回合 +1 信仰（只加首都，不随城市数增长，
--     用原版 COLLECTION_PLAYER_CAPITAL_CITY 收集器，见第 4b 节）
--   * v5 变更：产能 5→0、信仰 3→2。因为 nhs_06 加入「职业道德」（相邻→产能）
--     和「经文」（相邻翻倍），产能引擎已经由相邻值驱动，再叠固定 +5 会直接超模。
--     现在固定层只保留食物/文化/住房与 +0 产能旋钮（想加回来自行调 Amount）。
--     依据：v5 模型 A 方案 新手产能 1.56/1.02/0.65，熟练 1.72/1.20/0.81
--   * 已知局限：固定加成不随时代增长，后期必然被神级 AI 稀释（见 README 数值曲线）。
--     后期强度请靠原版「职业道德+经文」，或用 nhs_02 的可选缩放层。
--
-- 数值来源与假设见 ../README.md 与 ../VERIFICATION.md
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. 自定义 Trait：挂载所有加成
-- ---------------------------------------------------------------------------
INSERT INTO Types (Type, Kind) VALUES
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'KIND_TRAIT');

-- 【v7.3 修复】自定义 DynamicModifier 的 ModifierType 必须先在 Types 表注册为
-- KIND_MODIFIER，否则游戏构建数据库时外键校验失败 → 整个 mod 加载失败弹窗。
-- 离线验证库没建这个外键，所以之前 34 条断言全绿却在实机报错。
-- 依据：官方 Modifiers.xml 里 MODIFIER_PLAYER_CITIES_ADJUST_POLICY_HOUSING 等
-- 全都先在 <Types> 段注册 Kind="KIND_MODIFIER"。
INSERT OR IGNORE INTO Types (Type, Kind) VALUES
  ('NHS_MOD_CITY_YIELD',   'KIND_MODIFIER'),
  ('NHS_MOD_CITY_HOUSING', 'KIND_MODIFIER');

INSERT INTO Traits (TraitType, Name, Description) VALUES
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE',
   'LOC_TRAIT_NHS_NAME',
   'LOC_TRAIT_NHS_DESC');

-- 【v7 重大变更：本 mod 从此是「秦始皇专属」】
--   原来用 CivilizationTraits 发给所有文明，靠 PLAYER_IS_HUMAN 挡 AI。
--   但那留下一个漏洞：nhs_09 改的 UnitCommands 是全局表，挡不住 AI 秦始皇。
--   现在改成只挂到 LEADER_QIN（秦始皇）身上：
--     · 人类玩秦始皇 → AI 不可能是秦始皇（同一领袖默认唯一）→ 全 mod 零泄漏
--     · 人类玩别的文明 → 一层都拿不到，mod 完全无效（这是刻意的，不是 bug）
--   PLAYER_IS_HUMAN 门槛依然保留：多人局里若有另一个玩家也选秦始皇，
--   那份 trait 仍然不会给他效力。
--
--   注：忽必烈（LEADER_KUBLAI_KHAN）也能领导中国，但他不是秦始皇，
--   拿不到本 mod。如果你想让忽必烈也吃，把下面的 LEADER_QIN 换成 LEADER_KUBLAI_KHAN
--   或加一行即可。
INSERT OR IGNORE INTO LeaderTraits (LeaderType, TraitType) VALUES
  ('LEADER_QIN', 'TRAIT_NHS_NUCLEAR_HOLY_SITE');

-- ---------------------------------------------------------------------------
-- 2. Requirement：判断"城市拥有圣地"
--    REQUIREMENT_CITY_HAS_DISTRICT 是标准 Requirement；DistrictType 为其参数。
-- ---------------------------------------------------------------------------
INSERT INTO Requirements (RequirementId, RequirementType) VALUES
  ('NHS_REQ_CITY_HAS_HOLY_SITE', 'REQUIREMENT_CITY_HAS_DISTRICT');

INSERT INTO RequirementArguments (RequirementId, Name, Value) VALUES
  ('NHS_REQ_CITY_HAS_HOLY_SITE', 'DistrictType', 'DISTRICT_HOLY_SITE');

INSERT INTO RequirementSets (RequirementSetId, RequirementSetType) VALUES
  ('NHS_REQSET_CITY_HAS_HOLY_SITE', 'REQUIREMENTSET_TEST_ALL');

INSERT INTO RequirementSetRequirements (RequirementSetId, RequirementId) VALUES
  ('NHS_REQSET_CITY_HAS_HOLY_SITE', 'NHS_REQ_CITY_HAS_HOLY_SITE');

-- ---------------------------------------------------------------------------
-- 3. DynamicModifiers（标准 Effect + Collection 组合）
-- ---------------------------------------------------------------------------
-- 【v7.3 修复】EFFECT_ADJUST_HOUSING 在本版本不存在（Types 表里查无此行）；
-- 官方城市固定住房用的是 EFFECT_ADJUST_POLICY_HOUSING，参数同为 Amount。
-- 依据：MODIFIER_PLAYER_CITIES_ADJUST_POLICY_HOUSING = COLLECTION_PLAYER_CITIES
--       + EFFECT_ADJUST_POLICY_HOUSING，原版君主政体城墙 +1 住房即此组合。
INSERT OR IGNORE INTO DynamicModifiers (ModifierType, CollectionType, EffectType) VALUES
  ('NHS_MOD_CITY_YIELD',   'COLLECTION_PLAYER_CITIES', 'EFFECT_ADJUST_CITY_YIELD_CHANGE'),
  ('NHS_MOD_CITY_HOUSING', 'COLLECTION_PLAYER_CITIES', 'EFFECT_ADJUST_POLICY_HOUSING');

-- ---------------------------------------------------------------------------
-- 4. Modifiers：人类限定 + 城市有圣地才生效
-- ---------------------------------------------------------------------------
-- 产能 +0（v5：产能引擎已交给「职业道德」，此项仅作调参旋钮）
INSERT INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId) VALUES
  ('NHS_CITY_PROD',  'NHS_MOD_CITY_YIELD',   'PLAYER_IS_HUMAN', 'NHS_REQSET_CITY_HAS_HOLY_SITE');
INSERT INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_CITY_PROD', 'YieldType', 'YIELD_PRODUCTION'),
  ('NHS_CITY_PROD', 'Amount', '0');

-- 食物 +1（v4 下调：食物改由「国王的修道院」按相邻加成发放）
--   v3 说明：苔原城每时代有约 -0.5×苔原格 的食物拖累（平地苔原不能造农场），
--   中古约 -3。若食物只给 +3，苔原城净收益为 0，"高棉供养"名存实亡。
--   给 +4 后：苔原城净 +1，非苔原城 +4。
INSERT INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId) VALUES
  ('NHS_CITY_FOOD',  'NHS_MOD_CITY_YIELD',   'PLAYER_IS_HUMAN', 'NHS_REQSET_CITY_HAS_HOLY_SITE');
INSERT INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_CITY_FOOD', 'YieldType', 'YIELD_FOOD'),
  ('NHS_CITY_FOOD', 'Amount', '1');

-- 信仰 +2（v5 下调：相邻翻倍后信仰已严重溢出）
INSERT INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId) VALUES
  ('NHS_CITY_FAITH', 'NHS_MOD_CITY_YIELD',   'PLAYER_IS_HUMAN', 'NHS_REQSET_CITY_HAS_HOLY_SITE');
INSERT INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_CITY_FAITH', 'YieldType', 'YIELD_FAITH'),
  ('NHS_CITY_FAITH', 'Amount', '2');

-- 文化 +1（折算高棉人口文化红利，保持克制）
INSERT INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId) VALUES
  ('NHS_CITY_CULTURE', 'NHS_MOD_CITY_YIELD', 'PLAYER_IS_HUMAN', 'NHS_REQSET_CITY_HAS_HOLY_SITE');
INSERT INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_CITY_CULTURE', 'YieldType', 'YIELD_CULTURE'),
  ('NHS_CITY_CULTURE', 'Amount', '1');

-- 住房 +2（高棉特征）
INSERT INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId) VALUES
  ('NHS_CITY_HOUSING', 'NHS_MOD_CITY_HOUSING', 'PLAYER_IS_HUMAN', 'NHS_REQSET_CITY_HAS_HOLY_SITE');
INSERT INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_CITY_HOUSING', 'Amount', '2');

-- ---------------------------------------------------------------------------
-- 4b. 首都每回合 +1 信仰（v14）
--   不新建 ModifierType：原版已有 MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE
--   = COLLECTION_PLAYER_CAPITAL_CITY + EFFECT_ADJUST_CITY_YIELD_CHANGE，
--   收集器本身就只指向首都，因此**不需要**再挂 SubjectRequirement（挂了反而收不窄）。
--   依据（均为原版同写法）：
--     · 政体「专制」遗产 AUTOCRACY_FAITH      Amount=1, YieldType=YIELD_FAITH
--     · 城邦宗教宗主 MINOR_CIV_RELIGIOUS_YIELD_FOR_CAPITAL  Amount=2, 同 YieldType
--     · 城邦科技宗主 MINOR_CIV_SCIENTIFIC_YIELD_FOR_CAPITAL 同结构
--   这是"保底"设计：只加首都、不随城市数增长，避免与核心层「有圣地 +2 信仰」重复放大。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId) VALUES
  ('NHS_CAPITAL_FAITH', 'MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE', 'PLAYER_IS_HUMAN');
INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_CAPITAL_FAITH', 'YieldType', 'YIELD_FAITH'),
  ('NHS_CAPITAL_FAITH', 'Amount', '1');

-- ---------------------------------------------------------------------------
-- 4c. 农场 → 圣地 +1 信仰（v24）
--   不要自创 ModifierType：原版已有成例，拜占庭狄奥多拉就有一条一模一样的
--     THEODORA_HOLY_SITE_ADJACENCY_FARM
--       ModifierType = MODIFIER_PLAYER_CITIES_IMPROVEMENT_ADJACENCY
--       Amount=1 / DistrictType=DISTRICT_HOLY_SITE / ImprovementType=IMPROVEMENT_FARM
--       YieldType=YIELD_FAITH / Description=LOC_DISTRICT_FARM_1_FAITH
--   本行与之逐项相同，只把 Description 换成本 mod 自己的 tag（原版那个 tag
--   在 DebugLocalization 里查不到对应文本，会显示裸 tag）。
--
--   为什么用 PLAYER_CITIES 而不是 ALL_CITIES：
--     · MODIFIER_PLAYER_CITIES_IMPROVEMENT_ADJACENCY = COLLECTION_PLAYER_CITIES
--       + EFFECT_IMPROVEMENT_ADJACENCY，收集器天生只收「修饰器拥有者的城市」，
--       因此不需要再挂任何 SubjectRequirement 就能收窄。
--     · 若改用 COLLECTION_ALL_CITIES 又不加门槛，原版库里 35 条同类用法**全部**
--       都挂了 SubjectRequirement（如极光之舞的 CITY_FOLLOWS_PANTHEON），
--       不带门槛极可能把加成发给 AI 城市。宁可绕开这个不确定性。
--   生效范围：仅人类玩家 + 仅秦始皇（trait 挂在 LEADER_QIN 上，OwnerRequirementSet 拦 AI）。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId) VALUES
  ('NHS_HOLY_SITE_FARM_FAITH', 'MODIFIER_PLAYER_CITIES_IMPROVEMENT_ADJACENCY', 'PLAYER_IS_HUMAN', NULL);

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_HOLY_SITE_FARM_FAITH', 'Amount',          '1'),
  ('NHS_HOLY_SITE_FARM_FAITH', 'DistrictType',    'DISTRICT_HOLY_SITE'),
  ('NHS_HOLY_SITE_FARM_FAITH', 'ImprovementType', 'IMPROVEMENT_FARM'),
  ('NHS_HOLY_SITE_FARM_FAITH', 'TilesRequired',   '1'),
  ('NHS_HOLY_SITE_FARM_FAITH', 'YieldType',       'YIELD_FAITH'),
  ('NHS_HOLY_SITE_FARM_FAITH', 'Description',     'LOC_NHS_DISTRICT_FARM_FAITH');

-- ---------------------------------------------------------------------------
-- 5. 把 Modifier 挂到 Trait
-- ---------------------------------------------------------------------------
INSERT INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_CITY_PROD'),
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_CITY_FOOD'),
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_CITY_FAITH'),
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_CITY_CULTURE'),
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_CITY_HOUSING'),
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_CAPITAL_FAITH'),
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_HOLY_SITE_FARM_FAITH');
