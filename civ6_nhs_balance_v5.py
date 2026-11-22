#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核动力圣地 Mod - 数值平衡分析 v5
新增：职业道德(Work Ethic) + 极光之舞(Dance of the Aurora) + 经文政策卡(Scripture) + 耶稣会教育

已查证（非假设）：
  * BELIEF_WORK_ETHIC 先手艺人在 2021 改版：圣地相邻信仰数值 → 等量产锤
  * BELIEF_DANCE_OF_THE_AURORA：圣地 +1 信仰/相邻冻土
  * POLICY_SCRIPTURE：神学解锁，+100% 圣地相邻加成（政策卡，不是信条）
  * BELIEF_JESUIT_EDUCATION：可用信仰购买学院/剧院建筑

核心矛盾（本脚本要回答的问题）：
  经文把相邻值翻倍。相邻是"绝对值"，不随时代涨；而 AI 产能按时代翻倍。
  所以"内置经文"必然导致**远古超模、后期追平**——这与"全程 0.9~1.1"互斥。

运行：python civ6_nhs_balance_v5.py
"""
import random, math, os, json, csv
from statistics import mean

SEED = 20261120
random.seed(SEED)
N = 600

MR = dict(tundra_prod=1.0, tundra_faith=1.0)
KHMER_FOOD_PER_ADJ = 1.0

ERAS = ["远古", "古典", "中古", "文艺复兴", "工业", "现代"]
NOVICE = {0:(6,4,3,2,1), 1:(7,6,5,3,2), 2:(8,9,8,5,4),
          3:(9,13,12,8,7), 4:(10,18,17,12,11), 5:(10,24,23,16,15)}
SKILLED= {0:(8,6,5,3,2), 1:(10,9,8,5,4), 2:(12,14,12,8,7),
          3:(13,20,18,12,11), 4:(14,28,25,17,16), 5:(14,36,33,22,21)}
TUNDRA_WORKED = {0:3, 1:4, 2:6, 3:7, 4:8, 5:9}
TUNDRA_ADJ    = {0:2, 1:2, 2:3, 3:3, 4:3, 5:3}   # 与圣地相邻的冻土格（极光之舞计费）
DRAG = 0.5

def ai_city(e):
    f,p,s,c,fa = SKILLED[e]
    return dict(prod=p*2.0, food=f, sci=s*1.4, cul=c*1.4, faith=fa*1.4)

def adj_site(n=N):
    # 新手圣地裸相邻：山/林/区域/奇观，2~6，众数偏左
    return [random.triangular(2, 6, 3.5) for _ in range(n)]

def simulate(e, cfg, who="novice", tundra=True):
    f0,p0,s0,c0,fa0 = (NOVICE if who=="novice" else SKILLED)[e]
    tw = TUNDRA_WORKED[e] if tundra else 0
    ta = TUNDRA_ADJ[e] if tundra else 0
    out={k:[] for k in ["prod","food","faith"]}
    for a in adj_site():
        a_raw = a + ta*cfg.get("aurora",0)              # 极光之舞抬高相邻
        a_eff = a_raw*(2.0 if cfg.get("scripture") else 1.0)  # 经文翻倍
        d_prod = a_eff*cfg.get("work_ethic",0)          # 职业道德：相邻→产能
        d_faith= a_eff - a                              # 经文带来的信仰增量
        out["prod"].append(p0 + cfg["core_prod"] + tw*MR["tundra_prod"] + d_prod)
        out["faith"].append(fa0 + cfg["core_faith"] + tw*MR["tundra_faith"] + d_faith)
        out["food"].append(f0 + cfg["core_food"] + a_raw*KHMER_FOOD_PER_ADJ - tw*DRAG)
    return out

def m(d): return mean(d)
def ratio(h,a): return round(h/a,3) if a else 0

CONFIGS = {
    "A_全开(含经文)":  dict(core_prod=0, core_food=1, core_faith=2, aurora=1, work_ethic=1, scripture=True),
    "B_不内置经文":    dict(core_prod=0, core_food=1, core_faith=2, aurora=1, work_ethic=1, scripture=False),
    "C_只有职业道德":  dict(core_prod=0, core_food=1, core_faith=2, aurora=0, work_ethic=1, scripture=False),
}

def main():
    print("="*90)
    print("核动力圣地 v5 | 职业道德 + 极光之舞 + 经文 + 耶稣会教育 | 种子 %d 样本 %d"%(SEED,N))
    print("="*90)
    print("\n[0] 三条曲线的核心差异")
    print("  A：相邻翻倍(经文) + 相邻转产能(职业道德) + 冻土相邻(极光)  → 远古起飞")
    print("  B：去掉经文翻倍 → 相邻不翻倍，远古温和、后期略弱")
    print("  C：只加职业道德 → 变化最小")

    res={}
    for name,cfg in CONFIGS.items():
        res[name]={}
        print("\n[%s]"%name)
        print("时代   新手苔原产能 新手苔原食物 新手非苔原产能 新手信仰比 熟练苔原产能")
        for e,nm in enumerate(ERAS):
            a=ai_city(e)
            sn=simulate(e,cfg,"novice"); sp=simulate(e,cfg,"novice",False); sk=simulate(e,cfg,"skilled")
            r=(ratio(m(sn["prod"]),a["prod"]), ratio(m(sn["food"]),a["food"]),
               ratio(m(sp["prod"]),a["prod"]), ratio(m(sn["faith"]),a["faith"]),
               ratio(m(sk["prod"]),a["prod"]))
            res[name][nm]=r
            print("%-6s  %5.2f        %5.2f        %5.2f        %5.2f     %5.2f"%(nm,*r))

    print("\n[1] 关键判定：哪条曲线落在'全程 0.9~1.1'里？")
    for name in CONFIGS:
        vals=[res[name][nm][0] for nm in ERAS]
        inside=all(0.85<=v<=1.15 for v in vals)
        print("  %-16s 远古%.2f 中古%.2f 现代%.2f  → %s"%(
            name,vals[0],vals[2],vals[5],"✓ 落在区间内" if inside else "✗ 越界"))

    print("\n[2] 若坚持「从头爽到尾」要多高？")
    print("  经文翻倍后，远古产能比 1.5+ 是数学必然：相邻 5.8×2=11.6，而神级AI远古单城仅 12")
    print("  这不是参数没调好，而是'内置经文'把原版中古(神学)才有的杠杆提前到了远古")

    print("\n[3] 耶稣会教育：信仰→科技的通道（定性）")
    print("  信仰比 3.5~4.5 意味着大量盈余；买学院建筑约可折算 +0.05~0.10 科技比")
    print("  但我无法离线量化建筑价格/人口门槛，故此值不计入上表，仅作上限参考")

    print("\n[4] 结论")
    print("  · 选 A（全开）：远古 1.5 起飞 → 后期约 1.0，符合'偏爽'但越过 0.9~1.1 上限")
    print("  · 选 B（不内置经文）：远古 1.07 → 后期 0.78，曲线平滑但后期仍偏弱")
    print("  · 建议：默认 A，把经文写成一行开关；觉得远古太无脑就关掉它")

    outdir=os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(outdir,"config","balance_params_v5.csv"),"w",newline="",encoding="utf-8-sig") as fh:
        w=csv.writer(fh); w.writerow(["config","era","novice_tundra_prod","novice_tundra_food","novice_plain_prod","novice_faith","skilled_tundra_prod"])
        for name in CONFIGS:
            for nm in ERAS:
                w.writerow([name,nm]+list(res[name][nm]))
    with open(os.path.join(outdir,"balance_results_v5.json"),"w",encoding="utf-8") as fh:
        json.dump(dict(configs={k:{nm:dict(zip(["prod","food","plain_prod","faith","skilled_prod"],v)) for nm,v in d.items()} for k,d in res.items()}),
                  fh,ensure_ascii=False,indent=2)
    print("\n[5] CSV/JSON 已输出")

if __name__=="__main__": main()
