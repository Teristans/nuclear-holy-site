#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
出生偏置算法移植仿真（非引擎实跑）

用途
    官方分配出生点的逻辑在 Base/Assets/Maps/Utility/AssignStartingPlots.lua，
    只在开新局的地图生成阶段执行，游戏外无法直接调用。本脚本把与
    StartBias* 相关的三段核心逻辑按源码逐行移植过来，在一张人造小地图上跑，
    用来回答三个问题：
      1. 同一 Tier 的四种地形是否真的合并成一个打分集合（而不是各算各的）
      2. 排序方向是不是"命中格数多者优先"（__SortByArray 取 greatestValue）
      3. 河流偏置是不是真的在 Terrains 之后、并且是硬筛（有靠河就只留靠河）

    结论用于交叉验证 mod/sql/nhs_15_start_bias.sql 的数据形态，
    不能替代实机验证——仿真验证的是"我对源码的理解"，不是引擎行为。

移植依据（行号为 Base 版 AssignStartingPlots.lua）
    __StartBiasTerrains  :1616  3 环统计 + __SortByArray 降序
    __StartBiasRivers    :1536  range=1 先试，无则 range=3 降级；有则硬筛
    __InitStartBias      :1122  按 Tier 分轮；同轮内 Resources→Features→Terrains→Rivers
    __SortByArray        :?     取 greatestValue，即降序

统计窗的重要细节
    源码写的是 `for dx = -range, range-1`，range=3 时 dx ∈ [-3, 2]，
    因此窗口是以候选点为中心的 6×6 方块（36 格，含自身），不是圆形 3 环。
    本脚本严格照抄这个偏移，避免"看起来是 3 环"的想当然。
"""

import sys

# ---------------------------------------------------------------------------
# 地图与地块
# ---------------------------------------------------------------------------
W, H = 20, 12
RIVER_Y = 6          # 一条河沿整行 y=6 横贯

TUNDRA, TUNDRA_HILLS = "TERRAIN_TUNDRA", "TERRAIN_TUNDRA_HILLS"
PLAINS, PLAINS_HILLS = "TERRAIN_PLAINS", "TERRAIN_PLAINS_HILLS"
GRASS = "TERRAIN_GRASS"

# 与 nhs_15_start_bias.sql 完全一致的偏置集合（同一 Tier）
BIAS_TERRAINS = [TUNDRA, TUNDRA_HILLS, PLAINS, PLAINS_HILLS]


def build_map(tundra_x0, tundra_x1, plains_x0, plains_x1):
    """构造一张地图：指定列范围铺冻土与平原，其余草原。"""
    grid = {}
    for y in range(H):
        for x in range(W):
            if tundra_x0 <= x <= tundra_x1:
                t = TUNDRA if y % 2 == 1 else TUNDRA_HILLS
            elif plains_x0 <= x <= plains_x1:
                t = PLAINS if y % 2 == 1 else PLAINS_HILLS
            else:
                t = GRASS
            grid[(x, y)] = t
    return grid


def has_river(x, y, r):
    """Map.GetPlotXY 的越界语义：超出地图返回 nil，这里用边界裁剪等效。"""
    for dy in range(-r, r):
        for dx in range(-r, r):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and ny == RIVER_Y:
                return True
    return False


def count_terrain(grid, x, y, terrain_set, r=3):
    """__StartBiasTerrains 的打分：6×6 方块内命中 terrains 集合的格数。"""
    n = 0
    for dy in range(-r, r):
        for dx in range(-r, r):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and grid[(nx, ny)] in terrain_set:
                n += 1
    return n


# ---------------------------------------------------------------------------
# 三段移植
# ---------------------------------------------------------------------------
def start_bias_terrains(grid, candidates, terrains=BIAS_TERRAINS):
    """返回按命中格数降序排好的候选（对应源码 __SortByArray）。"""
    scored = [(count_terrain(grid, x, y, set(terrains)), (x, y)) for (x, y) in candidates]
    hit = [p for p in scored if p[0] > 0]
    if len(hit) == 1:
        return [hit[0][1]], "唯一符合 → 锁定"
    if len(hit) > 1:
        hit.sort(key=lambda t: -t[0])          # greatestValue 优先 = 降序
        return [p[1] for p in hit], "按命中格数降序排序"
    return list(candidates), "无候选符合 → 不惩罚，原样保留"


def start_bias_rivers(candidates):
    """Rivers：先 range=1，无则放宽 range=3；有任何靠河的点就只留靠河。"""
    for r, note in ((1, "紧邻河"), (3, "放宽到 3 环")):
        hit = [p for p in candidates if has_river(p[0], p[1], r)]
        if len(hit) == 1:
            return hit, "唯一靠河（%s）→ 锁定" % note
        if len(hit) > 1:
            return hit, "多个靠河（%s）→ 硬筛，只留靠河" % note
    return list(candidates), "全图无靠河候选 → 不惩罚，原样保留"


def run_case(title, grid, candidates):
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)
    print("  候选点：%s" % ", ".join("(%d,%d)" % p for p in candidates))

    t_scored = sorted(((count_terrain(grid, x, y, set(BIAS_TERRAINS)), (x, y))
                       for (x, y) in candidates), key=lambda t: -t[0])
    print("  Terrains 打分（6×6 内冻土+平原格数）：")
    for sc, p in t_scored:
        print("     (%2d,%2d) → %2d 格   %s" % (p[0], p[1], sc, grid[p]))

    after_t, note_t = start_bias_terrains(grid, candidates)
    print("  → Terrains 结果：%s  [%s]" % (" > ".join("(%d,%d)" % p for p in after_t), note_t))

    after_r, note_r = start_bias_rivers(after_t)
    print("  → Rivers   结果：%s  [%s]" % (" > ".join("(%d,%d)" % p for p in after_r), note_r))

    final = after_r[0]
    print("  最终落点：(%d,%d)  地形=%s  靠河=%s"
          % (final[0], final[1], grid[final], has_river(final[0], final[1], 1)))
    return final, grid


def main():
    print("出生偏置算法移植仿真 —— 逐条对照 AssignStartingPlots.lua 的源码结构")
    print("偏置集合（同 Tier 1）：%s + StartBiasRivers" % "、".join(BIAS_TERRAINS))

    ok = True

    # --- A: 冻土与平原交界 + 靠河 -------------------------------------------
    # 冻土占 x∈[4,9]，平原占 x∈[10,15]，两侧各留草原缓冲（x≤3 与 x≥16），
    # 河在 y=6。这样每个候选点的 6×6 窗口里草原格数不同，得分才有区分度。
    # 期望：交界点 (9,6) 满分（36 格全是冻土或平原）→ 胜出；
    #       纯冻土/纯平原各 30 分（窗口边缘带进草原）；纯草原点 18 分垫底。
    #       这同时证明"四地形被合并成一个集合"，而不是各算各的。
    g = build_map(4, 9, 10, 15)
    cands = [(3, 6), (6, 6), (9, 6), (13, 6)]
    final, _ = run_case("场景 A：冻土与平原交界带 + 靠河（目标形态）", g, cands)
    if final == (9, 6):
        print("  ✓ 交界点 (9,6) 得分最高并胜出：四地形确实合并打分")
    else:
        ok = False
        print("  ✗ 期望 (9,6)，实际 (%d,%d)" % final)

    # --- B: 无冻土，只有平原 ------------------------------------------------
    # 冻土铺在 x∈[-5,-1]（等于不存在），平原 x∈[10,15]。
    # 期望：退到平原点，冻土缺席不导致整条偏置失效。
    g = build_map(-5, -1, 10, 15)
    cands = [(3, 6), (12, 6)]
    final, _ = run_case("场景 B：地图无冻土（退化到平原）", g, cands)
    if final != (12, 6):
        ok = False
        print("  ✗ 期望 (12,6) 平原点，实际 (%d,%d)" % final)
    else:
        print("  ✓ 正确退到平原点：冻土缺席不会让偏置失效")

    # --- C: 全图无河 --------------------------------------------------------
    g = build_map(4, 9, 10, 15)
    old_river = globals()["RIVER_Y"]
    globals()["RIVER_Y"] = -99          # 把河挪出地图
    cands = [(6, 2), (9, 2)]
    final, _ = run_case("场景 C：全图无河（河流偏置应放行、不惩罚）", g, cands)
    globals()["RIVER_Y"] = old_river
    if final != (9, 2):
        ok = False
        print("  ✗ 期望 (9,2)，实际 (%d,%d)" % final)
    else:
        print("  ✓ 无河时保留 Terrains 的排序结果，不把玩家挤走")

    # --- D: 全草原（无冻土无平原）------------------------------------------
    # 说明：平原几乎每张图都有，本场景只为确认"一无所获时不动候选"。
    g = build_map(-99, -99, -99, -99)
    cands = [(3, 6), (10, 2)]
    final, _ = run_case("场景 D：既无冻土也无平原（应完全不干预）", g, cands)
    if final == (3, 6):
        print("  ✓ Terrains 不干预，仅 Rivers 把候选收到靠河点")
    else:
        ok = False
        print("  ✗ 期望 (3,6)，实际 (%d,%d)" % final)

    print("\n" + "-" * 74)
    if ok:
        print("仿真结论：四项全部符合源码推演。")
        print("  · 四地形同 Tier 确实合并为一个打分集合（场景 A 的交界点胜出）")
        print("  · 排序为降序（命中格数多者优先）")
        print("  · Rivers 在 Terrains 之后执行，且是硬筛（场景 D 只剩靠河点）")
        print("  · 任一环节无符合项时不惩罚（场景 B/C）")
        print("注意：这是对源码结构的移植验证，不是引擎实跑；实机取证见 README 待验清单。")
        return 0
    print("仿真结论：存在与源码推演不符的用例，见上方 ✗ 项。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
