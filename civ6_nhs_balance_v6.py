# -*- coding: utf-8 -*-
"""
核动力圣地 v6 · 「侦察兵/移民移动翻倍」+「工人加速全时代奇观 30%」的数值冲击分析
游戏数值平衡专家 设计产物

设计原则：
  这两项都**不改变城市产出**，所以 v5 的产能比曲线（1.56/1.02/0.65）不受影响。
  但它们改变的是另外两条独立价值线：
    (A) 节奏 tempo —— 探索与铺城的回合数
    (B) 奇观获取 —— 用工人产能换奇观产能的兑换率
  分开量化，不混进产能比里冒充"一点没变强"。
"""
import os
import csv

OUT = os.path.dirname(os.path.abspath(__file__))

ASSUME = """
[口径与假设 —— 先看清楚再信数字]
1. 移动力在 Civ6 是**加算**，游戏不支持"×N"百分比。故按基础值折算：
     侦察兵 3 → +3 = 6（等效翻倍）
     移民   2 → +2 = 4（等效翻倍）
2. 工人造价按原版标准速度近似：远古 60 / 古典 70 / 中古 85 / 文艺复兴 100 / 工业 120 / 现代 140。
   实际随已造数量递增，这里取单城第 3~5 个工人的典型值。
3. 奇观造价按原版标准速度近似（看量级与趋势，不追求逐项精确）：
   远古 200 / 古典 200 / 中古 440 / 文艺复兴 620 / 工业 950 / 现代 1250。
4. 工人使用次数：基础 3；建成金字塔后 4。
5. 城市产能按 25~35 锤/回合（中后期）估算，用于把"奇观产能"折算成"省下多少回合"。
"""

# (时代名, 奇观造价, 工人造价, 城市产能/回合)
ERAS = [
    ("远古",   200,  60, 10),
    ("古典",   200,  70, 14),
    ("中古",   440,  85, 22),
    ("文艺复兴", 620, 100, 28),
    ("工业",   950, 120, 35),
    ("现代",  1250, 140, 42),
]

# 奇观数量（原版大致口径，用于估算"全时代解禁"多拿到多少）
WONDER_COUNT = {"远古": 6, "古典": 6, "中古": 5, "文艺复兴": 6, "工业": 5, "现代": 5}

W = 74


def head(t):
    print("\n" + "=" * W)
    print(t)
    print("=" * W)


def sec_move():
    head("[1] 移动力翻倍：节奏收益（tempo）")
    print("侦察兵 3 → 6，探索同一片区域所需回合数直接减半：")
    print("  扫图范围   3移动耗时   6移动耗时   提前回合")
    for tiles in (9, 18, 30):
        t3, t6 = tiles / 3, tiles / 6
        print(f"  {tiles:>3} 格      {t3:>6.1f} 回合  {t6:>6.1f} 回合   {t3 - t6:>5.1f}")

    print("\n移民 2 → 4，到达铺城点所需回合：")
    print("  单程距离   2移动耗时   4移动耗时   省下回合")
    rows = []
    for d in (4, 6, 8, 12):
        t2, t4 = d / 2, d / 4
        rows.append((d, t2, t4, t2 - t4))
        print(f"  {d:>3} 格      {t2:>6.1f} 回合  {t4:>6.1f} 回合   {t2 - t4:>5.1f}")

    # 折算：一局典型 8 个移民，平均距离 8 格，早期城市 4 锤/回合
    settle_n, avg_d, city_prod = 8, 8, 4
    saved_per = avg_d / 2 - avg_d / 4
    saved_city_turns = settle_n * saved_per
    equiv = saved_city_turns * city_prod
    print(f"\n折算（{settle_n} 个移民、平均 {avg_d} 格、早期城市 {city_prod} 锤/回合）：")
    print(f"  累计省下约 {saved_city_turns:.0f} 个「城市已上线回合」")
    print(f"  ≈ 等效 {equiv:.0f} 产能的早期产出（不含更快触发的尤里卡/部落村庄）")
    print("  ⚠ 这只算了产能。真正的价值是**抢地**：AI 在神级扩张极快，")
    print("     早 2 回合到达就能占到本来会被抢走的地块——这部分无法用产能折算。")
    return equiv


def sec_wonder():
    head("[2] 工人加速：单次投入产出比（核心风险区）")
    print("每消耗 1 次工人使用次数 = 奇观当前进度的 pct%。")
    print("工人 = 3 次使用次数，所以 1 个工人 = 3×pct% 个奇观进度。\n")
    print(f"{'时代':<8}{'奇观造价':>8}{'工人造价':>8}{'pct':>6}{'1工人换到的产能':>16}{'投入产出比':>12}{'折合省下回合':>14}")
    for pct in (15, 30):
        print("-" * W)
        for name, wc, bc, cp in ERAS:
            gained = 3 * pct / 100 * wc
            ratio = gained / bc
            turns = gained / cp
            print(f"{name:<8}{wc:>8}{bc:>8}{pct:>6}{gained:>16.0f}{ratio:>11.2f}x{turns:>13.1f}")
    print("\n关键读数：")
    print("  · 15%（秦始皇原版）在远古是 1.50x，工业是 3.56x")
    print("  · 30%（本次要求）在远古是 3.00x，工业是 7.13x")
    print("  · **越到后期越离谱**——因为奇观造价涨了 5 倍，工人只涨了 2 倍")
    print("  · 工业时代一次工人使用次数 = 一个城市 8 回合的全部产能")


def sec_era_unlock():
    head("[3] 全时代解禁的边际影响：这才是真正的大头")
    print("秦始皇原版只能加速远古+古典奇观。解禁后：")
    qin_prod = sum(WONDER_COUNT[n] * wc for n, wc, bc, cp in ERAS if n in ("远古", "古典"))
    all_prod = sum(WONDER_COUNT[n] * wc for n, wc, bc, cp in ERAS)
    print(f"  原版可加速的奇观总产能（远古+古典，{WONDER_COUNT['远古'] + WONDER_COUNT['古典']} 座）：{qin_prod:>6} 锤")
    print(f"  解禁后可加速的奇观总产能（全 {sum(WONDER_COUNT.values())} 座）：{all_prod:>6} 锤")
    print(f"  可兑换的奇观产能池扩大 {all_prod / qin_prod:.1f} 倍")
    print("\n  再乘上 15%→30% 的倍率（2.0x）：")
    print(f"  总兑换能力放大 {all_prod / qin_prod * 2:.1f} 倍")
    print("\n  折算成工人数（按各时代工人造价，3 次/个，30%）：")
    total_builder_cost = 0
    for n, wc, bc, cp in ERAS:
        cnt = WONDER_COUNT[n]
        need = cnt * wc / (3 * 0.30 * wc)  # = cnt / 0.9
        cost = need * bc
        total_builder_cost += cost
        print(f"    {n:<8}{cnt} 座奇观 → 约需 {need:>4.1f} 个工人，折合 {cost:>6.0f} 锤")
    print(f"  合计约 {total_builder_cost:.0f} 锤的工人，可换走全场奇观")
    return all_prod / qin_prod * 2


def sec_instant():
    head("[4] 「30%」的实际游戏效果：不是加速，是必得")
    print("单次 pct × 使用次数：")
    for pct in (15, 30):
        for charges, note in ((3, "基础工人"), (4, "建成金字塔后")):
            total = pct * charges
            flag = "→ 一个工人直接完工" if total >= 100 else ("→ 剩 %.0f%% 靠正常生产" % (100 - total))
            print(f"  {pct}% × {charges} 次（{note}）= {total}%  {flag}")
    print("\n结论：30% + 金字塔后的 4 次工人 = 120%，")
    print("      意味着**任何奇观，只要开了头，一个工人就能当场拿下**。")
    print("      奇观竞赛从「产能比拼」退化成「谁手里有工人」。")


def sec_gold():
    head("[5] 与金币/信仰的耦合：把经济直接变成奇观")
    print("原版用金币买单位/建筑的兑换率约为 0.5 产能/金币（即 2 金币换 1 锤）。")
    print("买工人再拿去加速奇观，兑换率变成：")
    print(f"{'时代':<8}{'工人金币价':>10}{'30%换到的奇观产能':>20}{'产能/金币':>12}{'相对正常购买':>14}")
    for name, wc, bc, cp in ERAS:
        gold = bc * 2
        gained = 3 * 0.30 * wc
        rate = gained / gold
        print(f"{name:<8}{gold:>10}{gained:>20.0f}{rate:>11.2f}{rate / 0.5:>13.1f}x")
    print("\n  ⚠ 这直接绕过了「奇观不能用金币买」的原版设计。")
    print("  ⚠ 本 mod 的信仰是溢出的（v5 远古信仰比 1.30），信仰买工人 → 加速奇观 →")
    print("     奇观再给产出，形成正反馈。这是唯一需要靠试玩确认是否会失控的环节。")


def sec_sens():
    head("[6] 敏感性：pct 与工人造价的组合（工业时代奇观 950 锤）")
    print(f"{'pct':<6}" + "".join(f"{'工人%d' % bc:>10}" for bc in (85, 120, 160)))
    for pct in (10, 15, 20, 25, 30, 40, 50):
        line = f"{pct:<6}"
        for bc in (85, 120, 160):
            r = 3 * pct / 100 * 950 / bc
            line += f"{r:>9.2f}x"
        print(line)
    print("\n  红线建议：")
    print("   · 投入产出比 > 3.0x 就已经明显破坏经济平衡（正常投资回报约 1.0~1.5x）")
    print("   · 30% / 工业时代 = 7.1x，接近「无限产能」")
    print("   · 若要保留 30%，强烈建议**不解禁时代**（MaxEra 保持 2），把 7.1x 砍回远古的 3.0x")


def sec_concl():
    head("[7] 结论与红线")
    print("A. 移动力翻倍：属于「强但不破坏」的改动。")
    print("   它放大的是一切既有节奏（探索、铺城、逃跑），不直接产生数值。")
    print("   对新手是明显利好——新手最大的问题就是回合不够用。可以保留。\n")
    print("B. 工人加速 30% + 全时代：属于「破坏性」改动，必须明确告知。")
    print("   三点原因：")
    print("     1) 投入产出比 3.0x ~ 7.1x，正常投资是 1.0~1.5x")
    print("     2) 4 次工人 = 120%，奇观变成「有工人必得」")
    print("     3) 越到后期越离谱，恰好和「固定加成被时代稀释」的方向相反——")
    print("        等于用后期失控来补偿前期的产能不足，曲线形状会很怪")
    print("\n   我的建议：保留 30%（你要的爽感），但**保留时代限制**，")
    print("   或者把 pct 降到 15~20% 再解禁时代。两者选一，不要两个都要。")
    print("   代码里两个旋钮都留好了，改一行就行。")


def export_csv():
    path = os.path.join(OUT, "config", "tempo_impact.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["时代", "奇观造价", "工人造价", "pct15_投入产出比", "pct30_投入产出比",
                    "pct30_省下回合", "pct30_金币兑换率"])
        for name, wc, bc, cp in ERAS:
            w.writerow([name, wc, bc,
                        round(3 * 0.15 * wc / bc, 2),
                        round(3 * 0.30 * wc / bc, 2),
                        round(3 * 0.30 * wc / cp, 1),
                        round(3 * 0.30 * wc / (bc * 2), 2)])
    print("\n[导出] %s" % path)


if __name__ == "__main__":
    print(ASSUME)
    sec_move()
    sec_wonder()
    ratio = sec_era_unlock()
    sec_instant()
    sec_gold()
    sec_sens()
    sec_concl()
    export_csv()
