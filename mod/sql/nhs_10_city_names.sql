-- ============================================================================
-- 皇帝之威 · 秦郡城名 (nhs_10_city_names.sql)
--
-- 【v7.6】把中国（CIVILIZATION_CHINA）的城市名全量替换为秦三十六郡。
--
-- 为什么必须"先删后插"而不是只改名：
--   原版中国的城名表只有 30 行（ID 108~1416），而秦郡名要 41 个，
--   光把 30 个 CityName 改成郡名不够用，必须补行。CityNames 的
--   PRIMARY KEY 是 ID，原版最大 ID = 1705，这里从 900001 起避开冲突。
--
-- 排序依据：
--   SortIndex 原版全是 0，实际显示顺序跟行的插入顺序（ID 递增）一致。
--   本文件把 SortIndex 也写成 0..40 的序号，两种排序口径下结果一致。
--
-- 【v7.15 修正】首城名不走 CityNames！
--   开始游戏后首都仍叫「西安」，根因在 CivilizationLeaders 表：
--     Base/Assets/Gameplay/Data/Civilizations.xml:196
--       <Row CivilizationType="CIVILIZATION_CHINA" LeaderType="LEADER_QIN"
--            CapitalName="LOC_CITY_NAME_XIAN"/>
--   首城用 CivilizationLeaders.CapitalName，第二座城起才从 CityNames 取。
--   所以只替换 CityNames 时，首城永远回到西安。下面第 2 段 UPDATE 补这个口子。
--   条件写 CapitalName='LOC_CITY_NAME_XIAN' 而不是硬编码 LeaderType，
--   可同时覆盖原版两个秦始皇变体（LEADER_QIN / LEADER_QIN_ALT），
--   且不会误改永乐（BEIJING）、武则天（SHEN_DU）等其他中国领袖。
--
-- 影响面（刻意接受）：
--   CityNames 是按 CivilizationType 分组的，没有可用的 LeaderType 先例
--   （原版 1677 行 LeaderType 全为 NULL），因此这套地名会作用于所有中国，
--   包括 AI 的忽必烈。纯外观，不影响任何数值。
--
-- 文案：41 个 LOC_CITY_NAME_QIN_* 全部定义在 ../text/nhs_text.xml
--       （中英各一份），标签名与下面 CityName 列逐字对应。
-- ============================================================================

DELETE FROM CityNames WHERE CivilizationType = 'CIVILIZATION_CHINA';

-- ---------------------------------------------------------------------------
-- 1.2 【v7.22】补删「神都」
--
--    用户实机看到第二座城叫「神都」。它不是我们列表里的，来源是资料片：
--      DLC/RulersOfChina/Data/RulersOfChina_Civilizations.xml:11-13
--        <CityNames><Row CivilizationType="CIVILIZATION_CHINA"
--                       CityName="LOC_CITY_NAME_SHEN_DU"/></CityNames>
--    这是「中国统治者包」给武则天往同一个中国城名池里塞的一行（无显式 ID，
--    运行时自动分配到 900692）。
--
--    为什么上面那条 DELETE 没删掉它（实测 DebugGameplay.sqlite）：
--      最终库里恰好是「我们 41 行 900001~900041」+「神都 900692」，
--      说明这行是在本文件执行**之后**才插进来的——该 DLC 的 UpdateDatabase
--      加载顺序在我们之后，DELETE 删不到尚未存在的行。
--
--    因此这里按名字再删一次：若哪天加载顺序变成 DLC 在前，这条就生效；
--    若仍在后，则由 nhs_text.xml 里把 LOC_CITY_NAME_SHEN_DU 的中英文案
--    改写为「雍城 / Yongcheng」兜底（文本通道 UpdateText 一定最后应用）。
--    两条路都堵上，玩家不会再看到「神都」。
--
--    注意武则天（LEADER_WU_ZETIAN）的首都名也是 SHEN_DU，见同文件第 5 行
--    CivilizationLeaders.CapitalName；文本改写后她的首都会显示「雍城」——
--    本就是秦都（秦德公迁雍，近三百年），与整套秦郡名同源，不违和。
-- ---------------------------------------------------------------------------
DELETE FROM CityNames WHERE CityName = 'LOC_CITY_NAME_SHEN_DU';

INSERT INTO CityNames (ID, CivilizationType, LeaderType, ContinentType, CityName, SortIndex) VALUES
  -- ---- 第一梯队：开城必见 ----
  (900001, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_XIANYANG',  0),  -- 咸阳，秦都
  (900002, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_LONGXI',    1),  -- 陇西，秦人发祥
  (900003, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_HANZHONG',  2),  -- 汉中
  (900004, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_HANDAN',    3),  -- 邯郸，赵都
  (900005, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_JULU',      4),  -- 巨鹿，破釜沉舟
  (900006, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_YANMEN',    5),  -- 雁门，蒙恬戍边
  (900007, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_KUAIJI',    6),  -- 会稽，始皇东巡
  (900008, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_LANGYA',    7),  -- 琅琊刻石
  -- ---- 第二梯队 ----
  (900009, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_SHANGJUN',  8),  -- 上郡，蒙恬驻军
  (900010, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_BEIDI',     9),  -- 北地，义渠故地
  (900011, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_YUNZHONG', 10),  -- 云中，阴山之下
  (900012, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_TAIYUAN',  11),  -- 太原，晋阳
  (900013, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_SHANGDANG',12),  -- 上党，长平之战
  (900014, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_SANCHUAN', 13),  -- 三川，洛阳
  (900015, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_YINGCHUAN',14),  -- 颍川
  (900016, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_NANYANG',  15),  -- 南阳
  (900017, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_NANJUN',   16),  -- 南郡，楚郢都
  (900018, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_CHANGSHA', 17),  -- 长沙
  (900019, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_BAJUN',    18),  -- 巴郡，江州
  (900020, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_SHUJUN',   19),  -- 蜀郡，都江堰
  -- ---- 第三梯队：补齐三十六郡 ----
  (900021, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_SHANGGU',  20),  -- 上谷
  (900022, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_YUYANG',   21),  -- 渔阳
  (900023, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_YOUBEIPING',22), -- 右北平
  (900024, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_LIAOXI',   23),  -- 辽西
  (900025, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_LIAODONG', 24),  -- 辽东
  (900026, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_DAIJUN',   25),  -- 代郡
  (900027, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_HEDONG',   26),  -- 河东，安邑
  (900028, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_DONGJUN',  27),  -- 东郡，濮阳
  (900029, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_DANGJUN',  28),  -- 砀郡，刘邦起兵
  (900030, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_SISHUI',   29),  -- 泗水，沛县
  (900031, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_XUEJUN',   30),  -- 薛郡，孟尝君
  (900032, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_DONGHAI',  31),  -- 东海，郯城
  (900033, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_JIUJIANG', 32),  -- 九江，寿春
  (900034, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_QIJUN',    33),  -- 齐郡，临淄
  (900035, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_JIAODONG', 34),  -- 胶东
  (900036, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_JIBEI',    35),  -- 济北
  (900037, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_NEISHI',   36),  -- 内史，畿辅
  -- ---- 备用：城数超过 36 时启用 ----
  (900038, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_JIUYUAN',  37),  -- 九原，蒙恬筑城
  (900039, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_NANHAI',   38),  -- 南海，岭南
  (900040, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_GUILIN',   39),  -- 桂林
  (900041, 'CIVILIZATION_CHINA', NULL, NULL, 'LOC_CITY_NAME_QIN_XIANGJUN', 40);  -- 象郡

-- ---------------------------------------------------------------------------
-- 2. 首都名（首城）—— 走 CivilizationLeaders.CapitalName，不是 CityNames
--    见文件头 v7.15 说明。条件用 CapitalName 值匹配，自动覆盖
--    LEADER_QIN 与 LEADER_QIN_ALT（原版两个秦始皇变体），不碰其他中国领袖。
-- ---------------------------------------------------------------------------
UPDATE CivilizationLeaders
   SET CapitalName = 'LOC_CITY_NAME_QIN_XIANYANG'
 WHERE CivilizationType = 'CIVILIZATION_CHINA'
   AND CapitalName = 'LOC_CITY_NAME_XIAN';
