# -*- coding: utf-8 -*-
"""v46 规模层的反向测试：故意写坏，确认校验器一定报 ✗（而不是静默放过）。

规矩：判据只看 ✗ 行（失败信号），不看 ✓ 行。
每个用例：备份 → 篡改 → 跑校验器 → 断言目标 ✗ 行出现 → 还原。
"""
import io, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL18 = os.path.join(ROOT, "mod", "sql", "nhs_18_tech_scaling.sql")
SQL01 = os.path.join(ROOT, "mod", "sql", "nhs_01_core.sql")


def run(script):
    p = subprocess.run([sys.executable, script], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (p.stdout or "") + (p.stderr or "")


def bad_lines(out):
    return [l.strip() for l in out.splitlines() if l.lstrip().startswith("✗")]


CASES = []


def case(name, path, old, new, script, expect_kw):
    CASES.append((name, path, old, new, script, expect_kw))


# 1. 负号写丢 → 惩罚变加成
case("负号写丢（-10 → +10）", SQL18,
     "('NHS_TECH_SCALE_L1', 'Amount',    '-10')",
     "('NHS_TECH_SCALE_L1', 'Amount',    '10')",
     "run_mod_sql.py", "Amount 不符")

# 2. ModifierType 退回 v40 的加算类（前提已被推翻，不许退回）
case("退回 v40 加算类", SQL18,
     "('NHS_TECH_SCALE_L1', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER', 'PLAYER_IS_HUMAN')",
     "('NHS_TECH_SCALE_L1', 'NHS_MOD_CITY_YIELD', 'PLAYER_IS_HUMAN')",
     "run_mod_sql.py", "修饰器类型不对")

# 3. L3 的人口门槛挂错（16 → 10 的 set）
case("L3 门槛挂错", SQL18,
     "('NHS_TECH_SCALE_L3', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER', 'PLAYER_IS_HUMAN', 'NHS_REQS_CITY_POP_16')",
     "('NHS_TECH_SCALE_L3', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER', 'PLAYER_IS_HUMAN', 'NHS_REQS_CITY_POP_10')",
     "verify_mod.py", "Subject 门槛")

# 4. 累计折扣被改一档而其余没同步（-12 → -4）
case("累计折扣漂移（-12 → -4）", SQL18,
     "('NHS_TECH_SCALE_L2', 'Amount',    '-12')",
     "('NHS_TECH_SCALE_L2', 'Amount',    '-4')",
     "verify_mod.py", "累计折扣")

# 5. YieldType 写错产出（扣到文化上）
case("YieldType 写成文化", SQL18,
     "('NHS_TECH_SCALE_L2', 'YieldType', 'YIELD_SCIENCE')",
     "('NHS_TECH_SCALE_L2', 'YieldType', 'YIELD_CULTURE')",
     "verify_mod.py", "YieldType")

# 6. Owner 门槛被删 → AI 也吃惩罚
case("Owner 门槛被删", SQL18,
     "('NHS_TECH_SCALE_L2', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER', 'PLAYER_IS_HUMAN', 'NHS_REQS_CITY_POP_10')",
     "('NHS_TECH_SCALE_L2', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER', NULL, 'NHS_REQS_CITY_POP_10')",
     "run_mod_sql.py", "Owner")

# 7. 挂载被整行删掉 → 行在库里但没人拿得到
#    注：若只改 ModifierId 而不删行，会先撞上「悬空引用」检查（另一条断言），
#    那也是 ✗，但指向的是别的检查项，测不到「挂载数」这条，所以这里整行删。
case("TraitModifiers 挂载被删", SQL18,
     "INSERT OR IGNORE INTO TraitModifiers (TraitType, ModifierId) VALUES\n"
     "  ('TRAIT_NHS_NUCLEAR_HOLY_SITE', 'NHS_TECH_SCALE_L3');\n",
     "",
     "run_mod_sql.py", "只挂到")

# 8. 修饰器名拼错 → 库里没有这个类型，SQL 不报错、永远不生效
#    锚点必须是 SQL 声明语句本身：revtest 只替换第一处，而文件头注释里也出现过
#    这个类型名，锚在裸名字上会改到注释、改不到 SQL（上一版就是这么漏抓的）。
case("修饰器名拼错", SQL18,
     "('NHS_TECH_SCALE_L1', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER', 'PLAYER_IS_HUMAN')",
     "('NHS_TECH_SCALE_L1', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFER', 'PLAYER_IS_HUMAN')",
     "verify_mod.py", "的修饰器为")


def main():
    ok = 0
    fail = []
    for name, path, old, new, script, kw in CASES:
        src = io.open(path, encoding="utf-8").read()
        if old not in src:
            fail.append("%s —— 篡改锚点没找到，测试本身失效：%r" % (name, old[:50]))
            continue
        bak = path + ".revbak"
        shutil.copy2(path, bak)
        try:
            io.open(path, "w", encoding="utf-8").write(src.replace(old, new, 1))
            out = run(script)
            bad = bad_lines(out)
            hit = [l for l in bad if kw in l]
            if hit:
                ok += 1
                print("  ✓ 抓到  %-32s → %s" % (name, hit[0][:88]))
            else:
                fail.append("%s —— 未报含「%s」的 ✗ 行；实际 ✗ 行：%s"
                            % (name, kw, bad[:3] if bad else "（无，静默放过）"))
                print("  ✗ 漏抓  %-32s" % name)
        finally:
            shutil.move(bak, path)
    print("\n反向测试：%d/%d 抓到" % (ok, len(CASES)))
    if fail:
        print("\n失败用例：")
        for f in fail:
            print("  ·", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
