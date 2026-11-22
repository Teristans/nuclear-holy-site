-- ============================================================================
-- 皇帝之威 · 特色单位 (nhs_14_units.sql)
--
-- 【v7.16】开局勇士 → 「锐士」，侦察兵 → 「斥候」，均为秦始皇专属特色单位。
--
-- 为什么能用数据层做到，而不必写 Lua：
--   原版阿兹特克开局拿的是鹰武士（UNIT_AZTEC_EAGLE_WARRIOR）而不是勇士，
--   但 MajorStartingUnits 里根本没有鹰武士这一行，只有 UNIT_WARRIOR。
--   说明引擎在发放起始单位时，会检查该玩家的 UnitReplaces：
--   若存在替换此单位的特色单位，则直接发特色单位。
--   盖尔枪兵（UNIT_GAUL_GAESATAE replaces UNIT_WARRIOR）、克里斥候
--   （UNIT_CREE_OKIHTCITAW replaces UNIT_SCOUT）同理。
--   所以本文件只需建单位 + 建替代关系，开局与生产列表会一起生效。
--
-- 做法：整行克隆原型（Units 67 列逐列照抄，只换 UnitType/Name/Description/TraitType），
--   不手写数值，避免漏字段或写错列。数值与原型完全一致（勇士 20、侦察兵 10），
--   差别只在名号与归属，以及替代关系。
--
-- TraitType 挂 TRAIT_NHS_NUCLEAR_HOLY_SITE（天命玄鸟）——该 trait 已由
--   LeaderTraits 只发给 LEADER_QIN，所以这两件单位只有秦始皇能训练。
--   刻意不新建 trait：新建会打破「八威仪」的既有结构。
--
-- 执行顺序要求：本文件必须在 nhs_07_movement.sql 之后。
--   斥候是克隆当时的 UNIT_SCOUT 行，而 nhs_07 把侦察兵移动改成 6；
--   modinfo 里 NHS_DB_UNITS 排在 NHS_DB_MOVEMENT 之后，故斥候自动继承 6 移动。
--   （若哪天调序，斥候会退回 3 移动，run_mod_sql.py 有断言拦这个。）
--
-- 文案：LOC_UNIT_NHS_RUISHI_NAME / _DESCRIPTION、LOC_UNIT_NHS_SCOUT_NAME / _DESCRIPTION
--       定义在 ../text/nhs_text.xml（中英各一份）。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. 注册类型（Units 的 UnitType 外键指向 Types.Type，必须先插这里）
-- ---------------------------------------------------------------------------
INSERT OR REPLACE INTO Types (Type, Kind) VALUES
  ('UNIT_NHS_RUISHI', 'KIND_UNIT'),
  ('UNIT_NHS_SCOUT',  'KIND_UNIT');

-- ---------------------------------------------------------------------------
-- 2. 克隆单位本体
-- ---------------------------------------------------------------------------
INSERT OR REPLACE INTO Units (
  "UnitType",
  "Name",
  "BaseSightRange",
  "BaseMoves",
  "Combat",
  "RangedCombat",
  "Range",
  "Bombard",
  "Domain",
  "FormationClass",
  "Cost",
  "PopulationCost",
  "FoundCity",
  "FoundReligion",
  "MakeTradeRoute",
  "EvangelizeBelief",
  "LaunchInquisition",
  "RequiresInquisition",
  "BuildCharges",
  "ReligiousStrength",
  "ReligionEvictPercent",
  "SpreadCharges",
  "ReligiousHealCharges",
  "ExtractsArtifacts",
  "Description",
  "Flavor",
  "CanCapture",
  "CanRetreatWhenCaptured",
  "TraitType",
  "AllowBarbarians",
  "CostProgressionModel",
  "CostProgressionParam1",
  "PromotionClass",
  "InitialLevel",
  "NumRandomChoices",
  "PrereqTech",
  "PrereqCivic",
  "PrereqDistrict",
  "PrereqPopulation",
  "LeaderType",
  "CanTrain",
  "StrategicResource",
  "PurchaseYield",
  "MustPurchase",
  "Maintenance",
  "Stackable",
  "AirSlots",
  "CanTargetAir",
  "PseudoYieldType",
  "ZoneOfControl",
  "AntiAirCombat",
  "Spy",
  "WMDCapable",
  "ParkCharges",
  "IgnoreMoves",
  "TeamVisibility",
  "ObsoleteTech",
  "ObsoleteCivic",
  "MandatoryObsoleteTech",
  "MandatoryObsoleteCivic",
  "AdvisorType",
  "EnabledByReligion",
  "TrackReligion",
  "DisasterCharges",
  "UseMaxMeleeTrainedStrength",
  "ImmediatelyName",
  "CanEarnExperience"
)
SELECT
    'UNIT_NHS_RUISHI', 'LOC_UNIT_NHS_RUISHI_NAME', "BaseSightRange", "BaseMoves",
    "Combat", "RangedCombat", "Range", "Bombard",
    "Domain", "FormationClass", "Cost", "PopulationCost",
    "FoundCity", "FoundReligion", "MakeTradeRoute", "EvangelizeBelief",
    "LaunchInquisition", "RequiresInquisition", "BuildCharges", "ReligiousStrength",
    "ReligionEvictPercent", "SpreadCharges", "ReligiousHealCharges", "ExtractsArtifacts",
    'LOC_UNIT_NHS_RUISHI_DESCRIPTION', "Flavor", "CanCapture", "CanRetreatWhenCaptured",
    'TRAIT_NHS_NUCLEAR_HOLY_SITE', "AllowBarbarians", "CostProgressionModel", "CostProgressionParam1",
    "PromotionClass", "InitialLevel", "NumRandomChoices", "PrereqTech",
    "PrereqCivic", "PrereqDistrict", "PrereqPopulation", "LeaderType",
    "CanTrain", "StrategicResource", "PurchaseYield", "MustPurchase",
    "Maintenance", "Stackable", "AirSlots", "CanTargetAir",
    "PseudoYieldType", "ZoneOfControl", "AntiAirCombat", "Spy",
    "WMDCapable", "ParkCharges", "IgnoreMoves", "TeamVisibility",
    "ObsoleteTech", "ObsoleteCivic", "MandatoryObsoleteTech", "MandatoryObsoleteCivic",
    "AdvisorType", "EnabledByReligion", "TrackReligion", "DisasterCharges",
    "UseMaxMeleeTrainedStrength", "ImmediatelyName", "CanEarnExperience"
FROM Units WHERE UnitType='UNIT_WARRIOR';

INSERT OR REPLACE INTO Units (
  "UnitType",
  "Name",
  "BaseSightRange",
  "BaseMoves",
  "Combat",
  "RangedCombat",
  "Range",
  "Bombard",
  "Domain",
  "FormationClass",
  "Cost",
  "PopulationCost",
  "FoundCity",
  "FoundReligion",
  "MakeTradeRoute",
  "EvangelizeBelief",
  "LaunchInquisition",
  "RequiresInquisition",
  "BuildCharges",
  "ReligiousStrength",
  "ReligionEvictPercent",
  "SpreadCharges",
  "ReligiousHealCharges",
  "ExtractsArtifacts",
  "Description",
  "Flavor",
  "CanCapture",
  "CanRetreatWhenCaptured",
  "TraitType",
  "AllowBarbarians",
  "CostProgressionModel",
  "CostProgressionParam1",
  "PromotionClass",
  "InitialLevel",
  "NumRandomChoices",
  "PrereqTech",
  "PrereqCivic",
  "PrereqDistrict",
  "PrereqPopulation",
  "LeaderType",
  "CanTrain",
  "StrategicResource",
  "PurchaseYield",
  "MustPurchase",
  "Maintenance",
  "Stackable",
  "AirSlots",
  "CanTargetAir",
  "PseudoYieldType",
  "ZoneOfControl",
  "AntiAirCombat",
  "Spy",
  "WMDCapable",
  "ParkCharges",
  "IgnoreMoves",
  "TeamVisibility",
  "ObsoleteTech",
  "ObsoleteCivic",
  "MandatoryObsoleteTech",
  "MandatoryObsoleteCivic",
  "AdvisorType",
  "EnabledByReligion",
  "TrackReligion",
  "DisasterCharges",
  "UseMaxMeleeTrainedStrength",
  "ImmediatelyName",
  "CanEarnExperience"
)
SELECT
    'UNIT_NHS_SCOUT', 'LOC_UNIT_NHS_SCOUT_NAME', "BaseSightRange", "BaseMoves",
    "Combat", "RangedCombat", "Range", "Bombard",
    "Domain", "FormationClass", "Cost", "PopulationCost",
    "FoundCity", "FoundReligion", "MakeTradeRoute", "EvangelizeBelief",
    "LaunchInquisition", "RequiresInquisition", "BuildCharges", "ReligiousStrength",
    "ReligionEvictPercent", "SpreadCharges", "ReligiousHealCharges", "ExtractsArtifacts",
    'LOC_UNIT_NHS_SCOUT_DESCRIPTION', "Flavor", "CanCapture", "CanRetreatWhenCaptured",
    'TRAIT_NHS_NUCLEAR_HOLY_SITE', "AllowBarbarians", "CostProgressionModel", "CostProgressionParam1",
    "PromotionClass", "InitialLevel", "NumRandomChoices", "PrereqTech",
    "PrereqCivic", "PrereqDistrict", "PrereqPopulation", "LeaderType",
    "CanTrain", "StrategicResource", "PurchaseYield", "MustPurchase",
    "Maintenance", "Stackable", "AirSlots", "CanTargetAir",
    "PseudoYieldType", "ZoneOfControl", "AntiAirCombat", "Spy",
    "WMDCapable", "ParkCharges", "IgnoreMoves", "TeamVisibility",
    "ObsoleteTech", "ObsoleteCivic", "MandatoryObsoleteTech", "MandatoryObsoleteCivic",
    "AdvisorType", "EnabledByReligion", "TrackReligion", "DisasterCharges",
    "UseMaxMeleeTrainedStrength", "ImmediatelyName", "CanEarnExperience"
FROM Units WHERE UnitType='UNIT_SCOUT';

-- ---------------------------------------------------------------------------
-- 3. AI 标签（不克隆会让 AI 不会用这两个单位；同时驱动生产列表分类）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO UnitAiInfos (UnitType, AiType)
SELECT 'UNIT_NHS_RUISHI', AiType FROM UnitAiInfos WHERE UnitType='UNIT_WARRIOR';

INSERT OR IGNORE INTO UnitAiInfos (UnitType, AiType)
SELECT 'UNIT_NHS_SCOUT', AiType FROM UnitAiInfos WHERE UnitType='UNIT_SCOUT';

-- ---------------------------------------------------------------------------
-- 4. 升级链（锐士 → 剑士，斥候 → 游骑兵，与原单位一致）
-- ---------------------------------------------------------------------------
INSERT OR REPLACE INTO UnitUpgrades (Unit, UpgradeUnit)
SELECT 'UNIT_NHS_RUISHI', UpgradeUnit FROM UnitUpgrades WHERE Unit='UNIT_WARRIOR';

INSERT OR REPLACE INTO UnitUpgrades (Unit, UpgradeUnit)
SELECT 'UNIT_NHS_SCOUT', UpgradeUnit FROM UnitUpgrades WHERE Unit='UNIT_SCOUT';

-- ---------------------------------------------------------------------------
-- 5. 替代关系（UnitReplaces 的列名是 CivUniqueUnitType，不是 UnitType）
--    有了替代关系：秦始皇造不出普通勇士/侦察兵，只会看到锐士/斥候；
--    开局赠送的勇士/侦察兵也会被引擎换成这两个。
-- ---------------------------------------------------------------------------
INSERT OR REPLACE INTO UnitReplaces (CivUniqueUnitType, ReplacesUnitType) VALUES
  ('UNIT_NHS_RUISHI', 'UNIT_WARRIOR'),
  ('UNIT_NHS_SCOUT',  'UNIT_SCOUT');

-- ---------------------------------------------------------------------------
-- 6. 斥候的移动力（关键：不能只靠克隆）
--    nhs_07 的「侦察兵 3→6」不是改 Units.BaseMoves，而是加了一个 Modifier：
--      NHS_SCOUT_MOVEMENT（MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT，Amount 3）
--      用 Requirement 限定 UnitType='UNIT_SCOUT'
--    斥候是另一个 UnitType（UNIT_NHS_SCOUT），匹配不到那条门槛，
--    所以克隆出来的斥候 BaseMoves 仍是 3，必须单独给一份修饰，否则是 3 而不是 6。
--    这里复制同样的机制，只换 UnitType 与挂载点（同一个 trait 筚路蓝缕）。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Requirements (RequirementId, RequirementType) VALUES
  ('NHS_REQ_UNIT_IS_NHS_SCOUT', 'REQUIREMENT_UNIT_TYPE_MATCHES');

INSERT OR IGNORE INTO RequirementArguments (RequirementId, Name, Value) VALUES
  ('NHS_REQ_UNIT_IS_NHS_SCOUT', 'UnitType', 'UNIT_NHS_SCOUT');

INSERT OR IGNORE INTO RequirementSets (RequirementSetId, RequirementSetType) VALUES
  ('NHS_REQSET_UNIT_NHS_SCOUT', 'REQUIREMENTSET_TEST_ALL');

INSERT OR IGNORE INTO RequirementSetRequirements (RequirementSetId, RequirementId) VALUES
  ('NHS_REQSET_UNIT_NHS_SCOUT', 'NHS_REQ_UNIT_IS_NHS_SCOUT');

INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId) VALUES
  ('NHS_UNIQUE_SCOUT_MOVEMENT', 'MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT',
   'PLAYER_IS_HUMAN', 'NHS_REQSET_UNIT_NHS_SCOUT');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_UNIQUE_SCOUT_MOVEMENT', 'Amount', '3');

INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_SWIFT_PIONEERS', 'NHS_UNIQUE_SCOUT_MOVEMENT');

-- ---------------------------------------------------------------------------
-- 7. 单位分类标签（v7.20）
--
--    TypeTags 决定「引擎眼里这单位算哪一类」，是原版特征里最容易漏的一层。
--    原版实况（DebugGameplay.sqlite 逐行核对）：
--      UNIT_WARRIOR → CLASS_MELEE
--      UNIT_SCOUT   → CLASS_RECON、CLASS_REVEAL_STEALTH
--
--    漏了会怎样（全是静默失效，不报错、日志干净）：
--      · 锐士不算近战单位 → 一切按 CLASS_MELEE 判定的政策卡与加成全部落空；
--        生产列表分类掉进「其他」；AI 的兵种配比评估也认不出它。
--      · 斥候不算侦察单位 → 侦察类政策失效；CLASS_REVEAL_STEALTH 正是
--        「在视野内看得见隐形单位」的依据，缺了斥候就看不见隐形。
--
--    做法同其余各层：照抄原型行（INSERT ... SELECT），原版将来增删标签自动跟随。
--    TypeTags 主键是 (Type, Tag)，OR IGNORE 保证重复加载幂等。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO TypeTags (Type, Tag)
SELECT 'UNIT_NHS_RUISHI', Tag FROM TypeTags WHERE Type='UNIT_WARRIOR';

INSERT OR IGNORE INTO TypeTags (Type, Tag)
SELECT 'UNIT_NHS_SCOUT', Tag FROM TypeTags WHERE Type='UNIT_SCOUT';

-- ---------------------------------------------------------------------------
-- 7.2 锐士的额外特性：击败敌方战斗单位，有几率俘获为建造者（v7.21）
--
--     这不是勇士的特征，是用户点名要的**加强项**，所以和上面「照抄原型」分开写，
--     一眼能看出哪条是原版等身、哪条是本 mod 添的。
--
--     机制与原版鹰武士完全相同，纯数据、不新增任何数值：
--       单位 TypeTags 带 CLASS_CAPTURE_WORKER
--         → 引擎按 Tag 把 ABILITY_CAPTIVE_WORKERS 授给该单位
--         → 该能力经 UnitAbilityModifiers 挂 CAPTURE_COMBAT_UNITS_AS_WORKERS
--         → MODIFIER_UNIT_ADJUST_COMBAT_UNIT_CAPTURE，
--            参数 CanCapture=1 / UnitType=UNIT_BUILDER
--
--     关键：Tags 表里 CLASS_CAPTURE_WORKER 的 Vocabulary 是 ABILITY_CLASS，
--     即「能力类别」。单位认领同名 Tag 就自动获得对应能力，
--     所以这里只要一行标签，不必自建能力、不必写 modifier。
--     官方描述：Can capture defeated enemy civilization combat units and convert
--     them to Builders.（具体几率由引擎判定，该 modifier 没有 Amount 参数）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO TypeTags (Type, Tag) VALUES
  ('UNIT_NHS_RUISHI', 'CLASS_CAPTURE_WORKER');
