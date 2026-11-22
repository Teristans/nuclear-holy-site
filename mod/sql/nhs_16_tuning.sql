-- ============================================================================
-- 皇帝之威 · 平衡旋钮总表 (nhs_16_tuning.sql)  v7.33
--
-- 【为什么单独成文件】
--   实机反馈一句话概括：**前期太弱、圣地起来之后太强**。
--   查下来不是"数值高低"的问题，是曲线形状的问题，根因两条：
--
--     ① 前期弱是结构性的：八威仪里六条挂在「有圣地」或「已创教」后面。
--        圣地要占星术 + 54 锤，创教要圣地上线后再攒大预言家。
--        于是前 30~70 回合玩家实际只拿到：+1 宜居、首都 +1 信仰、
--        冻土 +1 信仰 +1 产能、一格通配符。
--        而出生偏置（nhs_15）把人放在冻土带——冻土平地不能建农场，
--        是全场粮食最差的出生点之一。**偏置制造了负项，却没有配套正项。**
--
--     ② 后期强是复利结构：同一份「圣地相邻值」被兑现了三次——
--        来源放大（极光无条件 +1/冻土格、河流大相邻 +2、农场 +1、山脉标准）
--        使相邻值从原版典型 3~4 升到 8~12（约 3 倍）；
--        经文 ×2 再兑一次信仰；职业道德 1:1 再兑一次产能。
--        一份相邻值 = 信仰两次 + 产能一次。
--
--   所以修法只有一条原则：**前期给「不依赖相邻轴的固定收益」，后期砍「乘数」。**
--   固定收益会随时代自动稀释，不会变成新的放大器；
--   乘数才是让曲线后段翘起来的东西。
--
--   【v33 追加】上述 ② 还漏了一层：原版 BELIEF_WORK_ETHIC 除「相邻信仰→产能」
--   之外，另挂了一条 WORK_ETHIC_FOLLOWER_PRODUCTION = **每信徒 +1 产能**。
--   它随人口线性增长、没有上限，且门槛是 COLLECTION_ALL_CITIES，
--   连信奉你宗教的 AI 城也吃 —— 这才是中后期真正失控的那条轴。
--   v33 起从克隆源头剔除，见文末【第二把刀】。
--
-- 【本文件改了什么 —— 五个旋钮】
--   一、圣地建造 +50%       （前期：让引擎早 6~8 回合上线，不加数字）
--   二、首都 +2 食物         （前期：对冲冻土粮食赤字，食物才是瓶颈）
--   三、首都 +2 产能         （前期：把多出来的人口转成锤子）
--   四、经文 100% → 50%     （后期：砍唯一那个「免费乘 2」）
--   五、删「每信徒 +1 产能」 （后期：v33 起默认执行，见文末【第二把刀】）
--   另有一处不在此文件：
--     · 物勒工名收时代上限      → 见 nhs_09_wonder_era.sql（MaxEra 9 → 3）
--
-- 【四条机制的出处 —— 全部在 db/gameplay_verify.sqlite 里逐条查过，非臆造】
--
--   (1) MODIFIER_PLAYER_CITIES_ADJUST_DISTRICT_PRODUCTION
--       = COLLECTION_PLAYER_CITIES + EFFECT_ADJUST_DISTRICT_PRODUCTION
--       参数：DistrictType / Amount。**Amount 是百分比，不是平值**，
--       铁证是政策「天空与星辰」POLICY_SKY_AND_STARS：
--         同 ModifierType、Amount=30，葡萄牙语与法语文本均写「+30% 太空港与机场产能」
--         （DLC/Byzantium_Gaul/Text/..._Translations_Text_MODE.xml:247 / :585）
--       同类原版用例还有 VETERANCY_ENCAMPMENT_PRODUCTION（Amount=30，军营 +30%）。
--       我们填 50 = 圣地建造 +50%，54 锤实际按 36 锤结算。
--       收集器是 PLAYER_CITIES，天生只收自己的城；再挂 PLAYER_IS_HUMAN 双保险。
--
--   (2)(3) MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE
--       = COLLECTION_PLAYER_CAPITAL_CITY + EFFECT_ADJUST_CITY_YIELD_CHANGE
--       参数：YieldType / Amount。与 nhs_01 第 4b 节的 NHS_CAPITAL_FAITH 同一条。
--       原版用例（含食物与产能两种 YieldType，Amount 都是 1~2 量级）：
--         PHARAOH_FOOD / PHARAOH_PRODUCTION   Amount=2
--         MINOR_CIV_MARITIME_YIELD_FOR_CAPITAL Amount=2 (YIELD_FOOD)
--         MONARCHY_PRODUCTION / AUTOCRACY_PRODUCTION Amount=1 (YIELD_PRODUCTION)
--       收集器只指向首都，因此**不需要**再挂 SubjectRequirement（挂了反而收不窄）。
--
--   (4) 经文克隆体 NHS_PL_SCRIPTURE_DISTRICTFAITH
--       = MODIFIER_PLAYER_DISTRICTS_ADJUST_YIELD_MODIFIER
--       参数：Amount='100' / YieldType='YIELD_FAITH'。
--       这里只改 Value，不动结构：把 100 变成 50，即「圣地相邻 +50%」。
--       保留它是有意的——「核动力」的观感就在这一条；砍成 0 手感会塌，
--       砍成 50 只是把上限压回三分之一（相邻 10：20 信仰 → 15 信仰）。
--
-- 【数值口径：食物 2、产能 2（v7.29 上调产能）】
--   冻土城的瓶颈首先是粮食（冻土丘 1 食 1 锤、冻土平 1 食 0 锤，
--   且平地不能建农场），所以食物必须先给够：+2 食物约等于多养一个人口，
--   按 8 人口每级 16 食物的曲线折算，等于把前三级人口的增长时间各砍 12~20%。
--   但只补食物会卡在另一头：**人口上来了，锤子没上来**，涨出来的人只能塞进
--   产能更低的格子，圣地那 54 锤照样要磨 15~20 回合。v7.28 只给 +1 产能，
--   实机验证后判定不足，v7.29 改为 +2，食物与产能同级。
--   叠加后的量级核对：首都开局约 3 锤 → 5 锤。圣地 54 锤，
--   原版 3 锤要 18 回合；现在 5 锤 + 50% 加速（按 36 锤结算）约 7 回合。
--   配合食物提前涨到 3~4 人口，实际上线时间大约从 t25~45 压到 t15~25。
--   —— 若实机觉得头两城起得太快，把第三节 Amount 退回 '1'（v7.28 原值）即可。
--
-- 【生效条件】
--   前三条是新增 Modifier 行，读档即生效；
--   第四条是 UPDATE 已克隆的参数行，同样读档即生效。
--   都不需要重开新局。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 一、圣地建造 +50%（前期启动）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId) VALUES
  ('NHS_HOLY_SITE_BUILD_FAST',
   'MODIFIER_PLAYER_CITIES_ADJUST_DISTRICT_PRODUCTION',
   'PLAYER_IS_HUMAN');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_HOLY_SITE_BUILD_FAST', 'DistrictType', 'DISTRICT_HOLY_SITE'),
  ('NHS_HOLY_SITE_BUILD_FAST', 'Amount',       '50');

INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_HOLY_SITE_BUILD_FAST');

-- ---------------------------------------------------------------------------
-- 二、首都 +2 食物（前期：冻土粮食赤字）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId) VALUES
  ('NHS_CAPITAL_FOOD', 'MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE', 'PLAYER_IS_HUMAN');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_CAPITAL_FOOD', 'YieldType', 'YIELD_FOOD'),
  ('NHS_CAPITAL_FOOD', 'Amount',    '2');

INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_CAPITAL_FOOD');

-- ---------------------------------------------------------------------------
-- 三、首都 +2 产能（前期：把新增人口转成产能）
-- ---------------------------------------------------------------------------
INSERT OR IGNORE INTO Modifiers (ModifierId, ModifierType, OwnerRequirementSetId) VALUES
  ('NHS_CAPITAL_PROD', 'MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE', 'PLAYER_IS_HUMAN');

INSERT OR IGNORE INTO ModifierArguments (ModifierId, Name, Value) VALUES
  ('NHS_CAPITAL_PROD', 'YieldType', 'YIELD_PRODUCTION'),
  ('NHS_CAPITAL_PROD', 'Amount',    '2');

INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES
  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_CAPITAL_PROD');

-- ---------------------------------------------------------------------------
-- 四、经文 100% → 50%（后期降温）
--    必须排在 nhs_06 之后执行（modinfo 里 NHS_DB_TUNING 在 NHS_DB_BELIEFS 之后），
--    否则克隆体还没生成，UPDATE 命中 0 行且不报错 —— 静默失效，这是本项目
--    已经踩过一次的坑（INSERT OR IGNORE ... SELECT 静默丢行）。
--    前缀用 'NHS_PL_' + 政策卡名，避免误伤 NHS_BL_ 下的信条参数。
-- ---------------------------------------------------------------------------
UPDATE ModifierArguments
   SET Value = '50'
 WHERE ModifierId LIKE 'NHS_PL_SCRIPTURE%'
   AND Name = 'Amount';

-- ============================================================================
-- 【第二把刀 · v33 起已开】去掉「每信徒 +1 产能」
--
--   背景：原版 BELIEF_WORK_ETHIC 下挂了**两条** Modifier：
--     · WORK_ETHIC_ADJACENCY_PRODUCTION_2  → 相邻信仰等量产锤（保留）
--     · WORK_ETHIC_FOLLOWER_PRODUCTION     → +1 产能/信徒（已剔除）
--       其参数指向原版 WORK_ETHIC_FOLLOWER_PRODUCTION_MODIFIER
--       （MODIFIER_FOLLOWER_YIELD_MODIFIER / Amount=1 / YIELD_PRODUCTION）
--   后者是 GS 改版时没删干净的历史遗留行，我们克隆时照单全收，
--   于是产能引擎多了一条**随人口线性增长**的轴：
--       10 城 × 12 人口 = +120 产能/回合，比「相邻值」那条还大，
--       而上限完全取决于人口，没有任何收敛机制。
--   相邻那条被城市质量（可选址格数）锁死，这条不会 —— 所以砍它。
--
--   另一个副作用：该 Modifier 的 attach 门槛是
--     COLLECTION_ALL_CITIES + CITY_FOLLOWS_RELIGION_REQUIREMENTS，
--   所以**信奉你宗教的 AI 城市也会拿到 +1 产能/信徒**。
--   这是原版 Work Ethic 的固有行为，但砍掉后一并解决。
--
--   ★ 两处改动互为保险：
--     1) nhs_06_beliefs.sql 的克隆语句已加 `AND m.ModifierId <>
--        'WORK_ETHIC_FOLLOWER_PRODUCTION'` —— 从源头不生成；
--     2) 本处三行 DELETE 兜底 —— 万一以后有人改回克隆、或加载顺序变动，
--        只要本文件在信条之后执行，最终状态仍然是不存在。
--     删的顺序必须是 关联表 → 参数 → 主表，否则外键残留。
--
--   要恢复（不推荐）：把 nhs_06 的排除条件去掉，并注释掉下面三行。
-- ============================================================================
DELETE FROM TraitModifiers     WHERE ModifierId = 'NHS_BL_WORK_ETHIC_FOLLOWER_PRODUCTION';
DELETE FROM ModifierArguments  WHERE ModifierId = 'NHS_BL_WORK_ETHIC_FOLLOWER_PRODUCTION';
DELETE FROM Modifiers          WHERE ModifierId = 'NHS_BL_WORK_ETHIC_FOLLOWER_PRODUCTION';

-- ============================================================================
-- 【其余旋钮速查】
--   · 前期还是顶不住（比如神级：AI 开局三移民）：
--       第三条 Amount 由 2 再提到 3；或把第一条 50 改 80（圣地 54 锤 ≈ 30 锤）。
--       不建议再加食物：+3 食物会让首都前 20 回合人口领先太多，
--       而本 mod 的宜居度只补到刚好够用（nhs_13），人多了反而红脸。
--       也不建议跳过「圣地 +50%」直接堆产能：那条是一次性的启动费，堆产能会一路吃到后期。
--   · 后期还是太强：
--       v33 已经砍掉「每信徒 +1 产能」，若仍溢出，把第四条的 50 改成 25。
--       再不够就把 nhs_09 的 MaxEra 从 3 改成 2（奇观加速只到古典）。
--   · 想让奇观加速恢复「到文艺复兴为止」：
--       改 nhs_09_wonder_era.sql 里的 MaxEra = 4（不是本文件）。
--   · 反过来觉得砍过头了：
--       第四条改回 100；要恢复信徒产能，需同时去掉 nhs_06 的排除条件
--       并注释掉上面三行 DELETE（**不推荐**：它随人口线性增长、无上限，
--       且会把 +1 产能/信徒发给同教的 AI 城市）。
--       若要恢复奇观加速到全时代，把 nhs_09 的 MaxEra 改回 9（v7.27 的原状）。
-- ============================================================================
