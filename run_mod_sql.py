# -*- coding: utf-8 -*-
"""
run_mod_sql.py —— 在"真实游戏表结构 + 真实游戏数据"的库上执行 mod 的 SQL

这不是静态检查。这是：
  1) 用游戏自带 01_GameplaySchema.sql 建的同构表
  2) 灌入 328 个游戏 XML 的真实数据（42020 行）
  3) 然后逐条执行 mod/sql/*.sql
  4) 再对结果做结构性断言

它仍然不等于"游戏里能跑"（引擎的 C++ 行为、UI、AI 无法模拟），
但能抓出所有"SQL 层面必然报错"的问题：列名错、引用不存在、约束冲突、类型错。

用法：python run_mod_sql.py
"""
import os
import re
import shutil
import sqlite3
import zlib
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DB = os.path.join(ROOT, "db", "gameplay_verify.sqlite")
TST_DB = os.path.join(ROOT, "db", "mod_test.sqlite")
BASELINE = os.path.join(ROOT, "db", "game_types_baseline.txt")


def load_baseline():
    """从游戏真实库导出的白名单读取 KIND_EFFECT / KIND_COLLECTION。
    验证库不灌这些引擎级类型，直接查 Types 会误报。"""
    eff, coll, section = set(), set(), None
    if not os.path.exists(BASELINE):
        return eff, coll
    with open(BASELINE, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s == "[KIND_EFFECT]":
                section = "e"; continue
            if s == "[KIND_COLLECTION]":
                section = "c"; continue
            if section == "e":
                eff.add(s)
            elif section == "c":
                coll.add(s)
    return eff, coll

SQL_FILES = ["nhs_01_core.sql", "nhs_02_advanced.sql",
             "nhs_04_mother_russia.sql", "nhs_05_monasteries.sql", "nhs_06_beliefs.sql",
             "nhs_07_movement.sql", "nhs_08_wonder_boost.sql", "nhs_09_wonder_era.sql",
             "nhs_10_city_names.sql", "nhs_11_roads.sql", "nhs_12_edicts.sql",
             "nhs_13_amenities.sql", "nhs_14_units.sql", "nhs_15_start_bias.sql",
             "nhs_16_tuning.sql", "nhs_17_last_best_west.sql",
             "nhs_18_tech_scaling.sql"]
# v7.3：本地化从 SQL 迁到 XML（UpdateText 通道），不在 SQL_FILES 内
TEXT_FILE = "text/nhs_text.xml"

errors, warns, oks = [], [], []


def ok(m): oks.append(m)
def err(m): errors.append(m)
def warn(m): warns.append(m)


def split_sql(text):
    """按分号切语句，跳过 -- 行注释与 '...' / "..." 字符串"""
    stmts, buf = [], []
    i, n = 0, len(text)
    in_s = None
    while i < n:
        ch = text[i]
        if in_s:
            buf.append(ch)
            if ch == in_s:
                if i + 1 < n and text[i + 1] == in_s:   # 转义的双引号
                    buf.append(text[i + 1]); i += 2; continue
                in_s = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_s = ch; buf.append(ch); i += 1; continue
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == ";":
            s = "".join(buf).strip()
            if s:
                stmts.append(s)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def run_all(conn, verbose=True):
    failures = []
    for fn in SQL_FILES:
        p = os.path.join(ROOT, "mod", "sql", fn)
        if not os.path.exists(p):
            err("[缺失] %s" % fn)
            continue
        with open(p, encoding="utf-8") as f:
            text = f.read()
        stmts = split_sql(text)
        n_ok = 0
        for idx, st in enumerate(stmts):
            try:
                conn.execute(st)
                n_ok += 1
            except Exception as e:
                failures.append((fn, idx, st[:110].replace("\n", " "), str(e)))
        if verbose:
            print("  %-26s %2d/%2d 条执行成功" % (fn, n_ok, len(stmts)))
    conn.commit()
    return failures


def q1(conn, sql, args=()):
    r = conn.execute(sql, args).fetchone()
    return r[0] if r else None


def assert_(cond, good, bad):
    if cond:
        ok(good)
    else:
        err(bad)


def verify(conn):
    # ---- 1. 引用完整性 ----
    bad_type = conn.execute("""
        SELECT DISTINCT m.ModifierType FROM Modifiers m
        WHERE m.ModifierId LIKE 'NHS%'
          AND m.ModifierType NOT IN (SELECT ModifierType FROM DynamicModifiers)
    """).fetchall()
    assert_(not bad_type, "[引用] 所有 NHS Modifier 的 ModifierType 均存在于 DynamicModifiers",
            "[引用] 存在不存在的 ModifierType: %s" % bad_type)

    # v7.3 新增：游戏构建数据库时会校验 DynamicModifiers 的三个字段外键到 Types。
    # 离线验证库没建这些外键，之前漏检，导致实机"加载失败弹窗"。
    # 这里手动补上等价校验：ModifierType 必须注册 KIND_MODIFIER；
    # CollectionType / EffectType 必须存在于 Types。
    bad_dyn_mt = conn.execute("""
        SELECT DISTINCT d.ModifierType FROM DynamicModifiers d
        WHERE d.ModifierType LIKE 'NHS%'
          AND d.ModifierType NOT IN (SELECT Type FROM Types WHERE Kind='KIND_MODIFIER')
    """).fetchall()
    assert_(not bad_dyn_mt, "[外键] 自定义 DynamicModifier 均已在 Types 注册为 KIND_MODIFIER",
            "[外键] 未注册 KIND_MODIFIER 的 ModifierType: %s" % bad_dyn_mt)

    eff_set, coll_set = load_baseline()
    used_coll = [r[0] for r in conn.execute("""
        SELECT DISTINCT CollectionType FROM DynamicModifiers WHERE ModifierType LIKE 'NHS%'
    """)]
    bad_dyn_coll = [x for x in used_coll if x not in coll_set]
    assert_((not bad_dyn_coll) and bool(coll_set),
            "[外键] 自定义 Modifier 的 CollectionType 均存在（基准 %d 个）" % len(coll_set),
            "[外键] 不存在的 CollectionType: %s（基准为空则白名单缺失）" % bad_dyn_coll)

    used_eff = [r[0] for r in conn.execute("""
        SELECT DISTINCT EffectType FROM DynamicModifiers WHERE ModifierType LIKE 'NHS%'
    """)]
    bad_dyn_eff = [x for x in used_eff if x not in eff_set]
    assert_((not bad_dyn_eff) and bool(eff_set),
            "[外键] 自定义 Modifier 的 EffectType 均存在（基准 %d 个）" % len(eff_set),
            "[外键] 不存在的 EffectType: %s（基准为空则白名单缺失）" % bad_dyn_eff)

    bad_req = conn.execute("""
        SELECT DISTINCT r FROM (
            SELECT OwnerRequirementSetId AS r FROM Modifiers WHERE ModifierId LIKE 'NHS%'
            UNION SELECT SubjectRequirementSetId FROM Modifiers WHERE ModifierId LIKE 'NHS%'
        ) WHERE r IS NOT NULL AND r NOT IN (SELECT RequirementSetId FROM RequirementSets)
    """).fetchall()
    assert_(not bad_req, "[引用] 所有 NHS Modifier 引用的 RequirementSet 均存在",
            "[引用] 不存在的 RequirementSet: %s" % bad_req)

    bad_tm = conn.execute("""
        SELECT DISTINCT tm.ModifierId FROM TraitModifiers tm
        WHERE tm.TraitType LIKE 'TRAIT_NHS%'
          AND tm.ModifierId NOT IN (SELECT ModifierId FROM Modifiers)
    """).fetchall()
    assert_(not bad_tm, "[引用] TraitModifiers 引用的 Modifier 均存在",
            "[引用] 悬空 Modifier: %s" % bad_tm)

    bad_trait = conn.execute("""
        SELECT DISTINCT t FROM (
            SELECT TraitType AS t FROM TraitModifiers WHERE TraitType LIKE 'TRAIT_NHS%'
            UNION SELECT TraitType FROM CivilizationTraits WHERE TraitType LIKE 'TRAIT_NHS%'
            UNION SELECT TraitType FROM LeaderTraits WHERE TraitType LIKE 'TRAIT_NHS%'
        ) WHERE t NOT IN (SELECT TraitType FROM Traits)
    """).fetchall()
    assert_(not bad_trait, "[引用] 自定义 Trait 均在 Traits 表中定义",
            "[引用] 未定义 Trait: %s" % bad_trait)

    bad_leader = conn.execute("""
        SELECT DISTINCT LeaderType FROM LeaderTraits
        WHERE TraitType LIKE 'TRAIT_NHS%'
          AND LeaderType NOT IN (SELECT LeaderType FROM Leaders)
    """).fetchall()
    assert_(not bad_leader, "[引用] 发放对象均为真实领袖",
            "[引用] 不存在的领袖: %s" % bad_leader)

    # ---- 2. 人类门槛 ----
    #   v34 起判定放宽一层：OwnerRequirementSetId 不必字面等于 PLAYER_IS_HUMAN，
    #   只要它指向的 Set 里**含** REQUIRES_PLAYER_IS_HUMAN 也算过关。
    #   原因：城市数阶梯要同时满足「是人类」+「至少 N 座城」，而 OwnerRequirementSetId
    #   只能给一个 Set，必须像原版 PLAYER_IS_HIGH_DIFFICULTY_HUMAN 那样组合。
    #   ⚠ 放宽的方向要小心：这里查的是"Set 里有没有那条 Requirement"，
    #   而不是"名字里像不像"，所以只要漏挂 HUMAN 就一定报错。
    no_gate = conn.execute("""
        SELECT COUNT(*) FROM Modifiers m
        WHERE m.ModifierId LIKE 'NHS%'
          AND (
            m.OwnerRequirementSetId IS NULL
            OR (
              m.OwnerRequirementSetId <> 'PLAYER_IS_HUMAN'
              AND NOT EXISTS (
                SELECT 1 FROM RequirementSetRequirements rsr
                WHERE rsr.RequirementSetId = m.OwnerRequirementSetId
                  AND rsr.RequirementId = 'REQUIRES_PLAYER_IS_HUMAN'
              )
            )
          )
    """).fetchone()[0]
    total = q1(conn, "SELECT COUNT(*) FROM Modifiers WHERE ModifierId LIKE 'NHS%'")
    assert_(no_gate == 0, "[门槛] %d 个 NHS Modifier 全部挂 PLAYER_IS_HUMAN（含组合式 Set）" % total,
            "[门槛] 有 %d/%d 个 Modifier 缺少人类门槛" % (no_gate, total))
    indirect = conn.execute("""
        SELECT COUNT(*) FROM Modifiers
        WHERE ModifierId LIKE 'NHS%'
          AND OwnerRequirementSetId IN ('NHS_AMENITY_HUMAN_5CITIES',
                                        'NHS_AMENITY_HUMAN_9CITIES',
                                        'NHS_AMENITY_HUMAN_13CITIES')
    """).fetchone()[0]
    assert_(indirect == 3,
            "[门槛] 3 条城市数阶梯 Modifier 经组合 Set 间接满足人类门槛",
            "[门槛] 城市数阶梯 Modifier 只找到 %d 条（应 3 条），组合 Set 可能没挂上" % indirect)

    # ---- 3. 克隆层实际产出 ----
    n_mr = q1(conn, "SELECT COUNT(*) FROM TraitModifiers WHERE TraitType='TRAIT_NHS_MOTHER_RUSSIA'")
    n_mr_src = q1(conn, "SELECT COUNT(*) FROM TraitModifiers WHERE TraitType='TRAIT_CIVILIZATION_MOTHER_RUSSIA'")
    assert_(n_mr and n_mr > 0, "[克隆] 俄罗斯母亲层克隆到 %d 个 modifier（原版共 %d 个，已排除暴风雪）" % (n_mr, n_mr_src),
            "[克隆] 俄罗斯母亲层没有克隆到任何 modifier")

    n_mk = q1(conn, "SELECT COUNT(*) FROM TraitModifiers WHERE TraitType='TRAIT_NHS_MONASTERIES_KING'")
    n_mk_src = q1(conn, "SELECT COUNT(*) FROM TraitModifiers WHERE TraitType='TRAIT_LEADER_MONASTERIES_KING'")
    assert_(n_mk and n_mk > 0, "[克隆] 国王的修道院层克隆到 %d 个 modifier（原版 %d 个）" % (n_mk, n_mk_src),
            "[克隆] 修道院层没有克隆到任何 modifier（原版 %d 个）" % n_mk_src)

    for tag, pref in (("极光之舞", "NHS_BL_"), ("经文政策", "NHS_PL_")):
        cnt = q1(conn, "SELECT COUNT(*) FROM Modifiers WHERE ModifierId LIKE ?", (pref + "%",))
        assert_(cnt and cnt > 0, "[克隆] %s 克隆到 %d 个 modifier" % (tag, cnt),
                "[克隆] %s 没有克隆到 modifier（前缀 %s）" % (tag, pref))

    # 克隆是否保住了宗教门槛
    need_rel = q1(conn, """
        SELECT COUNT(*) FROM Modifiers m
        WHERE m.ModifierId LIKE 'NHS_BL_%'
          AND m.SubjectRequirementSetId IS NOT NULL
          AND EXISTS (SELECT 1 FROM RequirementSetRequirements rsr
                      JOIN Requirements r ON r.RequirementId = rsr.RequirementId
                      WHERE rsr.RequirementSetId = m.SubjectRequirementSetId
                        AND r.RequirementType = 'REQUIREMENT_CITY_FOLLOWS_RELIGION')
    """)
    if need_rel and need_rel > 0:
        ok("[克隆] %d 个信条克隆保留了 REQUIRES_CITY_FOLLOWS_RELIGION（必须创教信教才生效）" % need_rel)
    else:
        warn("[克隆] 未检出带 CITY_FOLLOWS_RELIGION 的克隆体——信条可能在未创教时也生效")

    # ---- 4. 数值锚点 ----
    anchor = {"YIELD_PRODUCTION": "0", "YIELD_FOOD": "1", "YIELD_FAITH": "2", "YIELD_CULTURE": "1"}
    for y, expect in anchor.items():
        got = q1(conn, """SELECT a.Value FROM ModifierArguments a
                          JOIN Modifiers m ON m.ModifierId = a.ModifierId
                          WHERE m.ModifierId LIKE 'NHS_CITY%' AND a.Name='Amount'
                            AND EXISTS (SELECT 1 FROM ModifierArguments b
                                        WHERE b.ModifierId=a.ModifierId AND b.Name='YieldType' AND b.Value=?)""", (y,))
        assert_(got == expect, "[数值] %s = %s" % (y, got), "[数值] %s = %s，期望 %s" % (y, got, expect))

    # ---- 5. 移动力 ----
    for ut, mid, amt in (("UNIT_SCOUT", "NHS_SCOUT_MOVEMENT", "3"),
                         ("UNIT_SETTLER", "NHS_SETTLER_MOVEMENT", "2")):
        got = q1(conn, "SELECT Value FROM ModifierArguments WHERE ModifierId=? AND Name='Amount'", (mid,))
        assert_(got == amt, "[移动] %s Amount=%s" % (mid, got), "[移动] %s Amount=%s，期望 %s" % (mid, got, amt))
        base = q1(conn, "SELECT BaseMoves FROM Units WHERE UnitType=?", (ut,))
        if base is not None and str(base).isdigit():
            final = int(base) + int(amt)
            assert_(final == 2 * int(base),
                    "[移动] %s 基础 %s + %s = %d（精确翻倍）" % (ut, base, amt, final),
                    "[移动] %s 基础 %s + %s = %d，不是精确翻倍" % (ut, base, amt, final))
        # 单位限定
        req = q1(conn, """SELECT r.RequirementType FROM Modifiers m
                          JOIN RequirementSetRequirements rsr ON rsr.RequirementSetId=m.SubjectRequirementSetId
                          JOIN Requirements r ON r.RequirementId=rsr.RequirementId
                          WHERE m.ModifierId=?""", (mid,))
        assert_(req == "REQUIREMENT_UNIT_TYPE_MATCHES",
                "[移动] %s 用 REQUIREMENT_UNIT_TYPE_MATCHES 限定单位" % mid,
                "[移动] %s 的单位限定异常：%s" % (mid, req))

    # ---- 6. 工人加速 ----
    # v7.36：远古~中世纪 = 本层 15 + 原版秦始皇 15 = 30；
    #        文艺复兴起本层被 NHS_REQ_NOT_RENAISSANCE 关掉 → 只剩原版 15。
    pct = q1(conn, "SELECT Value FROM ModifierArguments WHERE ModifierId='NHS_BUILDER_WONDER_PERCENT' AND Name='Amount'")
    base = q1(conn, "SELECT Value FROM ModifierArguments WHERE ModifierId='TRAIT_BUILDER_WONDER_PERCENT' AND Name='Amount'")
    total_pct = int(pct) + int(base)
    assert_(total_pct == 30,
            "[奇观] 前期加速：本层 %s%% + 原版秦始皇 %s%% = %d%%/次" % (pct, base, total_pct),
            "[奇观] 本层 %s%% + 原版 %s%% = %d%%，期望前期合计 30%%" % (pct, base, total_pct))

    # 时代分档：文艺复兴起降到 15%。这层最容易静默失效 ——
    #   Inverse 写反 → 语义颠倒；Type 列漏写 → 参数可能不被识别；
    #   Set 忘了合并人类门槛 → AI 白拿。三种都不报错，所以逐项查。
    _rtype = q1(conn, "SELECT RequirementType FROM Requirements WHERE RequirementId='NHS_REQ_NOT_RENAISSANCE'")
    _inv = q1(conn, "SELECT Inverse FROM Requirements WHERE RequirementId='NHS_REQ_NOT_RENAISSANCE'")
    assert_(_rtype == "REQUIREMENT_PLAYER_ERA_AT_LEAST" and _inv == 1,
            "[奇观] 分档需求 = PLAYER_ERA_AT_LEAST + Inverse=1（语义：尚未进入该时代）",
            "[奇观] 分档需求异常：type=%s inverse=%s；必须 AT_LEAST+Inverse=1，"
            "写反会变成「文艺复兴之后才 +15%%」" % (_rtype, _inv))

    _earg = q1(conn, "SELECT Value FROM RequirementArguments WHERE RequirementId='NHS_REQ_NOT_RENAISSANCE' AND Name='EraType'")
    _etype = q1(conn, "SELECT Type FROM RequirementArguments WHERE RequirementId='NHS_REQ_NOT_RENAISSANCE' AND Name='EraType'")
    assert_(_earg == "ERA_RENAISSANCE",
            "[奇观] 分档门槛 EraType = ERA_RENAISSANCE（序号 4）",
            "[奇观] 分档门槛 EraType = %s，期望 ERA_RENAISSANCE" % _earg)
    assert_(_etype == "ARGTYPE_IDENTITY",
            "[奇观] 分档参数 Type = ARGTYPE_IDENTITY（与原版一致）",
            "[奇观] 分档参数 Type = %s，期望 ARGTYPE_IDENTITY。注意：漏写该列不算错"
            "（schema 有同值默认），真正的缺陷是写成了别的 Type" % _etype)

    _members = {r[0] for r in conn.execute(
        "SELECT RequirementId FROM RequirementSetRequirements WHERE RequirementSetId='NHS_RS_WONDER_BOOST'")}
    assert_(_members == {"REQUIRES_PLAYER_IS_HUMAN", "NHS_REQ_NOT_RENAISSANCE"},
            "[奇观] NHS_RS_WONDER_BOOST = 人类 且 尚未进文艺复兴（TEST_ALL 两成员齐备）",
            "[奇观] NHS_RS_WONDER_BOOST 成员不对：%s；应为人类门槛 + 时代分档两条" % sorted(_members))

    _ors = q1(conn, "SELECT OwnerRequirementSetId FROM Modifiers WHERE ModifierId='NHS_BUILDER_WONDER_PERCENT'")
    assert_(_ors == "NHS_RS_WONDER_BOOST",
            "[奇观] 百分比 modifier 已挂 NHS_RS_WONDER_BOOST（分档生效）",
            "[奇观] 百分比 modifier 挂的是 %s；若仍为 PLAYER_IS_HUMAN 则全程 30%%" % _ors)

    era = q1(conn, "SELECT MaxEra FROM UnitCommands WHERE CommandType='UNITCOMMAND_WONDER_PRODUCTION'")
    # v7.36：由 3（到中世纪）放开为 -1（不限时代）。原版是 2（远古/古典）。
    #   -1 不是随手写的：表内其余 41 条指令都是 -1，而它们在所有时代都能用，
    #   即 -1 = 不限。填 9 在 era <= MaxEra 下等效，但新增时代会漏。
    assert_(era is not None and int(era) == -1,
            "[奇观] UNITCOMMAND_WONDER_PRODUCTION 的 MaxEra = %s（-1 = 不限时代）" % era,
            "[奇观] MaxEra = %s，期望 -1（不限时代）；若为 3 则文艺复兴之后无法加速，"
            "15%% 那档永远看不到" % era)

    # ---- 6b. 平衡旋钮（v7.28）----
    #   这一层最容易"看着改过、其实没落地"：三条新增 Modifier 若有任一条
    #   只写了 Modifiers 却漏了 ModifierArguments，行会在库里但没有任何参数，
    #   引擎按默认值处理 —— 不报错、也没效果。所以逐项查参数，不只数条数。
    _tune = [
        # (ModifierId, 期望 ModifierType, 额外参数名, 期望值)
        ("NHS_HOLY_SITE_BUILD_FAST", "MODIFIER_PLAYER_CITIES_ADJUST_DISTRICT_PRODUCTION",
         "DistrictType", "DISTRICT_HOLY_SITE"),
        ("NHS_HOLY_SITE_BUILD_FAST", "MODIFIER_PLAYER_CITIES_ADJUST_DISTRICT_PRODUCTION",
         "Amount", "50"),
        ("NHS_CAPITAL_FOOD", "MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE",
         "YieldType", "YIELD_FOOD"),
        ("NHS_CAPITAL_FOOD", "MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE",
         "Amount", "2"),
        ("NHS_CAPITAL_PROD", "MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE",
         "YieldType", "YIELD_PRODUCTION"),
        ("NHS_CAPITAL_PROD", "MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE",
         "Amount", "2"),
        # v48：前期金币旋钮。与上面两条同 ModifierType，只换 YieldType。
        ("NHS_CAPITAL_GOLD", "MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE",
         "YieldType", "YIELD_GOLD"),
        ("NHS_CAPITAL_GOLD", "MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE",
         "Amount", "3"),
    ]
    for mid, mtype, arg, expect in _tune:
        got_t = q1(conn, "SELECT ModifierType FROM Modifiers WHERE ModifierId=?", (mid,))
        assert_(got_t == mtype, "[平衡] %s 类型正确（%s）" % (mid, mtype),
                "[平衡] %s 的 ModifierType 是 %s，期望 %s" % (mid, got_t, mtype))
        got_v = q1(conn, "SELECT Value FROM ModifierArguments WHERE ModifierId=? AND Name=?", (mid, arg))
        assert_(got_v == expect, "[平衡] %s.%s = %s" % (mid, arg, got_v),
                "[平衡] %s.%s = %s，期望 %s（参数缺失时引擎按默认值走，等于没写）"
                % (mid, arg, got_v, expect))

    for mid in ("NHS_HOLY_SITE_BUILD_FAST", "NHS_CAPITAL_FOOD", "NHS_CAPITAL_PROD", "NHS_CAPITAL_GOLD"):
        req = q1(conn, "SELECT OwnerRequirementSetId FROM Modifiers WHERE ModifierId=?", (mid,))
        assert_(req == "PLAYER_IS_HUMAN", "[平衡] %s 挂 PLAYER_IS_HUMAN" % mid,
                "[平衡] %s 的门槛是 %s，AI 会吃到" % (mid, req))
        attached = q1(conn, """SELECT COUNT(*) FROM TraitModifiers
                               WHERE TraitType='TRAIT_NHS_NUCLEAR_HOLY_SITE' AND ModifierId=?""", (mid,))
        assert_(attached == 1, "[平衡] %s 已挂到天命玄鸟" % mid,
                "[平衡] %s 没有挂到 TRAIT_NHS_NUCLEAR_HOLY_SITE，是个孤儿行" % mid)

    # 经文降温：克隆体还在，但 Amount 已由 100 改为 50
    scr = q1(conn, "SELECT Value FROM ModifierArguments WHERE ModifierId LIKE 'NHS_PL_SCRIPTURE%' AND Name='Amount'")
    assert_(scr == "50", "[平衡] 经文克隆体 Amount = %s（圣地相邻 +50%%）" % scr,
            "[平衡] 经文克隆体 Amount = %s，期望 50（100 = 未降温的旧值）" % scr)
    scr_n = q1(conn, "SELECT COUNT(*) FROM Modifiers WHERE ModifierId LIKE 'NHS_PL_SCRIPTURE%'")
    assert_(scr_n == 1, "[平衡] 经文克隆体仍在（%d 条）" % scr_n,
            "[平衡] 经文克隆体不见了（%d 条）；降温不应删掉这一层" % scr_n)

    # ---- 6c. 冻土农场（v7.30 / nhs_17_last_best_west.sql）----
    #   这一层用「克隆原版 trait 的全部 Modifier」实现，风险是**静默为空**：
    #   若原版 TRAIT_LEADER_LAST_BEST_WEST 不存在（缺 GS），
    #   INSERT ... SELECT 会插入 0 行且不报错，mod 里看着有一层、实际什么都没有。
    #   所以先数源、再数克隆体，两边必须相等。
    src_n = q1(conn, """SELECT COUNT(*) FROM Modifiers m
                        JOIN TraitModifiers tm ON tm.ModifierId=m.ModifierId
                        WHERE tm.TraitType='TRAIT_LEADER_LAST_BEST_WEST'""")
    clone_n = q1(conn, "SELECT COUNT(*) FROM Modifiers WHERE ModifierId LIKE 'NHS_LBW_%'")
    assert_(src_n and clone_n == src_n,
            "[冻土农场] 克隆 %s 条（源 %s 条）" % (clone_n, src_n),
            "[冻土农场] 克隆体 %s 条，源 trait 有 %s 条；克隆不完整或源 trait 不存在（缺 GS）"
            % (clone_n, src_n))

    # 参数也要一条不漏：INSERT OR IGNORE ... SELECT 静默丢行是本项目踩过的坑
    src_a = q1(conn, """SELECT COUNT(*) FROM ModifierArguments a
                        JOIN TraitModifiers tm ON tm.ModifierId=a.ModifierId
                        WHERE tm.TraitType='TRAIT_LEADER_LAST_BEST_WEST'""")
    clone_a = q1(conn, "SELECT COUNT(*) FROM ModifierArguments WHERE ModifierId LIKE 'NHS_LBW_%'")
    assert_(src_a and clone_a == src_a,
            "[冻土农场] 参数克隆 %s 条（源 %s 条）" % (clone_a, src_a),
            "[冻土农场] 参数 %s 条，源 %s 条；有 Modifier 没带上参数，引擎会按默认值处理"
            % (clone_a, src_a))

    # 人类门槛：克隆时统一改写为 PLAYER_IS_HUMAN，AI 拿到 trait 也不生效
    no_gate = q1(conn, """SELECT COUNT(*) FROM Modifiers
                          WHERE ModifierId LIKE 'NHS_LBW_%'
                            AND (OwnerRequirementSetId IS NULL
                                 OR OwnerRequirementSetId <> 'PLAYER_IS_HUMAN')""")
    assert_(no_gate == 0, "[冻土农场] 全部克隆体都挂 PLAYER_IS_HUMAN",
            "[冻土农场] %s 条克隆体没挂人类门槛，AI 会吃到" % no_gate)

    # 核心效果：冻土可建农场
    ft = q1(conn, """SELECT ModifierType FROM Modifiers
                     WHERE ModifierId='NHS_LBW_TUNDRA_FARMS'""")
    assert_(ft == "MODIFIER_PLAYER_CITIES_ADJUST_IMPROVEMENT_VALID_TERRAIN",
            "[冻土农场] 走 MODIFIER_PLAYER_CITIES_ADJUST_IMPROVEMENT_VALID_TERRAIN",
            "[冻土农场] TUNDRA_FARMS 的类型是 %s，不是改地形有效性的效果" % ft)
    farm_args = dict(conn.execute("""SELECT Name,Value FROM ModifierArguments
                                     WHERE ModifierId='NHS_LBW_TUNDRA_FARMS'""").fetchall())
    assert_(farm_args.get("ImprovementType") == "IMPROVEMENT_FARM"
            and farm_args.get("TerrainType") == "TERRAIN_TUNDRA",
            "[冻土农场] 参数 = 农场 + 冻土（%s）" % farm_args,
            "[冻土农场] 参数不对：%s（应为 IMPROVEMENT_FARM / TERRAIN_TUNDRA）" % farm_args)

    # 丘陵那条必须保留土木工程门槛（原版如此：工业时代市政）
    hills_subj = q1(conn, """SELECT SubjectRequirementSetId FROM Modifiers
                             WHERE ModifierId='NHS_LBW_TUNDRA_HILLS_FARMS'""")
    assert_(hills_subj == "PLAYER_HAS_CIVIL_ENGINEERING",
            "[冻土农场] 冻土丘陵保留土木工程门槛",
            "[冻土农场] 冻土丘陵的门槛是 %s，应为 PLAYER_HAS_CIVIL_ENGINEERING" % hills_subj)

    # 挂载：全部挂到「披荆斩棘」
    attached = q1(conn, """SELECT COUNT(*) FROM TraitModifiers
                           WHERE TraitType='TRAIT_NHS_MOTHER_RUSSIA'
                             AND ModifierId LIKE 'NHS_LBW_%'""")
    assert_(attached == clone_n,
            "[冻土农场] %s 条全部挂到 TRAIT_NHS_MOTHER_RUSSIA（披荆斩棘）" % attached,
            "[冻土农场] 只挂了 %s / %s 条，其余是孤儿行" % (attached, clone_n))

    # 关键回归：绝不能改全局地形表，否则所有文明（含 AI）都能建冻土农场
    global_row = q1(conn, """SELECT COUNT(*) FROM Improvement_ValidTerrains
                             WHERE ImprovementType='IMPROVEMENT_FARM'
                               AND TerrainType IN ('TERRAIN_TUNDRA','TERRAIN_TUNDRA_HILLS')""")
    assert_(global_row == 0,
            "[冻土农场] 未污染全局 Improvement_ValidTerrains（仍为 4 地形）",
            "[冻土农场] 全局表被写入了 %s 行冻土农场；这会让所有文明都能建，"
            "违背「只对秦始皇生效」的硬约束" % global_row)

    # ---- 7. 本地化（v7.3：改为校验 text/nhs_text.xml，不再查 LocalizedText 表）----
    # 原因：本地化走 UpdateText 通道写入独立的文本库，Gameplay 库里没有
    # LocalizedText 表；原先"在 SQL 里查 LocalizedText"的做法既跑不通也验不到。
    import xml.etree.ElementTree as ET
    tp = os.path.join(ROOT, "mod", TEXT_FILE)
    if not os.path.exists(tp):
        assert_(False, "", "[文案] 本地化文件缺失: %s" % TEXT_FILE)
    else:
        try:
            ttree = ET.parse(tp)
            tags, langs = set(), set()
            bad_lang = []
            for elem in ttree.iter():
                if elem.tag.rsplit("}", 1)[-1] not in ("Row", "Replace"):
                    continue
                t = elem.get("Tag") or ""
                if not t.startswith("LOC_"):
                    continue
                lang = elem.get("Language") or "en_US"
                if lang == "zh_CN":
                    bad_lang.append(t)
                tags.add(t)
                langs.add(lang)
            assert_(len(tags) >= 12,
                    "[文案] XML 已定义 %d 个特性文案 Tag（语言: %s）"
                    % (len(tags), ",".join(sorted(langs))),
                    "[文案] XML 只定义 %d 个 Tag，少于 12" % len(tags))
            assert_(not bad_lang,
                    "[文案] 语言代码合法（简体中文用 zh_Hans_CN）",
                    "[文案] 以下 Tag 用了非法的 zh_CN，游戏不识别: %s" % bad_lang)
        except ET.ParseError as e:
            assert_(False, "", "[文案] %s XML 解析失败: %s" % (TEXT_FILE, e))

    # ---- 7b. 城名替换（v7.6 秦三十六郡 / v7.15 补首都名）----
    n_city = q1(conn, "SELECT COUNT(*) FROM CityNames WHERE CivilizationType='CIVILIZATION_CHINA'")
    assert_(n_city and n_city >= 40,
            "[城名] 中国城名表已替换为 %d 个秦郡名" % (n_city or 0),
            "[城名] 中国城名只有 %s 个，少于 40（nhs_10 未生效或被覆盖）" % n_city)
    first_city = q1(conn, """SELECT CityName FROM CityNames
                             WHERE CivilizationType='CIVILIZATION_CHINA'
                             ORDER BY SortIndex, ID LIMIT 1""")
    assert_(first_city == "LOC_CITY_NAME_QIN_XIANYANG",
            "[城名] CityNames 首项为咸阳（第二座城起生效）",
            "[城名] CityNames 首项是 %s，不是咸阳；SortIndex 或插入顺序有问题" % first_city)

    # 真正的首城名在这里：CivilizationLeaders.CapitalName。
    # 只换 CityNames 时首城仍叫「西安」，v7.15 的 bug 就是漏了这张表。
    cap = q1(conn, """SELECT CapitalName FROM CivilizationLeaders
                      WHERE CivilizationType='CIVILIZATION_CHINA'
                        AND LeaderType='LEADER_QIN'""")
    assert_(cap == "LOC_CITY_NAME_QIN_XIANYANG",
            "[城名] 首都名已改为咸阳（CivilizationLeaders.CapitalName，首城生效）",
            "[城名] 首都名是 %s —— 首城不会走 CityNames，必须改 CivilizationLeaders.CapitalName" % cap)
    stale = [r[0] for r in conn.execute(
        """SELECT LeaderType FROM CivilizationLeaders
           WHERE CivilizationType='CIVILIZATION_CHINA'
             AND CapitalName='LOC_CITY_NAME_XIAN'""")]
    assert_(not stale,
            "[城名] 无中国领袖残留「西安」首都名",
            "[城名] 以下领袖首都仍是西安: %s" % ", ".join(stale))

    if os.path.exists(tp):
        missing = [c for c in
                   [r[0] for r in conn.execute(
                       "SELECT CityName FROM CityNames WHERE CivilizationType='CIVILIZATION_CHINA'")]
                   if c not in tags]
        assert_(not missing,
                "[城名] 全部城名 Tag 都在 %s 有中英文案" % TEXT_FILE,
                "[城名] 以下城名缺文案（界面会显示原始键名）: %s" % missing)

    # ---- 7c. 特色单位（v7.16 锐士 / 斥候）----
    for ut, proto, label in (("UNIT_NHS_RUISHI", "UNIT_WARRIOR", "锐士"),
                             ("UNIT_NHS_SCOUT", "UNIT_SCOUT", "斥候")):
        row = conn.execute(
            """SELECT TraitType, Domain, FormationClass, Cost, Combat, BaseMoves
               FROM Units WHERE UnitType=?""", (ut,)).fetchone()
        assert_(row is not None,
                "[单位] %s（%s）已建立" % (label, ut),
                "[单位] 表里没有 %s，nhs_14 未生效" % ut)
        if row:
            tr, dom, fc, cost, combat, moves = row
            assert_(tr == "TRAIT_NHS_NUCLEAR_HOLY_SITE",
                    "[单位] %s 挂在核心特性（只有秦始皇能造）" % label,
                    "[单位] %s 的 TraitType 是 %s，应为 TRAIT_NHS_NUCLEAR_HOLY_SITE" % (label, tr))
            assert_(dom and fc and cost,
                    "[单位] %s 克隆完整（Domain=%s / Formation=%s / Cost=%s）" % (label, dom, fc, cost),
                    "[单位] %s 克隆有缺列：Domain=%s Formation=%s Cost=%s" % (label, dom, fc, cost))
        rep = q1(conn, "SELECT COUNT(*) FROM UnitReplaces WHERE CivUniqueUnitType=? AND ReplacesUnitType=?",
                 (ut, proto))
        assert_(rep == 1,
                "[单位] %s 已替代 %s" % (label, proto),
                "[单位] %s 未建立对 %s 的替代关系" % (label, proto))
        n_ai = q1(conn, "SELECT COUNT(*) FROM UnitAiInfos WHERE UnitType=?", (ut,))
        assert_(n_ai and n_ai >= 2,
                "[单位] %s 有 %d 条 AI 标签" % (label, n_ai or 0),
                "[单位] %s 的 UnitAiInfos 只有 %s 条，AI 不会使用它" % (label, n_ai))
        n_up = q1(conn, "SELECT COUNT(*) FROM UnitUpgrades WHERE Unit=?", (ut,))
        assert_(n_up and n_up >= 1,
                "[单位] %s 有升级去向" % label,
                "[单位] %s 缺 UnitUpgrades，无法升级" % label)
        # v7.20：分类标签必须覆盖原版全部标签（缺 CLASS_MELEE 会让政策卡与 AI
        # 认不出它）；v7.21 起允许多出白名单里的额外标签（锐士的俘获工人）。
        tags_new = {r[0] for r in conn.execute("SELECT Tag FROM TypeTags WHERE Type=?", (ut,))}
        tags_proto = {r[0] for r in conn.execute("SELECT Tag FROM TypeTags WHERE Type=?", (proto,))}
        extra_allowed = {"UNIT_NHS_RUISHI": {"CLASS_CAPTURE_WORKER"}}.get(ut, set())
        lack = tags_proto - tags_new
        extra = tags_new - tags_proto - extra_allowed
        assert_((not lack) and (not extra) and bool(tags_new),
                "[单位] %s 分类标签覆盖原版（%s）" % (label, "、".join(sorted(tags_new))),
                "[单位] %s 的 TypeTags 是 %s：缺 %s，多出未登记的 %s"
                % (label, sorted(tags_new), sorted(lack) or "无", sorted(extra) or "无"))

    # 斥候的移动力走 modifier（nhs_07 的机制不是改 BaseMoves，克隆单位吃不到）
    base_moves = q1(conn, "SELECT BaseMoves FROM Units WHERE UnitType='UNIT_NHS_SCOUT'")
    assert_(base_moves == 3,
            "[单位] 斥候基础移动 3（与原版侦察兵一致，加成走 modifier 而非改基数）",
            "[单位] 斥候 BaseMoves 是 %s，应为 3；若已硬改成 6，会与筚路蓝缕的 +3 叠加成 9" % base_moves)
    mv = conn.execute(
        """SELECT ModifierType, SubjectRequirementSetId FROM Modifiers
           WHERE ModifierId='NHS_UNIQUE_SCOUT_MOVEMENT'""").fetchone()
    assert_(mv is not None,
            "[单位] 斥候移动修饰 NHS_UNIQUE_SCOUT_MOVEMENT 已建立",
            "[单位] 缺 NHS_UNIQUE_SCOUT_MOVEMENT，斥候只有 3 移动（侦察兵那条门槛匹配不到新单位）")
    if mv:
        assert_(mv[0] == "MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT",
                "[单位] 斥候移动修饰类型正确",
                "[单位] 斥候移动修饰的 ModifierType 是 %s" % mv[0])
        assert_(mv[1] == "NHS_REQSET_UNIT_NHS_SCOUT",
                "[单位] 斥候移动修饰只作用于斥候（门槛收窄）",
                "[单位] 斥候移动修饰的 SubjectRequirementSet 是 %s，会误加给其他单位" % mv[1])
    mv_amt = q1(conn, "SELECT Value FROM ModifierArguments WHERE ModifierId='NHS_UNIQUE_SCOUT_MOVEMENT' AND Name='Amount'")
    assert_(mv_amt == "3",
            "[单位] 斥候移动加成 +3（3 → 6）",
            "[单位] 斥候移动 Amount 是 %s，应为 3" % mv_amt)
    mv_req = q1(conn, """SELECT ra.Value FROM RequirementSetRequirements rsr
                         JOIN RequirementArguments ra ON ra.RequirementId=rsr.RequirementId
                         WHERE rsr.RequirementSetId='NHS_REQSET_UNIT_NHS_SCOUT'
                           AND ra.Name='UnitType'""")
    assert_(mv_req == "UNIT_NHS_SCOUT",
            "[单位] 斥候移动门槛指向 UNIT_NHS_SCOUT",
            "[单位] 斥候移动门槛指向 %s，应为 UNIT_NHS_SCOUT" % mv_req)
    mv_trait = q1(conn, "SELECT COUNT(*) FROM TraitModifiers WHERE TraitType='TRAIT_NHS_SWIFT_PIONEERS' AND ModifierId='NHS_UNIQUE_SCOUT_MOVEMENT'")
    assert_(mv_trait == 1,
            "[单位] 斥候移动修饰挂在筚路蓝缕（TRAIT_NHS_SWIFT_PIONEERS）",
            "[单位] 斥候移动修饰未挂到 TRAIT_NHS_SWIFT_PIONEERS")
    war_combat = q1(conn, "SELECT Combat FROM Units WHERE UnitType='UNIT_NHS_RUISHI'")
    assert_(war_combat == 20,
            "[单位] 锐士战力 20（与勇士一致；加强只体现在俘获工人，不动数值）",
            "[单位] 锐士战力是 %s，与设计的 20 不符" % war_combat)

    # ---- 7.2 锐士的「击敌获工」（v7.21）：标签 → 能力 → 修饰，三层都要通 ----
    cap_tag = q1(conn, "SELECT COUNT(*) FROM TypeTags WHERE Type='UNIT_NHS_RUISHI' AND Tag='CLASS_CAPTURE_WORKER'")
    assert_(cap_tag == 1,
            "[单位] 锐士带 CLASS_CAPTURE_WORKER（击敌可俘获建造者）",
            "[单位] 锐士缺 CLASS_CAPTURE_WORKER，击败敌人不会俘获工人")
    cap_vocab = q1(conn, "SELECT Vocabulary FROM Tags WHERE Tag='CLASS_CAPTURE_WORKER'")
    assert_(cap_vocab == "ABILITY_CLASS",
            "[单位] CLASS_CAPTURE_WORKER 是能力类别标签（Vocabulary=%s），认领即得能力" % cap_vocab,
            "[单位] CLASS_CAPTURE_WORKER 的 Vocabulary 是 %s，挂上去换不来能力" % cap_vocab)
    cap_mod = q1(conn, """SELECT uam.ModifierId FROM TypeTags tt
                          JOIN UnitAbilityModifiers uam ON uam.UnitAbilityType=tt.Type
                          WHERE tt.Tag='CLASS_CAPTURE_WORKER' AND tt.Type LIKE 'ABILITY_%'""")
    assert_(cap_mod == "CAPTURE_COMBAT_UNITS_AS_WORKERS",
            "[单位] 该标签换来的能力挂 CAPTURE_COMBAT_UNITS_AS_WORKERS（%s）" % cap_mod,
            "[单位] 能力→修饰链断了：拿到的是 %s" % cap_mod)
    cap_unit = q1(conn, "SELECT Value FROM ModifierArguments WHERE ModifierId='CAPTURE_COMBAT_UNITS_AS_WORKERS' AND Name='UnitType'")
    assert_(cap_unit == "UNIT_BUILDER",
            "[单位] 俘获产物是 UNIT_BUILDER（建造者）",
            "[单位] 俘获产物是 %s，应为 UNIT_BUILDER" % cap_unit)

    # ---- 8. 秦始皇专属（v7 核心约束）----
    # 8.1 七层 trait 必须全部挂到 LEADER_QIN
    NHS_TRAITS = ["TRAIT_NHS_NUCLEAR_HOLY_SITE", "TRAIT_NHS_MOTHER_RUSSIA",
                  "TRAIT_NHS_MONASTERIES_KING", "TRAIT_NHS_BELIEFS",
                  "TRAIT_NHS_SWIFT_PIONEERS", "TRAIT_NHS_MASTER_BUILDER",
                  "TRAIT_NHS_IMPERIAL_ROAD", "TRAIT_NHS_EDICTS"]
    for tr in NHS_TRAITS:
        n = q1(conn, "SELECT COUNT(*) FROM LeaderTraits WHERE TraitType=? AND LeaderType='LEADER_QIN'", (tr,))
        assert_(n == 1, "[专属] %s 已挂到 LEADER_QIN" % tr,
                "[专属] %s 未挂到 LEADER_QIN（秦始皇拿不到这一层）" % tr)

    # 8.2 不得发给任何文明（CivilizationTraits 必须为 0 行）
    n_civ = q1(conn, "SELECT COUNT(*) FROM CivilizationTraits WHERE TraitType LIKE 'TRAIT_NHS%'")
    assert_(n_civ == 0, "[专属] 没有任何文明被直接发放 NHS trait（只走领袖）",
            "[专属] 仍有 %d 行 CivilizationTraits 发放，mod 会对别的文明生效！" % n_civ)

    # 8.3 除秦始皇外，任何领袖都不该拿到
    others = conn.execute("""
        SELECT LeaderType, COUNT(*) FROM LeaderTraits
        WHERE TraitType LIKE 'TRAIT_NHS%' AND LeaderType <> 'LEADER_QIN'
        GROUP BY LeaderType
    """).fetchall()
    assert_(not others, "[专属] 除秦始皇外无其他领袖获得（AI 全部拿不到）",
            "[专属] 下列领袖也获得了 NHS trait: %s" % others)

    # 8.4 LEADER_QIN 确实存在（防拼写错误导致整段静默失效）
    n_qin = q1(conn, "SELECT COUNT(*) FROM Leaders WHERE LeaderType='LEADER_QIN'")
    assert_(n_qin == 1, "[专属] LEADER_QIN 在 Leaders 表中存在（拼写正确）",
            "[专属] Leaders 表中找不到 LEADER_QIN，领袖 ID 可能拼错")

    # ---- 8b. 驰道层（v7.7：新建城市自动连通首都）----
    road = conn.execute("""
        SELECT m.ModifierType, m.OwnerRequirementSetId, d.CollectionType, d.EffectType
        FROM Modifiers m LEFT JOIN DynamicModifiers d ON d.ModifierType = m.ModifierType
        WHERE m.ModifierId = 'NHS_ROAD_TO_CAPITAL'
    """).fetchone()
    if not road:
        assert_(False, "", "[驰道] 找不到 Modifier NHS_ROAD_TO_CAPITAL（nhs_11_roads.sql 未执行）")
    else:
        mt, owner_req, coll, eff = road
        assert_(mt == "MODIFIER_PLAYER_CITIES_GRANT_ROAD_TO_CAPITAL",
                "[驰道] 复用原版 ModifierType MODIFIER_PLAYER_CITIES_GRANT_ROAD_TO_CAPITAL（同罗马）",
                "[驰道] ModifierType 是 %s，不是原版罗马那个" % mt)
        assert_(eff == "EFFECT_GRANT_CITY_ROAD_TO_CAPITAL",
                "[驰道] 效应为 EFFECT_GRANT_CITY_ROAD_TO_CAPITAL（Types 已注册）",
                "[驰道] 效应是 %s，Types 里可能没有这个 Effect" % eff)
        assert_(coll == "COLLECTION_PLAYER_CITIES",
                "[驰道] 收集类型 COLLECTION_PLAYER_CITIES",
                "[驰道] 收集类型是 %s，不是逐城生效" % coll)
        assert_(owner_req == "PLAYER_IS_HUMAN",
                "[驰道] 已加 PLAYER_IS_HUMAN 人类门槛",
                "[驰道] 未加人类门槛（当前 %s），AI 也会铺路" % owner_req)
        n_arg = q1(conn, "SELECT COUNT(*) FROM ModifierArguments WHERE ModifierId='NHS_ROAD_TO_CAPITAL'")
        assert_(n_arg == 0,
                "[驰道] 无参数（原版该 Modifier 本身不需要参数）",
                "[驰道] 多写了 %d 个参数，原版该 Modifier 不吃参数" % n_arg)
        n_trait = q1(conn, """SELECT COUNT(*) FROM TraitModifiers
                              WHERE TraitType='TRAIT_NHS_IMPERIAL_ROAD'
                                AND ModifierId='NHS_ROAD_TO_CAPITAL'""")
        assert_(n_trait == 1, "[驰道] 已挂到 TRAIT_NHS_IMPERIAL_ROAD",
                "[驰道] TraitModifiers 里没有挂载关系")

    # ---- 8c. 法令一统（v7.8：开局 +1 通配符政策槽）----
    slot = conn.execute("""
        SELECT m.ModifierType, m.OwnerRequirementSetId, d.CollectionType, d.EffectType
        FROM Modifiers m LEFT JOIN DynamicModifiers d ON d.ModifierType = m.ModifierType
        WHERE m.ModifierId = 'NHS_WILDCARD_SLOT'
    """).fetchone()
    if not slot:
        assert_(False, "", "[法令] 找不到 Modifier NHS_WILDCARD_SLOT（nhs_12_edicts.sql 未执行）")
    else:
        smt, sowner, scoll, seff = slot
        assert_(smt == "MODIFIER_PLAYER_CULTURE_ADJUST_GOVERNMENT_SLOTS_MODIFIER",
                "[法令] 复用原版 ModifierType（同希腊柏拉图理想国）",
                "[法令] ModifierType 是 %s，不是原版希腊那个" % smt)
        assert_(seff == "EFFECT_ADJUST_PLAYER_GOVERNMENT_SLOT_TYPE",
                "[法令] 效应为 EFFECT_ADJUST_PLAYER_GOVERNMENT_SLOT_TYPE",
                "[法令] 效应是 %s，Types 里可能没有这个 Effect" % seff)
        assert_(scoll == "COLLECTION_OWNER",
                "[法令] 收集类型 COLLECTION_OWNER（只作用于玩家本人）",
                "[法令] 收集类型是 %s，可能扩散到其他玩家" % scoll)
        assert_(sowner == "PLAYER_IS_HUMAN",
                "[法令] 已加 PLAYER_IS_HUMAN 人类门槛",
                "[法令] 未加人类门槛（当前 %s），AI 也会多一个槽" % sowner)
        sargs = dict(conn.execute(
            "SELECT Name, Value FROM ModifierArguments WHERE ModifierId='NHS_WILDCARD_SLOT'").fetchall())
        assert_(sargs.get("GovernmentSlotType") == "SLOT_WILDCARD",
                "[法令] 槽位类型为 SLOT_WILDCARD（通配符）",
                "[法令] 槽位类型是 %s，不是通配符" % sargs.get("GovernmentSlotType"))
        assert_(len(sargs) == 1,
                "[法令] 只传 1 个参数（数量沿用该 Effect 默认值 1）",
                "[法令] 传输了 %d 个参数：%s" % (len(sargs), sorted(sargs)))
        n_edict = q1(conn, """SELECT COUNT(*) FROM TraitModifiers
                              WHERE TraitType='TRAIT_NHS_EDICTS'
                                AND ModifierId='NHS_WILDCARD_SLOT'""")
        assert_(n_edict == 1, "[法令] 已挂到 TRAIT_NHS_EDICTS",
                "[法令] TraitModifiers 里没有挂载关系")

    # ---------- 宜居度层（v13 / nhs_13_amenities.sql）----------
    am = conn.execute("""
        SELECT m.ModifierType, m.OwnerRequirementSetId, m.SubjectRequirementSetId,
               d.CollectionType, d.EffectType
        FROM Modifiers m LEFT JOIN DynamicModifiers d ON d.ModifierType = m.ModifierType
        WHERE m.ModifierId = 'NHS_CITY_AMENITY'
    """).fetchone()
    if not am:
        assert_(False, "", "[宜居] 找不到 Modifier NHS_CITY_AMENITY（nhs_13_amenities.sql 未执行）")
    else:
        amt, aowner, asub, acoll, aeff = am
        assert_(aeff == "EFFECT_ADJUST_POLICY_AMENITY",
                "[宜居] 每城宜居度用原版 EFFECT_ADJUST_POLICY_AMENITY（同数字民主政体）",
                "[宜居] 效应是 %s，Types 里可能没有这个 Effect" % aeff)
        assert_(acoll == "COLLECTION_PLAYER_CITIES",
                "[宜居] 收集类型 COLLECTION_PLAYER_CITIES",
                "[宜居] 收集类型是 %s" % acoll)
        assert_(aowner == "PLAYER_IS_HUMAN",
                "[宜居] 每城宜居度已加 PLAYER_IS_HUMAN 门槛",
                "[宜居] 未加人类门槛（当前 %s），AI 也吃得到" % aowner)
        assert_(asub is None,
                "[宜居] 每城宜居度未挂 SubjectRequirement（全城生效）",
                "[宜居] 意外挂了 SubjectRequirement %s，会收窄范围" % asub)
        aargs = dict(conn.execute(
            "SELECT Name, Value FROM ModifierArguments WHERE ModifierId='NHS_CITY_AMENITY'").fetchall())
        assert_(aargs.get("Amount") == "1",
                "[宜居] 每城 Amount=1",
                "[宜居] Amount=%s，与文件头标注的 +1 不符" % aargs.get("Amount"))

    hs = conn.execute("""
        SELECT m.ModifierType, m.OwnerRequirementSetId, m.SubjectRequirementSetId,
               d.CollectionType, d.EffectType
        FROM Modifiers m LEFT JOIN DynamicModifiers d ON d.ModifierType = m.ModifierType
        WHERE m.ModifierId = 'NHS_HOLY_SITE_AMENITY'
    """).fetchone()
    if not hs:
        assert_(False, "", "[宜居] 找不到 Modifier NHS_HOLY_SITE_AMENITY（nhs_13_amenities.sql 未执行）")
    else:
        hmt, howner, hsub, hcoll, heff = hs
        assert_(heff == "EFFECT_ADJUST_DISTRICT_AMENITY",
                "[宜居] 圣地宜居度用原版 EFFECT_ADJUST_DISTRICT_AMENITY（同河神信条）",
                "[宜居] 效应是 %s" % heff)
        assert_(hcoll == "COLLECTION_CITY_DISTRICTS",
                "[宜居] 收集类型 COLLECTION_CITY_DISTRICTS",
                "[宜居] 收集类型是 %s" % hcoll)
        assert_(hsub == "DISTRICT_IS_HOLY_SITE",
                "[宜居] 已收窄到原版 reqset DISTRICT_IS_HOLY_SITE（只对圣地生效）",
                "[宜居] SubjectRequirement 是 %s，会导致非圣地区域也加宜居度" % hsub)
        n_req = q1(conn, "SELECT COUNT(*) FROM RequirementSets WHERE RequirementSetId='DISTRICT_IS_HOLY_SITE'")
        assert_(n_req == 1, "[宜居] DISTRICT_IS_HOLY_SITE 在原版 RequirementSets 中真实存在",
                "[宜居] RequirementSets 里找不到 DISTRICT_IS_HOLY_SITE")
        assert_(howner == "PLAYER_IS_HUMAN",
                "[宜居] 圣地宜居度已加 PLAYER_IS_HUMAN 门槛",
                "[宜居] 未加人类门槛（当前 %s）" % howner)
        hargs = dict(conn.execute(
            "SELECT Name, Value FROM ModifierArguments WHERE ModifierId='NHS_HOLY_SITE_AMENITY'").fetchall())
        assert_(hargs.get("Amount") == "1",
                "[宜居] 每座圣地 Amount=1（与每城 +1 合计 +2）",
                "[宜居] Amount=%s，与文件头标注不符" % hargs.get("Amount"))

    n_am_trait = q1(conn, """SELECT COUNT(*) FROM TraitModifiers
                             WHERE TraitType='TRAIT_NHS_NUCLEAR_HOLY_SITE'
                               AND ModifierId IN ('NHS_CITY_AMENITY','NHS_HOLY_SITE_AMENITY')""")
    assert_(n_am_trait == 2,
            "[宜居] 两条宜居度 Modifier 均挂在核心特性 TRAIT_NHS_NUCLEAR_HOLY_SITE（不新增第 9 条特性）",
            "[宜居] 挂载数=%d，应为 2" % n_am_trait)

    # ---------- 城市数阶梯宜居（v34 / nhs_13_amenities.sql 第 4 节）----------
    #   这一层的失效方式很安静：Requirement 建了但 Amount 没写、或 Set 里忘了
    #   塞 Requirement，都会导致「条件永远为真或永远为假」，而游戏不报错。
    #   前者 = 4 城也白拿（前期变强），后者 = 一次都不触发（白写）。
    #   所以逐条查 Amount，并核对每个 Set 正好含 2 条（HUMAN + 城市数）。
    _ladder = [("NHS_REQ_5_CITIES", "5"), ("NHS_REQ_9_CITIES", "9"), ("NHS_REQ_13_CITIES", "13")]
    for rid, want in _ladder:
        got = conn.execute("SELECT Value FROM RequirementArguments WHERE RequirementId=? AND Name='Amount'",
                           (rid,)).fetchone()
        assert_(got is not None and got[0] == want,
                "[宜居] %s 阈值 = 至少 %s 座城" % (rid, want),
                "[宜居] %s 的 Amount = %s，应为 %s；写错会让阶梯提前或永不触发"
                % (rid, got[0] if got else "缺失", want))
        rtype = conn.execute("SELECT RequirementType FROM Requirements WHERE RequirementId=?",
                             (rid,)).fetchone()
        assert_(rtype is not None and rtype[0] == "REQUIREMENT_PLAYER_HAS_AT_LEAST_NUMBER_CITIES",
                "[宜居] %s 使用原版「至少 N 城」判定" % rid,
                "[宜居] %s 的 RequirementType = %s" % (rid, rtype[0] if rtype else "缺失"))
    _sets = {"NHS_AMENITY_HUMAN_5CITIES": "NHS_REQ_5_CITIES",
             "NHS_AMENITY_HUMAN_9CITIES": "NHS_REQ_9_CITIES",
             "NHS_AMENITY_HUMAN_13CITIES": "NHS_REQ_13_CITIES"}
    for sid, rid in _sets.items():
        members = {r[0] for r in conn.execute(
            "SELECT RequirementId FROM RequirementSetRequirements WHERE RequirementSetId=?", (sid,))}
        assert_(members == {"REQUIRES_PLAYER_IS_HUMAN", rid},
                "[宜居] %s = 「人类」∧「%s」（与组合 Set 的预期一致）" % (sid, rid),
                "[宜居] %s 的成员是 %s，应恰好是 HUMAN + %s；"
                "少了 HUMAN 会泄漏给 AI，少了城市数则该档恒真" % (sid, sorted(members), rid))
    _mods = {"NHS_AMENITY_MANY_CITIES_5": "NHS_AMENITY_HUMAN_5CITIES",
             "NHS_AMENITY_MANY_CITIES_9": "NHS_AMENITY_HUMAN_9CITIES",
             "NHS_AMENITY_MANY_CITIES_13": "NHS_AMENITY_HUMAN_13CITIES"}
    for mid, sid in _mods.items():
        row = conn.execute("SELECT OwnerRequirementSetId FROM Modifiers WHERE ModifierId=?", (mid,)).fetchone()
        amt = conn.execute("SELECT Value FROM ModifierArguments WHERE ModifierId=? AND Name='Amount'",
                           (mid,)).fetchone()
        assert_(row is not None and row[0] == sid and amt is not None and amt[0] == "1",
                "[宜居] %s：Amount=1 且指向 %s" % (mid, sid),
                "[宜居] %s 的 Set=%s Amount=%s，应为 %s / 1"
                % (mid, row[0] if row else "缺失", amt[0] if amt else "缺失", sid))
    n_ladder_trait = q1(conn, """SELECT COUNT(*) FROM TraitModifiers
                                 WHERE TraitType='TRAIT_NHS_NUCLEAR_HOLY_SITE'
                                   AND ModifierId LIKE 'NHS_AMENITY_MANY_CITIES_%'""")
    assert_(n_ladder_trait == 3,
            "[宜居] 三档阶梯全部挂在核心特性上（合计上限 +3，加原有两条共 +5）",
            "[宜居] 阶梯挂载数=%d，应为 3" % n_ladder_trait)

    # ---------- 首都信仰（v14 / nhs_01_core.sql 第 4b 节）----------
    cf = conn.execute("""
        SELECT m.ModifierType, m.OwnerRequirementSetId, m.SubjectRequirementSetId,
               d.CollectionType, d.EffectType
        FROM Modifiers m LEFT JOIN DynamicModifiers d ON d.ModifierType = m.ModifierType
        WHERE m.ModifierId = 'NHS_CAPITAL_FAITH'
    """).fetchone()
    if not cf:
        assert_(False, "", "[首都] 找不到 Modifier NHS_CAPITAL_FAITH（nhs_01_core.sql 未执行）")
    else:
        cmt, cowner, csub, ccoll, ceff = cf
        assert_(cmt == "MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE",
                "[首都] 复用原版首都收集器 ModifierType（同专制遗产/城邦宗主）",
                "[首都] ModifierType 是 %s，不是原版首都那个" % cmt)
        assert_(ccoll == "COLLECTION_PLAYER_CAPITAL_CITY",
                "[首都] 收集类型 COLLECTION_PLAYER_CAPITAL_CITY（只作用于首都）",
                "[首都] 收集类型是 %s，可能扩到非首都城市" % ccoll)
        assert_(ceff == "EFFECT_ADJUST_CITY_YIELD_CHANGE",
                "[首都] 效应为 EFFECT_ADJUST_CITY_YIELD_CHANGE",
                "[首都] 效应是 %s" % ceff)
        assert_(cowner == "PLAYER_IS_HUMAN",
                "[首都] 已加 PLAYER_IS_HUMAN 人类门槛",
                "[首都] 未加人类门槛（当前 %s）" % cowner)
        assert_(csub is None,
                "[首都] 未挂 SubjectRequirement（收集器已限定首都，多挂反而可能收错）",
                "[首都] 意外挂了 SubjectRequirement %s" % csub)
        cargs = dict(conn.execute(
            "SELECT Name, Value FROM ModifierArguments WHERE ModifierId='NHS_CAPITAL_FAITH'").fetchall())
        assert_(cargs.get("YieldType") == "YIELD_FAITH",
                "[首都] 产出类型 YIELD_FAITH",
                "[首都] 产出类型是 %s" % cargs.get("YieldType"))
        assert_(cargs.get("Amount") == "1",
                "[首都] Amount=1（每回合 +1 信仰）",
                "[首都] Amount=%s，与文案标注的 +1 不符" % cargs.get("Amount"))
        n_cf = q1(conn, """SELECT COUNT(*) FROM TraitModifiers
                           WHERE TraitType='TRAIT_NHS_NUCLEAR_HOLY_SITE'
                             AND ModifierId='NHS_CAPITAL_FAITH'""")
        assert_(n_cf == 1, "[首都] 已挂到核心特性 TRAIT_NHS_NUCLEAR_HOLY_SITE",
                "[首都] TraitModifiers 里没有挂载关系")

    # ---------- 农场 → 圣地 +1 信仰（v24 / nhs_01_core.sql 第 4c 节）----------
    ff = conn.execute("""
        SELECT m.ModifierType, m.OwnerRequirementSetId, m.SubjectRequirementSetId,
               d.CollectionType, d.EffectType
        FROM Modifiers m LEFT JOIN DynamicModifiers d ON d.ModifierType = m.ModifierType
        WHERE m.ModifierId = 'NHS_HOLY_SITE_FARM_FAITH'
    """).fetchone()
    if not ff:
        assert_(False, "", "[农场] 找不到 Modifier NHS_HOLY_SITE_FARM_FAITH（nhs_01_core.sql 未执行）")
    else:
        fmt, fowner, fsub, fcoll, feff = ff
        assert_(fmt == "MODIFIER_PLAYER_CITIES_IMPROVEMENT_ADJACENCY",
                "[农场] 复用原版「改善设施相邻」修饰器（同狄奥多拉圣地-农场）",
                "[农场] ModifierType 是 %s" % fmt)
        assert_(fcoll == "COLLECTION_PLAYER_CITIES",
                "[农场] 收集类型 COLLECTION_PLAYER_CITIES（只作用于自己的城市）",
                "[农场] 收集类型是 %s，可能波及他国城市" % fcoll)
        assert_(feff == "EFFECT_IMPROVEMENT_ADJACENCY",
                "[农场] 效应 EFFECT_IMPROVEMENT_ADJACENCY",
                "[农场] 效应是 %s" % feff)
        assert_(fowner == "PLAYER_IS_HUMAN",
                "[农场] 已加 PLAYER_IS_HUMAN 人类门槛",
                "[农场] 未加人类门槛（当前 %s）" % fowner)
        assert_(fsub is None,
                "[农场] 未挂 SubjectRequirement（收集器已限定本城，结果判定靠 Effect 参数）",
                "[农场] 意外挂了 %s" % fsub)
        fargs = dict(conn.execute(
            "SELECT Name, Value FROM ModifierArguments WHERE ModifierId='NHS_HOLY_SITE_FARM_FAITH'").fetchall())
        for nm, want in (("Amount", "1"), ("DistrictType", "DISTRICT_HOLY_SITE"),
                         ("ImprovementType", "IMPROVEMENT_FARM"),
                         ("YieldType", "YIELD_FAITH"),
                         ("Description", "LOC_NHS_DISTRICT_FARM_FAITH")):
            assert_(fargs.get(nm) == want,
                    "[农场] %s = %s" % (nm, want),
                    "[农场] %s = %s，期望 %s" % (nm, fargs.get(nm), want))
        assert_(fargs.get("TilesRequired", "1") == "1",
                "[农场] TilesRequired=1（每相邻一处农场即 +1，不是每两处）",
                "[农场] TilesRequired=%s，与「每处农场」的文案不符" % fargs.get("TilesRequired"))
        # 与原版同款逐项对账：除 Description 外应与 THEODORA_HOLY_SITE_ADJACENCY_FARM 完全相同
        van = dict(conn.execute(
            "SELECT Name, Value FROM ModifierArguments WHERE ModifierId='THEODORA_HOLY_SITE_ADJACENCY_FARM'").fetchall())
        if van:
            # TilesRequired 缺省即 1（原版狄奥多拉那行就没写），先归一化再比
            mine = {k: v for k, v in fargs.items() if k != "Description"}
            theirs = {k: v for k, v in van.items() if k != "Description"}
            mine.setdefault("TilesRequired", "1")
            theirs.setdefault("TilesRequired", "1")
            assert_(mine == theirs,
                    "[农场] 参数与原版狄奥多拉那条逐项相同（仅描述 tag 不同）",
                    "[农场] 与原版不同：我方 %s / 原版 %s" % (mine, theirs))
        n_ff = q1(conn, """SELECT COUNT(*) FROM TraitModifiers
                           WHERE TraitType='TRAIT_NHS_NUCLEAR_HOLY_SITE'
                             AND ModifierId='NHS_HOLY_SITE_FARM_FAITH'""")
        assert_(n_ff == 1, "[农场] 已挂到核心特性 TRAIT_NHS_NUCLEAR_HOLY_SITE",
                "[农场] TraitModifiers 里没有挂载关系")

    # ---------- 极光之舞改写（v24 / nhs_06_beliefs.sql 第 1b 节）----------
    aur = conn.execute("""
        SELECT m.ModifierId, m.ModifierType, m.SubjectRequirementSetId, d.CollectionType
        FROM Modifiers m LEFT JOIN DynamicModifiers d ON d.ModifierType = m.ModifierType
        WHERE m.ModifierId LIKE 'NHS_BL_DANCE_OF_THE_AURORA%'
        ORDER BY m.ModifierId
    """).fetchall()
    assert_(len(aur) == 2,
            "[冻土] 极光之舞两条（苔原 + 苔原丘陵）都在",
            "[冻土] 极光之舞克隆数为 %d，应为 2" % len(aur))
    for mid, mt, sub, coll in aur:
        assert_(mt == "MODIFIER_PLAYER_CITIES_TERRAIN_ADJACENCY",
                "[冻土] %s 已换成 PLAYER_CITIES 收集器" % mid,
                "[冻土] %s 的 ModifierType 仍是 %s" % (mid, mt))
        assert_(sub is None,
                "[冻土] %s 已去掉万神殿门槛（不立万神殿也生效）" % mid,
                "[冻土] %s 仍挂着 %s，没立万神殿时整条静默失效" % (mid, sub))
        assert_(coll == "COLLECTION_PLAYER_CITIES",
                "[冻土] %s 收集类型 COLLECTION_PLAYER_CITIES" % mid,
                "[冻土] %s 收集类型是 %s" % (mid, coll))
    for mid, terr in (("NHS_BL_DANCE_OF_THE_AURORA_FAITHTUNDRAADJACENCY", "TERRAIN_TUNDRA"),
                      ("NHS_BL_DANCE_OF_THE_AURORA_FAITHTUNDRAHILLSADJACENCY", "TERRAIN_TUNDRA_HILLS")):
        a = dict(conn.execute("SELECT Name, Value FROM ModifierArguments WHERE ModifierId=?", (mid,)).fetchall())
        assert_(a.get("TerrainType") == terr and a.get("DistrictType") == "DISTRICT_HOLY_SITE"
                and a.get("YieldType") == "YIELD_FAITH" and a.get("Amount") == "1",
                "[冻土] %s 参数完整（圣地 +1 信仰/相邻%s）" % (mid.split("_")[-1], terr),
                "[冻土] %s 参数缺失或被改：%s" % (mid, a))

    # ---------- 职业道德克隆必须真的落地（v24 补检）----------
    #   v19 的库里头像/单位都在，唯独这条不见了：INSERT OR IGNORE ... SELECT 是
    #   *静默* 的，一行没插进去也不会报错。后果是「产能引擎」整条消失，
    #   而玩家看到的只是「勤则不匮好像没生效」。教训：克隆类语句一律补"落地检查"。
    we = conn.execute("""
        SELECT m.ModifierType, m.SubjectRequirementSetId
        FROM Modifiers m WHERE m.ModifierId = 'NHS_BL_WORK_ETHIC_ADJACENCY_PRODUCTION_2'
    """).fetchone()
    if not we:
        assert_(False, "",
                "[信条] 职业道德克隆体 NHS_BL_WORK_ETHIC_ADJACENCY_PRODUCTION_2 不存在"
                "（nhs_06 的 INSERT OR IGNORE 静默丢行了）")
    else:
        wmt, wsub = we
        assert_(wmt == "MODIFIER_ALL_DISTRICTS_ADJUST_YIELD_BASED_ON_ADJACENCY_BONUS",
                "[信条] 职业道德克隆体存在，修饰器为「相邻加成转产出」",
                "[信条] 职业道德克隆体修饰器异常：%s" % wmt)
        assert_(wsub == "WORK_ETHIC_ADJACENCY_PRODUCTION_REQUIREMENTS",
                "[信条] 职业道德保留原版门槛（需城市信奉你的宗教）",
                "[信条] 职业道德门槛被改：%s" % wsub)
        wa = dict(conn.execute(
            "SELECT Name, Value FROM ModifierArguments WHERE ModifierId='NHS_BL_WORK_ETHIC_ADJACENCY_PRODUCTION_2'").fetchall())
        assert_(wa.get("YieldTypeToGrant") == "YIELD_PRODUCTION"
                and wa.get("YieldTypeToMirror") == "YIELD_FAITH",
                "[信条] 职业道德参数完整（相邻信仰 → 等量产锤）",
                "[信条] 职业道德参数缺失：%s" % wa)

    # ---------- 「每信徒 +1 产能」必须真的消失（v33）----------
    #   这条是"删掉一整个乘数轴"，静默失效的方式与克隆丢行正好相反：
    #   如果排除条件写错（比如写成 LIKE 而不是 <>），克隆体照样生成，
    #   而静态层看不出来 —— 所以必须在真实库里查「不存在」。
    #   同时查原版那条仍在：我们只该砍 'NHS_BL_' 前缀的克隆体，
    #   若原版 WORK_ETHIC_FOLLOWER_PRODUCTION 也没了，说明 DELETE 写宽了，
    #   会破坏不装本 mod 时的原版行为（以及别的引用它的地方）。
    _wef = conn.execute(
        "SELECT COUNT(*) FROM Modifiers WHERE ModifierId='NHS_BL_WORK_ETHIC_FOLLOWER_PRODUCTION'"
    ).fetchone()[0]
    assert_(_wef == 0,
            "[信条] 已剔除「每信徒 +1 产能」克隆体（NHS_BL_WORK_ETHIC_FOLLOWER_PRODUCTION 不存在）",
            "[信条] NHS_BL_WORK_ETHIC_FOLLOWER_PRODUCTION 仍然存在 %d 条；"
            "这条随人口线性增长、无上限，且会把 +1 产能/信徒发给同教 AI 城" % _wef)
    _wef_att = conn.execute(
        "SELECT COUNT(*) FROM TraitModifiers WHERE ModifierId='NHS_BL_WORK_ETHIC_FOLLOWER_PRODUCTION'"
    ).fetchone()[0]
    assert_(_wef_att == 0,
            "[信条] 该克隆体已从 Trait 挂载表中摘除（无孤儿引用）",
            "[信条] TraitModifiers 仍挂着 NHS_BL_WORK_ETHIC_FOLLOWER_PRODUCTION（%d 行），"
            "外键残留会让游戏构建库时失败" % _wef_att)
    _orig_wef = conn.execute(
        "SELECT COUNT(*) FROM Modifiers WHERE ModifierId='WORK_ETHIC_FOLLOWER_PRODUCTION'"
    ).fetchone()[0]
    assert_(_orig_wef == 1,
            "[信条] 原版 WORK_ETHIC_FOLLOWER_PRODUCTION 未被误删（只砍克隆体）",
            "[信条] 原版 WORK_ETHIC_FOLLOWER_PRODUCTION 行数为 %d，应为 1；"
            "DELETE 条件写宽了，会破坏不装本 mod 的原版行为" % _orig_wef)

    # ---------- 出生地关联（v25 / nhs_15_start_bias.sql）----------
    #   机制：AssignStartingPlots.lua 按 Tier 分轮，同轮内 Terrains 先按
    #   「3 环内命中格数」给候选排序，Rivers 再在同一候选集上筛靠河的点。
    #   因此三个约束必须同时成立，缺一条整套偏置就形同虚设：
    #     ① 冻土与平原必须同 Tier（否则后一轮被前一轮的收敛结果架空）
    #     ② 河流必须与地形同 Tier（Rivers 在 Terrains 之后执行才有意义）
    #     ③ 地形名必须真在 Terrains 表里（写错不会报错，只是永远不计分）
    _want_terrains = {"TERRAIN_TUNDRA", "TERRAIN_TUNDRA_HILLS",
                      "TERRAIN_PLAINS", "TERRAIN_PLAINS_HILLS"}
    _sb = conn.execute(
        "SELECT TerrainType, Tier FROM StartBiasTerrains "
        "WHERE CivilizationType='CIVILIZATION_CHINA'").fetchall()
    _got = {r[0] for r in _sb}
    assert_(_got == _want_terrains,
            "[出生] 中国地形偏置齐备（冻土/冻土丘陵/平原/平原丘陵）",
            "[出生] 地形偏置为 %s，应为 %s" % (sorted(_got), sorted(_want_terrains)))
    _tiers = {r[1] for r in _sb}
    assert_(_tiers == {1},
            "[出生] 四类地形同为 Tier 1（合并进同一个打分集合）",
            "[出生] 地形 Tier 不统一：%s；分轮会让低优先那轮失效" % sorted(_tiers))

    _rv = conn.execute(
        "SELECT Tier FROM StartBiasRivers WHERE CivilizationType='CIVILIZATION_CHINA'").fetchall()
    assert_(len(_rv) == 1,
            "[出生] 已加河流偏置（一行）",
            "[出生] StartBiasRivers 里中国有 %d 行，应为 1 行" % len(_rv))
    if _rv:
        assert_(_rv[0][0] in _tiers,
                "[出生] 河流与地形同 Tier（%s），能在排序结果上再筛靠河" % _rv[0][0],
                "[出生] 河流 Tier=%s 与地形 %s 不同；Rivers 排在 Terrains 之后，"
                "不同轮等于白写" % (_rv[0][0], sorted(_tiers)))

    _bad = [t for (t, _tier) in _sb
            if not q1(conn, "SELECT COUNT(*) FROM Terrains WHERE TerrainType=?", (t,))]
    assert_(not _bad,
            "[出生] 偏置里的地形名都真实存在于 Terrains 表",
            "[出生] 地形名不存在：%s（不报错，只是永远不计分）" % _bad)

    # ---------- 帝国规模 / 科技人口抑制（v42 / nhs_18_tech_scaling.sql）----------
    #   ★ v42 起这一层的口径回到「负百分比」，理由见 nhs_18 文件头：
    #     v37/v38/v40 三轮「实机零效果」并不是 effect 不生效，而是**三轮都在老存档上测**——
    #     Civ6 建局时就把玩家已挂载的 modifier 集合写进存档，之后新增的 SQL 只进游戏库、
    #     不追溯。v41 探针（三条 +20）逐城科研一分未动，就是铁证。
    #   所以离线校验的意义没有变（它保证「新开一局时库里的东西是对的」），但**结论只能靠
    #   新开一局验证**，这一点写在 nhs_18 文件末尾的验收节里。
    #
    #   这一层的失效方式有四种，都不报错、只能查最终状态：
    #     ① ModifierType 被换成加算类/每人口类 → 与设计口径不符（v40 的过渡写法，已弃用）；
    #     ② 参数或门槛挂错 → 惩罚要么全玩家吃、要么一条不生效；
    #     ③ 分档数字被改了一档忘了改其余 → 累计折扣静默漂移，界面看不出来；
    #     ④ 挂载被删 → 行在库里但没有玩家拿得到。
    #   四种都能在离线库抓，下面把「类型 / EffectType / 符号 / 逐档门槛 / 累计折扣 /
    #   挂载 / 唯一性」钉死。
    _YMOD = "MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER"
    _YMOD_EFFECT = "EFFECT_ADJUST_CITY_YIELD_MODIFIER"
    #            档位 ModifierId      : (Subject 门槛, 本档 Amount)
    _tiers = {"NHS_TECH_SCALE_L1": (None, -10),
              "NHS_TECH_SCALE_L2": ("NHS_REQS_CITY_POP_10", -12),
              "NHS_TECH_SCALE_L3": ("NHS_REQS_CITY_POP_16", -8)}
    #    v47 起三档统一挂组合 Owner 门槛 NHS_REQS_HUMAN_POST_ANCIENT（人类 且 ≥古典），
    #    远古时代整层豁免；Amount 数值本身没动（仍是 −10 / −12 / −8，累计 −30）。
    _CUM = 30   # 巨型城累计折扣（−10 −12 −8，v46 从 −53 调轻，见 nhs_18 文件头）
    _tech = {}
    for _mid in _tiers:
        _tech[_mid] = conn.execute(
            "SELECT ModifierType, OwnerRequirementSetId, SubjectRequirementSetId "
            "FROM Modifiers WHERE ModifierId=?", (_mid,)).fetchone()

    assert_(all(_tech.values()),
            "[规模] 三条分档科研折扣都已入库（规模税 + 大城 + 巨型城）",
            "[规模] 缺失：%s" % [k for k, v in _tech.items() if not v])

    if all(_tech.values()):
        assert_(all(r[0] == _YMOD for r in _tech.values()),
                "[规模] 三条均为负百分比「%s」" % _YMOD,
                "[规模] 修饰器类型不对：%s；应为 %s。v40 的加算固定值（NHS_MOD_CITY_YIELD）"
                "是「误以为百分比不生效」时的过渡写法，前提已推翻，不要再退回"
                % ({k: v[0] for k, v in _tech.items()}, _YMOD))

        # ModifierType 折射出的 EffectType 必须是百分比类：这一行若被换成加算类，
        # 三条 Amount 的含义会从「−18%」变成「−18 科研」而不报任何错，数值全错。
        _dm = conn.execute(
            "SELECT CollectionType, EffectType FROM DynamicModifiers WHERE ModifierType=?",
            (_YMOD,)).fetchone()
        assert_(_dm == ("COLLECTION_PLAYER_CITIES", _YMOD_EFFECT),
                "[规模] 该 ModifierType = COLLECTION_PLAYER_CITIES + %s（百分比类）"
                % _YMOD_EFFECT,
                "[规模] DynamicModifiers 不对：%s；应为 (COLLECTION_PLAYER_CITIES, %s)。"
                "换 effect 会让 Amount 的单位从「%%」变成「固定值」，数值静默错一个量级"
                % (_dm, _YMOD_EFFECT))
        _OWNER = "NHS_REQS_HUMAN_POST_ANCIENT"
        assert_(all(r[1] == _OWNER for r in _tech.values()),
                "[规模] 三条 Owner 门槛均为 %s（人类 且 已过远古）" % _OWNER,
                "[规模] Owner 门槛不是 %s：%s；会让远古期也征税，或让 AI 也吃惩罚"
                % (_OWNER, {k: v[1] for k, v in _tech.items()}))

        # v47 时代门控：远古豁免完全靠这条组合 Set，两个成员缺一个都**静默**失效——
        #   少 REQUIRES_PLAYER_IS_HUMAN → AI 也吃（惩罚全图）
        #   少 NHS_REQ_PLAYER_POST_ANCIENT → 远古也扣（等于退回 v46）
        # 两者都不报错，只能查最终状态，所以在这里钉死。
        _mem = set(x[0] for x in conn.execute(
            "SELECT RequirementId FROM RequirementSetRequirements "
            "WHERE RequirementSetId=?", (_OWNER,)).fetchall())
        assert_(_mem == {"REQUIRES_PLAYER_IS_HUMAN", "NHS_REQ_PLAYER_POST_ANCIENT"},
                "[规模] 时代门控 Set = TEST_ALL{ 人类, ≥古典时代 }",
                "[规模] Owner Set 成员不对：%s；应为 {REQUIRES_PLAYER_IS_HUMAN, "
                "NHS_REQ_PLAYER_POST_ANCIENT}。少 HUMAN 则 AI 也吃，"
                "少 ERA 则远古也扣，两种都不报错" % sorted(_mem))

        _era = conn.execute(
            "SELECT r.RequirementType, a.Value FROM Requirements r "
            "LEFT JOIN RequirementArguments a ON a.RequirementId=r.RequirementId "
            "AND a.Name='EraType' WHERE r.RequirementId='NHS_REQ_PLAYER_POST_ANCIENT'"
        ).fetchone()
        assert_(_era == ("REQUIREMENT_PLAYER_ERA_AT_LEAST", "ERA_CLASSICAL"),
                "[规模] 时代门槛 = REQUIREMENT_PLAYER_ERA_AT_LEAST + ERA_CLASSICAL"
                "（判玩家自己的时代，不是全场时代）",
                "[规模] 时代门槛不对：%s；换成 REQUIREMENT_GAME_ERA_* 会让"
                "「AI 先进入古典」也触发征税，与「前期不削弱人类」相反；"
                "换成别的 EraType 会挪动豁免边界" % (_era,))

        # 逐档核对 Subject 门槛。第 1 档必须为 None：挂了门槛就等于把小城
        # 排除在「规模税」之外，与「任何城市都有规模成本」的设计不符。
        _badsub = {k: (_tech[k][2], w[0]) for k, w in _tiers.items() if _tech[k][2] != w[0]}
        assert_(not _badsub,
                "[规模] 三档 Subject 门槛与设计一致（L1 无门槛 / L2 人口≥10 / L3 人口≥16）",
                "[规模] Subject 门槛不符（实际, 应为）：%s；门槛错位不会报错，"
                "只会让分档点落在错误的人口数上，累计折扣随之跑偏" % _badsub)

        # 参数：符号、绝对值、产出类型三项都要对。
        # 符号为正 = 人口越多科研越多，与设计完全相反且照常生效 —— 最危险的一种写错。
        _got = {}
        for _mid in _tiers:
            _args = dict(conn.execute(
                "SELECT Name, Value FROM ModifierArguments WHERE ModifierId=?", (_mid,)).fetchall())
            try:
                _got[_mid] = (float(_args.get("Amount", "nan")), _args.get("YieldType"))
            except ValueError:
                _got[_mid] = (float("nan"), _args.get("YieldType"))
        assert_(all(_got[k][1] == "YIELD_SCIENCE" for k in _tiers),
                "[规模] 三条 YieldType 均为 YIELD_SCIENCE（不误伤文化/产能）",
                "[规模] YieldType 不对：%s" % {k: v[1] for k, v in _got.items()})
        _badamt = {k: (_got[k][0], w[1]) for k, w in _tiers.items()
                   if abs(_got[k][0] - w[1]) > 1e-9}
        assert_(not _badamt,
                "[规模] 三档 Amount 与设计一致（−10 / −12 / −8，累计 −30%）",
                "[规模] Amount 不符（实际, 应为）：%s；符号为正会变成「人口越多科研越多」"
                % _badamt)

        # 三档加和：累计折扣是设计口径的核心数字，改任一档都必须同步文件头旋钮表。
        _cum = sum(-_got[k][0] for k in _tiers)
        assert_(abs(_cum - _CUM) < 1e-9,
                "[规模] 巨型城累计折扣恰为 %g%%（−10 −12 −8）" % _CUM,
                "[规模] 累计折扣为 %g%%，设计值 %g%%；改档必须同步 nhs_18 文件头"
                "的旋钮表与 nhs_text.xml / modinfo 文案" % (_cum, _CUM))

        # 挂载：必须挂在核心 trait 上，否则整层是死代码（行在库里，但没有任何玩家拿到）。
        _att = conn.execute(
            "SELECT ModifierId FROM TraitModifiers WHERE TraitType='TRAIT_NHS_NUCLEAR_HOLY_SITE' "
            "AND ModifierId LIKE 'NHS_TECH_SCALE_%'").fetchall()
        assert_(len(_att) == 3,
                "[规模] 三条都挂到 TRAIT_NHS_NUCLEAR_HOLY_SITE（秦始皇专属）",
                "[规模] 只挂到 %d 条；行在库里却没人拿到，等于整层失效" % len(_att))

    # 门槛本体：两条都要是「一条 REQUIREMENT_CITY_HAS_X_POPULATION + 对应 Amount」+ TEST_ALL。
    for _rsid, _pop in (("NHS_REQS_CITY_POP_10", "10"), ("NHS_REQS_CITY_POP_16", "16")):
        _rs = conn.execute(
            "SELECT RequirementSetType FROM RequirementSets WHERE RequirementSetId=?",
            (_rsid,)).fetchone()
        assert_(_rs and _rs[0] == "REQUIREMENTSET_TEST_ALL",
                "[规模] %s 已建且为 TEST_ALL" % _rsid,
                "[规模] 需求集缺失或类型不是 TEST_ALL：%s" % (_rs,))
        _ra = conn.execute(
            "SELECT r.RequirementType, ra.Value FROM RequirementSetRequirements rsr "
            "JOIN Requirements r ON r.RequirementId=rsr.RequirementId "
            "LEFT JOIN RequirementArguments ra ON ra.RequirementId=rsr.RequirementId AND ra.Name='Amount' "
            "WHERE rsr.RequirementSetId=?", (_rsid,)).fetchall()
        assert_(len(_ra) == 1 and _ra[0][0] == "REQUIREMENT_CITY_HAS_X_POPULATION"
                and _ra[0][1] == _pop,
                "[规模] 门槛为「城市人口 ≥ %s」（一条 REQUIREMENT_CITY_HAS_X_POPULATION）" % _pop,
                "[规模] %s 内容不对：%s；写错人口数不会报错，只会让分档点落在错误位置"
                % (_rsid, _ra))

    # 唯一性：恰好三条，且不得残留 v37 的 NHS_TECH_POP_COST_*
    # （残留 = 新旧两层同时生效，折扣会翻倍，且界面看不出是哪一层）。
    _n = q1(conn, "SELECT COUNT(*) FROM Modifiers WHERE ModifierId LIKE 'NHS_TECH_SCALE_%'")
    assert_(_n == 3,
            "[规模] NHS_TECH_SCALE_* 恰好 3 条（无重复、无残留）",
            "[规模] 现有 %d 条，应为 3 条；重复会让惩罚翻倍" % _n)
    _old = q1(conn, "SELECT COUNT(*) FROM Modifiers WHERE ModifierId LIKE 'NHS_TECH_POP_COST%'")
    assert_(_old == 0,
            "[规模] v37 的 NHS_TECH_POP_COST_* 已完全移除（实机已证明无效，留着是死代码）",
            "[规模] 仍残留 %d 条 NHS_TECH_POP_COST_*；这段实机零效果，"
            "留着只会让后来者误以为它在起作用" % _old)

    # 绝不能误伤原版：本层只新增、不写任何已有行。
    # 这两条是同构来源，值一旦被改，说明有人把 UPDATE 写宽了。
    for _mid, _want in (("YONGLE_SCIENCE_POPULATION", "1"),
                        ("DECENTRALIZATION_HIGHPOP_GOLD", "-15")):
        _v = conn.execute(
            "SELECT Value FROM ModifierArguments WHERE ModifierId=? AND Name='Amount'",
            (_mid,)).fetchone()
        assert_(_v and _v[0] == _want,
                "[规模] 原版 %s 的 Amount 仍为 %s（未被误改）" % (_mid, _want),
                "[规模] 原版 %s 参数被改成 %s；本层只该新增，不该动原版"
                % (_mid, _v))


def main():
    if not os.path.exists(SRC_DB):
        print("找不到底库，请先运行 python build_game_db.py")
        sys.exit(1)
    shutil.copyfile(SRC_DB, TST_DB)
    conn = sqlite3.connect(TST_DB)
    # 游戏引擎内置的 Make_Hash（Types 表触发器要用它），这里用 crc32 等价替代
    conn.create_function("Make_Hash", 1,
                         lambda x: zlib.crc32(str(x).encode("utf-8")) & 0x7FFFFFFF)
    print("=" * 78)
    print("在真实游戏表结构 + 真实游戏数据上执行 mod SQL")
    print("=" * 78)
    print("\n[执行]")
    fails = run_all(conn)
    if fails:
        for fn, idx, snip, e in fails:
            err("[SQL] %s 第 %d 条失败: %s\n        %s" % (fn, idx + 1, e, snip))
    else:
        ok("[SQL] %d 个 SQL 文件、全部语句在真实表结构上执行通过，0 报错"
           "（本地化已独立走 %s）" % (len(SQL_FILES), TEXT_FILE))

    print("\n[断言]")
    verify(conn)

    # 幂等性：再跑一遍，行数不应翻倍
    before = q1(conn, "SELECT COUNT(*) FROM Modifiers WHERE ModifierId LIKE 'NHS%'")
    bias_before = q1(conn, "SELECT COUNT(*) FROM StartBiasTerrains "
                           "WHERE CivilizationType='CIVILIZATION_CHINA'")
    run_all(conn, verbose=False)
    after = q1(conn, "SELECT COUNT(*) FROM Modifiers WHERE ModifierId LIKE 'NHS%'")
    bias_after = q1(conn, "SELECT COUNT(*) FROM StartBiasTerrains "
                          "WHERE CivilizationType='CIVILIZATION_CHINA'")
    assert_(before == after, "[幂等] 重复加载两次，NHS Modifier 数量不变（%s → %s）" % (before, after),
            "[幂等] 重复加载导致数量变化（%s → %s）" % (before, after))
    assert_(bias_before == bias_after,
            "[幂等] 重复加载两次，出生地形偏置仍为 %s 行（主键去重生效）" % bias_before,
            "[幂等] 出生地形偏置从 %s 行涨到 %s 行" % (bias_before, bias_after))

    conn.close()

    print("\n--- OK (%d) ---" % len(oks))
    for m in oks:
        print("  \u2713", m)
    if warns:
        print("\n--- WARN (%d) ---" % len(warns))
        for m in warns:
            print("  \u26a0", m)
    print("\n--- ERROR (%d) ---" % len(errors))
    for m in errors:
        print("  \u2717", m)
    print("\n" + "=" * 78)
    if errors:
        print("执行验证未通过：%d 个问题。" % len(errors))
        sys.exit(1)
    print("在真实游戏数据库结构上执行验证通过。")
    sys.exit(0)


if __name__ == "__main__":
    main()
