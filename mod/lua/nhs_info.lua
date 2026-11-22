-- ============================================================================
-- 核动力圣地 · 实机诊断 (lua/nhs_info.lua)  v7.44
--
-- 【用途】只读诊断。把「玩家身份 / 库里的修饰器 / 人类与每个 AI 的科研 /
--        逐城科研 / 科研明细 / 单位移动力」打到 Lua.log。不改任何游戏状态。
--        规模层验收通过后，删掉 .modinfo 里的 NHS_SCRIPT 动作块。
--
-- 【为什么需要它】
--   v37（每人口负值）、v38（负百分比）、v40（加算固定值）三轮「实机零效果」，
--   v41 用探针（三条改成 +20 正值）才查清：**与 effect 无关，与符号无关**，
--   是这三轮都在同一个老存档上测——Civ6 建局时就把玩家已挂载的 modifier 集合
--   写进存档，之后新增的 SQL 只进游戏库、不追溯挂到存档上。
--   所以本脚本现在的用途变了：**在新开的局里证明规模层真的生效**。
--
-- 【怎么读日志（v42 的判据）】
--   ① GameInfo: 三行应显示 MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER。
--      显示 nil 说明 SQL 没进游戏库；显示 NHS_MOD_CITY_YIELD 说明读到的是 v40 旧文件。
--   ② 「对照 · 全玩家科研」这一段是核心：
--        新开局第 1~3 回合，人类首都与任意 AI 首都人口相同、都只有宫殿 +2 科研，
--        AI 那一行另有神级难度加成（约 +40%），所以人类会比 AI 更低——
--        这不是判据，判据看下面 ③ 的「折扣实测」。
--        两者相同 = 规模层没生效；人类更低 = 生效，本层收工。
--   ③ 两条证据链，按可信度排序：
--      a) 【最硬】人口跨门槛时的跳变（逐城行下面的 ↳ 行）。同一座城、只多一个人口，
--         折扣整档跳下去。v42 实测：咸阳 pop 9 → sci 11.23（−18%），
--         pop 10 → sci 8.68（−38%）；反推无折扣 13.695 / 14.000，
--         差 0.305 恰好是一个人口的贡献，8.68 = 14.000 × 0.62
--         → 百分比按**加法**叠加（−18 −20 = −38），不是乘法。
--      b) 「折扣实测」= 人类首城 / 城邦单城均值。城邦不吃难度加成也不吃本 mod 的 trait，
--         开局头几回合是干净的基准（v42 实测 1.89 / 2.30 = −17.8%）。
--         中期城邦建了第二城后样本会消失，那时以 a) 为准。
--   ④ 单位：移民 max=4 / 斥候 max=6 是 trait 链路的旁证（基础 2 / 3）。
--
-- 【历史坑，别再踩】
--   · Game.GetTurn() 不存在 → Game.GetCurrentGameTurn()
--   · Player 上没有 HasTrait → 查 PlayerConfigurations + GameInfo.LeaderTraits
--   · Events.LoadScreenClosed 是 UI 上下文事件，AddGameplayScripts 收不到
--   · GameInfo.Units[...].Moves 不是列名 → BaseMoves
--   · PlayerTechs:GetScienceYieldToolTip() 是 UI 上下文方法，玩法脚本里是 nil
-- ============================================================================

local function S(v)
    if type(v) ~= "number" then return "nil" end
    return string.format("%.2f", v)
end

local function GameTurn()
    local ok, t = pcall(function() return Game.GetCurrentGameTurn() end)
    if ok and t ~= nil then return t end
    return "?"
end

-- 玩家是否持有某个 trait：照抄 nhs_wonder_watch 的做法（Player 上没有 HasTrait）
local function HasTraitForLeader(iPlayerID, sTrait)
    local ok, r = pcall(function()
        local sLeader = PlayerConfigurations[iPlayerID]:GetLeaderTypeName()
        for row in GameInfo.LeaderTraits() do
            if row.LeaderType == sLeader and row.TraitType == sTrait then
                return true
            end
        end
        return false
    end)
    if ok then return tostring(r) end
    return "查询失败"
end

local function LeaderOf(iPlayerID)
    local ok, r = pcall(function()
        return PlayerConfigurations[iPlayerID]:GetLeaderTypeName()
    end)
    return ok and tostring(r) or "?"
end

-- 引擎给的科研来源清单：把富文本标记压成一行，便于 grep
local function CleanTT(sz)
    if type(sz) ~= "string" then return tostring(sz) end
    sz = sz:gsub("%[NEWLINE%]", " | ")
    sz = sz:gsub("%[ICON_[%w_]+%]", "")
    sz = sz:gsub("%[COLOR[^%]]*%]", "")
    sz = sz:gsub("%[/COLOR%]", "")
    sz = sz:gsub("%s+", " ")
    return sz
end

local g_lastTurn = nil

-- 逐城科研历史：只为抓「人口跨过 10 / 16 那一刻科研跳降多少」。
-- 这是本项目验证三档最干净的一条：同一座城、只多一个人口，其余全不变。
-- 重启进程后清空，所以第一次跨档必须在同一次游戏会话内完成才有记录。
local g_cityHist = {}

local function DumpHeader(tag)
    print("===== [NHS-DIAG] " .. tostring(tag) .. " | turn=" .. tostring(GameTurn())
          .. " | pid=" .. tostring(Game.GetLocalPlayer()) .. " =====")
end

local function Dump(tag)
    local ok, err = pcall(function()
        local pid = Game.GetLocalPlayer()
        local p = Players[pid]
        if p == nil then
            print("[NHS-DIAG] 玩家对象为空 pid=" .. tostring(pid))
            return
        end

        DumpHeader(tag)

        -- ① 身份与门槛链路
        local okH, human = pcall(function() return p:IsHuman() end)
        print("[NHS-DIAG] isHuman=" .. (okH and tostring(human) or "调用失败")
              .. "  leader=" .. LeaderOf(pid)
              .. "  traitQin=" .. HasTraitForLeader(pid, "TRAIT_NHS_NUCLEAR_HOLY_SITE"))

        -- ② 库里这三条到底是什么类型（v42 应为负百分比类型）
        print("[NHS-DIAG] GameInfo: L1=" .. tostring(GameInfo.Modifiers["NHS_TECH_SCALE_L1"]
              and GameInfo.Modifiers["NHS_TECH_SCALE_L1"].ModifierType)
              .. " L2=" .. tostring(GameInfo.Modifiers["NHS_TECH_SCALE_L2"]
              and GameInfo.Modifiers["NHS_TECH_SCALE_L2"].ModifierType)
              .. " L3=" .. tostring(GameInfo.Modifiers["NHS_TECH_SCALE_L3"]
              and GameInfo.Modifiers["NHS_TECH_SCALE_L3"].ModifierType))

        -- ③ 折扣实测量：人类首城 / 城邦基准
        --    城邦（minor civ）不吃难度加成、也不吃本 mod 的 trait，它们的单城科研
        --    就是「这个版本的无修正基础值」。所以比值直接读出当前吃了几档：
        --      −18% ≈ 只有 L1（人口 <10 时的正确状态）
        --      −38% ≈ L2 也生效（人口 ≥10）
        --      −53% ≈ 三档全叠（人口 ≥16）
        --    ★ 别再调 GetScienceYieldToolTip：那是 UI 上下文的方法，
        --      玩法脚本里是 nil（v7.42 那个 `function expected instead of nil`
        --      就是它，报错还把整段 traceback 灌进了日志）。
        local mine, myName, myPop = nil, "?", 0
        for _, city in p:GetCities():Members() do
            local okCap, isCap = pcall(function() return city:IsCapital() end)
            if (okCap and isCap) or mine == nil then
                local okC, cv = pcall(function() return city:GetYield(YieldTypes.SCIENCE) end)
                if okC and type(cv) == "number" then
                    mine, myName, myPop = cv, tostring(city:GetName()), city:GetPopulation()
                    if okCap and isCap then break end
                end
            end
        end
        --    ★ pid 必须从 0 扫起：城邦编号不是固定从 10 开始（本局 Armagh 就是 pid=2，
        --      v7.43 只扫 10..63 导致「城邦城数=0」，样本永远不足）。
        --      也不要用 IsMinorCiv()（返回 false），直接看 leader 名里有没有 MINOR_CIV。
        local refSum, refN = 0, 0
        for i = 0, 63 do
            local p2 = Players[i]
            if p2 ~= nil then
                local okA, alive = pcall(function() return p2:IsAlive() end)
                if okA and alive and string.find(LeaderOf(i), "MINOR_CIV") ~= nil then
                    local cnt = 0
                    pcall(function() cnt = p2:GetCities():GetCount() end)
                    if cnt == 1 then
                        for _, c2 in p2:GetCities():Members() do
                            local okC2, v2 = pcall(function() return c2:GetYield(YieldTypes.SCIENCE) end)
                            if okC2 and type(v2) == "number" then
                                refSum = refSum + v2
                                refN = refN + 1
                            end
                        end
                    end
                end
            end
        end
        if mine ~= nil and refN > 0 and refSum > 0 then
            local base = refSum / refN
            local ratio = mine / base
            print(string.format(
                "[NHS-DIAG] 折扣实测: 人类首城 %s pop=%d sci=%.2f | 城邦基准 n=%d 均=%.2f | 比值=%.3f（−%.1f%%）",
                myName, myPop, mine, refN, base, ratio, (1 - ratio) * 100))
            print("[NHS-DIAG]   判据：−18%≈只有 L1（人口<10 的正确状态）｜−38%≈L2 也在｜−53%≈三档全叠｜0%≈没生效")
        else
            print("[NHS-DIAG] 折扣实测: 样本不足（mine=" .. tostring(mine)
                  .. " 城邦城数=" .. tostring(refN) .. "）")
        end

        -- ④ 人类逐城（并在人口跨过 10 / 16 时打出跳变，这是三档最硬的证据）
        local total, n = 0, 0
        for _, city in p:GetCities():Members() do
            n = n + 1
            local cs = 0
            local okC = pcall(function() cs = city:GetYield(YieldTypes.SCIENCE) end)
            if type(cs) == "number" then total = total + cs end
            local pop = city:GetPopulation()
            local nm = tostring(city:GetName())
            print(string.format("[NHS-DIAG]   城 %-18s pop=%2d sci=%-8s%s",
                  nm, pop, S(cs), okC and "" or "  (GetYield 失败)"))

            -- 跨档跳变：同城、只多一个人口，折扣应当整档跳下去。
            -- 实测（v42，咸阳）pop 9 → 11.23，pop 10 → 8.68；
            -- 反推无折扣 13.695 / 14.000（差 0.305 恰好是一人口的贡献），
            -- 8.68 = 14.000 × 0.62 → 说明百分比是按**加法**叠加（−18 −20 = −38），
            -- 不是乘法（0.82×0.80 = 0.656 会得 9.18，实测不是）。
            local okId, cid = pcall(function() return city:GetID() end)
            if okId and cid and type(cs) == "number" then
                local prev = g_cityHist[cid]
                if prev ~= nil and prev.pop ~= pop then
                    local mark = ""
                    if prev.pop < 10 and pop >= 10 then
                        mark = "  ★跨 L2 门槛(10)：折扣应 −18% → −38%"
                    elseif prev.pop < 16 and pop >= 16 then
                        mark = "  ★跨 L3 门槛(16)：折扣应 −38% → −53%"
                    end
                    local pct = 0
                    if prev.sci > 0 then pct = (cs / prev.sci - 1) * 100 end
                    print(string.format("[NHS-DIAG]   ↳ pop %d→%d  sci %.2f→%.2f（%+.1f%%）%s",
                          prev.pop, pop, prev.sci, cs, pct, mark))
                end
                g_cityHist[cid] = { pop = pop, sci = cs }
            end
        end
        print(string.format("[NHS-DIAG]   人类城市数=%d  逐城科研合计=%s", n, S(total)))

        -- ⑤ 对照：全玩家科研（新开局时 AI 首都是天然对照组，它们拿不到惩罚）
        print("[NHS-DIAG] 对照 · 全玩家科研：")
        for i = 0, 63 do
            local p2 = Players[i]
            if p2 ~= nil then
                local okA, alive = pcall(function() return p2:IsAlive() end)
                if okA and alive then
                    local okS, sci = pcall(function() return p2:GetTechs():GetScienceYield() end)
                    local okC, cnt = pcall(function() return p2:GetCities():GetCount() end)
                    local okH2, h2 = pcall(function() return p2:IsHuman() end)
                    print(string.format("[NHS-DIAG]   pid=%-2d %s %-18s sci=%-8s 城=%s",
                          i, (okH2 and h2) and "人类" or "AI  ", LeaderOf(i),
                          okS and S(sci) or "?", okC and tostring(cnt) or "?"))
                end
            end
        end

        -- ⑥ 移动力旁证（基础列是 BaseMoves，不是 Moves）
        local shown = 0
        for _, u in p:GetUnits():Members() do
            if shown >= 6 then break end
            local okU, t = pcall(function() return u:GetType() end)
            if okU and t then
                local info = GameInfo.Units[t]
                if info and (info.UnitType == "UNIT_SCOUT" or info.UnitType == "UNIT_SETTLER") then
                    local mv, mx = -1, -1
                    pcall(function() mv = u:GetMoves() end)
                    pcall(function() mx = u:GetMaxMoves() end)
                    print(string.format("[NHS-DIAG]   unit=%-14s moves=%-3s max=%-3s 基础=%s",
                          info.UnitType, tostring(mv), tostring(mx), tostring(info.BaseMoves)))
                    shown = shown + 1
                end
            end
        end

        print("===== [NHS-DIAG] END =====")
    end)
    if not ok then print("[NHS-DIAG] 诊断异常(" .. tostring(tag) .. "): " .. tostring(err)) end
end

-- ① 脚本加载即打印一次（此时玩家对象可能还没就绪，报错也无所谓——
--    看到这一行就证明脚本被加载了，且 version 串能确认读的是磁盘上的最新文件）
print("[NHS-DIAG] ---- nhs_info.lua loaded (v7.44) ----")
Dump("脚本加载")

-- ② 每回合开始一次，用回合号闸门去重
pcall(function()
    GameEvents.OnGameTurnStarted.Add(function(iTurn)
        local t = GameTurn()
        if t == g_lastTurn then return end
        g_lastTurn = t
        Dump("回合开始 t" .. tostring(t))
    end)
end)
