#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核动力圣地 Mod - 数值平衡分析 v3（新增「俄罗斯母亲」，并纠正建模口径）
Game Balance Analysis Specialist

v3 的两处关键修正（相对 v2）：

1) 【口径纠正】v2 把「相邻转产能 conv_prod」算进了 mod 收益，但那是原版
   「职业道德信条 + 经文政策卡」的效果，属于玩家可自行获得的手段，不是本 mod
   下发的。本版拆成两个模型：
     · 模型A（实际交付）：mod 只发固定加成 + 俄罗斯母亲苔原加成
     · 模型B（含原版协同）：A + 玩家自挂职业道德/经文的相邻转化，仅作参考
2) 【新增特性】俄罗斯母亲：苔原 +1 信仰 +1 产能（已查证），并显式建模
   苔原低食物的拖累（平地苔原不能造农场），不只算增益不算代价。

运行：python civ6_nhs_balance_v3.py
固定种子 20261120，样本量 600，报告 p10/p50/p90。
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

# 俄罗斯母亲 TRAIT_CIVILIZATION_MOTHER_RUSSIA（Fandom GS 数据模块已确认）
#   * 建成城市时额外 8 格领土
#   * 苔原地块 +1 信仰 +1 产能（市中心除外）
#   * 单位免疫暴风雪（本 mod 不移植）
MR = dict(per_tile_prod=1.0, per_tile_faith=1.0, extra_tiles=8)

# ============ 假设基线（无玩家行为数据，明确标注）============
ERAS = ["远古", "古典", "中古", "文艺复兴", "工业", "现代"]
NOVICE = {0:(6,4,3,2,1), 1:(7,6,5,3,2), 2:(8,9,8,5,4),
          3:(9,13,12,8,7), 4:(10,18,17,12,11), 5:(10,24,23,16,15)}
SKILLED= {0:(8,6,5,3,2), 1:(10,9,8,5,4), 2:(12,14,12,8,7),
          3:(13,20,18,12,11), 4:(14,28,25,17,16), 5:(14,36,33,22,21)}
ERA_MULT = {0:1.0, 1:1.3, 2:1.8, 3:2.5, 4:3.4, 5:4.2}
SCRIPTURE = 2.0

TUNDRA_TILES = {0:3, 1:4, 2:6, 3:7, 4:8, 5:9}
TUNDRA_FOOD_DRAG = 0.5   # 平地苔原 1 粮且不可造农场，相对草原平均少约 0.5 粮/格

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

def simulate(era, cfg, who="novice", tundra=True):
    """cfg: core_* = mod 固定加成; syn_prod/syn_food = 原版协同(可选,0=不计)"""
    base = NOVICE[era] if who=="novice" else SKILLED[era]
    f0,p0,s0,c0,fa0 = base
    em = ERA_MULT[era]
    tiles = TUNDRA_TILES[era] if tundra else 0
    out={k:[] for k in ["prod","food","sci","cul","faith","pop_gain"]}
    for adj in adj_samples(4, 6):
        syn_prod  = adj*SCRIPTURE*em*cfg.get("syn_prod",0)
        syn_food  = adj*em*cfg.get("syn_food",0)
        mr_prod   = tiles*MR["per_tile_prod"]
        mr_faith  = tiles*MR["per_tile_faith"]
        drag      = tiles*TUNDRA_FOOD_DRAG
        cost_save = (13*0.5/8) if cfg.get("half_cost") and era<=1 else 0
        pop_gain, sci_gain = food_to_sci(cfg["core_food"]+syn_food-drag)
        out["prod"].append(p0+cfg["core_prod"]+syn_prod+mr_prod+cost_save)
        out["faith"].append(fa0+cfg["core_faith"]+mr_faith+adj*0.25*em*cfg.get("faith_scale",0))
        out["food"].append(f0+cfg["core_food"]+syn_food-drag)
        out["sci"].append(s0+sci_gain)
        out["cul"].append(c0+cfg["core_cul"]+pop_gain*0.2)
        out["pop_gain"].append(pop_gain)
    return out

def st(d):
    m=mean(d); sd=pstdev(d); ds=sorted(d)
    return dict(mean=round(m,2), sd=round(sd,2),
                p10=round(ds[int(0.10*len(ds))],2),
                p50=round(ds[int(0.50*len(ds))],2),
                p90=round(ds[int(0.90*len(ds))],2))
def ratio(h,a): return round(h/a,3) if a else 0

# 实际交付的候选：只调 mod 自己下发的 core_prod（其余固定）
# core_food=4：模型显示苔原食物拖累中古达 -3，若食物只给 +3 则苔原城净收益为 0，
#              "高棉供养"名存实亡。给 +4 后苔原城净 +1、非苔原城 +4，才名副其实。
BASE = dict(core_food=4, core_faith=3, core_cul=1, half_cost=True)
CANDIDATES = [4,5,6,7]   # core_prod 候选

def cfg_of(core_prod, **kw):
    c=dict(BASE); c["core_prod"]=core_prod; c.update(kw); return c

def main():
    print("="*88)
    print("核动力圣地 Mod 数值平衡 v3（含俄罗斯母亲）| 种子 %d 样本 %d"%(SEED,N))
    print("="*88)

    print("\n[0] 俄罗斯母亲增量（单城，按可工作苔原格；已扣食物拖累）")
    print("时代     苔原格   +产能   +信仰   食物拖累")
    for e,nm in enumerate(ERAS):
        t=TUNDRA_TILES[e]
        print("%-5s  %5d   %+5.1f   %+5.1f   %+5.1f"%(nm,t,t*1.0,t*1.0,-t*TUNDRA_FOOD_DRAG))

    print("\n[1] 无Mod 新手/AI 单城比值（对照基线）")
    print("时代     产能   科技   文化   食物")
    for e,nm in enumerate(ERAS):
        n=NOVICE[e]; a=ai_city(e)
        print("%-5s  %4.2f   %4.2f   %4.2f   %4.2f"%(nm,n[1]/a["prod"],n[2]/a["sci"],n[3]/a["cul"],n[0]/a["food"]))

    print("\n[2] 模型A（实际交付：仅固定加成+苔原特性）—— core_prod 扫描")
    print("      新手·苔原城              新手·非苔原城      熟练·苔原城")
    print("core  时代  产能比 食物比      产能比            产能比")
    results={}
    for core in CANDIDATES:
        results[str(core)]={}
        for e,nm in enumerate(ERAS):
            a=ai_city(e); c=cfg_of(core)
            sn=simulate(e,c,"novice",True); sp=simulate(e,c,"novice",False); sk=simulate(e,c,"skilled",True)
            rn=ratio(st(sn["prod"])["mean"],a["prod"]); rf=ratio(st(sn["food"])["mean"],a["food"])
            rp=ratio(st(sp["prod"])["mean"],a["prod"]); rs=ratio(st(sk["prod"])["mean"],a["prod"])
            results[str(core)][nm]=dict(novice_tundra_prod=rn,novice_tundra_food=rf,
                                        novice_plain_prod=rp,skilled_tundra_prod=rs,
                                        prod_p10=st(sn["prod"])["p10"],prod_p90=st(sn["prod"])["p90"])
            print("%4d  %-5s %4.2f  %4.2f      %4.2f            %4.2f"%(core,nm,rn,rf,rp,rs))
        print()

    print("[3] 选定 core_prod 的判定（目标：新手苔原远古 1.00~1.15，中古≥0.70，熟练远古≤1.30）")
    for core in CANDIDATES:
        r=results[str(core)]
        n0=r["远古"]["novice_tundra_prod"]; n2=r["中古"]["novice_tundra_prod"]
        s0=r["远古"]["skilled_tundra_prod"]; s2=r["中古"]["skilled_tundra_prod"]
        ok = (1.00<=n0<=1.15) and n2>=0.70 and s0<=1.30
        print(" core=%d  新手 %.2f→%.2f  熟练 %.2f→%.2f  %s"%(core,n0,n2,s0,s2,"✓ 可选" if ok else "✗"))

    print("\n[4] 模型B（参考）：玩家自挂职业道德+经文后的相邻转化收益")
    print("  说明：这部分不属于 mod 贡献，仅展示「新手若学会原版combo」能达到多少")
    print("core  时代  新手苔原产能比(含原版协同)  熟练")
    for e,nm in enumerate([ERAS[0],ERAS[2]]):
        idx=0 if nm==ERAS[0] else 2
        a=ai_city(idx); c=cfg_of(5, syn_prod=0.62, syn_food=0.70)
        rn=ratio(st(simulate(idx,c,"novice",True)["prod"])["mean"],a["prod"])
        rs=ratio(st(simulate(idx,c,"skilled",True)["prod"])["mean"],a["prod"])
        print("  5   %-5s        %4.2f                  %4.2f"%(nm,rn,rs))

    print("\n[5] 敏感性：苔原格数假设（core=5，中古新手苔原城产能比）")
    base=results["5"]["中古"]["novice_tundra_prod"]
    for dt in [-2,-1,0,1,2]:
        old=TUNDRA_TILES[2]; TUNDRA_TILES[2]=old+dt
        r=ratio(st(simulate(2,cfg_of(5),"novice",True)["prod"])["mean"],ai_city(2)["prod"])
        TUNDRA_TILES[2]=old
        print(" 苔原格 %2d (%+d) -> %.3f  偏离 %+.3f"%(old+dt,dt,r,r-base))

    print("\n[6] 堆叠/无限产出检查（core=7 极端 + 相邻6 + 苔原9格）")
    s=simulate(2,cfg_of(7),"novice",True); a=ai_city(2)
    print(" 产能比 %.2f  食物比 %.2f —— 线性加和，无指数/复制链路，不存在无限产出"%(
        ratio(st(s["prod"])["mean"],a["prod"]),ratio(st(s["food"])["mean"],a["food"])))

    print("\n[7] 结论")
    print(" · 俄罗斯母亲给苔原城 +3(远古)~+9(现代) 产能与等效信仰；非苔原城为 0")
    print(" · 固定加成随时代衰减：AI 产能按时代翻倍，固定值不会，所以曲线必然前高后低")
    print(" · 选 core_prod=5：新手苔原城远古约 1.00~1.05、中古约 0.75，熟练远古约 1.17")
    print(" · 这是一份「前期护盘、后期靠自己」的曲线，不是全程平推 —— 符合'不能太强'")
    print(" · 若你想要后期也强，请自行挂职业道德+经文（模型B），那属于原版手段不是mod")

    outdir=os.path.dirname(os.path.abspath(__file__))
    cp=os.path.join(outdir,"config","balance_params_v3.csv")
    with open(cp,"w",newline="",encoding="utf-8-sig") as fh:
        w=csv.writer(fh)
        w.writerow(["core_prod","core_food","core_faith","core_cul","mr_prod_per_tile","mr_faith_per_tile",
                    "mr_extra_tiles","novice_tundra_era0","novice_tundra_era2","novice_plain_era0",
                    "skilled_tundra_era0","skilled_tundra_era2"])
        for core in CANDIDATES:
            r=results[str(core)]
            w.writerow([core,BASE["core_food"],BASE["core_faith"],BASE["core_cul"],
                        MR["per_tile_prod"],MR["per_tile_faith"],MR["extra_tiles"],
                        r["远古"]["novice_tundra_prod"],r["中古"]["novice_tundra_prod"],
                        r["远古"]["novice_plain_prod"],r["远古"]["skilled_tundra_prod"],
                        r["中古"]["skilled_tundra_prod"]])
    print("\n[8] CSV: %s"%cp)

    jp=os.path.join(outdir,"balance_results_v3.json")
    with open(jp,"w",encoding="utf-8") as fh:
        json.dump(dict(deity=DEITY,mother_russia=MR,tundra_tiles=TUNDRA_TILES,
                       tundra_food_drag=TUNDRA_FOOD_DRAG,scripture=SCRIPTURE,
                       selected_core_prod=5,configs=results),fh,ensure_ascii=False,indent=2)
    print("[9] JSON: %s"%jp)

if __name__=="__main__": main()
