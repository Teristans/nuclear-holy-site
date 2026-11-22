#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核动力圣地 Mod - 静态校验器 v2
Game Balance Analysis Specialist

在没有游戏本体的情况下，对 mod 文件做可复现的静态检查：
  1. XML (.modinfo) 是否 well-formed，引用的文件是否都存在
  2. SQL 的 INSERT/UPDATE 目标表是否为已知标准表（抓幽灵表）
  3. 引用一致性：ModifierId / TraitType / 本地化 Tag 是否先定义后引用
  4. 人类限定门槛：每个 Modifier 是否都带 OwnerRequirementSetId='PLAYER_IS_HUMAN'
  5. 数值锚点：产出加成是否等于 v3 数值分析的选定值
  6. 俄罗斯母亲层：克隆逻辑是否安全（NULL 安全、排除暴风雪、排除俄罗斯本体）
  7. SQL 危险写法：检出 NOT IN (SELECT ...) 这类空值陷阱
  8. 移动力层：ModifierType 是否用对（玩家级而非单单位级）、单位限定、加值
  9. 工人加速层：百分比、人类门槛、是否排除中国
 10. 全时代解禁：UnitCommands.MaxEra 更新是否命中，并声明全局泄漏风险

这不是"游戏内能跑"的证明，只是"静态结构自洽"的证明。
运行：python verify_mod.py
"""
import os, re, sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
MOD  = os.path.join(ROOT, "mod")
SQL_FILES = ["sql/nhs_01_core.sql", "sql/nhs_02_advanced.sql",
             "sql/nhs_04_mother_russia.sql",
             "sql/nhs_05_monasteries.sql", "sql/nhs_06_beliefs.sql",
             "sql/nhs_07_movement.sql", "sql/nhs_08_wonder_boost.sql",
             "sql/nhs_09_wonder_era.sql", "sql/nhs_10_city_names.sql",
             "sql/nhs_11_roads.sql", "sql/nhs_12_edicts.sql",
             "sql/nhs_13_amenities.sql", "sql/nhs_14_units.sql",
             "sql/nhs_15_start_bias.sql", "sql/nhs_16_tuning.sql",
             "sql/nhs_17_last_best_west.sql", "sql/nhs_18_tech_scaling.sql"]
# v7.3：本地化从 SQL 迁到 XML（UpdateText 通道），单独校验
TEXT_FILE = "text/nhs_text.xml"

KNOWN_TABLES = {
    "Types","Traits","CivilizationTraits","LeaderTraits",
    "Requirements","RequirementArguments","RequirementSets","RequirementSetRequirements",
    "DynamicModifiers","Modifiers","ModifierArguments","TraitModifiers","BeliefModifiers",
    "LocalizedText","Districts","DistrictModifiers","Buildings","Civilizations","Leaders",
    "Policies","PolicyModifiers","Units","Improvements","UnitCommands",
    "CityNames",   # v7.6：nhs_10 替换中国城名为秦三十六郡
    "CivilizationLeaders",   # v7.15：首城名在此表 CapitalName，不换则首城永远叫西安
    "UnitReplaces", "UnitAiInfos", "UnitUpgrades",   # v7.16：特色单位锐士/斥候
    "TypeTags",   # v7.20：单位分类标签（CLASS_MELEE / CLASS_RECON），漏了政策卡不认人
    "StartBiasTerrains", "StartBiasRivers",   # v7.27：开局出生地形偏置
}
CUSTOM_TABLES = set()   # 本 mod 不建自定义表

errors, warnings, infos = [], [], []
def err(m): errors.append(m)
def warn(m): warnings.append(m)
def info(m): infos.append(m)

# ---------- 1. modinfo XML ----------
modinfo = os.path.join(MOD, "NuclearHolySite.modinfo")
try:
    tree = ET.parse(modinfo)
    info("[XML] .modinfo 解析成功（well-formed）")
    referenced = set()
    for elem in tree.iter():
        # 容忍命名空间：真实 modinfo 无 xmlns，但解析器可能带上前缀
        if elem.tag.rsplit("}", 1)[-1] == "File":
            f = (elem.text or "").strip()
            if f: referenced.add(f.replace("\\", "/"))
    for f in sorted(referenced):
        p = os.path.join(MOD, f.replace("\\", "/"))
        if os.path.exists(p):
            info("[XML] 引用文件存在: %s" % f)
        else:
            err("[XML] 引用文件缺失: %s" % f)
    # 反向检查：磁盘上的 sql 是否都被 modinfo 装载（漏装=静默失效）
    for f in SQL_FILES:
        if f not in referenced:
            err("[XML] SQL 文件存在于目录但未在 .modinfo 装载: %s" % f)
except Exception as e:
    err("[XML] .modinfo 解析失败: %s" % e)

# ---------- 1b. 版本号三处一致（v7.31）----------
#  Civ6 的 mod 管理器**不显示** modinfo 的 version 属性：详情面板那行
#  `ModIdVersion` 实际是 Mods.lua:454 的 `SetText(info.Id)`，即 GUID。
#  所以版本号只能写进 <Name> 和 <Description> 才看得见。
#  但这带来新风险：标题里的号是手写的，`version` 属性是改的，两者会漂移。
#  一旦漂移，用户看到"v30"就以为加载了 v30，实际是 v31——比不显示更糟。
#  所以三处必须逐字对齐，不一致即报错。
try:
    _root = ET.parse(modinfo).getroot()
    _ver = (_root.get("version") or "").strip()
    _props = {}
    for _e in _root.iter():
        if _e.tag.rsplit("}", 1)[-1] == "Properties":
            for _c in _e:
                _props[_c.tag.rsplit("}", 1)[-1]] = (_c.text or "")
            break
    _name = _props.get("Name", "")
    _desc = _props.get("Description", "")

    if not _ver.isdigit():
        err("[版本] .modinfo 的 version 属性不是纯数字：%r" % _ver)
    else:
        _tag = "v%s" % _ver
        if _tag in _name:
            info("[版本] 标题里带版本号 %s（mod 管理器列表可见）" % _tag)
        else:
            err("[版本] 标题 <Name> 里没有 %s。Civ6 的 mod 管理器不显示 version 属性，"
                "不写进标题就只能看到 GUID，无法判断游戏读的是哪一版" % _tag)

        if _tag in _desc:
            info("[版本] 描述里带版本号 %s（详情面板可见）" % _tag)
        else:
            err("[版本] 描述 <Description> 里没有 %s；详情面板将无法确认版本" % _tag)

        # 反向：标题与描述里不许出现别的版本号（防止改了属性忘了改文字）
        _stale_n = set(re.findall(r"v(\d+)", _name)) - {_ver}
        _stale_d = set(re.findall(r"v(\d+)\s*·", _desc)) - {_ver}
        if _stale_n:
            err("[版本] 标题里残留旧版本号 %s，与 version=%s 冲突"
                % (", ".join("v" + s for s in sorted(_stale_n)), _ver))
        if _stale_d:
            err("[版本] 描述开头残留旧版本号 %s，与 version=%s 冲突"
                % (", ".join("v" + s for s in sorted(_stale_d)), _ver))
except Exception as e:
    err("[版本] 版本一致性检查失败: %s" % e)

# ---------- 读取并去注释 ----------
raw = {}
for f in SQL_FILES:
    p = os.path.join(MOD, f)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            raw[f] = fh.read()
    else:
        err("[SQL] 文件缺失: %s" % f)
        raw[f] = ""

def strip_comments(t):
    return "\n".join(l for l in t.splitlines() if not l.strip().startswith("--"))

code = "\n".join(strip_comments(v) for v in raw.values())
info("[SQL] 有效代码行数（去注释）: %d" % len([l for l in code.splitlines() if l.strip()]))

# ---------- 2. 幽灵表（支持 INSERT OR IGNORE / OR REPLACE）----------
tbl_pat = r"\b(?:INSERT(?:\s+OR\s+(?:IGNORE|REPLACE))?\s+INTO|UPDATE|DELETE\s+FROM)\s+([A-Za-z_][A-Za-z0-9_]*)"
seen_tables = set()
for m in re.finditer(tbl_pat, code, re.I):
    tbl = m.group(1)
    if tbl not in KNOWN_TABLES and tbl not in CUSTOM_TABLES:
        err("[SQL] 未知/幽灵表: %s" % tbl)
    else:
        seen_tables.add(tbl)
info("[SQL] 合法表使用: %s" % ", ".join(sorted(seen_tables)))

# ---------- 3. 引用一致性 ----------
defined_modifiers = set()
for mi in re.finditer(
        r"INSERT(?:\s+OR\s+IGNORE)?\s+INTO\s+Modifiers\s*\([^)]*\)\s*VALUES([\s\S]*?);", code, re.I):
    # 支持多行 VALUES：取每个元组的第一个字段（ModifierId）
    defined_modifiers |= set(re.findall(r"\(\s*'([^']+)'", mi.group(1)))
used_modifiers = set()
for m in re.finditer(r"TraitModifiers\s*\([^)]*\)\s*VALUES([\s\S]*?);", code, re.I):
    used_modifiers |= set(re.findall(r"'([^']+)'", m.group(1)))
used_modifiers = {x for x in used_modifiers if not x.startswith("TRAIT_")}
for mid in sorted(used_modifiers):
    if mid not in defined_modifiers:
        err("[REF] TraitModifiers 引用了未定义的 Modifier: %s" % mid)
    else:
        info("[REF] Modifier 定义/引用一致: %s" % mid)
info("[REF] VALUES 型 Modifier 定义数: %d" % len(defined_modifiers))

defined_traits = set(re.findall(r"'([A-Z_]*TRAIT_[A-Z0-9_]+)'", code))
for t in sorted(defined_traits):
    if t.startswith("TRAIT_NHS") and ("'%s'" % t) not in code:
        err("[REF] Trait 未定义: %s" % t)

# 本地化 Tag（v7.3：来源改为 text/nhs_text.xml，不再从 SQL 抽取）
loc_defined = set()
loc_langs = {}
loc_text = {}
tp = os.path.join(MOD, TEXT_FILE)
if not os.path.exists(tp):
    err("[LOC] 本地化文件缺失: %s" % TEXT_FILE)
else:
    try:
        ttree = ET.parse(tp)
        for elem in ttree.iter():
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag in ("Row", "Replace"):
                t = elem.get("Tag") or ""
                if not t.startswith("LOC_"):
                    continue
                # BaseGameText 无 Language（默认语言）；LocalizedText 带 Language
                lang = elem.get("Language") or "en_US"
                if lang == "zh_CN":
                    err("[LOC] 语言代码 %s 非法，简体中文应为 zh_Hans_CN" % lang)
                loc_defined.add(t)
                loc_langs.setdefault(t, set()).add(lang)
                tx = elem.find("Text")
                if tx is not None and tx.text:
                    loc_text.setdefault(t, {})[lang] = tx.text.strip()
        info("[LOC] XML 共 %d 个本地化 Tag，语言: %s"
             % (len(loc_defined),
                ", ".join(sorted({l for s in loc_langs.values() for l in s}))))
        # 每个 LOC_TRAIT_NHS* 必须同时有默认语言与 zh_Hans_CN
        for t in sorted(loc_defined):
            langs = loc_langs[t]
            if "zh_Hans_CN" not in langs:
                warn("[LOC] %s 缺简体中文（仅 %s）" % (t, ",".join(sorted(langs))))
        # v7.10：八项特征的中文名统一为四字（用户明确要求）
        names = {t: v.get("zh_Hans_CN", "") for t, v in loc_text.items()
                 if t.startswith("LOC_TRAIT_NHS") and t.endswith("_NAME")}
        bad_len = {t: n for t, n in names.items() if len(n) != 4}
        if bad_len:
            err("[NAME] 以下特征名不是四字：%s"
                % "、".join("%s=%s(%d字)" % (t.rsplit("_", 2)[-2], n, len(n))
                            for t, n in sorted(bad_len.items())))
        else:
            info("[NAME] 八项特征中文名均为四字：%s"
                 % "、".join(names[t] for t in sorted(names)))
    except Exception as e:
        err("[LOC] %s 解析失败: %s" % (TEXT_FILE, e))

for t in re.findall(r"'(LOC_[A-Z0-9_]+)'", code):
    if t.startswith("LOC_TRAIT_NHS") and t not in loc_defined:
        err("[LOC] 本地化 Tag 引用但未定义: %s" % t)

# ---------- 4. 人类限定门槛 ----------
#   v34 起放宽一层：OwnerRequirementSetId 不必字面等于 PLAYER_IS_HUMAN，
#   允许指向「组合 Set」——只要那个 Set 在 SQL 里确实被挂了 REQUIRES_PLAYER_IS_HUMAN。
#   组合 Set 是原版 PLAYER_IS_HIGH_DIFFICULTY_HUMAN 的写法，用于同时表达
#   「是人类」+「另一条玩家级条件」（本 mod 是城市数 ≥ N）。
#   ⚠ 这里必须真的去查 Set 的成员行，不能只看名字里有没有 HUMAN —— 名字是
#   人取的，改个名就会假通过；本项目已因"看名字"踩过坑。
_gated_sets = set(re.findall(
    r"\(\s*'([A-Z0-9_]+)'\s*,\s*'REQUIRES_PLAYER_IS_HUMAN'\s*\)", code))
if _gated_sets:
    info("[GATE] 检出组合式人类门槛 Set：%s" % "、".join(sorted(_gated_sets)))
mod_inserts = re.findall(r"INSERT(?:\s+OR\s+IGNORE)?\s+INTO\s+Modifiers[\s\S]*?;", code, re.I)
info("[GATE] 检测到 %d 条 Modifiers 插入语句" % len(mod_inserts))
for mi in mod_inserts:
    _via = [s for s in _gated_sets if "'%s'" % s in mi]
    if "PLAYER_IS_HUMAN" in mi:
        info("[GATE] Modifier 人类限定 OK")
    elif _via:
        info("[GATE] Modifier 人类限定 OK（经组合 Set %s）" % "、".join(_via))
    else:
        midm = re.search(r"VALUES\s*\(\s*'([^']+)'", mi, re.I)
        err("[GATE] Modifier %s 未设置 OwnerRequirementSetId='PLAYER_IS_HUMAN'，会作用于 AI！"
            % (midm.group(1) if midm else "?"))

# ---------- 5. 数值锚点（v3 选定：5/3/3/1，住房 2）----------
anchor = {"YIELD_PRODUCTION":"0", "YIELD_FOOD":"1", "YIELD_FAITH":"2", "YIELD_CULTURE":"1"}
for y, val in anchor.items():
    mm = re.search(r"'YieldType'\s*,\s*'%s'[\s\S]{0,160}?'Amount'\s*,\s*'(\d+)'" % y, code)
    if mm:
        if mm.group(1) == val:
            info("[BAL] %s = %s (符合 v4 选定值)" % (y, val))
        else:
            warn("[BAL] %s = %s, v4 选定 %s（偏离需有理由）" % (y, mm.group(1), val))
    else:
        warn("[BAL] 未找到 %s 的 Amount 定义" % y)
mh = re.search(r"'NHS_CITY_HOUSING'[\s\S]{0,160}?'Amount'\s*,\s*'(\d+)'", code)
if mh:
    info("[BAL] YIELD_HOUSING = %s" % mh.group(1))

# ---------- 5b. 宜居度层（v13，nhs_13_amenities.sql）----------
for _mid in ("NHS_CITY_AMENITY", "NHS_HOLY_SITE_AMENITY"):
    ma = re.search(r"'%s'[\s\S]{0,300}?'Amount'\s*,\s*'(\d+)'" % _mid, code)
    if ma:
        info("[AM] %s Amount = %s" % (_mid, ma.group(1)))
    else:
        err("[AM] 未找到 %s 的 Amount 定义" % _mid)
_blk = re.search(r"NHS_HOLY_SITE_AMENITY[\s\S]{0,400}", code)
if _blk:
    _seg = _blk.group(0)
    if "'DISTRICT_IS_HOLY_SITE'" in _seg:
        info("[AM] 圣地宜居度已收窄到原版 reqset DISTRICT_IS_HOLY_SITE")
    else:
        err("[AM] NHS_HOLY_SITE_AMENITY 缺 SubjectRequirementSetId='DISTRICT_IS_HOLY_SITE'："
            "COLLECTION_CITY_DISTRICTS 会给每座城的每个区域都加宜居度，数值直接失控")
    if "PLAYER_IS_HUMAN" not in _seg:
        err("[AM] NHS_HOLY_SITE_AMENITY 缺 PLAYER_IS_HUMAN 门槛")
else:
    err("[AM] 找不到 NHS_HOLY_SITE_AMENITY（nhs_13_amenities.sql 未装载？）")
if "'NHS_CITY_AMENITY', 'MODIFIER_PLAYER_CITIES_ADJUST_POLICY_AMENITY'" not in code:
    err("[AM] NHS_CITY_AMENITY 未使用 MODIFIER_PLAYER_CITIES_ADJUST_POLICY_AMENITY")

# ---------- 5b2. 城市数阶梯宜居（v34，nhs_13_amenities.sql 第 4 节）----------
#   为什么单独查：这一层有两种"写了等于没写"的写法，静态层最该拦的是第二种。
#     ① Amount 写错（如 5 写成 4）→ 阶梯提前，前期多拿 1 点，不报错
#     ② Requirement 建了但没塞进 Set，或 Set 名字对不上 → 该档恒真或恒假
#   还有一个反向陷阱：REQUIREMENT_PLAYER_HAS_AT_LEAST_NUMBER_CITIES 一旦带
#   Inverse=1，语义立刻反转为「少于 N 座城」（原版 REQUIRES_PLAYER_HAS_ONLY_ONE_CITY
#   就是 Amount=2 + Inverse=1 = 少于两城）。照抄那一行会让「城越多越不加」。
_LADDER = [("NHS_REQ_5_CITIES", "5"), ("NHS_REQ_9_CITIES", "9"), ("NHS_REQ_13_CITIES", "13")]
if not re.search(r"NHS_AMENITY_MANY_CITIES_5", code):
    err("[AM2] 未找到城市数阶梯（nhs_13_amenities.sql 第 4 节）；"
        "中后期宜居只靠固定 +2 会越铺越紧")
else:
    info("[AM2] 检出城市数阶梯（5/9/13 座城各 +1，上限 +3）")
    for _rid, _want in _LADDER:
        _seg = re.search(r"'%s'[\s\S]{0,200}" % _rid, code)
        if not _seg:
            err("[AM2] 找不到 Requirement %s" % _rid); continue
        _s = _seg.group(0)
        if "REQUIREMENT_PLAYER_HAS_AT_LEAST_NUMBER_CITIES" in _s:
            info("[AM2] %s 使用原版「至少 N 城」判定" % _rid)
        else:
            err("[AM2] %s 的 RequirementType 不是 REQUIREMENT_PLAYER_HAS_AT_LEAST_NUMBER_CITIES" % _rid)
        # Amount 要全局限定查，不能用 _s 那个窗口 —— 三个 INSERT 块之间隔了
        # 几百字符，窗口一缩就查不到（第一版就是这么误报 3 条的）
        _am = re.search(r"'%s'\s*,\s*'Amount'\s*,\s*'(\d+)'" % _rid, code)
        if _am and _am.group(1) == _want:
            info("[AM2] %s Amount = %s" % (_rid, _want))
        elif _am:
            err("[AM2] %s Amount = %s，应为 %s" % (_rid, _am.group(1), _want))
        else:
            err("[AM2] %s 缺 Amount 参数；缺了这档永不触发" % _rid)
        # 反向：这三个 Requirement 不许带 Inverse=1。
        #   REQUIREMENT_PLAYER_HAS_AT_LEAST_NUMBER_CITIES 一旦 Inverse=1，语义立刻
        #   反转为「少于 N 座城」（原版 REQUIRES_PLAYER_HAS_ONLY_ONE_CITY 就是
        #   Amount=2 + Inverse=1 = 少于两城），照抄那一行会变成「城越多越不加」。
        #   这里必须解析列清单拿 Inverse 的**值**，不能只看行内有没有 "Inverse"
        #   字样 —— 列名写在 INSERT 的列清单里，不在 VALUES 行里。第一版就是这么
        #   写错的：注入 Inverse=1 后断言仍然通过（永远为真的死断言）。
        _inv_ok = None
        for _blk in re.findall(r"INSERT(?:\s+OR\s+IGNORE)?\s+INTO\s+Requirements[\s\S]*?;", code, re.I):
            if "'%s'" % _rid not in _blk:
                continue
            _h = re.search(r"INTO\s+Requirements\s*\(([^)]*)\)\s*VALUES([\s\S]*?);", _blk, re.I)
            if not _h:
                continue
            _cols = [c.strip() for c in _h.group(1).split(",")]
            for _rowtxt in re.findall(r"\(([^()]*)\)", _h.group(2)):
                _vals = [v.strip().strip("'") for v in _rowtxt.split(",")]
                if len(_vals) != len(_cols):
                    continue
                _d = dict(zip(_cols, _vals))
                if _d.get("RequirementId") != _rid:
                    continue
                _inv_ok = _d.get("Inverse", "0") in ("0", "", "None")
        if _inv_ok is False:
            err("[AM2] %s 带了 Inverse=1 —— 语义会反转为「少于 %s 座城」，"
                "与「至少 N 城」正好相反" % (_rid, _want))
        else:
            info("[AM2] %s 未设 Inverse（语义为「至少」）" % _rid)
    # 每个组合 Set 必须恰好含 HUMAN + 对应城市数。
    #   两个坑都在这里踩过：
    #   ① 必须只在该表的 INSERT 块里找 —— 否则 RequirementSets 那行的
    #      RequirementSetType（REQUIREMENTSET_TEST_ALL）会被当成成员混进来；
    #   ② 必须合并**所有**该表的 INSERT 块 —— 本 mod 在 nhs_01 里还有一条
    #      RequirementSetRequirements 插入，用 re.search 取第一条会拿到它，
    #      于是这里恒为「成员为空」并误报 3 条错。
    _rsr_blocks = re.findall(
        r"INSERT(?:\s+OR\s+IGNORE)?\s+INTO\s+RequirementSetRequirements[\s\S]*?;", code, re.I)
    _rsr_txt = "\n".join(_rsr_blocks)
    if not _rsr_txt:
        err("[AM2] 找不到 RequirementSetRequirements 的插入语句")
    else:
        info("[AM2] 合并 %d 段 RequirementSetRequirements 插入语句后比对成员" % len(_rsr_blocks))
    for _n in ("5", "9", "13"):
        _sid = "NHS_AMENITY_HUMAN_%sCITIES" % _n
        _members = re.findall(r"\(\s*'%s'\s*,\s*'([A-Z0-9_]+)'\s*\)" % _sid, _rsr_txt)
        _need = {"REQUIRES_PLAYER_IS_HUMAN", "NHS_REQ_%s_CITIES" % _n}
        if set(_members) == _need:
            info("[AM2] %s = 人类 ∧ 至少 %s 城" % (_sid, _n))
        else:
            err("[AM2] %s 的成员是 %s，应恰好是 %s；少了 HUMAN 会泄漏给 AI，"
                "少了城市数则该档恒真" % (_sid, sorted(set(_members)), sorted(_need)))
    if "'TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_AMENITY_MANY_CITIES_13'" in code:
        info("[AM2] 三档阶梯挂在核心特性（不新增第 9 条威仪）")
    else:
        err("[AM2] 城市数阶梯未挂到 TRAIT_NHS_NUCLEAR_HOLY_SITE，会成为孤儿行")
    _tp_am = os.path.join(MOD, TEXT_FILE)
    _txt_am = open(_tp_am, encoding="utf-8").read() if os.path.exists(_tp_am) else ""
    if "5、9、13" in _txt_am:
        info("[AM2] 文案已写明 5/9/13 座城各 +1（与实际阈值同源）")
    else:
        err("[AM2] 文案未提城市数阶梯；玩家看到的仍是「所有城市 +1」，与实装不符")

# ---------- 5c. 首都信仰（v14，nhs_01_core.sql 第 4b 节）----------
_cf = re.search(r"NHS_CAPITAL_FAITH[\s\S]{0,320}", code)
if _cf:
    _seg = _cf.group(0)
    if "MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE" in _seg:
        info("[CAP] 首都信仰复用原版首都收集器 ModifierType")
    else:
        err("[CAP] NHS_CAPITAL_FAITH 未使用 MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE，"
            "用城市收集器会变成全城加信仰")
    _ma = re.search(r"'NHS_CAPITAL_FAITH'[\s\S]{0,300}?'Amount'\s*,\s*'(\d+)'", code)
    if _ma:
        info("[CAP] 首都信仰 Amount = %s" % _ma.group(1))
    else:
        err("[CAP] 未找到 NHS_CAPITAL_FAITH 的 Amount")
    if "PLAYER_IS_HUMAN" not in _seg:
        err("[CAP] NHS_CAPITAL_FAITH 缺 PLAYER_IS_HUMAN 门槛")
else:
    err("[CAP] 找不到 NHS_CAPITAL_FAITH（nhs_01_core.sql 第 4b 节）")

# ---------- 5d. 农场 → 圣地 +1 信仰（v24，nhs_01_core.sql 第 4c 节）----------
#   这一段的三个"必须"都是踩过坑的类型：
#     · 必须用原版现成的 MODIFIER_PLAYER_CITIES_IMPROVEMENT_ADJACENCY
#       （自造 ModifierType 忘注册 KIND_MODIFIER → 整包加载失败）
#     · 必须带 DistrictType=DISTRICT_HOLY_SITE（漏了会加到所有区域）
#     · 必须带 PLAYER_IS_HUMAN（否则 AI 秦始皇也吃）
_farm = re.search(r"'NHS_HOLY_SITE_FARM_FAITH'[\s\S]{0,800}", code)
if not _farm:
    err("[FARM] 找不到 NHS_HOLY_SITE_FARM_FAITH（nhs_01_core.sql 第 4c 节）")
else:
    _fs = _farm.group(0)
    if "'MODIFIER_PLAYER_CITIES_IMPROVEMENT_ADJACENCY'" in _fs:
        info("[FARM] 复用原版「改善设施相邻」修饰器（同狄奥多拉圣地-农场）")
    else:
        err("[FARM] NHS_HOLY_SITE_FARM_FAITH 未使用 MODIFIER_PLAYER_CITIES_IMPROVEMENT_ADJACENCY；"
            "自造 ModifierType 需先注册 KIND_MODIFIER，否则整包加载失败")
    for _need, _why in (
        ("'DISTRICT_HOLY_SITE'",    "漏了 DistrictType 会把信仰加给所有区域"),
        ("'IMPROVEMENT_FARM'",      "改善设施写成别的就完全不生效"),
        ("'YIELD_FAITH'",           "产出类型必须是信仰"),
        ("'LOC_NHS_DISTRICT_FARM_FAITH'", "缺 Description 会显示裸 tag"),
        ("'PLAYER_IS_HUMAN'",       "缺人类门槛，AI 秦始皇也吃"),
    ):
        if _need in _fs:
            info("[FARM] 含 %s" % _need)
        else:
            err("[FARM] 缺 %s；%s" % (_need, _why))
    if re.search(r"'TRAIT_NHS_NUCLEAR_HOLY_SITE'\s*,\s*'NHS_HOLY_SITE_FARM_FAITH'", code):
        info("[FARM] 已挂到核心特性 TRAIT_NHS_NUCLEAR_HOLY_SITE")
    else:
        err("[FARM] TraitModifiers 里没有 NHS_HOLY_SITE_FARM_FAITH（写了也没人给）")

# ---------- 5e. 极光之舞改写（v24，nhs_06_beliefs.sql 第 1b 节）----------
#   克隆体继承了原版 CITY_FOLLOWS_PANTHEON_REQUIREMENTS，没立万神殿时整条静默失效；
#   但门槛又不能一删了事——原版正是靠它把 COLLECTION_ALL_CITIES 收回到自己的城市。
_aur = re.search(r"UPDATE\s+Modifiers[\s\S]{0,400}?NHS_BL_DANCE_OF_THE_AURORA", code)
if not _aur:
    err("[AUR] nhs_06 缺第 1b 节：未把极光之舞克隆体改成 PLAYER_CITIES + 去门槛；"
        "没立万神殿时相邻冻土不产信仰")
else:
    _as = _aur.group(0)
    if "MODIFIER_PLAYER_CITIES_TERRAIN_ADJACENCY" in _as:
        info("[AUR] 极光之舞已换成 PLAYER_CITIES 收集器")
    else:
        err("[AUR] 第 1b 节未改成 MODIFIER_PLAYER_CITIES_TERRAIN_ADJACENCY")
    if re.search(r"SubjectRequirementSetId\s*=\s*NULL", _as):
        info("[AUR] 极光之舞已去万神殿门槛")
    else:
        err("[AUR] 第 1b 节未把 SubjectRequirementSetId 置空")
if "MODIFIER_ALL_CITIES_TERRAIN_ADJACENCY" in code:
    err("[AUR] SQL 里仍有 MODIFIER_ALL_CITIES_TERRAIN_ADJACENCY；"
        "该收集器是全世界所有城市，去掉门槛会把信仰发给 AI")

# ---------- 6. 克隆层专项（俄罗斯母亲 / 国王的修道院）----------
CLONE_LAYERS = [
    # (文件, 标签, 克隆前缀, 原版 Trait, 是否应排除暴风雪)
    # v7：不再需要"排除某文明"，因为 mod 只挂 LEADER_QIN，秦始皇身上本来就没有这些原版特性
    ("sql/nhs_04_mother_russia.sql", "MR", "NHS_MR_", "TRAIT_CIVILIZATION_MOTHER_RUSSIA", True),
    ("sql/nhs_05_monasteries.sql",   "MK", "NHS_MK_", "TRAIT_LEADER_MONASTERIES_KING",    False),
]
# 信条/政策层单独检查（无"排除某文明"需求，但需要检查克隆源与门槛）
BELIEF_LAYER = ("sql/nhs_06_beliefs.sql", "BL", "NHS_BL_",
                ["BELIEF_DANCE_OF_THE_AURORA", "BELIEF_WORK_ETHIC",
                 "BELIEF_JESUIT_EDUCATION"], "POLICY_SCRIPTURE")
for fn, tag, prefix, src, blizz in CLONE_LAYERS:
    t = raw.get(fn, "")
    c = strip_comments(t)
    if not c:
        err("[%s] %s 为空" % (tag, fn)); continue
    if src in c:
        info("[%s] 引用原版 Trait %s" % (tag, src))
    else:
        err("[%s] 未引用原版 Trait %s" % (tag, src))
    if ("'%s' ||" % prefix) in c:
        info("[%s] 使用 %s 前缀克隆 Modifier" % (tag, prefix))
    else:
        err("[%s] 未找到克隆前缀 %s" % (tag, prefix))
    if "PLAYER_IS_HUMAN" in c:
        info("[%s] 克隆体挂载 PLAYER_IS_HUMAN 门槛" % tag)
    else:
        err("[%s] 克隆体缺少人类门槛，会作用于 AI！" % tag)
    if "LEADER_QIN" in c:
        info("[%s] 只挂到 LEADER_QIN（秦始皇专属）" % tag)
    else:
        err("[%s] 未挂到 LEADER_QIN，秦始皇拿不到该层" % tag)
    if blizz:
        if "BLIZZARD" in c:
            info("[%s] 已排除暴风雪相关 Modifier" % tag)
        else:
            warn("[%s] 未排除暴风雪 Modifier" % tag)
    if re.search(r"NOT\s+IN\s*\(\s*SELECT", c, re.I):
        warn("[%s] 检出 NOT IN (SELECT ...) 空值陷阱，建议改 NOT EXISTS" % tag)
    else:
        info("[%s] 未检出 NOT IN 空值陷阱" % tag)

# ---------- 7. 信条/政策层专项 ----------
bfn, btag, bprefix, beliefs, policy = BELIEF_LAYER
bc = strip_comments(raw.get(bfn, ""))
if not bc:
    err("[%s] %s 为空" % (btag, bfn))
else:
    for b in beliefs:
        if b in bc:
            info("[%s] 引用信条 %s" % (btag, b))
        else:
            err("[%s] 未引用信条 %s" % (btag, b))
    if policy in bc:
        info("[%s] 引用政策卡 %s" % (btag, policy))
    else:
        err("[%s] 未引用政策卡 %s" % (btag, policy))
    if ("'%s' ||" % bprefix) in bc or "NHS_PL_" in bc:
        info("[%s] 使用 NHS_BL_ / NHS_PL_ 前缀克隆" % btag)
    else:
        err("[%s] 未找到克隆前缀" % btag)
    if "PLAYER_IS_HUMAN" in bc:
        info("[%s] 克隆体挂载 PLAYER_IS_HUMAN 门槛" % btag)
    else:
        err("[%s] 克隆体缺少人类门槛，会作用于 AI！" % btag)
    if "BeliefModifiers" in bc:
        info("[%s] 从 BeliefModifiers 克隆（表名正确）" % btag)
    else:
        err("[%s] 未使用 BeliefModifiers 表" % btag)
    if "PolicyModifiers" in bc:
        info("[%s] 从 PolicyModifiers 克隆（表名正确）" % btag)
    else:
        err("[%s] 未使用 PolicyModifiers 表" % btag)
    if "SubjectRequirementSetId" in bc:
        info("[%s] 保留原版宗教门槛（需创教/信教才生效，已在文件内注明）" % btag)

# ---------- 8. SQL 危险写法（全库扫描）----------
if re.search(r"NOT\s+IN\s*\(\s*SELECT", code, re.I):
    warn("[SQL] 检出 NOT IN (SELECT ...)：若子查询含 NULL 会整体失效，建议改 NOT EXISTS")
else:
    info("[SQL] 全库未检出 NOT IN (SELECT ...) 空值陷阱")

# ---------- 9. 移动力层 / 工人加速层 / 时代解禁层 ----------
# 9.1 移动力
mc = strip_comments(raw.get("sql/nhs_07_movement.sql", ""))
if not mc:
    err("[MV] nhs_07_movement.sql 为空或缺失")
else:
    if "MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT" in mc:
        info("[MV] 使用玩家级 ModifierType（COLLECTION_PLAYER_UNITS，作用于该玩家所有单位）")
    else:
        err("[MV] 未使用 MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT")
    if re.search(r"MODIFIER_PLAYER_UNIT_ADJUST_MOVEMENT", mc) and \
       not re.search(r"MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT", mc):
        err("[MV] 检出单单位版 MODIFIER_PLAYER_UNIT_ADJUST_MOVEMENT，挂到 trait 上不生效")
    for ut, amt, mid in (("UNIT_SCOUT", "3", "NHS_SCOUT_MOVEMENT"),
                         ("UNIT_SETTLER", "2", "NHS_SETTLER_MOVEMENT")):
        if re.search(r"'UnitType'\s*,\s*'%s'" % ut, mc):
            info("[MV] Requirement 已限定到 %s" % ut)
        else:
            err("[MV] 未用 REQUIREMENT_UNIT_TYPE_MATCHES 限定 %s，加成会落到所有单位" % ut)
        if re.search(r"\('%s'\s*,\s*'Amount'\s*,\s*'%s'\)" % (mid, amt), mc):
            info("[MV] %s = +%s 移动力（与基础值相加后翻倍）" % (mid, amt))
        elif mid in mc:
            err("[MV] %s 的 Amount 不是 %s，与基础移动力不符" % (mid, amt))
        else:
            err("[MV] 缺少 Modifier %s" % mid)
    if "PLAYER_IS_HUMAN" in mc:
        info("[MV] 挂载 PLAYER_IS_HUMAN 门槛")
    else:
        err("[MV] 缺少人类门槛，AI 也会跑得飞快")

# 9.2 工人加速百分比
wc = strip_comments(raw.get("sql/nhs_08_wonder_boost.sql", ""))
if not wc:
    err("[WB] nhs_08_wonder_boost.sql 为空或缺失")
else:
    if "MODIFIER_PLAYER_ADJUST_UNIT_WONDER_PERCENT" in wc:
        info("[WB] 使用原版 ModifierType MODIFIER_PLAYER_ADJUST_UNIT_WONDER_PERCENT")
    else:
        err("[WB] 未使用 MODIFIER_PLAYER_ADJUST_UNIT_WONDER_PERCENT")
    mpct = re.search(r"'NHS_BUILDER_WONDER_PERCENT'\s*,\s*'Amount'\s*,\s*'(-?\d+)'", wc)
    if mpct:
        pct = int(mpct.group(1))
        early = pct + 15   # 远古~中世纪：本层 + 原版秦始皇 TRAIT_BUILDER_WONDER_PERCENT(15)
        late = 15          # 文艺复兴起：本层被 NHS_REQ_NOT_RENAISSANCE 关掉，只剩原版
        info("[WB] 本层 += %d%%；远古~中世纪每次 %d%%，文艺复兴起每次 %d%%" % (pct, early, late))
        if early != 30:
            warn("[WB] 文艺复兴前合计 %d%%，设计目标 30%%（本层应为 15）" % early)
        if pct < 0:
            err("[WB] Amount 为负：时代分档应靠需求实现，不能用负数扣减"
                "（单条 modifier 若被 clamp 到 0，扣减会静默失效）")
        if early * 3 >= 100:
            warn("[WB] 前期 %d%% × 3 次 = %d%%：普通 3 次工人即可直接完工"
                 "（v7.36 起仅限文艺复兴之前，后期 15%%×4=60%% 打不满）"
                 % (early, early * 3))
    else:
        err("[WB] 未找到 NHS_BUILDER_WONDER_PERCENT 的 Amount 定义")

    # 时代分档（v7.36）：这条需求决定了"文艺复兴起降到 15%"到底成不成立。
    #   Inverse=1 是最容易写反的地方 —— 写成 0 就变成"文艺复兴之后才 +15"，
    #   语义整个反过来，而且不会报错。
    if "NHS_REQ_NOT_RENAISSANCE" in wc:
        info("[WB] 时代分档需求 NHS_REQ_NOT_RENAISSANCE 已定义")
    else:
        err("[WB] 缺少时代分档需求：文艺复兴之后仍会按 30% 计算")
    if re.search(r"'NHS_REQ_NOT_RENAISSANCE'\s*,\s*'REQUIREMENT_PLAYER_ERA_AT_LEAST'\s*,\s*1\s*\)", wc):
        info("[WB] 该需求 = REQUIREMENT_PLAYER_ERA_AT_LEAST + Inverse=1（语义：尚未进入该时代）")
    else:
        err("[WB] 时代分档需求的类型或 Inverse 不对：必须 REQUIREMENT_PLAYER_ERA_AT_LEAST + Inverse=1")
    if "ARGTYPE_IDENTITY" in wc:
        info("[WB] RequirementArguments 显式写了 Type=ARGTYPE_IDENTITY")
    else:
        # 不是致命错：schema 里该列 DEFAULT "ARGTYPE_IDENTITY"，漏写落库值相同。
        # 真正会坏的是写成别的 Type，那条由 run_mod_sql.py 查落库值来兜。
        warn("[WB] 未显式写 Type=ARGTYPE_IDENTITY（schema 默认值相同，功能无害，建议补上便于审阅）")
    if re.search(r"'ERA_RENAISSANCE'", wc):
        info("[WB] 分档门槛设在 ERA_RENAISSANCE（ChronologyIndex=4）")
    else:
        err("[WB] 分档门槛不是 ERA_RENAISSANCE")
    if re.search(r"'NHS_RS_WONDER_BOOST'\s*,\s*'REQUIRES_PLAYER_IS_HUMAN'", wc):
        info("[WB] 人类门槛已并入 NHS_RS_WONDER_BOOST（TEST_ALL）")
    else:
        err("[WB] 新 Set 里没有合并人类门槛：AI 也会拿到这 +15%")
    if re.search(r"'NHS_BUILDER_WONDER_PERCENT'\s*,\s*'MODIFIER_PLAYER_ADJUST_UNIT_WONDER_PERCENT'\s*,\s*'NHS_RS_WONDER_BOOST'", wc):
        info("[WB] 百分比 modifier 已挂到 NHS_RS_WONDER_BOOST")
    else:
        err("[WB] 百分比 modifier 未挂 NHS_RS_WONDER_BOOST：分档不会生效，全程 30%")
    if "LEADER_QIN" in wc:
        info("[WB] 只发给 LEADER_QIN（秦始皇专属）")
    else:
        err("[WB] 未挂到 LEADER_QIN，秦始皇拿不到这一层")

# 9.3 全时代解禁
ec = strip_comments(raw.get("sql/nhs_09_wonder_era.sql", ""))
if not ec:
    warn("[WE] nhs_09_wonder_era.sql 为空：奇观加速仍受原版远古/古典限制")
else:
    if "UNITCOMMAND_WONDER_PRODUCTION" in ec:
        info("[WE] 目标指令 UNITCOMMAND_WONDER_PRODUCTION")
    else:
        err("[WE] 未定位到 UNITCOMMAND_WONDER_PRODUCTION")
    # 注意 (-?\d+)：v7.36 起设计值是 -1，用 (\d+) 会抓不到负号，
    # 把"正确的 -1"误报成"没找到 MaxEra 更新语句"。
    mera = re.search(r"UPDATE\s+UnitCommands[\s\S]{0,400}?MaxEra\s*=\s*(-?\d+)", ec, re.I)
    if mera:
        v = int(mera.group(1))
        if v == -1:
            info("[WE] UnitCommands.MaxEra = -1（不限时代，v7.36 设计值；表内其余 41 条指令同值）")
        elif v == 9:
            info("[WE] UnitCommands.MaxEra = 9（等效全开；建议改 -1，新增时代时不会漏）")
        elif v == 3:
            warn("[WE] UnitCommands.MaxEra = 3（到中世纪）——v7.36 起应为 -1；"
                 "否则文艺复兴之后连按钮都没有，15% 那档永远看不到")
        elif v == 2:
            info("[WE] UnitCommands.MaxEra = 2（原版值，仅远古/古典）")
        else:
            warn("[WE] UnitCommands.MaxEra = %d，仅覆盖到第 %d 个时代，请确认是否有意为之" % (v, v))
    else:
        err("[WE] 未找到 MaxEra 更新语句（列名可能写错，会导致整个文件中止）")
    warn("[WE] ⚠ UnitCommands 是全局表、无玩家归属，无法加人类门槛。"
         "但 v7 起 mod 只挂 LEADER_QIN：人类玩秦始皇时 AI 不可能是秦始皇，"
         "而 AI 没有该 modifier 就连加速按钮都没有 → 实际泄漏为 0。"
         "若人类玩别的文明而 AI 有秦始皇，AI 会白拿'全时代加速(15%)'，已写入 README")

# ---------- 10. 秦始皇专属挂载（v7 核心约束）----------
NHS_TRAITS = [
    "TRAIT_NHS_NUCLEAR_HOLY_SITE",
    "TRAIT_NHS_MOTHER_RUSSIA",
    "TRAIT_NHS_MONASTERIES_KING",
    "TRAIT_NHS_BELIEFS",
    "TRAIT_NHS_SWIFT_PIONEERS",
    "TRAIT_NHS_MASTER_BUILDER",
    "TRAIT_NHS_IMPERIAL_ROAD",
    "TRAIT_NHS_EDICTS",
]

# 10.1 不允许再有 CivilizationTraits 插入（v7 已全部改为 LeaderTraits）
if re.search(r"INSERT[^;]{0,80}INTO\s+CivilizationTraits", code, re.I):
    err("[挂载] 仍存在 INSERT INTO CivilizationTraits：v7 应全部改为 LeaderTraits，"
        "否则 mod 会发给所有文明，破坏『秦始皇专属』设计")
else:
    info("[挂载] 无 CivilizationTraits 插入（6 层已全部改为 LeaderTraits）")

# 10.2 每层 trait 必须与 LEADER_QIN 同处一个文件
for tr in NHS_TRAITS:
    hit = None
    for fn, txt in raw.items():
        c2 = strip_comments(txt)
        if ("'%s'" % tr) in c2 and "LeaderTraits" in c2 and "LEADER_QIN" in c2:
            hit = fn
            break
    if hit:
        info("[挂载] %s → LEADER_QIN（%s）" % (tr, hit))
    else:
        err("[挂载] %s 未在含 LeaderTraits 的文件里挂到 LEADER_QIN" % tr)

# 10.3 不得残留"按文明发 trait"的旧逻辑（v7 只挂 LEADER_QIN）
#      v7.6 说明：nhs_10 会 DELETE/INSERT CityNames 并出现 CIVILIZATION_CHINA，
#      那属于城名替换，不是发 trait，因此只检查 CivilizationTraits 插入语句。
civ_trait_ins = re.findall(
    r"INSERT(?:\s+OR\s+IGNORE)?\s+INTO\s+CivilizationTraits[\s\S]*?;", code, re.I)
for stale in ("CIVILIZATION_RUSSIA", "CIVILIZATION_KHMER", "CIVILIZATION_CHINA"):
    if any(stale in m for m in civ_trait_ins):
        warn("[挂载] 仍向 %s 整个文明发 trait（v7 只挂 LEADER_QIN），请确认是否为多余代码" % stale)

# ---------- 11. 首城名（v7.15）----------
# Civ6 的首城名取 CivilizationLeaders.CapitalName，第二座城起才轮到 CityNames。
# 只改 CityNames 时开局首都永远叫「西安」——这是 v7.6~v7.14 的实际 bug。
_mcap = re.search(
    r"UPDATE\s+CivilizationLeaders[\s\S]{0,300}?SET\s+CapitalName\s*=\s*'LOC_CITY_NAME_QIN_XIANYANG'",
    code, re.I)
if _mcap:
    info("[城名] nhs_10 已改写 CivilizationLeaders.CapitalName → 咸阳（首城生效）")
else:
    err("[城名] nhs_10 缺少 UPDATE CivilizationLeaders SET CapitalName='LOC_CITY_NAME_QIN_XIANYANG'；"
        "首城名不走 CityNames，缺这句则开局首都仍叫西安")

# ---------- 11.2 「神都」必须消失（v7.22）----------
# DLC/RulersOfChina 给武则天往中国城名池插了一行 LOC_CITY_NAME_SHEN_DU，
# 且该 DLC 在 mod 之后加载——实测 DebugGameplay.sqlite 里它就活在我们 41 行之后
# （ID 900692），所以只靠 DELETE 抹不干净。两条路都必须有：
#   ① SQL 按名字补删（应付加载顺序反过来）
#   ② 文本通道把该 tag 改成「雍城」（UpdateText 一定最后应用，必杀）
_CITY_SQL = os.path.join(MOD, "sql/nhs_10_city_names.sql")
_city_sql = open(_CITY_SQL, encoding="utf-8").read() if os.path.exists(_CITY_SQL) else ""

if re.search(r"DELETE\s+FROM\s+CityNames\s+WHERE\s+CityName\s*=\s*'LOC_CITY_NAME_SHEN_DU'",
             _city_sql, re.I):
    info("[城名] nhs_10 已按名字补删 LOC_CITY_NAME_SHEN_DU（中国统治者包那一行）")
else:
    err("[城名] nhs_10 缺 DELETE FROM CityNames WHERE CityName='LOC_CITY_NAME_SHEN_DU'")

_mins = re.search(r"INSERT\s+INTO\s+CityNames[\s\S]*?;", _city_sql)
if _mins and "SHEN_DU" in _mins.group(0):
    err("[城名] 41 个秦郡名的 INSERT 里混进了 SHEN_DU")

_text_all = ""
_tp = os.path.join(MOD, TEXT_FILE)
if os.path.exists(_tp):
    _text_all = open(_tp, encoding="utf-8").read()
for _lang, _want in (("zh_Hans_CN", "雍城"), ("en_US", "Yongcheng")):
    _m = re.search(r'<Replace\s+Tag="LOC_CITY_NAME_SHEN_DU"\s+Language="%s"><Text>([^<]*)</Text>'
                   % _lang, _text_all)
    if not _m:
        err("[城名] 文本缺 LOC_CITY_NAME_SHEN_DU 的 %s 替换；该 DLC 行在 mod 之后加载，"
            "删不掉，只能靠改名兜底" % _lang)
    elif _m.group(1) != _want:
        err("[城名] LOC_CITY_NAME_SHEN_DU 的 %s 文案是「%s」，应为「%s」"
            % (_lang, _m.group(1), _want))
    else:
        info("[城名] LOC_CITY_NAME_SHEN_DU(%s) → %s" % (_lang, _m.group(1)))

# ---------- 12. 奇观监听（v7.17：lua + 图标 + 文本）----------
# 这一层的失败模式与 v7.4「缺 <Files> 节点」完全同类：不报错、不弹窗，只是静静地不通知。
# 所以四个环节都要断死——脚本已注册、图标已补、槽位对得上、占位符数量对得上。
LUA_WATCH = "lua/nhs_wonder_watch.lua"
ICON_XML  = "data/nhs_icons.xml"
NOTIF_XML = "data/nhs_notifications.xml"

_p_mod = os.path.join(MOD, "NuclearHolySite.modinfo")
modinfo_text = ""
if os.path.exists(_p_mod):
    with open(_p_mod, encoding="utf-8") as fh:
        modinfo_text = fh.read()

# 12.1 文件存在
for _f in (LUA_WATCH, ICON_XML, NOTIF_XML):
    if os.path.exists(os.path.join(MOD, _f)):
        info("[监听] 文件存在: %s" % _f)
    else:
        err("[监听] 文件缺失: %s" % _f)

# 12.2 脚本必须用 <AddGameplayScripts> 注册
#      只写进 <Files> 是不执行的——lua/nhs_info.lua 从 v7 起就一直躺在 <Files> 里没跑过。
if re.search(r"<AddGameplayScripts[^>]*>[\s\S]{0,400}?%s" % re.escape(LUA_WATCH), modinfo_text):
    info("[监听] lua 已用 AddGameplayScripts 注册")
else:
    err("[监听] .modinfo 未用 <AddGameplayScripts> 注册 %s；只写 <Files> 不会有任何效果" % LUA_WATCH)

# 12.3 图标补丁必须用 <UpdateIcons> 注册（缺了只是刷 DataError，不影响功能，但仍算缺陷）
if re.search(r"<UpdateIcons[^>]*>[\s\S]{0,300}?%s" % re.escape(ICON_XML), modinfo_text):
    info("[监听] 图标补丁已用 UpdateIcons 注册")
else:
    err("[监听] .modinfo 未用 <UpdateIcons> 注册 %s；每发一条通知会刷一次 DataError" % ICON_XML)

# 12.3b 自定义通知类型必须用 <UpdateDatabase> 注册
#       只写进 <Files> 不会执行——Types / Notifications 都是数据表。
if re.search(r"<UpdateDatabase[^>]*>[\s\S]{0,300}?%s" % re.escape(NOTIF_XML), modinfo_text):
    info("[监听] 通知类型定义已用 UpdateDatabase 注册")
else:
    err("[监听] .modinfo 未用 <UpdateDatabase> 注册 %s；通知类型不会建表，"
        "lua 里 NotificationTypes.NHS_WONDER_STARTED 取到 nil、只能退回预留槽" % NOTIF_XML)

_lua_text, _icon_text, _text_text = "", "", ""
for _rel in (LUA_WATCH, ICON_XML, TEXT_FILE):
    _p = os.path.join(MOD, _rel)
    if os.path.exists(_p):
        with open(_p, encoding="utf-8") as fh:
            _v = fh.read()
        if _rel == LUA_WATCH:    _lua_text  = _v
        elif _rel == ICON_XML:   _icon_text = _v
        else:                    _text_text = _v

# 12.4 自建通知类型必须「Types 注册 + Notifications 定义 + 图标」三件齐
#      v7.22 及以前用的是原版预留槽 NOTIFICATION_USER_DEFINED_1，两个硬伤：
#        · 该槽 DB 行写死 ExpiresEndOfTurn=True → 通知当回合结束即被清除
#        · 该槽 Icon 列为空、九个槽公共，堆叠时与其他 mod 的通知打架
#      所以 v7.23 改为自建类型。少写 <Notifications> 则该类型根本没有行，
#      VisibleInUI 不成立；少写图标则通知栏只有一个空框。任何一处缺失都不报错，只是看不见。
#
#      ⚠ v7.27 更正：<Types> 这一行的作用**不是**「生成 NotificationTypes 枚举」。
#        实测 Lua.log 里 notify type 一直是 USER_DEFINED_1，说明 mod 自建类型
#        根本不会出现在 NotificationTypes 里（该枚举按基础库固化，官方 DLC 做自定义
#        通知也只用 USER_DEFINED_1~4）。这一行的真正作用是让引擎的类型注册表认识它，
#        从而 GameInfo.Types[名字].Hash 查得到 —— 脚本拿这个 Hash 当运行时数值。
NOTIF_TYPE = "NOTIFICATION_NHS_WONDER_STARTED"
_notif_text = ""
_p_notif = os.path.join(MOD, NOTIF_XML)
if os.path.exists(_p_notif):
    with open(_p_notif, encoding="utf-8") as fh:
        _notif_text = fh.read()

if re.search(r'<Row\s+Type="%s"\s+Kind="KIND_NOTIFICATION"' % NOTIF_TYPE, _notif_text):
    info("[监听] 通知类型已注册 KIND_NOTIFICATION（引擎类型表可查，供 Types.Hash 取值）")
else:
    err("[监听] %s 里缺 <Types><Row Type=\"%s\" Kind=\"KIND_NOTIFICATION\"/>；"
        "缺这一行，GameInfo.Types 查不到它，脚本只能退回原版槽" % (NOTIF_XML, NOTIF_TYPE))

_m_notif_row = re.search(r'<Row\s+NotificationType="%s"([^/>]*)' % NOTIF_TYPE, _notif_text)
if not _m_notif_row:
    err("[监听] %s 里缺 <Notifications><Row NotificationType=\"%s\" .../>" % (NOTIF_XML, NOTIF_TYPE))
else:
    _attrs = _m_notif_row.group(1)
    # 逐项核对，因为每一项缺了都只会「悄悄看不见」
    for _attr, _want, _why in (
        ("ExpiresEndOfNextTurn", "False", "v7.24：两个过期标志都为 0 才是常驻；写 True 只挂一回合"),
        ("ExpiresEndOfTurn",     "False", "必须显式关掉当回合过期，否则仍是当日消失"),
        ("VisibleInUI",          "True",  "为假则通知栏不生成条目，等于完全看不见"),
        ("ShowIconSinglePlayer", "True",  "为假则单人游戏里不显示图标"),
    ):
        _m_attr = re.search(r'\b%s="([^"]*)"' % _attr, _attrs)
        if not _m_attr:
            err("[监听] 通知定义缺 %s 属性；%s" % (_attr, _why))
        elif _m_attr.group(1).lower() != _want.lower():
            err("[监听] 通知定义 %s=\"%s\"，应为 \"%s\"；%s"
                % (_attr, _m_attr.group(1), _want, _why))
    _m_group = re.search(r'\bGroupType="([^"]*)"', _attrs)
    if not _m_group:
        warn("[监听] 通知定义未写 GroupType，会落到默认分组里")
    elif _m_group.group(1) == "USER":
        warn("[监听] GroupType 写成了 \"USER\"；那是九个预留槽共用的分组，"
             "建议写自己的类型名以独占一组，避免与其他 mod 的通知挤在一起")

# 12.4b 图标：自建类型必须配（主路径）；USER_DEFINED_1 必须**不配**
#        v7.27：那个名字的 (Name, Atlas) 与工坊 3810795757 (Civilization Assimilation)
#        撞联合主键，Database.log 实测每周目刷一条 UNIQUE constraint failed。
#        ⚠ 只认真正的 <Row> 元素，不认注释——注释里提到这个名字是正常的说明。
_slot = NOTIF_TYPE.replace("NOTIFICATION_", "")
if re.search(r'<Row\s+Name="ICON_NOTIFICATION_%s"' % re.escape(_slot), _icon_text):
    info("[监听] 图标在位: ICON_NOTIFICATION_%s" % _slot)
else:
    err("[监听] %s 里缺 ICON_NOTIFICATION_%s 的 <Row>；通知栏会是个空框" % (ICON_XML, _slot))

if re.search(r'<Row\s+Name="ICON_NOTIFICATION_USER_DEFINED_1"', _icon_text):
    err("[监听] %s 里又加回了 ICON_NOTIFICATION_USER_DEFINED_1 的 <Row>；"
        "(Name,Atlas) 是联合主键，会与工坊 3810795757 的同一行撞车，"
        "对方那行插不进去。本 mod 已不用该槽，这行必须删掉。" % ICON_XML)

# 12.4c Lua 必须走「枚举 → Types.Hash → 常驻槽」三级，且不许再依赖 USER_DEFINED_1
#        同样只看代码、不看注释（v7.27 的注释里特意写了 USER_DEFINED_1 的来龙去脉）
_lua_code = "\n".join(re.sub(r'--.*$', '', _ln) for _ln in _lua_text.splitlines())

if "NHS_WONDER_STARTED" not in _lua_code:
    err("[监听] lua 里没有引用自建类型 NHS_WONDER_STARTED；等于白建了这张表")
if "GameInfo.Types" not in _lua_code:
    err("[监听] lua 没有从 GameInfo.Types 取 Hash。mod 自建类型进不了 NotificationTypes 枚举，"
        "只查枚举会永远落到兜底，等于白建")
if "WONDER_COMPLETED" not in _lua_code:
    err("[监听] lua 没有常驻通知槽兜底；自建类型万一被引擎拒绝就彻底静默")
if "USER_DEFINED_1" in _lua_code:
    warn("[监听] lua 代码里还残留 USER_DEFINED_1；该槽 ExpiresEndOfTurn=1，"
         "一旦走到它，通知就只挂一回合（这正是 v7.24 的假修复）")

# 12.5 文本 tag 中英各一份
for _tag in ("LOC_NHS_WATCH_TITLE", "LOC_NHS_WATCH_BODY", "LOC_NHS_UNKNOWN_CIV"):
    if ('<Row Tag="%s"' % _tag) not in _text_text:
        err("[监听] %s 缺少默认语言（英文）行" % _tag)
    if ('<Replace Tag="%s" Language="zh_Hans_CN"' % _tag) not in _text_text:
        err("[监听] %s 缺少 zh_Hans_CN 行" % _tag)

# 12.6 lua 里引用的 LOC_NHS_* tag 必须真的存在于文本文件（抓拼写错误）
for _tag in sorted(set(re.findall(r'Locale\.Lookup\("(LOC_NHS_[A-Z_]+)"', _lua_text))):
    if _tag not in _text_text:
        err("[监听] lua 引用了文本里不存在的 tag: %s" % _tag)

# 12.7 正文占位符数量必须与 Locale.Lookup 实参个数一致，否则通知会显示成 {3_WonderName}
_body_nums = set()
for _line in _text_text.splitlines():
    if "LOC_NHS_WATCH_BODY" in _line:
        _body_nums |= {int(x) for x in re.findall(r"\{(\d+)_", _line)}
_m_args = re.search(r'Locale\.Lookup\("LOC_NHS_WATCH_BODY"(.*?)\)', _lua_text)
if _body_nums and _m_args:
    _n_args = len([x for x in _m_args.group(1).split(",") if x.strip()])
    _n_slots = max(_body_nums)
    if _n_args == _n_slots:
        info("[监听] 通知正文占位符 %d 个，与传参个数一致" % _n_slots)
    else:
        err("[监听] 正文有 %d 个占位符，但 Locale.Lookup 传了 %d 个参数；通知会露出占位符原文"
            % (_n_slots, _n_args))
elif _body_nums:
    err("[监听] 正文有占位符，但 lua 里找不到对应带参的 Locale.Lookup(\"LOC_NHS_WATCH_BODY\", ...)")

# 12.8 轮询入口必须真的绑上，否则脚本加载了也不扫描
if "GameEvents.OnGameTurnStarted.Add" not in _lua_text:
    err("[监听] lua 未绑定 GameEvents.OnGameTurnStarted；脚本加载后不会触发任何扫描")
#      v7.23：主入口是 PlayerTurnActivated（本地玩家回合开始）。
#      OnGameTurnStarted 对所有文明都触发，用它当主入口会让通知在 AI 行动阶段产生，
#      玩家自己的回合还没开始它就躺在通知栏里了——这是「发了却看不见」的成因之一。
if "GameEvents.PlayerTurnActivated.Add" not in _lua_text:
    err("[监听] lua 未绑定 GameEvents.PlayerTurnActivated；主触发点缺失，"
        "只能靠对所有文明都触发的 OnGameTurnStarted 兜底")

# 12.9 Player 对象没有 HasTrait 方法
#      原版 HasTrait 是 UI 层的全局函数 HasTrait(name, playerID)
#      （Base/Assets/UI/Scripts/GameCapabilities.lua:16），查的是 PlayerConfigurations。
#      写成 pPlayer:HasTrait(...) 会抛错，而外层 pcall 会把它吞成 false，
#      结果是整套通知静默不工作——这是个不会报错、只会「什么都没发生」的坑。
#      只查有效代码行：注释里为了记教训保留了这句错误写法，不能算违规。
_lua_code = "\n".join(l for l in _lua_text.splitlines() if not l.strip().startswith("--"))
if re.search(r":HasTrait\s*\(", _lua_code):
    err("[监听] lua 里出现 xxx:HasTrait(...)；Player 对象没有该方法，应改查 PlayerConfigurations")

# 12.10 文明名必须查 PlayerConfigurations
#       同类坑：Player 对象上也没有 GetCivilizationShortDescription。
#       v7.22 正是写成 Players[i]:GetCivilizationShortDescription()，pcall 吞错，
#       十条通知的文明名全是「?」。这一条只能靠静态断言挡住。
if re.search(r"Players\s*\[[^\]]*\]\s*:\s*GetCivilization(ShortDescription|Description)\s*\(", _lua_code):
    err("[监听] lua 里对 Players[...] 调了 GetCivilizationShortDescription；"
        "Player 没有该方法，必须改查 PlayerConfigurations[i]:GetCivilizationShortDescription()")
if "PlayerConfigurations[" not in _lua_code:
    err("[监听] lua 没有用 PlayerConfigurations 取文明名；文明名会显示成占位符")

# 12.11 城市名必须过 Locale.Lookup
#       AI 城市的 City:GetName() 返回的是 LOC key（实测 LOC_CITY_NAME_TOKYO），
#       直接拼进正文会原样显示成代码。
if not re.search(r"Locale\.Lookup\(\s*pCity:GetName\(\)\s*\)", _lua_code):
    err("[监听] lua 未对 pCity:GetName() 套 Locale.Lookup；正文里会直接出现 LOC_CITY_NAME_XXX")

# 12.12 只有发送成功才写去重标记
#       v7.22 是先 MarkNotified 再 Notify，一旦 SendNotification 失败，
#       该「文明+奇观」就被永久标记为已报，再也不会补发。
if not re.search(r"if\s+Notify\(", _lua_code):
    err("[监听] lua 里没有「发送成功才标记」的写法（if Notify(...) then MarkNotified(...)）；"
        "一次发送失败会导致该奇观永久不再提示")

# 12.13 英文正文的占位符序号必须与传参顺序对应：1=文明 2=城市 3=奇观
#       v7.22 的英文行是「{2_WonderName} ... {3_CityName}」，而 lua 传的是 (文明,城市,奇观)，
#       英文会读成「has begun building <城> in <奇观>」。中文行本来就对，所以一直没被发现。
for _line in _text_text.splitlines():
    if '<Row Tag="LOC_NHS_WATCH_BODY"' in _line:
        if not re.search(r"\{2_CityName\}", _line):
            err("[监听] 英文正文的城市名占位符不是 {2_CityName}（lua 第 2 个实参是城市）")
        if not re.search(r"\{3_WonderName\}", _line):
            err("[监听] 英文正文的奇观名占位符不是 {3_WonderName}（lua 第 3 个实参是奇观）")
        if not re.search(r"\{1_CivName\}", _line):
            err("[监听] 英文正文的文明名占位符不是 {1_CivName}（lua 第 1 个实参是文明）")

# 12.14 回合号 API：Game.GetGameTurn() 不存在
#       游戏自带 Lua 里一次都没出现过这个名字，正解是 Game.GetCurrentGameTurn()。
#       写成前者会在事件回调里抛 attempt to call nil，回调照样「绑上了」，
#       但每次触发都失败——扫描永远不会执行，而 Modding.log 干干净净。
if re.search(r"Game\.GetGameTurn\s*\(", _lua_code):
    err("[监听] lua 里用了 Game.GetGameTurn()，该方法不存在；应改用 Game.GetCurrentGameTurn()")
if "Game.GetCurrentGameTurn" not in _lua_code:
    warn("[监听] lua 没有取回合号；每回合去重闸门会退化为「不设闸门」")

# 12.15 回合激活事件要两条路都试
#       游戏自带的写法是 Events.PlayerTurnActivated（Tutorial.lua:119），
#       gameplay 作用域未必有同名事件；两条都写、谁存在用谁，才不会一bind就抛错。
for _ev in ("GameEvents.PlayerTurnActivated", "Events.PlayerTurnActivated"):
    if _ev not in _lua_text:
        warn("[监听] lua 未尝试绑定 %s；若另一条也不存在就只剩 OnGameTurnStarted 兜底" % _ev)

# ---------------------------------------------------------------------------
# 13. 特色单位图标（v7.19：全部复用原版图集）
#     单位没有 IconDefinitions 时，地图旗帜与生产列表就是一个空白框，
#     而且引擎只在日志里刷 DataError，不报错、不进 Modding.log。
#     v7.19 起不再自绘 DDS，改为把「锐士/斥候的图标名」映射到游戏自带图集的
#     现成格子（锐士=鹰武士、斥候=侦察兵）。好处是不必再管 DDS 头、mip 链、
#     ImportFiles 三道坎——那三道里任何一道断了都会静默变空白。
#     本节钉住四件事：
#       · 自绘贴图已彻底退场（残留会让双份配置打架）
#       · 每个图标名都登记了，且指向原版图集的具体格子
#       · 指向的格子与游戏本体里同款图标完全一致（可读游戏目录时实时对账）
#       · 亚洲民族性立绘名齐全（中国单位立绘首选这条路径）
# ---------------------------------------------------------------------------
ICON_XML = "data/nhs_icons.xml"

# 游戏安装目录：用来把「我们登记的名字」与「原版同款图标的真实格子」逐条对账。
# 取不到时退化为内置期望表，仍能拦住「索引写错一位」这类事故。
GAME_DIR = os.environ.get("CIV6_DIR") or \
    r"D:/SteamLibrary/steamapps/common/Sid Meier's Civilization VI"
_UNITS_ICONS    = os.path.join(GAME_DIR, "Base", "Assets", "UI", "Icons", "Icons_Units.xml")
_PORTRAIT_ICONS = os.path.join(GAME_DIR, "Base", "Assets", "UI", "Icons", "Icons_UnitPortraits.xml")

_icon_path = os.path.join(MOD, ICON_XML)
_modinfo_path = os.path.join(MOD, "NuclearHolySite.modinfo")
_mod_txt = open(_modinfo_path, encoding="utf-8").read()
_ic_xml = ""
if os.path.exists(_icon_path):
    _ic_xml = open(_icon_path, encoding="utf-8").read()
else:
    err("[图标] 缺少 %s" % ICON_XML)

# 13.1 自绘贴图必须彻底退场
#      还留着 DDS / ImportFiles / 自建图集，就会出现「自己画的图仍被加载、
#      与新的原版映射同时生效」的双份配置，排查起来极难。
_icons_dir = os.path.join(MOD, "icons")
_left = []
if os.path.isdir(_icons_dir):
    _left = sorted(f for f in os.listdir(_icons_dir) if f.lower().endswith(".dds"))
if _left:
    err("[图标] mod/icons 下仍有 %d 个自绘 DDS：%s；v7.19 已改用原版图集，应删净"
        % (len(_left), ", ".join(_left[:6])))
elif os.path.isdir(_icons_dir):
    info("[图标] mod/icons 已清空，无残留自绘贴图")
if ".dds" in _mod_txt:
    err("[图标] modinfo 仍引用 .dds；改用原版图集后不应再有任何贴图文件")
# 按 XML 节点判断，不能按文本：注释里为了说明「为什么现在不需要它」会提到 ImportFiles
if ET.parse(_modinfo_path).getroot().find(".//ImportFiles") is not None:
    err("[图标] modinfo 仍有 <ImportFiles> 节点；不再自带贴图，该节点应删除")
if "IconTextureAtlases" in _ic_xml:
    err("[图标] %s 里仍有 <IconTextureAtlases>；应只做「名字 → 原版格子」映射" % ICON_XML)

# 13.2 图标名对账：每个名字必须落在原版同款图标的那一格
#      元组含义：(原版参考图标名, 图集, Index)
#      参考值均来自 Base/Assets/UI/Icons/Icons_Units.xml 与 Icons_UnitPortraits.xml，
#      行号见 data/nhs_icons.xml 文件头，可逐条复核。
_EXPECT = {
    # 地图旗帜 + 战争迷雾
    "ICON_UNIT_NHS_RUISHI":       ("ICON_UNIT_AZTEC_EAGLE_WARRIOR",     "ICON_ATLAS_UNITS",     "25"),
    "ICON_UNIT_NHS_RUISHI_WHITE": ("ICON_UNIT_AZTEC_EAGLE_WARRIOR",     "ICON_ATLAS_UNITS",     "25"),
    "ICON_UNIT_NHS_RUISHI_FOW":   ("ICON_UNIT_AZTEC_EAGLE_WARRIOR_FOW", "ICON_ATLAS_UNITS_FOW", "25"),
    "ICON_UNIT_NHS_SCOUT":        ("ICON_UNIT_SCOUT",                   "ICON_ATLAS_UNITS",     "19"),
    "ICON_UNIT_NHS_SCOUT_WHITE":  ("ICON_UNIT_SCOUT",                   "ICON_ATLAS_UNITS",     "19"),
    "ICON_UNIT_NHS_SCOUT_FOW":    ("ICON_UNIT_SCOUT_FOW",               "ICON_ATLAS_UNITS_FOW", "19"),
    # 立绘：通用图集（全档 256/200/95/70/50/38）
    "ICON_UNIT_NHS_RUISHI_PORTRAIT":
        ("ICON_UNIT_AZTEC_EAGLE_WARRIOR_PORTRAIT", "ICON_ATLAS_UNIT_PORTRAITS", "23"),
    "ICON_UNIT_NHS_RUISHI_PORTRAIT_ERA_ANCIENT":
        ("ICON_UNIT_AZTEC_EAGLE_WARRIOR_PORTRAIT", "ICON_ATLAS_UNIT_PORTRAITS", "23"),
    "ICON_UNIT_NHS_SCOUT_PORTRAIT":
        ("ICON_UNIT_SCOUT_PORTRAIT", "ICON_ATLAS_UNIT_PORTRAITS", "17"),
    "ICON_UNIT_NHS_SCOUT_PORTRAIT_ERA_ANCIENT":
        ("ICON_UNIT_SCOUT_PORTRAIT", "ICON_ATLAS_UNIT_PORTRAITS", "17"),
    # 立绘：亚洲民族性图集（只有 70/95 两档，原版中国单位同样走它，引擎自行缩放）
    "ICON_ETHNICITY_ASIAN_UNIT_NHS_RUISHI_PORTRAIT":
        ("ICON_ETHNICITY_ASIAN_UNIT_AZTEC_EAGLE_WARRIOR_PORTRAIT",
         "ICON_ATLAS_ASIAN_UNIT_PORTRAITS", "23"),
    "ICON_ETHNICITY_ASIAN_UNIT_NHS_RUISHI_PORTRAIT_ERA_ANCIENT":
        ("ICON_ETHNICITY_ASIAN_UNIT_AZTEC_EAGLE_WARRIOR_PORTRAIT",
         "ICON_ATLAS_ASIAN_UNIT_PORTRAITS", "23"),
    "ICON_ETHNICITY_ASIAN_UNIT_NHS_SCOUT_PORTRAIT":
        ("ICON_ETHNICITY_ASIAN_UNIT_SCOUT_PORTRAIT", "ICON_ATLAS_ASIAN_UNIT_PORTRAITS", "17"),
    "ICON_ETHNICITY_ASIAN_UNIT_NHS_SCOUT_PORTRAIT_ERA_ANCIENT":
        ("ICON_ETHNICITY_ASIAN_UNIT_SCOUT_PORTRAIT", "ICON_ATLAS_ASIAN_UNIT_PORTRAITS", "17"),
}

def _parse_icon_defs(text):
    return {m[0]: (m[1], m[2]) for m in re.findall(
        r'<Row\s+Name="([^"]+)"\s+Atlas="([^"]+)"\s+Index="(\d+)"', text)}

if _ic_xml:
    _defined = _parse_icon_defs(_ic_xml)
    for _name, (_twin, _atlas, _idx) in _EXPECT.items():
        if _name not in _defined:
            err("[图标] IconDefinitions 缺 %s（旗帜/立绘会落到空框）" % _name)
        elif _defined[_name] != (_atlas, _idx):
            err("[图标] %s 指向 %s/%s，应为 %s/%s"
                % (_name, _defined[_name][0], _defined[_name][1], _atlas, _idx))

    # 与实际游戏文件对账：确认参考图标真的就在那一格（防「照记忆写索引」）
    _vanilla = {}
    for _f in (_UNITS_ICONS, _PORTRAIT_ICONS):
        if os.path.exists(_f):
            _vanilla.update(_parse_icon_defs(open(_f, encoding="utf-8").read()))
    if _vanilla:
        _bad = []
        for _name, (_twin, _atlas, _idx) in _EXPECT.items():
            if _twin not in _vanilla:
                _bad.append("%s（原版无 %s）" % (_name, _twin))
            elif _vanilla[_twin] != (_atlas, _idx):
                _bad.append("%s（原版 %s 实为 %s/%s）"
                            % (_name, _twin, _vanilla[_twin][0], _vanilla[_twin][1]))
        if _bad:
            err("[图标] 与游戏本体不符：%s" % "；".join(_bad[:4]))
        else:
            info("[图标] %d 个图标名与游戏本体逐条对账一致（锐士=鹰武士 / 斥候=侦察兵）"
                 % len(_EXPECT))
    else:
        warn("[图标] 未找到游戏目录（%s），跳过与原版图标的对账；本次仅按内置期望表校验"
             % GAME_DIR)

    # 中国民族性是 ETHNICITY_ASIAN（DebugGameplay.sqlite 实测），写错则首选名永远查不到
    if "ICON_ETHNICITY_ASIAN_UNIT_NHS_RUISHI_PORTRAIT" not in _ic_xml:
        warn("[图标] 未登记 ETHNICITY_ASIAN 前缀的立绘名，将只能走回退链")

# ---------- 14. 文案与新增特征的对账（v24）----------
#   农场相邻加成的说明文本由 nhs_01_core.sql 的 Description 参数点名引用，
#   少一份就显示裸 tag（"LOC_NHS_DISTRICT_FARM_FAITH"）。
for _tag, _pat in (("LOC_NHS_DISTRICT_FARM_FAITH", r'<Row\s+Tag="LOC_NHS_DISTRICT_FARM_FAITH"'),
                   ("LOC_NHS_DISTRICT_FARM_FAITH(zh)", r'<Replace\s+Tag="LOC_NHS_DISTRICT_FARM_FAITH"\s+Language="zh_Hans_CN"')):
    if re.search(_pat, _text_text):
        info("[文案] 已提供 %s" % _tag)
    else:
        err("[文案] text/nhs_text.xml 缺 %s；圣地面板会显示裸 tag" % _tag)
if "{1_num}" not in _text_text:
    warn("[文案] 农场相邻的说明里没有 {1_num} 占位符；数值不会随 Amount 变化")

# 正文里必须真的写了"农场 +1 信仰"，否则玩家看不到这条新特征
if "农场相邻" not in _text_text:
    err("[文案] 主特性描述里没有提「农场相邻」，新特征在界面上不可见")

# ---------- 15. 出生地关联（v7.27 / nhs_15_start_bias.sql）----------
#   这份偏置只在**开新局的地图生成阶段**被 AssignStartingPlots.lua 读取，
#   平时不进游戏库、界面上也无从验证，所以静态校验是唯一能提前拦住错误的地方。
#   四条硬约束（每条都对应一次"静默失效"）：
#     ① 表里只有 CivilizationType 这一种作用主体——写成 LeaderType 会 no such column
#     ② 冻土与平原必须同一 Tier，分轮则后一轮被前一轮的候选收敛架空
#     ③ 河流必须与地形同 Tier，Rivers 排在 Terrains 之后才能"再筛一遍靠河"
#     ④ 地形名必须与 Terrains 表逐字相同，写错不报错、只是永远不计分
_BIAS_SQL = "sql/nhs_15_start_bias.sql"
_bias_src = raw.get(_BIAS_SQL, "")
_bias_code = strip_comments(_bias_src)

if not _bias_src:
    err("[出生] 缺少 %s" % _BIAS_SQL)
else:
    info("[出生] 文件存在: %s" % _BIAS_SQL)

    # ① 作用主体只能是 CivilizationType
    if re.search(r"LeaderType", _bias_code):
        err("[出生] SQL 里出现了 LeaderType；StartBias* 四张表没有这一列，"
            "执行会报 no such column，出生偏置完全失效")
    else:
        info("[出生] 只用 CivilizationType 作作用主体（该表无 LeaderType 列）")

    # ②③ 地形与河流
    if "StartBiasTerrains" in _bias_code:
        info("[出生] 已写入 StartBiasTerrains")
    else:
        err("[出生] 没有写 StartBiasTerrains，冻土/平原偏置不会存在")
    if "StartBiasRivers" in _bias_code:
        info("[出生] 已写入 StartBiasRivers")
    else:
        err("[出生] 没有写 StartBiasRivers，靠河这条不会生效")

    # 四类地形必须齐（含丘陵变体：3 环统计只认完全相同的字符串）
    for _t in ("TERRAIN_TUNDRA", "TERRAIN_TUNDRA_HILLS",
               "TERRAIN_PLAINS", "TERRAIN_PLAINS_HILLS"):
        if re.search(r"'(%s)'" % _t, _bias_code):
            info("[出生] 地形已列出: %s" % _t)
        else:
            err("[出生] 缺地形 %s；3 环统计会漏掉这整类地块" % _t)

    # ② 同一 Tier：抓住所有地形行末尾的 Tier 数字
    _tier_vals = {int(m.group(1)) for m in re.finditer(
        r"'TERRAIN_[A-Z_]+'\s*,\s*(\d+)\s*\)", _bias_code)}
    if _tier_vals == {1}:
        info("[出生] 四类地形同为 Tier 1（合并进同一个打分集合）")
    elif not _tier_vals:
        err("[出生] 解析不到地形行的 Tier 值，无法确认同轮；请检查 VALUES 写法")
    else:
        err("[出生] 地形 Tier 不统一：%s。分轮会让后一轮失效——"
            "前一轮可能已把候选收敛到 1 个点" % sorted(_tier_vals))

    # ③ 河流 Tier 必须落在同一集合里
    _m_rv = re.search(r"INSERT[^;]*StartBiasRivers[^;]*?VALUES\s*\([^)]*?,\s*(\d+)\s*\)",
                      _bias_code, re.S)
    if _m_rv:
        _rv_tier = int(_m_rv.group(1))
        if _rv_tier in _tier_vals:
            info("[出生] 河流 Tier=%d 与地形同轮，能在排序结果上再筛靠河" % _rv_tier)
        else:
            err("[出生] 河流 Tier=%d 与地形 %s 不同；Rivers 排在 Terrains 之后，"
                "不同轮等于白写" % (_rv_tier, sorted(_tier_vals)))
    else:
        err("[出生] 解析不到 StartBiasRivers 的 Tier 值")

# modinfo 必须挂上这一层，否则文件在磁盘、SQL 不执行
if _BIAS_SQL in globals().get("referenced", set()):
    info("[出生] .modinfo 已装载 %s" % _BIAS_SQL)
else:
    err("[出生] .modinfo 未装载 %s；文件存在也不会被执行" % _BIAS_SQL)

# ---------- 16. 平衡旋钮（v7.28 建立 / v7.29 首都产能 1→2 / nhs_16_tuning.sql）----------
#   这一层全是"改一个数字"的动作，最容易犯的不是写错表名，而是两类静默失效：
#     ① UPDATE 的目标行还不存在（nhs_06 的克隆体没生成）→ 命中 0 行、不报错
#        → 经文仍是 +100%，而文件看上去"改过了"
#     ② 挂载目标 trait 写错 → 新增三条 Modifier 成为孤儿行，只有 FK 会拦，
#        但 FK 只在游戏构建库时校验，离线校验器拦不到 → 必须在静态层查名字
#   另外做一次"文案 ↔ 数值"对账：text 里的 +50% 必须与这里的 50 同源，
#   否则玩家看到的说明与实际生效值会漂移（本项目已因文案漂移返工过一次）。
_TUNE_SQL = "sql/nhs_16_tuning.sql"
_tune_src = raw.get(_TUNE_SQL, "")
_tune = strip_comments(_tune_src)

if not _tune_src:
    err("[平衡] 缺少 %s" % _TUNE_SQL)
else:
    info("[平衡] 文件存在: %s" % _TUNE_SQL)

    # ① 圣地建造加速
    if "MODIFIER_PLAYER_CITIES_ADJUST_DISTRICT_PRODUCTION" in _tune:
        info("[平衡] 圣地建造用 MODIFIER_PLAYER_CITIES_ADJUST_DISTRICT_PRODUCTION")
    else:
        err("[平衡] 未找到圣地建造加速的 ModifierType；该 Effect 是唯一可靠的"
            "「区域产能百分比」写法（原版 POLICY_SKY_AND_STARS Amount=30 即 +30%）")
    if "'DistrictType', 'DISTRICT_HOLY_SITE'" in _tune or "'DistrictType','DISTRICT_HOLY_SITE'" in _tune:
        info("[平衡] 加速目标已限定 DISTRICT_HOLY_SITE（不会给别的区域提速）")
    else:
        err("[平衡] 圣地建造加速缺 DistrictType=DISTRICT_HOLY_SITE 参数；"
            "缺了会变成「所有区域 +50%」，直接超模")

    # ② 首都食物 / 产能
    _cap = re.findall(r"MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE", _tune)
    if len(_cap) >= 2:
        info("[平衡] 首都产出用 MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE（%d 处）" % len(_cap))
    else:
        err("[平衡] 首都食物/产能应各有一条 CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE，"
            "实际只找到 %d 处" % len(_cap))
    for _y in ("YIELD_FOOD", "YIELD_PRODUCTION"):
        if _y in _tune:
            info("[平衡] 首都已加 %s" % _y)
        else:
            err("[平衡] 首都缺 %s；前期两样都要，只给一样顶不住冻土" % _y)

    # ③ 经文降温：必须是 UPDATE 且前缀精确
    if re.search(r"UPDATE\s+ModifierArguments[\s\S]{0,160}?SET\s+Value\s*=\s*'50'", _tune, re.I):
        info("[平衡] 经文参数已 UPDATE 为 50（圣地相邻 +50%）")
    else:
        err("[平衡] 未找到「UPDATE ModifierArguments SET Value='50'」；经文仍是 +100%")
    if re.search(r"LIKE\s+'NHS_PL_SCRIPTURE%'", _tune):
        info("[平衡] 经文 UPDATE 用 NHS_PL_SCRIPTURE 前缀限定，不会误伤信条参数")
    else:
        warn("[平衡] 经文 UPDATE 未用 NHS_PL_SCRIPTURE 前缀限定；若用宽前缀可能误伤 NHS_BL_ 下的参数")

    # ④ 人类门槛与挂载目标
    if _tune.count("PLAYER_IS_HUMAN") >= 3:
        info("[平衡] 三条新增 Modifier 均带 PLAYER_IS_HUMAN 门槛")
    else:
        err("[平衡] 新增 Modifier 的人类门槛少于 3 处，AI 会吃到首都加成")
    if "TRAIT_NHS_NUCLEAR_HOLY_SITE" in _tune:
        info("[平衡] 新增加成挂到 TRAIT_NHS_NUCLEAR_HOLY_SITE（八威仪结构不变）")
    else:
        err("[平衡] 新增加成没有挂到 TRAIT_NHS_NUCLEAR_HOLY_SITE，会成为孤儿行")

    # ⑤ 执行顺序：TUNING 必须在 BELIEFS 之后，否则 UPDATE 命中 0 行
    try:
        _order = [(e.text or "").strip().replace("\\", "/") for e in tree.iter()
                  if e.tag.rsplit("}", 1)[-1] == "File"]
        if _TUNE_SQL in _order and "sql/nhs_06_beliefs.sql" in _order:
            if _order.index(_TUNE_SQL) > _order.index("sql/nhs_06_beliefs.sql"):
                info("[平衡] modinfo 执行序：nhs_06 → nhs_16（UPDATE 能在克隆体上命中）")
            else:
                err("[平衡] nhs_16 排在 nhs_06 之前！经文 UPDATE 会命中 0 行且不报错，"
                    "等于这一条完全没生效")
    except Exception:
        warn("[平衡] 无法读取 modinfo 的文件顺序，请人工确认 nhs_16 在 nhs_06 之后")

    # ⑥ 文案 ↔ 数值对账
    #    注意 raw{} 只装了 SQL_FILES，文本要单独读盘（这里踩过一次：
    #    用 raw.get(TEXT_FILE) 恒为空串，导致三条断言全部误报"文案未改"）。
    _tp2 = os.path.join(MOD, TEXT_FILE)
    _txt = open(_tp2, encoding="utf-8").read() if os.path.exists(_tp2) else ""
    if "圣地相邻 +50%" in _txt or "+50% Holy Site adjacency" in _txt:
        info("[平衡] 文案已同步为 +50%（与 nhs_16 的 50 同源）")
    else:
        err("[平衡] 文案仍写 +100%；玩家看到的说明与实际生效值不一致")
    # v7.36：口径由「至中世纪为止」改为「30%，文艺复兴起 15%」。
    #   中英必须同时改 —— 只改一种语言时，另一种语言的玩家看到的仍是旧规则。
    _t_zh = "自文艺复兴时代起" in _txt
    _t_en = "falls to 15%" in _txt
    if _t_zh and _t_en:
        info("[平衡] 物勒工名文案已同步为中英「30%，文艺复兴起 15%」")
    elif _t_zh or _t_en:
        err("[平衡] 物勒工名文案只有一种语言改了口径（中/英必须同步）")
    else:
        err("[平衡] 物勒工名文案仍是旧口径（至中世纪为止）；"
            "nhs_09 已放开全时代、nhs_08 已加分档，说明必须同步")
    if "+2 食物" in _txt or "+2 Food" in _txt:
        info("[平衡] 首都新增食物已写入文案")
    else:
        err("[平衡] 首都 +2 食物未写入文案")
    # v7.29：产能由 1 提到 2，三处文案（中/英/描述）必须跟着走，
    #        否则玩家看到的仍是 +1，这与「数值改了但说明没改」是同一类静默错误。
    if "+2 产能" in _txt or "+2 Production" in _txt:
        info("[平衡] 首都新增产能已写入文案（+2）")
    else:
        err("[平衡] 首都 +2 产能未写入文案；数值已由 1 改 2，说明仍是旧值")
    _m_prod = re.search(r"NHS_CAPITAL_PROD'\s*,\s*'Amount'\s*,\s*'(-?\d+)'", _tune)
    if _m_prod is None:
        err("[平衡] nhs_16 里找不到 NHS_CAPITAL_PROD 的 Amount 参数行")
    elif _m_prod.group(1) == "2":
        info("[平衡] NHS_CAPITAL_PROD.Amount = 2（v7.29 值）")
    else:
        err("[平衡] NHS_CAPITAL_PROD.Amount = %s，v7.29 应为 2；"
            "只改文案不改这里等于没改" % _m_prod.group(1))

# ---------- 16b. 剔除「每信徒 +1 产能」（v33）----------
#   这条不是"调数值"，而是"删掉一整条乘数轴"，所以要比对两处：
#     ① nhs_06 的克隆语句必须显式排除 WORK_ETHIC_FOLLOWER_PRODUCTION（源头）
#     ② nhs_16 必须有**未被注释**的三行 DELETE（兜底，且顺序 关联→参数→主表）
#   判断"有没有被注释"必须用 strip_comments 后的文本 —— 纯文本包含会把
#   文件里大段解释性注释中的 "-- DELETE ..." 当成真语句（本项目已误判两次）。
_belief_c = strip_comments(raw.get("sql/nhs_06_beliefs.sql", ""))

if not _belief_c:
    err("[信徒产能] nhs_06_beliefs.sql 为空或读不到")
else:
    if re.search(r"<>\s*'WORK_ETHIC_FOLLOWER_PRODUCTION'", _belief_c):
        info("[信徒产能] nhs_06 克隆语句已排除 WORK_ETHIC_FOLLOWER_PRODUCTION（源头不生成）")
    else:
        err("[信徒产能] nhs_06 未排除 WORK_ETHIC_FOLLOWER_PRODUCTION；"
            "该 Modifier 是「每信徒 +1 产能」，随人口线性增长、无上限，"
            "且门槛为 COLLECTION_ALL_CITIES，连信奉你宗教的 AI 城也吃 —— v33 起必须剔除")
    # 相邻那条必须留着（它才是职业道德的正确效果）
    if "BELIEF_WORK_ETHIC" in _belief_c and not re.search(
            r"<>\s*'WORK_ETHIC_ADJACENCY_PRODUCTION", _belief_c):
        info("[信徒产能] 职业道德的「相邻信仰等量产锤」未被误删（保留）")
    else:
        err("[信徒产能] 职业道德的相邻产线不见了或被误排除；"
            "本次只该砍「信徒」那条，相邻那条要留")

_del_pat = r"DELETE\s+FROM\s+%s\s+WHERE\s+ModifierId\s*=\s*'NHS_BL_WORK_ETHIC_FOLLOWER_PRODUCTION'"
_del_hits = []
for _tbl in ("TraitModifiers", "ModifierArguments", "Modifiers"):
    if re.search(_del_pat % _tbl, _tune, re.I):
        _del_hits.append(_tbl)
if len(_del_hits) == 3:
    info("[信徒产能] nhs_16 有三行启用的 DELETE（关联表 → 参数 → 主表）")
    _pos = [re.search(_del_pat % t, _tune, re.I).start()
            for t in ("TraitModifiers", "ModifierArguments", "Modifiers")]
    if _pos == sorted(_pos):
        info("[信徒产能] DELETE 顺序正确：TraitModifiers → ModifierArguments → Modifiers")
    else:
        warn("[信徒产能] DELETE 顺序不是 关联→参数→主表；外键残留风险")
else:
    err("[信徒产能] nhs_16 启用的 DELETE 只有 %d/3 条（%s）；"
        "要么被注释掉了，要么写错表名 —— 注释文本不会被本检查计入"
        % (len(_del_hits), ",".join(_del_hits) or "无"))

_tp3 = os.path.join(MOD, TEXT_FILE)
_txt2 = open(_tp3, encoding="utf-8").read() if os.path.exists(_tp3) else ""
if "每信徒" in _txt2 and ("剔除" in _txt2 or "已删" in _txt2):
    info("[信徒产能] 文案已注明「每信徒 +1 产能」被剔除")
else:
    warn("[信徒产能] 文案未说明信徒产能已剔除；玩家会按原版职业道德预期估算强度")

# ---------- 17. 冻土农场（v7.30 / nhs_17_last_best_west.sql）----------
#   这一层最容易犯的错不是写错字，而是**用错实现路径**：
#   想让农田能建在冻土上，最直觉的做法是往 Improvement_ValidTerrains 插一行
#   (IMPROVEMENT_FARM, TERRAIN_TUNDRA)。但那张表是全局静态表——一插，
#   所有文明（含 AI）都能建，直接破坏本 mod「只对秦始皇生效」的硬约束。
#   原版唯一正确的做法（加拿大劳雷尔）是走 Modifier：
#     MODIFIER_PLAYER_CITIES_ADJUST_IMPROVEMENT_VALID_TERRAIN
#   全库仅此一例，所以这里既查"该有的都在"，也查"不该写的没写"。
_TUNDRA_SQL = "sql/nhs_17_last_best_west.sql"
_tundra_src = raw.get(_TUNDRA_SQL, "")
_tundra = strip_comments(_tundra_src)

if not _tundra_src:
    err("[冻土农场] 缺少 %s" % _TUNDRA_SQL)
else:
    info("[冻土农场] 文件存在: %s" % _TUNDRA_SQL)

    # ① 必须克隆，不许手抄 26 条 ModifierId
    if re.search(r"INSERT\s+OR\s+IGNORE\s+INTO\s+Modifiers[\s\S]{0,400}?SELECT", _tundra, re.I) \
       or re.search(r"INSERT\s+INTO\s+Modifiers[\s\S]{0,400}?SELECT", _tundra, re.I):
        info("[冻土农场] 用克隆（INSERT ... SELECT）而非手抄 ModifierId")
    else:
        err("[冻土农场] 未见 INSERT ... SELECT 克隆；手抄 26 条 ModifierId 容易敲错且不跟随原版")

    # ② 源 trait 必须是加拿大劳雷尔那条
    if "TRAIT_LEADER_LAST_BEST_WEST" in _tundra:
        info("[冻土农场] 克隆源 = TRAIT_LEADER_LAST_BEST_WEST（加拿大·劳雷尔）")
    else:
        err("[冻土农场] 未引用 TRAIT_LEADER_LAST_BEST_WEST；原版只有这条特性允许冻土建农场")

    # ③ 人类门槛
    if "PLAYER_IS_HUMAN" in _tundra:
        info("[冻土农场] 克隆时统一挂 PLAYER_IS_HUMAN（AI 拿到 trait 也不生效）")
    else:
        err("[冻土农场] 少了 PLAYER_IS_HUMAN；AI 秦始皇会一起吃这套加成")

    # ④ 挂载目标：披荆斩棘（冻土威仪）
    if "TRAIT_NHS_MOTHER_RUSSIA" in _tundra:
        info("[冻土农场] 挂到 TRAIT_NHS_MOTHER_RUSSIA（披荆斩棘），不新增第九个威仪")
    else:
        err("[冻土农场] 没有挂到 TRAIT_NHS_MOTHER_RUSSIA；克隆体会成为孤儿行")

    # ⑤ 反向断言：绝不能直接改全局地形表
    if re.search(r"INSERT\s+(OR\s+IGNORE\s+)?INTO\s+Improvement_ValidTerrains", _tundra, re.I) \
       or re.search(r"UPDATE\s+Improvement_ValidTerrains", _tundra, re.I):
        err("[冻土农场] 直接在改全局表 Improvement_ValidTerrains！"
            "这会让所有文明（含 AI）都能建冻土农场，必须改用 Modifier 方式")
    else:
        info("[冻土农场] 未触碰全局 Improvement_ValidTerrains（加成只对人类秦始皇）")

    # ⑥ 执行序：本文件把克隆体挂到 nhs_04 建的 Trait，必须排在其后
    try:
        _order2 = [(e.text or "").strip().replace("\\", "/") for e in tree.iter()
                   if e.tag.rsplit("}", 1)[-1] == "File"]
        if _TUNDRA_SQL in _order2 and "sql/nhs_04_mother_russia.sql" in _order2:
            if _order2.index(_TUNDRA_SQL) > _order2.index("sql/nhs_04_mother_russia.sql"):
                info("[冻土农场] modinfo 执行序：nhs_04 → nhs_17（挂载目标已存在）")
            else:
                err("[冻土农场] nhs_17 排在 nhs_04 之前！TRAIT_NHS_MOTHER_RUSSIA 还不存在，"
                    "TraitModifiers 插入会被 OR IGNORE 静默吞掉")
        else:
            warn("[冻土农场] modinfo 里没同时找到 nhs_04 与 nhs_17，请人工确认执行序")
    except Exception as e:
        warn("[冻土农场] 无法读取 modinfo 文件顺序（%s）" % e)

    # ⑦ 文案：披荆斩棘这条必须写明可建农场，否则玩家看不到
    _tp3 = os.path.join(MOD, TEXT_FILE)
    _txt3 = open(_tp3, encoding="utf-8").read() if os.path.exists(_tp3) else ""
    if "冻土上可建农场" in _txt3 or "Farms may be built on Tundra" in _txt3:
        info("[冻土农场] 披荆斩棘文案已写明「冻土可建农场」")
    else:
        err("[冻土农场] 文案没提农场；玩家在特性说明里看不到这项能力")

# ---------- 18. 实机加载对账（v7.31）----------
#  文件写对了 ≠ 游戏加载了。Civ6 只在进程启动时解析一次 modinfo 的
#  <InGameActions> 并缓存动作列表；游戏内读档只是重放这份缓存。
#  v7.28~v7.30 三个版本因此全部未生效，且 Database.log / Lua.log 都不报错
#  ——这是本项目最隐蔽的一类失败：文件、断言、离线库全绿，游戏里什么都不变。
#  这里读 Modding.log 对账，只出 WARN（工作区没错，是游戏该重启了）。
try:
    import check_loaded as _cl
    _decl = _cl.declared_files()
    _ts, _loaded = _cl.loaded_blocks()
    if _ts is None:
        warn("[实机] Modding.log 里没有本 mod 的加载记录；可能尚未启用或日志被清空")
    else:
        _have = {r for _, r in _loaded}
        _miss = [f for f in _decl if f not in _have]
        if _miss:
            warn("[实机] 上次启动未加载 %d 个文件：%s。"
                 "SQL 类改动必须「完全退出游戏 → 重启 → 新开一局」，游戏内读档无效。"
                 % (len(_miss), "、".join(_miss)))
        else:
            info("[实机] modinfo 声明的 %d 个文件均已在上次启动时加载" % len(_decl))
        # v34 新增：名字在加载列表里、但文件在此之后被改过 → 游戏跑的是旧内容。
        # 这类假象比"从未加载"更难发现（对账通过、双校验全绿、游戏里不变）。
        _stale = [f for f in _cl.stale_files() if f not in _miss]
        if _stale:
            warn("[实机] %d 个文件加载过但内容已过期（%s）；"
                 "游戏里跑的是改动之前的内容，同样要退出重启"
                 % (len(_stale), "、".join(_stale)))
        else:
            info("[实机] 已加载文件均无「改了但没重启」的过期情况")
except Exception as _e:
    warn("[实机] 加载对账跳过：%s" % _e)

# ---------- 19. 建库顺序（LoadOrder）与实机库对账（v7.35）----------
#  背景：v34 那局 22 个文件全部加载、双校验全绿，但游戏库少了 30 条修饰器：
#    NHS_LBW_*                             26 条（冻土农场整套）
#    NHS_BL_WORK_ETHIC_ADJACENCY_PRODUCTION_2   1 条（勤则不匮的产能转化本体）
#    NHS_MK_*                              离线基线多算 2 条（源在游戏库里本就不存在）
#  根因不是 SQL 写错，是**执行顺序**：官方资料片的 UpdateDatabase 带
#  <LoadOrder>100</LoadOrder>（Expansion2Core 甚至是 -100），而我们没设，默认 0，
#  于是 16 个 SQL 在 Expansion2_Leaders.xml 之前跑完。
#  `INSERT OR IGNORE ... SELECT FROM TraitModifiers WHERE TraitType='...LBW'`
#  在源 trait 还不存在时匹配 0 行，**静默插入 0 条、不报任何错**。
#  教训：离线库是「全 DLC 合并后」再跑我们的 SQL，天然看不到这个顺序问题。
#  所以这里做两件事：
#    A. 静态：每个 UpdateDatabase 组件都必须带 LoadOrder，且大于官方最大值。
#    B. 实机：直接查游戏建出来的 DebugGameplay.sqlite，核对克隆层条数。

_DLC_MAX_LOADORDER = 100   # 实测 DLC/*/*.modinfo 里出现的最大值（另有两处 -100）
_MIN_OUR_LOADORDER = 101

try:
    _mi = os.path.join(MOD, "NuclearHolySite.modinfo")
    _root = ET.parse(_mi).getroot()
    _comps = _root.findall(".//UpdateDatabase")
    if not _comps:
        err("[顺序] modinfo 里找不到任何 UpdateDatabase 组件")
    else:
        _bad = []
        for _c in _comps:
            _cid = _c.get("id") or "?"
            _lo = _c.find("./Properties/LoadOrder")
            if _lo is None or not (_lo.text or "").strip():
                _bad.append("%s(未设→默认0)" % _cid)
                continue
            try:
                _v = int((_lo.text or "").strip())
            except ValueError:
                _bad.append("%s(非整数:%r)" % (_cid, _lo.text))
                continue
            if _v <= _DLC_MAX_LOADORDER:
                _bad.append("%s(=%d)" % (_cid, _v))
        if _bad:
            err("[顺序] %d/%d 个组件未排在官方资料片之后：%s。"
                "官方 DLC 是 LoadOrder=100，默认 0 会让我们在其之前建库，"
                "克隆源 trait/belief 尚不存在 → INSERT...SELECT 静默插入 0 条"
                % (len(_bad), len(_comps), "、".join(_bad)))
        else:
            _vals = sorted({int((c.find("./Properties/LoadOrder").text or "0").strip())
                            for c in _comps})
            info("[顺序] %d 个 UpdateDatabase 组件 LoadOrder=%s，均晚于官方资料片(%d)"
                 % (len(_comps), "/".join(map(str, _vals)), _DLC_MAX_LOADORDER))
        # 组件在 modinfo 里的声明顺序必须让依赖方在后（同 LoadOrder 时按声明顺序执行）
        _order = [c.get("id") for c in _comps]
        for _a, _b, _why in [("NHS_DB_CORE", "NHS_DB_LAST_BEST_WEST", "后者挂到前者的 TRAIT_NHS_*"),
                             ("NHS_DB_MOTHER_RUSSIA", "NHS_DB_LAST_BEST_WEST", "注释声明依赖")]:
            if _a in _order and _b in _order and _order.index(_a) < _order.index(_b):
                info("[顺序] %s 声明在 %s 之前（%s）" % (_a, _b, _why))
            elif _a in _order and _b in _order:
                err("[顺序] %s 排在 %s 之前，但它依赖后者（%s）；"
                    "同 LoadOrder 按声明顺序执行，这会让它读不到源数据"
                    % (_b, _a, _why))
except Exception as _e:
    err("[顺序] modinfo 顺序检查失败：%s" % _e)

# ---- B. 实机库对账：直接看游戏真的建出了什么 ----
#  离线 mod_test.sqlite 是「全 DLC 先合并、再跑我们」的产物，顺序问题在它上面
#  永远不出现。只有游戏自己建的 DebugGameplay.sqlite 能反映真实顺序。
try:
    import sqlite3, glob
    _cache = os.path.join(os.environ.get("LOCALAPPDATA", r"C:\Users\Smart\AppData\Local"),
                          "Firaxis Games", "Sid Meier's Civilization VI", "Cache",
                          "DebugGameplay.sqlite")
    if not os.path.exists(_cache):
        warn("[顺序] 找不到 DebugGameplay.sqlite，实机库对账跳过")
    else:
        _g = sqlite3.connect("file:%s?mode=ro" % _cache.replace("\\", "/"), uri=True)

        def _cnt(sql, *a):
            return _g.execute(sql, a).fetchone()[0]

        # (前缀, 离线应有多少, 说明)
        _EXPECT = [
            ("NHS_LBW_", 26, "冻土农场整套（加拿大 LAST_BEST_WEST，属 Expansion1）"),
            ("NHS_MK_",   None, "国王的修道院（源条数以游戏库为准，只查非空）"),
            ("NHS_BL_",   None, "信条克隆（BELIEF_WORK_ETHIC 属 Expansion2）"),
        ]
        _missing_layers = []
        for _pre, _want, _why in _EXPECT:
            _n = _cnt("SELECT COUNT(*) FROM Modifiers WHERE ModifierId LIKE ?", _pre + "%")
            if _n == 0:
                _missing_layers.append("%s(0 条，%s)" % (_pre, _why))
            elif _want is not None and _n < _want:
                _missing_layers.append("%s(%d/%d，%s)" % (_pre, _n, _want, _why))
            else:
                info("[顺序] 实机库 %s 有 %d 条（%s）" % (_pre, _n, _why))
        # 单条关键项：勤则不匮的产能转化本体
        if _cnt("SELECT COUNT(*) FROM Modifiers WHERE ModifierId=?",
                "NHS_BL_WORK_ETHIC_ADJACENCY_PRODUCTION_2") == 0:
            _missing_layers.append("NHS_BL_WORK_ETHIC_ADJACENCY_PRODUCTION_2(0 条，"
                                   "「勤则不匮」的产能转化完全没生效)")
        if _missing_layers:
            warn("[顺序] 实机库里克隆层有缺失：%s。"
                 "若本轮刚加过 LoadOrder，说明这局仍是旧库 —— 要完全退出 → 重启 → 新开一局；"
                 "若已重开仍有缺，则源 trait/belief 真的不在库里，查其所属 DLC 是否启用"
                 % "；".join(_missing_layers))
        else:
            info("[顺序] 实机库三个克隆层均完整，LoadOrder 生效")
        _g.close()
except Exception as _e:
    warn("[顺序] 实机库对账跳过：%s" % _e)

# ---------- 19b. 帝国规模层（v40 / nhs_18_tech_scaling.sql）----------
#  这一层的静态风险与别层不同：不是「漏写就静默失效」，而是**写错方向会反向生效**。
#  Amount 丢了负号 = 人口越多科研越多；YieldType 写成 YIELD_CULTURE = 扣错产出。
#  两者都能正常入库、也不报任何错，实机只表现为「数值不对」，极难定位。
#  所以这里对符号、产出类型、逐档门槛、累计削减、挂载逐项做文本级钉死；
#  真正的「落库结果」由 run_mod_sql.py 在真实表结构上再查一遍（两层互补）。
#
#  v37 / v38 / v40 的教训（v42 已查明，别再被旧注释误导）：
#  那三轮「实机零效果」不是 effect 不生效，而是**三轮都在老存档上验证** ——
#  Civ6 建局时把玩家已挂载的 modifier 集合写进存档，之后新增的 SQL 只进游戏库、
#  不追溯。v41 探针（三条改成 +20 正值）逐城科研一分未动即为铁证。
#  所以静态校验的作用是「保证新开一局时库里的东西是对的」，而不是证明实机生效。
#  这里的钉死项：负号、产出类型、逐档门槛、累计折扣、挂载、修饰器名真实存在。
_T18 = "sql/nhs_18_tech_scaling.sql"
_t18 = raw.get(_T18, "")
if not _t18:
    err("[规模] 未读到 %s；本层不存在时科技会继续随人口等比膨胀" % _T18)
else:
    # 原版负百分比类型：与巴比伦 TRAIT_SCIENCE_DECREASE（−50% 科研）、
    # 权力下放 DECENTRALIZATION_HIGHPOP_GOLD（−15%，人口≥7 门槛）同形同 effect。
    # v40 的加算固定值 NHS_MOD_CITY_YIELD 是「误判百分比无效」时的过渡写法，已弃用。
    _YMOD = "MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER"
    _TIERS = (("L1", None, -10, None),
              ("L2", "NHS_REQS_CITY_POP_10", -12, "10"),
              ("L3", "NHS_REQS_CITY_POP_16", -8, "16"))

    # Modifiers 声明：L1 三列、L2/L3 四列，一并抓。
    # 第三/四列显式允许 NULL：写成 NULL 时若正则只认 'ABC'，会退化成「少一条声明」，
    # 报错指向「缺档」而不是「Owner 没写」，误导排查方向。
    _decl = {}
    for _m in re.finditer(
            r"'NHS_TECH_SCALE_(L\d)',\s*'([A-Z_0-9]+)',\s*(?:'([A-Z_0-9]+)'|(NULL))"
            r"(?:,\s*(?:'([A-Z_0-9]+)'|(NULL)))?", _t18):
        _decl[_m.group(1)] = (_m.group(2), _m.group(3) or _m.group(4),
                              _m.group(5) or _m.group(6))

    if len(_decl) != 3:
        err("[规模] 未找到三条 NHS_TECH_SCALE_* 的 Modifiers 声明（实得 %d 条）；"
            "三档缺一档，累计折扣就不成立" % len(_decl))
    else:
        info("[规模] 三档 Modifiers 声明齐全（L1 规模税 / L2 大城 / L3 巨型城）")
        for _tag, _sub, _amt, _pop in _TIERS:
            _t, _own, _got_sub = _decl[_tag]
            if _t != _YMOD:
                err("[规模] %s 的修饰器为 %s；应为 %s。v40 的加算固定值"
                    "（NHS_MOD_CITY_YIELD）是误判时的过渡写法，不要再退回"
                    % (_tag, _t, _YMOD))
            if _own != "PLAYER_IS_HUMAN":
                err("[规模] %s 的 Owner 门槛为 %s；必须 PLAYER_IS_HUMAN，"
                    "否则 AI 也吃科研惩罚" % (_tag, _own))
            if _got_sub != _sub:
                err("[规模] %s 的 Subject 门槛为 %s；应为 %s。门槛错位不会报错，"
                    "只会让分档点落在错误的人口数上"
                    % (_tag, _got_sub, _sub if _sub else "None"))
            else:
                info("[规模] %s 门槛正确（%s）"
                     % (_tag, "无门槛·所有城市" if _sub is None else "人口≥%s" % _pop))

    def _amt(_tag):
        _m = re.search(r"\('NHS_TECH_SCALE_%s',\s*'Amount',\s*'([-+]?[0-9.]+)'\)" % _tag, _t18)
        return float(_m.group(1)) if _m else None

    def _yld(_tag):
        _m = re.search(r"\('NHS_TECH_SCALE_%s',\s*'YieldType',\s*'([A-Z_]+)'\)" % _tag, _t18)
        return _m.group(1) if _m else None

    _cum = 0.0
    for _tag, _sub, _amt_want, _pop in _TIERS:
        _a, _y = _amt(_tag), _yld(_tag)
        if _a is None:
            err("[规模] NHS_TECH_SCALE_%s 缺少 Amount 参数" % _tag)
            continue
        _cum += -_a
        if _a >= 0:
            err("[规模] NHS_TECH_SCALE_%s 的 Amount 为 %+g（非负）；正号会把折扣变成加成，"
                "表现是「人口越多科研越多」，与设计完全相反且不报错" % (_tag, _a))
        elif abs(_a - _amt_want) > 1e-9:
            err("[规模] NHS_TECH_SCALE_%s 的 Amount 为 %+g；设计值为 %+g。改数值必须同步 "
                "nhs_18 文件头旋钮表与 nhs_text.xml / modinfo 的文案"
                % (_tag, _a, _amt_want))
        else:
            info("[规模] NHS_TECH_SCALE_%s Amount = %+g%%（累计 −%g%%）" % (_tag, _a, _cum))
        if _y != "YIELD_SCIENCE":
            err("[规模] NHS_TECH_SCALE_%s 的 YieldType 为 %s；必须 YIELD_SCIENCE"
                "（写错会扣文化或产能）" % (_tag, _y))
    if abs(_cum - 30) > 1e-9:
        err("[规模] 三档累计折扣为 −%g%%；设计值 −30%%（v46 从 −53%% 调轻，"
            "目标倍数 1.26）。累计值变了，文件头验算与 nhs_text.xml / modinfo 的文案也全部作废"
            % _cum)

    # 挂载：三条都要出现在 TraitModifiers 里，且目标 trait 是核心 trait。
    for _tag, _sub, _amt_want, _pop in _TIERS:
        if re.search(r"INTO\s+TraitModifiers[\s\S]{0,200}?NHS_TECH_SCALE_%s" % _tag, _t18):
            info("[规模] NHS_TECH_SCALE_%s 已挂载到核心特性" % _tag)
        else:
            err("[规模] NHS_TECH_SCALE_%s 未写入 TraitModifiers；行在库里但没有玩家拿得到，"
                "等于整档失效" % _tag)

    # v37 的旧 ID 必须彻底消失：留着是死代码，后来者会以为它在起作用。
    if re.search(r"NHS_TECH_POP_COST", _t18):
        err("[规模] 文件里仍残留 v37 的 NHS_TECH_POP_COST_* 字样；那个写法实机已证明无效，"
            "留着会让人误以为它在起作用")
    else:
        info("[规模] v37 的 PER_POPULATION 写法已彻底移除（残留在库里只会误导）")

    # 本层只新增，不许 UPDATE 任何已有行：一旦写宽会连带改坏原版同构用例。
    if re.search(r"^\s*UPDATE\s", strip_comments(_t18), re.M):
        err("[规模] 本层出现 UPDATE 语句；该层只应新增 Modifier，"
            "改已有行会波及原版（永乐、权力下放等）数值")
    else:
        info("[规模] 本层纯新增，无 UPDATE（不会误改原版数值）")

    # 机制名拼写核对：修饰器与要求类型必须真实存在于游戏库，拼错不会报错、只会不生效。
    #   v42 的 _YMOD 又是原版类型（MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER），
    #   所以可以也应当拿原版库核对 —— 这是唯一能抓到「类型名拼错」的检查。
    try:
        import sqlite3 as _sq
        _gdb = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "db", "gameplay_verify.sqlite")
        if os.path.exists(_gdb):
            _c = _sq.connect("file:%s?mode=ro" % _gdb.replace("\\", "/"), uri=True)
            for _sql, _label, _val in (
                    ("SELECT COUNT(*) FROM DynamicModifiers WHERE ModifierType=?", "修饰器", _YMOD),
                    ("SELECT COUNT(*) FROM Requirements WHERE RequirementType=?", "要求类型",
                     "REQUIREMENT_CITY_HAS_X_POPULATION"),
                    ("SELECT COUNT(*) FROM RequirementSets WHERE RequirementSetId=?", "需求集",
                     "PLAYER_IS_HUMAN")):
                _n = _c.execute(_sql, (_val,)).fetchone()[0]
                if _n:
                    info("[规模] 游戏库里存在%s：%s" % (_label, _val))
                else:
                    err("[规模] 游戏库里找不到%s %s；拼错时 SQL 不报错，只是永远不生效"
                        % (_label, _val))
            _c.close()
        else:
            warn("[规模] 找不到 db/gameplay_verify.sqlite，跳过修饰器名核对")
    except Exception as _e:
        warn("[规模] 修饰器名核对跳过：%s" % _e)

# ---------- 输出 ----------
print("=" * 76)
print("核动力圣地 Mod · 静态校验报告（秦始皇专属版 / 母亲·修道院·信条·移动·奇观加速）")
print("=" * 76)
print("\n--- INFO (%d) ---" % len(infos))
for m in infos: print("  ·", m)
print("\n--- WARN (%d) ---" % len(warnings))
for m in warnings: print("  ⚠ ", m)
print("\n--- ERROR (%d) ---" % len(errors))
for m in errors: print("  ✗ ", m)
print("\n" + "=" * 76)
if errors:
    print("校验未通过：存在 %d 个结构错误，修复后再交付。" % len(errors))
    sys.exit(1)
else:
    print("静态结构校验通过。注意：这不等于游戏内可运行，实机验证项见 README 第 4 节。")
    sys.exit(0)
