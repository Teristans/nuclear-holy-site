-- ============================================================================
-- 皇帝之威 · 宜居度层 (nhs_13_amenities.sql)
--
-- 需求：实机反馈宜居度严重不足。
--   根因不在宜居度本身，而在本 mod 的引擎逻辑：圣地城 +1 食物、+2 住房，
--   叠上「勤则不匮」把相邻信仰转成产能、极光之舞 +1 信仰/冻土相邻，
--   城市人口长得比原版快得多，而宜居度的供给端（奢侈品、娱乐区）没变。
--   Civ6 的宜居度需求随人口走（每 2 人口 1 点），人口越快越缺——这是设计的
--   必然结果，不是 bug。
--
-- 所以这一层是「补上人口加速带来的缺口」，不是白送：
--   ① 所有城市 +1 宜居度（底线，覆盖新城/刚征服尚未建圣地的城）
--   ② 每座圣地再 +1 宜居度（主题奖励，与「天命玄鸟」的圣地叙事一致）
--   一座有圣地的城合计 +2；没有圣地的城只有 +1。
--
-- ★ v34 追加第三组（第 4 节）：城市数阶梯 5/9/13 座城各 +1。
--   实机反馈「中后期宜居逐渐紧缺」，查下来主因不是人口（上面 ①② 已补），
--   而是原版两条硬扣：城市数惩罚（每约 2 城全城 −1）＋ 奢侈品只供应 4 座城
--   （第 5 座城起完全断供）。这两条随城市数恶化，固定 +2 越往后越不够，
--   所以第 4 节按城市数加码，4 城以内不触发，前期曲线保持不变。
--
-- 【机制出处 —— 均取自 db/gameplay_verify.sqlite，非臆造】
--   ① MODIFIER_PLAYER_CITIES_ADJUST_POLICY_AMENITY
--      → DynamicModifiers: EFFECT_ADJUST_POLICY_AMENITY / COLLECTION_PLAYER_CITIES
--      → 原版用例 GOVERNMENT_DIGITAL_DEMOCRACY 的 DIGITAL_DEMOCRACY_CITY_AMENITIES
--        （Amount=2，无任何 Requirement，就是"所有城市 +2 宜居度"）
--      参数只有 Amount（同 POLICY_RETAINERS 的写法）。
--   ② MODIFIER_CITY_DISTRICTS_ADJUST_DISTRICT_AMENITY
--      → DynamicModifiers: EFFECT_ADJUST_DISTRICT_AMENITY / COLLECTION_CITY_DISTRICTS
--      → 原版用例信条「河神」RIVER_GODDESS_HOLY_SITE_AMENITIES_MODIFIER
--        （Amount=2，SubjectRequirementSet = PLOT_HAS_HOLY_SITE_RIVER_REQUIREMENTS）
--      我们只保留「区域是圣地」这个条件、去掉「靠河」，因为靠河的条件已由
--      「江河淮济」层的相邻加成承担，宜居度不该再绑河流。
--   ③ SubjectRequirementSet 直接复用原版 DISTRICT_IS_HOLY_SITE
--      （REQUIREMENT_DISTRICT_TYPE_MATCHES + DistrictType = DISTRICT_HOLY_SITE）
--      先例：DIVINE_SPARK_HOLY_SITE_MODIFIER 同样是 COLLECTION_CITY_DISTRICTS +
--      该门槛，说明这个 reqset 在区域收集器下可用。故本层不新建 Requirement。
--
-- 【数值判断】
--   +2 相当于在每座有圣地的城里白送一座竞技场（库里 Arena 的 Entertainment = 2，
--   已核对 db/gameplay_verify.sqlite；娱乐区本身另 +1）。
--   本 mod 已有八项加成，宜居度只是把"人口长得太快"的副作用抹平，不新增节奏优势；
--   再高（如 +3/+4）会让人口/宜居度曲线彻底失效，打仗的战争疲劳也不再有代价。
--   v34 的阶梯补到顶是 +5（2 + 3），但那是 13 座城之后才到，且此时原版硬扣已 −6。
--   调参旋钮见文件末尾。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. 所有城市 +1 宜居度（底线）
--    门槛：OwnerRequirementSetId = PLAYER_IS_HUMAN（AI 拿不到）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId) VALUES
  ('NHS_CITY_AMENITY', 'MODIFIER_PLAYER_CITIES_ADJUST_POLICY_AMENITY', 'PLAYER_IS_HUMAN');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_CITY_AMENITY', 'Amount', '1');

-- ---------------------------------------------------------------------------
-- 2. 每座圣地 +1 宜居度
--    SubjectRequirementSetId 用原版 DISTRICT_IS_HOLY_SITE，只对圣地生效
--    （若留空，COLLECTION_CITY_DISTRICTS 会让每个区域都加宜居度，直接失控）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId, SubjectRequirementSetId) VALUES
  ('NHS_HOLY_SITE_AMENITY', 'MODIFIER_CITY_DISTRICTS_ADJUST_DISTRICT_AMENITY',
   'PLAYER_IS_HUMAN', 'DISTRICT_IS_HOLY_SITE');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_HOLY_SITE_AMENITY', 'Amount', '1');

-- ---------------------------------------------------------------------------
-- 3. 挂到核心特性「天命玄鸟」
--    宜居度与圣地同源：圣地是祭祀安民之所，加在核心层比新开第 9 条特性更自然
--    （八项特征的结构因此保持不变，介绍文案仍是"八威仪"）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_CITY_AMENITY'),
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_HOLY_SITE_AMENITY');

-- ---------------------------------------------------------------------------
-- 4. 城市数阶梯（v34）：5 / 9 / 13 座城时各再 +1 宜居（叠加，最高 +3）
--
--   为什么加这一层：上面两条补的是「人口长得快」，而实机反馈的「中后期宜居
--   逐渐紧缺」真正来自另一条线——**城市数量**。原版有两条硬扣：
--     ① 城市数量惩罚：每约 2 座城，所有城市 −1 宜居（硬编码，无 Modifier 可改）
--     ② 奢侈品只供应 4 座城（Resources.Happiness=4，全库 35 种里 32 种为 4）
--   第 ② 条是断崖而不是缓坡：**第 5 座城起完全吃不到奢侈品**。
--   两条叠加的结果是：4 城以内还算宽裕，第 5 座一落成，边远城的宜居净值
--   直接掉一大截，之后每 2 城再扣 1，一路滑向 −5（−30% 产出、停止增长）。
--   我们此前只给了 +2，相当于把整条曲线抬高 2 格，越往后越不够。
--
--   所以这一层的原则是「跟着城市数走」，而不是再抬一个固定数：
--     5 城 → +1 ／ 9 城 → +1 ／ 13 城 → +1（三者叠加，4 城以内完全不触发）
--   前 4 座城（也就是前期）拿到的宜居与 v33 完全一致，不动刚调好的前期曲线；
--   城市越多补得越多，正好抵消上面那条硬扣。
--
-- 【机制出处】
--   REQUIREMENT_PLAYER_HAS_AT_LEAST_NUMBER_CITIES（参数 Amount）
--     原版用例 REQUIRES_PLAYER_HAS_AT_LEAST_ONE_CITY（Amount=1，Inverse=0）
--     —— 「至少 N 座城」就是 Amount=N 且不设 Inverse；
--     设了 Inverse=1 的 REQUIRES_PLAYER_HAS_ONLY_ONE_CITY（Amount=2）
--     语义是「少于 2 座」，不要照抄那一行。
--   组合写法参照 PLAYER_IS_HIGH_DIFFICULTY_HUMAN：
--     一个 Set 里同时放「是人类」+ 另一条玩家级 Requirement（TEST_ALL 为与）。
--     我们照此把 REQUIRES_PLAYER_IS_HUMAN 与城市数放进同一个 Set，
--     这样既能保留人类门槛，又不必在 OwnerRequirementSetId 上二选一。
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO RequirementSets (RequirementSetId, RequirementSetType) VALUES
  ('NHS_AMENITY_HUMAN_5CITIES',  'REQUIREMENTSET_TEST_ALL'),
  ('NHS_AMENITY_HUMAN_9CITIES',  'REQUIREMENTSET_TEST_ALL'),
  ('NHS_AMENITY_HUMAN_13CITIES', 'REQUIREMENTSET_TEST_ALL');

INSERT OR IGNORE INTO Requirements (RequirementId, RequirementType) VALUES
  ('NHS_REQ_5_CITIES',  'REQUIREMENT_PLAYER_HAS_AT_LEAST_NUMBER_CITIES'),
  ('NHS_REQ_9_CITIES',  'REQUIREMENT_PLAYER_HAS_AT_LEAST_NUMBER_CITIES'),
  ('NHS_REQ_13_CITIES', 'REQUIREMENT_PLAYER_HAS_AT_LEAST_NUMBER_CITIES');

INSERT OR IGNORE INTO RequirementArguments (RequirementId, Name, Value) VALUES
  ('NHS_REQ_5_CITIES',  'Amount', '5'),
  ('NHS_REQ_9_CITIES',  'Amount', '9'),
  ('NHS_REQ_13_CITIES', 'Amount', '13');

INSERT OR IGNORE INTO RequirementSetRequirements (RequirementSetId, RequirementId) VALUES
  ('NHS_AMENITY_HUMAN_5CITIES',  'REQUIRES_PLAYER_IS_HUMAN'),
  ('NHS_AMENITY_HUMAN_5CITIES',  'NHS_REQ_5_CITIES'),
  ('NHS_AMENITY_HUMAN_9CITIES',  'REQUIRES_PLAYER_IS_HUMAN'),
  ('NHS_AMENITY_HUMAN_9CITIES',  'NHS_REQ_9_CITIES'),
  ('NHS_AMENITY_HUMAN_13CITIES', 'REQUIRES_PLAYER_IS_HUMAN'),
  ('NHS_AMENITY_HUMAN_13CITIES', 'NHS_REQ_13_CITIES');

INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId) VALUES
  ('NHS_AMENITY_MANY_CITIES_5',  'MODIFIER_PLAYER_CITIES_ADJUST_POLICY_AMENITY', 'NHS_AMENITY_HUMAN_5CITIES'),
  ('NHS_AMENITY_MANY_CITIES_9',  'MODIFIER_PLAYER_CITIES_ADJUST_POLICY_AMENITY', 'NHS_AMENITY_HUMAN_9CITIES'),
  ('NHS_AMENITY_MANY_CITIES_13', 'MODIFIER_PLAYER_CITIES_ADJUST_POLICY_AMENITY', 'NHS_AMENITY_HUMAN_13CITIES');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_AMENITY_MANY_CITIES_5',  'Amount', '1'),
  ('NHS_AMENITY_MANY_CITIES_9',  'Amount', '1'),
  ('NHS_AMENITY_MANY_CITIES_13', 'Amount', '1');

INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_AMENITY_MANY_CITIES_5'),
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_AMENITY_MANY_CITIES_9'),
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_AMENITY_MANY_CITIES_13');

-- ---------------------------------------------------------------------------
-- 调参旋钮
--   * 还是不够（例如打到 -5 以上）：把 NHS_CITY_AMENITY 的 Amount 改成 2（合计 +3）。
--     不建议再把圣地那一条也提到 2：两处同加会变成 +4/城，宜居度系统直接失效。
--   * 想让阶梯更早/更晚生效：改第 4 节三个 Requirement 的 Amount
--     （5/9/13）。注意改了 Amount 必须同步改 RequirementId 与 Set 的名字，
--     否则名字与实际阈值不符，后来人会按名字误解（本项目已因命名漂移返工过一次）。
--   * 想更狠地压城市数惩罚：再加一档 17 城 +1（四档合计 +4）。
--     不建议超过 +4 的阶梯总额：那样多城铺张就完全没有宜居代价了。
--   * 若实机发现圣地那条不生效（区域收集器偶尔不吃 trait 级挂载）：
--     改为挂 RequirementSet 到 COLLECTION_PLAYER_DISTRICTS + 原版
--     MINOR_CIV_RELIGIOUS_YIELD_FOR_HOLY_SITE 的写法（该 modifier 用的是
--     COLLECTION_PLAYER_DISTRICTS + DISTRICT_IS_HOLY_SITE，可作备选模板）。
-- ---------------------------------------------------------------------------
