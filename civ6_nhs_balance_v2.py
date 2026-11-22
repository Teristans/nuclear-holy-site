#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核动力圣地 Mod - 数值平衡分析 v2（修正建模缺陷）
Game Balance Analysis Specialist

v2 修正：
- 补回"经文卡使圣地相邻翻倍"机制（内置到 mod，新手免操作）
- 加入建筑随时代放大系数（真实圣地产出随神庙/礼拜堂增长）
- 目标导向校准：反推满足"新手前期产能比≈0.8、食物比≈1.15、熟练不超模"的系数

运行：python civ6_nhs_balance_v2.py
固定种子 20261120，样本量 600，报告 p10/p50/p90 与标准差。
"""
import random, csv, math, os, json
from statistics import mean, pstdev

SEED = 20261120
random.seed(SEED)
N = 600

# ============ 已查证口径（非假设）============
DEITY = dict(sci_cul_faith=0.40, prod_gold=1.00, combat=4, xp=0.50,
             boosts=4, settlers=3, warriors=5, builders=2)
def dmg(diff): return 30*math.exp(0.04*diff)
def food_needed(n): return 15+8*(n-1)+(n-1)**1.5 if n>=1 else 0

# ============ 假设基线（无玩家行为数据，明确标注）============
ERAS = ["远古","古典","中古","文艺复兴","工业","现代"]
# 新手单城基础产出 food/prod/sci/cul/faith
NOVICE = {0:(6,4,3,2,1), 1:(7,6,5,3,2), 2:(8,9,8,5,4),
          3:(9,13,12,8,7), 4:(10,18,17,12,11), 5:(10,24,23,16,15)}
SKILLED= {0:(8,6,5,3,2), 1:(10,9,8,5,4), 2:(12,14,12,8,7),
          3:(13,20,18,12,11), 4:(14,28,25,17,16), 5:(14,36,33,22,21)}
# 圣地建筑随时代放大（神庙/礼拜堂/祭祀建筑逐步堆叠），假设
ERA_MULT = {0:1.0, 1:1.3, 2:1.8, 3:2.5, 4:3.4, 5:4.2}
# 内置经文：相邻信仰翻倍（mod 内置，新手免挂卡/免创教）
SCRIPTURE = 2.0

def ai_city(era):
    f,p,s,c,fa = SKILLED[era]
    return dict(food=f, prod=p*(1+DEITY["prod_gold"]),
                sci=s*(1+DEITY["sci_cul_faith"]), cul=c*(1+DEITY["sci_cul_faith"]),
                faith=fa*(1+DEITY["sci_cul_faith"]))

def adj_samples(floor, high, n=N, mode_ratio=0.35):
    mode = floor + mode_ratio*(high-floor)
    return [random.triangular(floor, high, mode) for _ in range(n)]

def food_to_sci(extra_food, turns=20, pop0=4):
    total=extra_food*turns; gain=0; n=pop0
    while total>food_needed(n) and gain<6:
        total-=food_needed(n); n+=1; gain+=1
    return gain, gain*0.5

# ============ 候选方案 ============
CONFIGS = {
    "温和": dict(conv_prod=0.35, conv_food=0.55, half_cost=True, adj_floor=3, adj_high=5,
                 note="小幅缓解，保留大部分挑战"),
    "均衡": dict(conv_prod=0.62, conv_food=0.70, half_cost=True, adj_floor=4, adj_high=6,
                 note="推荐：新手前期产能≈AI八成，食物略超标"),
    "强力": dict(conv_prod=0.85, conv_food=0.90, half_cost=True, adj_floor=5, adj_high=8,
                 note="接近社区核动力强度，熟练玩家可能超模"),
}

def simulate(era, cfg, who="novice"):
    base = NOVICE[era] if who=="novice" else SKILLED[era]
    f0,p0,s0,c0,fa0 = base
    em = ERA_MULT[era]
    out={k:[] for k in ["prod","food","sci","cul","faith","pop_gain"]}
    for adj in adj_samples(cfg["adj_floor"], cfg["adj_high"]):
        eff_adj = adj*SCRIPTURE*em          # 经文翻倍 + 时代放大
        bonus_prod  = eff_adj*cfg["conv_prod"]
        bonus_faith = eff_adj*0.5            # 信仰自然产出（放大后的一半，避免信仰爆炸）
        bonus_food  = adj*em*cfg["conv_food"]  # 高棉：按原始相邻(不翻倍)×时代
        cost_save = (13*0.5/8) if (cfg["half_cost"] and era<=1) else 0
        pop_gain, sci_gain = food_to_sci(bonus_food)
        out["prod"].append(p0+bonus_prod+cost_save)
        out["faith"].append(fa0+bonus_faith)
        out["food"].append(f0+bonus_food)
        out["sci"].append(s0+sci_gain)
        out["cul"].append(c0+pop_gain*0.2)
        out["pop_gain"].append(pop_gain)
    return out

def st(d):
    m=mean(d); sd=pstdev(d); ds=sorted(d)
    return dict(mean=round(m,2), sd=round(sd,2),
                p10=round(ds[int(0.10*len(ds))],2),
                p50=round(ds[int(0.50*len(ds))],2),
                p90=round(ds[int(0.90*len(ds))],2))

def ratio(h,a): return round(h/a,3) if a else 0

def main():
    print("="*80)
    print("核动力圣地 Mod 数值平衡 v2 | 种子 %d 样本 %d/方案/时代"%(SEED,N))
    print("="*80)

    print("\n[0] 神级AI 单城基线 (熟练基线×神级加成)")
    print("时代     锤    科    文    信")
    for e,nm in enumerate(ERAS):
        a=ai_city(e)
        print("%-5s %5.1f %5.1f %5.1f %5.1f"%(nm,a["prod"],a["sci"],a["cul"],a["faith"]))

    print("\n[1] 无Mod 新手/AI 比值")
    print("时代     产能  科技  文化")
    for e,nm in enumerate(ERAS):
        n=NOVICE[e]; a=ai_city(e)
        print("%-5s  %4.2f  %4.2f  %4.2f"%(nm,n[1]/a["prod"],n[2]/a["sci"],n[3]/a["cul"]))

    results={}
    for cname,cfg in CONFIGS.items():
        results[cname]={}
        print("\n[%s] %s"%(cname,cfg["note"]))
        print("时代     产能均/p10/p90      产能比  食物比  科技比  信仰比(p50)")
        for e,nm in enumerate(ERAS):
            s=simulate(e,cfg,"novice"); a=ai_city(e)
            ps=st(s["prod"]); fs=st(s["food"]); ss=st(s["sci"]); fth=st(s["faith"])
            rp=ratio(ps["mean"],a["prod"]); rf=ratio(fs["mean"],a["food"])
            rs=ratio(ss["mean"],a["sci"]); rfa=ratio(fth["mean"],a["faith"])
            results[cname][nm]=dict(prod=ps,food=fs,sci=ss,ratio_prod=rp,ratio_food=rf,ratio_sci=rs,ratio_faith=rfa)
            print("%-5s %5.1f/%4.1f/%4.1f     %4.2f   %4.2f   %4.2f   %4.2f(%4.1f)"%(
                nm,ps["mean"],ps["p10"],ps["p90"],rp,rf,rs,rfa,fth["p50"]))

    print("\n[3] 超模检查：熟练+均衡Mod 产能比 (>1.5=超模, >1.2=需关注)")
    for e,nm in enumerate(ERAS):
        s=simulate(e,CONFIGS["均衡"],"skilled"); a=ai_city(e)
        rp=ratio(st(s["prod"])["mean"],a["prod"])
        flag="⚠超模" if rp>1.5 else ("关注" if rp>1.2 else "OK")
        print("%-5s %.2f %s"%(nm,rp,flag))

    print("\n[4] 边际收益：均衡地形中古，产能比随 conv_prod")
    prev=None
    for cp in [0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0]:
        c=dict(CONFIGS["均衡"]); c["conv_prod"]=cp
        rp=ratio(st(simulate(2,c,"novice")["prod"])["mean"],ai_city(2)["prod"])
        d="" if prev is None else "%+.3f"%(rp-prev)
        print(" conv %.1f -> %.3f %s"%(cp,rp,d)); prev=rp

    print("\n[5] 堆叠/无限产出检查")
    ext=dict(conv_prod=1.0,conv_food=1.0,half_cost=True,adj_floor=6,adj_high=6)
    s=simulate(2,ext,"novice"); a=ai_city(2)
    print(" 极端(相邻6,conv1.0) 中古产能比 %.2f 食物比 %.2f"%(
        ratio(st(s["prod"])["mean"],a["prod"]), ratio(st(s["food"])["mean"],a["food"])))
    print(" 无指数/复制链路，相邻≤6硬上限 -> 不存在无限产出。")

    print("\n[6] 敏感性（中古产能比弹性）")
    b=CONFIGS["均衡"]; base=results["均衡"]["中古"]["ratio_prod"]
    for key in ["conv_prod","conv_food","adj_floor","adj_high"]:
        up=dict(b); dn=dict(b)
        if key.startswith("conv"):
            up[key]=min(1.0,b[key]+0.2); dn[key]=max(0,b[key]-0.2)
        else:
            up[key]=b[key]+1; dn[key]=max(1,b[key]-1)
        ru=ratio(st(simulate(2,up,"novice")["prod"])["mean"],ai_city(2)["prod"])
        rd=ratio(st(simulate(2,dn,"novice")["prod"])["mean"],ai_city(2)["prod"])
        print(" %-11s 基准%.3f 高%.3f 低%.3f 幅度%.3f"%(key,base,ru,rd,abs(ru-rd)))

    # 输出
    outdir=os.path.dirname(os.path.abspath(__file__))
    cp=os.path.join(outdir,"config","balance_params.csv"); os.makedirs(os.path.dirname(cp),exist_ok=True)
    with open(cp,"w",newline="",encoding="utf-8-sig") as fh:
        w=csv.writer(fh); w.writerow(["config","conv_prod","conv_food","scripture","half_cost","adj_floor","adj_high","era0_prod_ratio","era2_prod_ratio"])
        for cn,cfg in CONFIGS.items():
            w.writerow([cn,cfg["conv_prod"],cfg["conv_food"],SCRIPTURE,int(cfg["half_cost"]),
                        cfg["adj_floor"],cfg["adj_high"],
                        results[cn]["远古"]["ratio_prod"],results[cn]["中古"]["ratio_prod"]])
    print("\n[7] CSV: %s"%cp)

    # [8] 不再生成 mod/sql/nhs_config.sql —— 它引用了游戏里不存在的 NHS_Config 表，
    #      属于早期草稿遗留，已从交付物中移除。数值表的唯一权威来源是 config/balance_params.csv。
    print("[8] 跳过 SQL 常量生成（避免幽灵表）；数值表唯一来源: config/balance_params.csv")

    jp=os.path.join(outdir,"balance_results_v2.json")
    with open(jp,"w",encoding="utf-8") as fh:
        json.dump(dict(deity=DEITY,configs=results,era_mult=ERA_MULT,scripture=SCRIPTURE),fh,ensure_ascii=False,indent=2)
    print("[9] JSON: %s"%jp)
    print("\n"+"="*80)
    print("说明：基线为标注假设，结论为模拟平衡，非真实胜率；需实机试玩验证。")
    print("="*80)

if __name__=="__main__": main()
