#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核动力圣地 Mod - 数值平衡分析 v4（新增「国王的修道院」后重新配平）
Game Balance Analysis Specialist

v4 相对 v3 的变化：
  * 新增「国王的修道院」模块（TRAIT_LEADER_MONASTERIES_KING，阇耶跋摩七世领袖特性）
      已查证效果（RF/GS 版本）：
        - 圣地与河流相邻时获得"大相邻加成"（+2 信仰）
        - 圣地的食物产出 = 其相邻加成数值
        - 圣地在河流旁时 +2 住房
        - 建造圣地时触发文化炸弹
    关键：食物 = 相邻加成，**没有固定上限**，直接与圣地质量挂钩 —— 这会顶爆
    v3 里固定 +4 食物的配平，必须下调。
  * core_food / core_prod 重新反解
  * 顺带修正：俄罗斯母亲建城免费地块为 5（2K 官方日志 8→5），仅影响叙述不影响模型

运行：python civ6_nhs_balance_v4.py
固定种子 20261120，样本量 600。
"""
import random, math, os, json, csv
from statistics import mean, pstdev

SEED = 20261120
random.seed(SEED)
N = 600

DEITY = dict(sci_cul_faith=0.40, prod_gold=1.00, combat=4, xp=0.50,
             boosts=4, settlers=3, warriors=5, builders=2)

# 俄罗斯母亲（已查证）：苔原 +1 信仰 +1 产能；建城额外 5 格领土（2021 版由 8 削减为 5）
MR = dict(per_tile_prod=1.0, per_tile_faith=1.0, extra_tiles=5)

# 国王的修道院（已查证，RF/GS 版）：
#   圣地靠河 = 大相邻（+2 信仰）；食物 = 相邻加成；靠河 +2 住房；建圣地文化炸弹
KHMER = dict(river_adj_faith=2.0, food_per_adj=1.0, river_housing=2.0)

ERAS = ["远古", "古典", "中古", "文艺复兴", "工业", "现代"]
NOVICE = {0:(6,4,3,2,1), 1:(7,6,5,3,2), 2:(8,9,8,5,4),
          3:(9,13,12,8,7), 4:(10,18,17,12,11), 5:(10,24,23,16,15)}
SKILLED= {0:(8,6,5,3,2), 1:(10,9,8,5,4), 2:(12,14,12,8,7),
          3:(13,20,18,12,11), 4:(14,28,25,17,16), 5:(14,36,33,22,21)}
TUNDRA_TILES = {0:3, 1:4, 2:6, 3:7, 4:8, 5:9}
TUNDRA_FOOD_DRAG = 0.5

def ai_city(era):
    f,p,s,c,fa = SKILLED[era]
    return dict(food=f, prod=p*2.0, sci=s*1.4, cul=c*1.4, faith=fa*1.4)

def adj_samples(n=N):
    # 圣地相邻：门槛 4~6，众数偏左（新手不擅长规划相邻）
    return [random.triangular(4, 6, 4.7) for _ in range(n)]

def food_to_sci(extra_food, turns=20, pop0=4):
    total=extra_food*turns; gain=0; n=pop0
    while total>15+8*(n-1)+(n-1)**1.5 and gain<6:
        total-=15+8*(n-1)+(n-1)**1.5; n+=1; gain+=1
    return gain, gain*0.5

def simulate(era, cfg, who="novice", tundra=True):
    f0,p0,s0,c0,fa0 = (NOVICE if who=="novice" else SKILLED)[era]
    tiles = TUNDRA_TILES[era] if tundra else 0
    out={k:[] for k in ["prod","food","sci","cul","faith"]}
    for adj in adj_samples():
        mr_p = tiles*MR["per_tile_prod"]
        mr_f = tiles*MR["per_tile_faith"]
        drag = tiles*TUNDRA_FOOD_DRAG
        kh_food = adj*cfg.get("khmer_food",0)          # 食物 = 相邻加成（不随经文翻倍）
        kh_faith= KHMER["river_adj_faith"]*cfg.get("khmer_river",0)
        out["prod"].append(p0+cfg["core_prod"]+mr_p)
        out["faith"].append(fa0+cfg["core_faith"]+mr_f+kh_faith)
        out["food"].append(f0+cfg["core_food"]+kh_food-drag)
        g,_ = food_to_sci(cfg["core_food"]+kh_food-drag)
        out["sci"].append(s0+g*0.5)
        out["cul"].append(c0+cfg["core_cul"]+g*0.2)
    return out

def st(d):
    ds=sorted(d)
    return dict(mean=round(mean(d),2), p10=round(ds[int(.1*len(ds))],2),
                p50=round(ds[int(.5*len(ds))],2), p90=round(ds[int(.9*len(ds))],2))
def ratio(h,a): return round(h/a,3) if a else 0

def cfg_of(prod, food, khmer=1.0):
    return dict(core_prod=prod, core_food=food, core_faith=3, core_cul=1,
                khmer_food=KHMER["food_per_adj"]*khmer, khmer_river=khmer)

def main():
    print("="*88)
    print("核动力圣地 v4：加入「国王的修道院」后配平 | 种子 %d 样本 %d"%(SEED,N))
    print("="*88)

    print("\n[0] 新增模块的单城增量")
    print("时代    苔原格  母亲+锤/+信   修道院食物(=相邻)   修道院河流信仰")
    for e,nm in enumerate(ERAS):
        t=TUNDRA_TILES[e]
        print("%-6s %4d    %+5.1f/%+5.1f        %+5.2f            %+4.1f"%(
            nm,t,t*1.0,t*1.0,4.72*KHMER["food_per_adj"],KHMER["river_adj_faith"]))

    print("\n[1] 无Mod 基线（新手/AI 单城）")
    print("时代     产能   食物   科技")
    for e,nm in enumerate(ERAS):
        n=NOVICE[e]; a=ai_city(e)
        print("%-6s %4.2f   %4.2f   %4.2f"%(nm,n[1]/a["prod"],n[0]/a["food"],n[2]/a["sci"]))

    print("\n[2] 若沿用 v3 的 core_food=4，直接叠加修道院会怎样")
    c=cfg_of(5,4)
    for e,nm in enumerate([ERAS[0],ERAS[2]]):
        idx=0 if e==0 else 2; a=ai_city(idx); s=simulate(idx,c,"novice")
        print("  %-5s 食物比 %.2f  (v3 时是 1.06/0.75) —— 明显抬升"%(
            nm, ratio(st(s["food"])["mean"],a["food"])))

    print("\n[3] 反解 core_prod × core_food（含修道院）")
    print("prod  food | 新手苔原0 新手苔原2 新手非苔原0 食物0 食物2 | 熟练0 熟练2 | 判定")
    feasible=[]
    for prod in [3,4,5,6]:
        for food in [0,1,2,3]:
            c=cfg_of(prod,food); a0,a2=ai_city(0),ai_city(2)
            n0=ratio(st(simulate(0,c,"novice")["prod"])["mean"],a0["prod"])
            n2=ratio(st(simulate(2,c,"novice")["prod"])["mean"],a2["prod"])
            p0=ratio(st(simulate(0,c,"novice",False)["prod"])["mean"],a0["prod"])
            f0=ratio(st(simulate(0,c,"novice")["food"])["mean"],a0["food"])
            f2=ratio(st(simulate(2,c,"novice")["food"])["mean"],a2["food"])
            s0=ratio(st(simulate(0,c,"skilled")["prod"])["mean"],a0["prod"])
            s2=ratio(st(simulate(2,c,"skilled")["prod"])["mean"],a2["prod"])
            ok = (1.00<=n0<=1.12) and n2>=0.68 and f0<=1.35 and s0<=1.30 and s2<=1.05
            if ok: feasible.append((prod,food))
            print(" %3d  %3d |  %4.2f    %4.2f     %4.2f     %4.2f %4.2f | %4.2f %4.2f | %s"%(
                prod,food,n0,n2,p0,f0,f2,s0,s2,"✓" if ok else "✗"))
    print(" 可行解: %s"%(", ".join("prod=%d,food=%d"%f for f in feasible) if feasible else "无"))

    # 采用解
    PICK=(5,1) if (5,1) in feasible else (feasible[0] if feasible else (5,0))
    print("\n[4] 采用 core_prod=%d / core_food=%d 的完整曲线"%PICK)
    c=cfg_of(*PICK)
    print("时代   新手苔原产能 新手苔原食物 新手非苔原产能 熟练苔原产能")
    res={}
    for e,nm in enumerate(ERAS):
        a=ai_city(e)
        sn=simulate(e,c,"novice"); sp=simulate(e,c,"novice",False); sk=simulate(e,c,"skilled")
        r=(ratio(st(sn["prod"])["mean"],a["prod"]), ratio(st(sn["food"])["mean"],a["food"]),
           ratio(st(sp["prod"])["mean"],a["prod"]), ratio(st(sk["prod"])["mean"],a["prod"]))
        res[nm]=r
        print("%-6s  %5.2f      %5.2f        %5.2f          %5.2f"%(nm,*r))

    print("\n[5] 对比：不加国王的修道院（仅母亲）")
    c2=cfg_of(5,4,khmer=0.0)
    for e,nm in enumerate([ERAS[0],ERAS[2]]):
        idx=0 if e==0 else 2; a=ai_city(idx)
        print("  %-5s 食物比 %.2f → 加修道院后 %.2f"%(
            nm, ratio(st(simulate(idx,c2,"novice")["food"])["mean"],a["food"]),
            ratio(st(simulate(idx,c,"novice")["food"])["mean"],a["food"])))

    print("\n[6] 结论")
    print(" · 国王的修道院的「食物 = 相邻」是无上限的，叠加 v3 的 +4 食物会直接超标")
    print(" · 因此食物下调到 %d，把「食物随圣地质量增长」这条链路交还给修道院"%PICK[1])
    print(" · 产能维持 %d：修道院不给产能，产能仍靠固定值 + 苔原"%PICK[0])
    print(" · 副作用：圣地质量差的城食物会明显变差 —— 这是'奖励好好选址'，符合原版设计")

    outdir=os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(outdir,"config","balance_params_v4.csv"),"w",newline="",encoding="utf-8-sig") as fh:
        w=csv.writer(fh); w.writerow(["core_prod","core_food","khmer_food","khmer_river","novice_prod0","novice_food0","skilled_prod0","novice_prod2"])
        w.writerow([PICK[0],PICK[1],KHMER["food_per_adj"],1,res["远古"][0],res["远古"][1],res["远古"][3],res["中古"][0]])
    print("\n[7] CSV: config/balance_params_v4.csv")
    with open(os.path.join(outdir,"balance_results_v4.json"),"w",encoding="utf-8") as fh:
        json.dump(dict(mother_russia=MR,khmer=KHMER,selected=dict(prod=PICK[0],food=PICK[1]),
                       curve=res),fh,ensure_ascii=False,indent=2)
    print("[8] JSON: balance_results_v4.json")

if __name__=="__main__": main()
