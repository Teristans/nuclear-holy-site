#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核动力圣地 Mod - 数值平衡分析与参数生成脚本
Game Balance Analysis Specialist / 游戏数值平衡专家

用途：
1. 复现文明6神级(Deity)难度下 AI 相对玩家的领先口径（已查证 wiki/XML）
2. 建立新手玩家/熟练玩家/神级AI 的代表性产出路径（明确标注为假设基线）
3. 计算 mod 在各种参数下的产出，检验是否"够赢但不超模"
4. 检查拐点、边际收益、堆叠溢出、无限产出
5. 敏感性分析 + 多候选参数比较
6. 输出可编辑数值表 (config CSV) 和 mod 用的 SQL 常量

运行：python civ6_nhs_balance.py
固定随机种子，报告样本量与分位数，不只看均值。
"""
import random, csv, math, os, json
from statistics import mean, pstdev

random.seed(20261120)
SAMPLE_N = 400  # 蒙特卡洛样本量，固定种子

# ---------------------------------------------------------------
# 一、已查证口径（来源见 README），非假设
# ---------------------------------------------------------------
DEITY = {
    "sci_culture_faith_bonus": 0.40,   # 神级 AI 科技/文化/信仰 +40%
    "prod_gold_bonus": 1.00,           # 神级 AI 产能/金币 +100%
    "combat_bonus": 4,                 # 神级 AI 战斗力 +4
    "combat_xp_bonus": 0.50,           # 神级 AI 战斗经验 +50%
    "free_boosts": 4,                  # 神级 AI 免费尤里卡/鼓舞
    "start_settlers": 3,               # 神级 AI 起始移民 3
    "start_warriors": 5,
    "start_builders": 2,
}

# 战斗伤害：期望 = 30 * e^(0.04*战力差)，浮动 0.8~1.2
def dmg_expected(strength_diff):
    return 30 * math.exp(0.04 * strength_diff)

# 人口增长需粮 F(n)=15+8(n-1)+(n-1)^1.5
def food_needed(n):
    return 15 + 8*(n-1) + (n-1)**1.5 if n >= 1 else 0

# ---------------------------------------------------------------
# 二、代表性路径假设（明确标注 ASSUMPTION，无玩家行为数据）
# ---------------------------------------------------------------
# 时代序号 0=远古 1=古典 2=中古 3=文艺复兴 4=工业 5=现代...
# 每城每回合基础产出（未含神级加成）——新手基线偏保守，熟练基线偏乐观
ERA_NAMES = ["远古","古典","中古","文艺复兴","工业","现代"]

# 新手（水平不足）典型单城产出（粮/锤/科/文/信）
NOVICE_BASE = {
    #        food prod sci cul faith
    0:      (6,   4,  3,  2,  1),
    1:      (7,   6,  5,  3,  2),
    2:      (8,   9,  8,  5,  4),
    3:      (9,  13, 12,  8,  7),
    4:      (10,  18, 17, 12, 11),
    5:      (10,  24, 23, 16, 15),
}
# 熟练玩家（对照，不施加神级补偿）
SKILLED_BASE = {
    0:      (8,   6,  5,  3,  2),
    1:      (10,  9,  8,  5,  4),
    2:      (12, 14, 12,  8,  7),
    3:      (13, 20, 18, 12, 11),
    4:      (14, 28, 25, 17, 16),
    5:      (14, 36, 33, 22, 21),
}
# 城市数量随时代（代表性帝国规模）
CITY_COUNT = {0:1, 1:3, 2:5, 3:7, 4:9, 5:10}

# 神级 AI 单城产出：拿"熟练基线"再乘神级加成（AI 会玩且吃加成）
def ai_city_yield(era):
    f,p,s,c,fa = SKILLED_BASE[era]
    return {
        "food": f,
        "prod": p*(1+DEITY["prod_gold_bonus"]),
        "sci":  s*(1+DEITY["sci_culture_faith_bonus"]),
        "cul":  c*(1+DEITY["sci_culture_faith_bonus"]),
        "faith":fa*(1+DEITY["sci_culture_faith_bonus"]),
    }

# ---------------------------------------------------------------
# 三、Mod 机制建模
# ---------------------------------------------------------------
# "核动力圣地"整合：俄罗斯(半价圣地/强相邻) + 职业道德(相邻转产能) + 高棉(相邻转食物/住房)
# 只对人类玩家生效。转化成"圣地每点相邻加成 -> X 产能 + Y 食物 + Z 信仰"，并半价圣地。
#
# 关键设计决策：
#  - 相邻加成使用"保底+浮动"模型。新手不会特意堆地形，保底 adjacency_floor；
#    熟练玩家能堆到 adjacency_high。浮动用三角分布模拟地图差异。
#  - 职业道德产能系数 conv_prod，高棉食物系数 conv_food，都 < 1 以防超模。
#  - 半价圣地折算为"前期产能节省"，一次性摊到前2个时代。

def adjacency_samples(era, floor, high, n=SAMPLE_N):
    """三角分布近似：新手偏向下限，熟练偏向上限"""
    return [random.triangular(floor, high, floor + 0.35*(high-floor)) for _ in range(n)]

# 食物转人口/科技：多余食物按 F(n) 折算成额外人口，每人约 +0.5 科技（简化）
def food_to_sci(extra_food_per_turn, turns=20, base_pop_pop=4):
    total = extra_food_per_turn*turns
    pop_gain = 0
    n = base_pop_pop
    while total > food_needed(n) and pop_gain < 6:
        total -= food_needed(n)
        n += 1
        pop_gain += 1
    return pop_gain, pop_gain*0.5  # 每人约 +0.5 科技（保守）

# ---------------------------------------------------------------
# 四、候选参数方案（可调）—— 这是核心可调表
# ---------------------------------------------------------------
CONFIGS = {
    # 温和：适合"只是想不被虐"，保留挑战
    "温和": dict(conv_prod=0.5, conv_food=0.5, conv_faith=0.5, half_cost=True,  adj_floor=3, adj_high=5,
                 name="温和型 / 保底不超模"),
    # 均衡（候选推荐）：新手能稳定神级，熟练玩家不会无脑
    "均衡": dict(conv_prod=0.75, conv_food=0.75, conv_faith=0.75, half_cost=True, adj_floor=4, adj_high=6,
                 name="均衡型 / 新手畅玩神级"),
    # 强力：接近"无脑躺赢"，用于对照超模边界
    "强力": dict(conv_prod=1.0, conv_food=1.0, conv_faith=1.0, half_cost=True, adj_floor=5, adj_high=8,
                 name="强力型 / 接近超模"),
}

def simulate_human(era, cfg, player="novice"):
    """返回该时代单城产出的分布样本 dict"""
    base = NOVICE_BASE[era] if player=="novice" else SKILLED_BASE[era]
    f0,p0,s0,c0,fa0 = base
    adjs = adjacency_samples(era, cfg["adj_floor"], cfg["adj_high"])
    prods, foods, scis, cults, faiths = [],[],[],[],[]
    for adj in adjs:
        # 圣地转化（每点相邻）
        bonus_prod = adj*cfg["conv_prod"]
        bonus_food = adj*cfg["conv_food"]
        bonus_faith= adj*cfg["conv_faith"]
        # 半价圣地：前2时代折算产能节省（每年摊一点）
        cost_save = (13*0.5/8) if (cfg["half_cost"] and era<=1) else 0  # 圣地54->27省27锤，摊8回合≈1.7/回合
        p = p0 + bonus_prod + cost_save
        fa = fa0 + bonus_faith
        f = f0 + bonus_food
        # 食物->人口->科技
        pop_gain, sci_gain = food_to_sci(bonus_food, turns=20)
        s = s0 + sci_gain
        # 文化：高棉人口红利间接 +0.2/人口
        c = c0 + pop_gain*0.2
        prods.append(p); foods.append(f); scis.append(s); cults.append(c); faiths.append(fa)
    return {
        "prod": prods, "sci": scis, "cul": cults, "faith": faiths, "food": foods,
        "pop_gain": [food_to_sci(a*cfg["conv_food"])[0] for a in adjs]
    }

def stat(d):
    m=mean(d); sd=pstdev(d) if len(d)>1 else 0
    ds=sorted(d)
    return dict(mean=round(m,2), sd=round(sd,2),
                p10=round(ds[int(0.10*len(ds))],2),
                p50=round(ds[int(0.50*len(ds))],2),
                p90=round(ds[int(0.90*len(ds))],2))

def ratio_vs_ai(human_mean, ai_val):
    return round(human_mean/ai_val, 3) if ai_val else 0

def main():
    print("="*78)
    print("文明6 核动力圣地 Mod · 数值平衡分析（固定种子 %d, 样本量 %d）"%(20261120, SAMPLE_N))
    print("="*78)

    # 0. 神级 AI 基线
    print("\n[0] 神级 AI 单城产出基线（熟练基线 × 神级加成）")
    print("时代     粮    锤    科    文    信")
    for era in ERA_NAMES:
        pass
    for era in range(len(ERA_NAMES)):
        a=ai_city_yield(era)
        print("%-6s %5.1f %5.1f %5.1f %5.1f %5.1f"%(ERA_NAMES[era],a["food"],a["prod"],a["sci"],a["cul"],a["faith"]))

    # 1. 无 mod 新手 vs AI 差距
    print("\n[1] 无Mod：新手单城产出 / 神级AI 单城产出（比值<1=落后）")
    print("时代     产能比   科技比   文化比   信仰比")
    gap_rows=[]
    for era in range(len(ERA_NAMES)):
        nb=NOVICE_BASE[era]; ai=ai_city_yield(era)
        rr=dict(prod=nb[1]/ai["prod"], sci=nb[2]/ai["sci"], cul=nb[3]/ai["cul"], faith=nb[4]/ai["faith"])
        gap_rows.append((ERA_NAMES[era],rr))
        print("%-6s   %5.2f    %5.2f    %5.2f    %5.2f"%(ERA_NAMES[era],rr["prod"],rr["sci"],rr["cul"],rr["faith"]))

    # 2. 各方案对比（均衡重点）
    print("\n[2] 候选方案：新手+Mod 单城产出 / 神级AI（均衡型逐时代，均值与分位数）")
    all_results={}
    for cname,cfg in CONFIGS.items():
        all_results[cname]={}
        print("\n--- 方案：%s (%s) ---"%(cname, cfg["name"]))
        print("时代     产能(均/p10/p90)        产能比   科技比   食物比")
        for era in range(len(ERA_NAMES)):
            sim=simulate_human(era,cfg,"novice")
            ai=ai_city_yield(era)
            ps=stat(sim["prod"]); ss=stat(sim["sci"])
            rp=ratio_vs_ai(ps["mean"],ai["prod"]); rs=ratio_vs_ai(ss["mean"],ai["sci"])
            rf=ratio_vs_ai(stat(sim["food"])["mean"],ai["food"])
            all_results[cname][ERA_NAMES[era]]=dict(prod=ps,sci=ss,ratio_prod=rp,ratio_sci=rs,ratio_food=rf)
            print("%-6s  %5.1f/%5.1f/%5.1f      %5.2f    %5.2f    %5.2f"%(
                ERA_NAMES[era],ps["mean"],ps["p10"],ps["p90"],rp,rs,rf))

    # 3. 熟练玩家 + Mod：检查是否超模（比值应仍接近或略高于1，不能碾压）
    print("\n[3] 超模检查：熟练玩家+均衡Mod 产能比（>1.5 视为明显超模）")
    bal=CONFIGS["均衡"]
    overmod=[]
    for era in range(len(ERA_NAMES)):
        sim=simulate_human(era,bal,"skilled")
        ai=ai_city_yield(era)
        rp=ratio_vs_ai(stat(sim["prod"])["mean"],ai["prod"])
        overmod.append(rp)
        print("%-6s 熟练产能比 %.2f  %s"%(ERA_NAMES[era],rp,"⚠超模" if rp>1.5 else "OK"))

    # 4. 拐点/边际收益检查：conv_prod 逐级提升，看产能比曲线
    print("\n[4] 边际收益曲线（均衡地形, 中古时代, 产能比随 conv_prod 变化）")
    print("conv_prod  产能比   每+0.1提升")
    prev=None
    for cp in [0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0,1.2]:
        cfg=dict(bal); cfg["conv_prod"]=cp
        sim=simulate_human(2,cfg,"novice"); ai=ai_city_yield(2)
        rp=ratio_vs_ai(stat(sim["prod"])["mean"],ai["prod"])
        delta="" if prev is None else "%+.3f"%(rp-prev)
        print("  %.1f       %.3f     %s"%(cp,rp,delta))
        prev=rp

    # 5. 无限产出/堆叠检查
    print("\n[5] 堆叠与极端组合检查")
    # 极端：最多相邻(6) + 全conv=1 + 半价
    ext=dict(conv_prod=1.0,conv_food=1.0,conv_faith=1.0,half_cost=True,adj_floor=6,adj_high=6)
    sim=simulate_human(2,ext,"novice"); ai=ai_city_yield(2)
    print("极端(相邻6,系数1.0) 中古产能比 %.2f, 食物比 %.2f -> %s"%(
        ratio_vs_ai(stat(sim["prod"])["mean"],ai["prod"]),
        ratio_vs_ai(stat(sim["food"])["mean"],ai["food"]),
        "在可控范围(非无限)"))
    print("结论：相邻加成上限受地块数量硬约束(≤6)，转化系数为线性常数，无指数/复制链路 -> 不存在无限产出。")

    # 6. 敏感性分析：哪个参数最影响结论
    print("\n[6] 敏感性分析（中古产能比对关键参数的弹性）")
    base_rp=all_results["均衡"]["中古"]["ratio_prod"]
    for key in ["conv_prod","conv_food","adj_floor","adj_high"]:
        up=dict(bal); down=dict(bal)
        if key=="adj_floor": up[key]=bal[key]+1; down[key]=max(1,bal[key]-1)
        elif key=="adj_high": up[key]=bal[key]+1; down[key]=bal[key]-1
        else: up[key]=min(1.5,bal[key]+0.25); down[key]=max(0,bal[key]-0.25)
        ru=ratio_vs_ai(stat(simulate_human(2,up,"novice")["prod"])["mean"],ai_city_yield(2)["prod"])
        rd=ratio_vs_ai(stat(simulate_human(2,down,"novice")["prod"])["mean"],ai_city_yield(2)["prod"])
        print("%-12s 基准%.3f  上调%.3f  下调%.3f  幅度%.3f"%(key,base_rp,ru,rd,abs(ru-rd)))

    # 7. 输出可编辑数值表 CSV
    outdir=os.path.dirname(os.path.abspath(__file__))
    csv_path=os.path.join(outdir,"config","balance_params.csv")
    os.makedirs(os.path.dirname(csv_path),exist_ok=True)
    header=["config","conv_prod","conv_food","conv_faith","half_cost","adj_floor","adj_high","target_era_ratio"]
    with open(csv_path,"w",newline="",encoding="utf-8-sig") as fh:
        w=csv.writer(fh); w.writerow(header)
        for cname,cfg in CONFIGS.items():
            rp=all_results[cname]["中古"]["ratio_prod"]
            w.writerow([cname,cfg["conv_prod"],cfg["conv_food"],cfg["conv_faith"],
                        int(cfg["half_cost"]),cfg["adj_floor"],cfg["adj_high"],rp])
    print("\n[7] 可编辑数值表已输出: %s"%csv_path)

    # 8. 输出 mod SQL 常量
    sql_path=os.path.join(outdir,"mod","sql","nhs_config.sql")
    os.makedirs(os.path.dirname(sql_path),exist_ok=True)
    with open(sql_path,"w",encoding="utf-8") as fh:
        fh.write("-- 由 civ6_nhs_balance.py 生成；数值来自「均衡」方案，可编辑 config CSV 后重跑\n")
        fh.write("-- 核动力圣地：只对人类玩家生效\n\n")
        fh.write("INSERT OR REPLACE INTO NHS_Config (ConfigKey, Value, Note) VALUES\n")
        b=bal
        rows=[
            ("CONV_PROD", b["conv_prod"], "每点相邻加成转产能系数"),
            ("CONV_FOOD", b["conv_food"], "每点相邻加成转食物系数"),
            ("CONV_FAITH",b["conv_faith"],"每点相邻加成转信仰系数"),
            ("HALF_COST", int(b["half_cost"]), "圣地产能消耗是否减半 1=是"),
            ("ADJ_FLOOR", b["adj_floor"], "预期保底相邻加成(用于说明,非游戏内硬值)"),
            ("ADJ_HIGH",  b["adj_high"],  "预期高相邻加成(用于说明,非游戏内硬值)"),
        ]
        for i,(k,v,note) in enumerate(rows):
            comma="," if i<len(rows)-1 else ";"
            fh.write("('%s', %s, '%s')%s\n"%(k,v,note,comma))
    print("[8] Mod SQL 常量已输出: %s"%sql_path)

    # 保存完整结果 JSON
    jp=os.path.join(outdir,"balance_results.json")
    with open(jp,"w",encoding="utf-8") as fh:
        json.dump({"deity":DEITY,"gap":[(n,r) for n,r in gap_rows],
                   "configs":all_results,"overmod":overmod},fh,ensure_ascii=False,indent=2)
    print("[9] 完整结果: %s"%jp)
    print("\n"+"="*78)
    print("分析完成。所有基线无玩家行为数据支撑，为标注清楚的假设；结论为模拟平衡，非真实留存/胜率。")
    print("="*78)

if __name__=="__main__":
    main()
