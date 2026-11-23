# -*- coding: utf-8 -*-
"""
v47 时代门控的反向测试。

规则（HANDOFF 第 8 条）：每条新增断言都必须能做反向验证——故意写坏，
确认有脚本抓住，且报错文案指向失败原因。抓不住即视为断言无效。

用法：python reverse_test_v47.py
不修改最终状态：每次变异跑完立即还原，结束时校验文件 sha256 与原始一致。
"""
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
T18 = os.path.join(HERE, "mod", "sql", "nhs_18_tech_scaling.sql")
BAK = T18 + ".reversetest.bak"


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def run(cmd):
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    return (r.stdout or "") + (r.stderr or "")


# (名称, 原文, 替换为, 顺带跑的脚本, 期望命中的关键词组)
#   关键词组 = 只需命中其中一个即算抓住
CASES = [
    ("① EraType 从古典改为远古（豁免等于不存在）",
     "('NHS_REQ_PLAYER_POST_ANCIENT', 'EraType', 'ERA_CLASSICAL');",
     "('NHS_REQ_PLAYER_POST_ANCIENT', 'EraType', 'ERA_ANCIENT');",
     ["verify_mod.py", "run_mod_sql.py"],
     ["豁免边界会漂移", "时代门槛不对"]),

    ("② 删掉 Set 里的时代成员（远古照样扣税）",
     "INSERT OR IGNORE INTO RequirementSetRequirements (RequirementSetId, RequirementId) VALUES\n"
     "  ('NHS_REQS_HUMAN_POST_ANCIENT', 'NHS_REQ_PLAYER_POST_ANCIENT');",
     "",
     ["verify_mod.py", "run_mod_sql.py"],
     ["时代门控 Set 缺成员 NHS_REQ_PLAYER_POST_ANCIENT", "Owner Set 成员不对"]),

    ("③ 删掉 Set 里的人类成员（AI 也吃惩罚）",
     "INSERT OR IGNORE INTO RequirementSetRequirements (RequirementSetId, RequirementId) VALUES\n"
     "  ('NHS_REQS_HUMAN_POST_ANCIENT', 'REQUIRES_PLAYER_IS_HUMAN');",
     "",
     ["verify_mod.py", "run_mod_sql.py"],
     ["时代门控 Set 缺成员 REQUIRES_PLAYER_IS_HUMAN", "Owner Set 成员不对"]),

    ("④ L1 的 Owner 改回 PLAYER_IS_HUMAN（远古重新扣 10%）",
     "('NHS_TECH_SCALE_L1', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER', "
     "'NHS_REQS_HUMAN_POST_ANCIENT');",
     "('NHS_TECH_SCALE_L1', 'MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER', "
     "'PLAYER_IS_HUMAN');",
     ["verify_mod.py", "run_mod_sql.py"],
     ["的 Owner 门槛为 PLAYER_IS_HUMAN", "Owner 门槛不是 NHS_REQS_HUMAN_POST_ANCIENT"]),

    ("⑤ 要求类型名少一个下划线（拼错，静默不生效）",
     "'REQUIREMENT_PLAYER_ERA_AT_LEAST'",
     "'REQUIREMENT_PLAYER_ERA_ATLEAST'",
     ["verify_mod.py"],
     ["类型不是 REQUIREMENT_PLAYER_ERA_AT_LEAST", "游戏库里找不到时代要求类型"]),
]


def main():
    orig = sha(T18)
    shutil.copy2(T18, BAK)
    base = open(T18, encoding="utf-8").read()
    ok = fail = 0

    try:
        for name, old, new, scripts, keywords in CASES:
            n = base.count(old)
            if n != 1:
                print("[SKIP] %s：原文命中 %d 次（应为 1），变异无法精确定位" % (name, n))
                fail += 1
                continue
            open(T18, "w", encoding="utf-8", newline="").write(base.replace(old, new, 1))
            caught, where = False, []
            for sc in scripts:
                out = run([sys.executable, sc])
                hit = [k for k in keywords if k in out]
                if hit:
                    caught = True
                    where.append("%s→「%s」" % (sc, hit[0]))
            if caught:
                print("[CAUGHT] %s" % name)
                for w in where:
                    print("         %s" % w)
                ok += 1
            else:
                print("[MISSED] %s：%s 都没报错 —— 该断言无效，必须补强"
                      % (name, " / ".join(scripts)))
                fail += 1
            # 还原，供下一条用
            open(T18, "w", encoding="utf-8", newline="").write(base)
    finally:
        shutil.copy2(BAK, T18)
        os.remove(BAK)
        if sha(T18) != orig:
            print("[FATAL] 还原后 sha256 不一致！请 git checkout -- mod/sql/nhs_18_tech_scaling.sql")
            return 2

    print("\n抓到 %d / %d，漏 %d" % (ok, len(CASES), fail))
    print("文件已还原，sha256 = %s" % orig[:16])
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
