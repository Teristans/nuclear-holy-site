-- ============================================================================
-- 皇帝之威 · 奇观监听（nhs_wonder_watch.lua）  v7.27
--
-- 【v7.17】其他文明开始建造世界奇观时，给人类玩家发一条通知。
-- 【v7.22】实机反馈「只提示建成奇观，没有提示 AI 开建」。日志证明扫描与发送
--          都在跑（Lua.log 里 notified 十次），问题出在「发了但看不见 / 看不懂」，
--          v7.23 逐条修掉（见下）。这不是重写，是把三个哑巴故障点各个击破。
--
-- 为什么这件事必须写脚本、数据层做不到：
--   游戏本体 211 个 KIND_NOTIFICATION 里，跟奇观有关的只有两条——
--     NOTIFICATION_WONDER_COMPLETED（自己建成）、NOTIFICATION_WONDER_FAILED（被抢先）
--   没有「开始建造」。GameEvents 里同样没有任何「开始生产」事件，只有
--   BuildingConstructed（建成）和 Events.WonderCompleted。
--   也就是说「AI 在建什么」在原版里是刻意不给的信息（只能靠间谍、大工程师间接摸）。
--
-- ── v7.23 修掉的三件事 ──────────────────────────────────────────────────
--   ① 发送时机：原来绑 GameEvents.OnGameTurnStarted，而这个事件**每个文明回合开始
--      都触发**（Lua.log 实测：一场 25 回合的局扫了 178 次）。于是通知几乎都在 AI
--      的行动阶段被创建，玩家自己的回合开始时它已经在通知栏里躺了一会儿，若赶上
--      原版预留槽「当回合结束即清」的过期规则，常常还没扫到就没了。
--      ⇒ 改为 GameEvents.PlayerTurnActivated + 只认本地玩家；OnGameTurnStarted 只留
--        作兜底，且必须 Players[me]:IsTurnActive() 为真才扫。
--   ② 过期与堆叠：原版预留槽 NOTIFICATION_USER_DEFINED_1 的 DB 行写死
--      ExpiresEndOfTurn=True、Icon 为空、且九个槽是全 mod 公共资源。
--      ⇒ 改用自建类型 NOTIFICATION_NHS_WONDER_STARTED（data/nhs_notifications.xml），
--        独占图标、独占堆叠组、常驻通知栏不自动过期。
--        （v7.24：ExpiresEndOfNextTurn 也从 True 改为 False——实机反馈「只显示一回合」，
--          现与原版 NOTIFICATION_WONDER_COMPLETED 一样，一直挂着直到玩家点掉。）
--        ⚠ v7.27 更正：上面这步只改对了**数据库**，Lua 侧从来没拿到过自建类型。
--          实测 Lua.log 五行都是 `notify type = USER_DEFINED_1`，即一直退回旧槽，
--          而旧槽 ExpiresEndOfTurn=1 —— 所以「只显示一回合」是必然的，不是偶发。
--          真实机制与修法见下方 ResolveNotifyType 上方的长注释：mod 自建类型
--          不进 NotificationTypes 枚举（官方 DLC 也只用 USER_DEFINED_1~4），
--          但引擎认 Types.Hash，故改从 GameInfo.Types 取数值，兜底换常驻的
--          NOTIFICATION_WONDER_COMPLETED。
--   ③ 文案：原来文明名一律显示成「?」——因为 Players[i]:GetCivilizationShortDescription()
--      这个方法在 gameplay 作用域并不存在（它在 PlayerConfigurations 上），
--      pcall 把错误吞成 false，于是每一次通知都是「?已在LOC_CITY_NAME_TOKYO动工」。
--      ⇒ 文明名改查 PlayerConfigurations[i]:GetCivilizationShortDescription()
--        （Base/Assets/UI/DiplomacyActionView.lua:542 同款用法），
--        城市名套 Locale.Lookup（AI 城市的 GetName() 返回的是 LOC key，不是成品文本）。
--        英文正文的占位符顺序也修正了（原为 {2_WonderName} 在 {3_CityName} 之前，
--        与传参顺序相反，英文会读成「has begun building <城> in <奇观>」）。
--
-- 三个环节全部是原生 API，没有一个自造：
--   1) 判定奇观：GameInfo.Buildings[t].MaxWorldInstances == 1
--      （真实库 DebugGameplay.sqlite 里恰好 54 行，正是全世界奇观；普通建筑为 -1）
--   2) 轮询时点：GameEvents.PlayerTurnActivated（本地玩家回合开始）
--      兜底 GameEvents.OnGameTurnStarted
--   3) 发通知：NotificationManager.SendNotification(playerID, type, 标题, 正文, x, y)
--      第 3 参=标题、第 4 参=正文（BlackDeathScenario_Support.lua:23-28 对照确认）
--
-- 去重：每个「文明 + 奇观」组合写一条 Game 属性（Game:SetProperty），随存档保存。
--   读档后不会把正在建的奇观再报一遍。注意只有**发送成功**才写标记——
--   v7.22 的写法是先标记后发送，一旦发送失败就永远不再报。
--
-- 已知边界（都是刻意的，不是缺陷）：
--   * 回合粒度：你在自己回合开头收到，那时 AI 上回合的生产已经结算完。
--   * 只看当前生产项：看不到排在队列后面还没开工的。
--   * AI 中途取消、过几回合重开同一奇观，会再报一次（合理，因为它真重新开工了）。
--   * 只有已相遇的文明才报（REQUIRE_MET），避免泄漏未知大陆的情报。
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 配置
-- ---------------------------------------------------------------------------
local WATCH_ALL_AI = true   -- true：任何 AI 开建任何世界奇观都通知
                            -- false：只在本地玩家也在建同一座时才通知（竞争提醒）
local REQUIRE_MET  = true   -- true：只通知已相遇的文明（避免泄漏未知大陆的情报）

local DEBUG_LOG    = true   -- 打开后每回合往 Logs/Lua.log 写一行扫描计数

-- 去重属性前缀。
--   v7.23 故意把前缀从 NHS_WS_ 改成 NHS_WS2_：旧前缀的标记已写进存档（上一版报了十条，
--   那十条对应的奇观都被永久标记为「已报」），若不换前缀，升级后同一个存档里
--   永远等不到一条新通知——正好会让人误以为这功能还是坏的。
--   换前缀的效果：本次加载后会先把**当前所有在建奇观**各报一遍（当作新版本的基线），
--   之后照常去重。多报一轮，换一个「能亲眼确认它在工作」的机会，值得。
local PROP_PREFIX  = "NHS_WS2_"

local ME_TRAIT     = "TRAIT_NHS_NUCLEAR_HOLY_SITE"      -- 本 mod 的专属特性，非秦始皇直接不干活

-- 自建通知类型（data/nhs_notifications.xml 里注册为 NOTIFICATION_NHS_WONDER_STARTED）。
-- 枚举键是去掉 NOTIFICATION_ 前缀的那一段——原版一律如此
-- （NotificationTypes.WONDER_COMPLETED ← NOTIFICATION_WONDER_COMPLETED）。
local NOTIFY_KEY      = "NHS_WONDER_STARTED"
local NOTIFY_FULLNAME = "NOTIFICATION_NHS_WONDER_STARTED"

-- ---------------------------------------------------------------------------
-- 工具
-- ---------------------------------------------------------------------------
local function Log(msg)
    if DEBUG_LOG then
        print("[NHS-Wonder] " .. tostring(msg))
    end
end

-- 当前回合号。
--   ⚠ 正确的是 Game.GetCurrentGameTurn()。Game.GetGameTurn() 在游戏自带的几百个
--   Lua 脚本里一次都没出现过——写成它会在事件回调里抛 Runtime Error，
--   每回合都抛一次，结果是整套扫描压根不执行，而日志里只有一堆 attempt to call nil。
local function CurrentTurn()
    local ok, t = pcall(function() return Game.GetCurrentGameTurn() end)
    if ok and t ~= nil then return t end
    return nil
end

-- ── 解析通知类型（v7.27 重大更正）─────────────────────────────────────────
-- ⚠ 此前 v7.23/v7.24 的假设是错的：不是「Types 里注册了 KIND_NOTIFICATION，
--   Lua 的 NotificationTypes 就会多一个键」。实测不会。
--
-- 三条硬证据：
--   1) 本次 Lua.log 五行全是 `notify type = USER_DEFINED_1`，而不是 NHS_WONDER_STARTED。
--      这说明自建类型一路取不到、退回旧槽——v7.24 声称的「已迁到常驻自建类型」
--      从上线起就没真正生效过。玩家看到的「只显示一回合」是旧槽的原版行为
--      （NOTIFICATIONS 表里 USER_DEFINED_1 的 ExpiresEndOfTurn=1）。
--   2) 数据库侧其实完全成功：DebugGameplay.sqlite 里
--        Types       : NOTIFICATION_NHS_WONDER_STARTED, Hash=-911488681, KIND_NOTIFICATION
--        Notifications: 该行存在，ExpiresEndOfTurn=0 / ExpiresEndOfNextTurn=0
--      也就是说「数据对了、Lua 看不见」。
--   3) 官方自己的 DLC 做自定义通知也不用自建类型：
--        DLC/BlackDeathScenario/Scripts/BlackDeathScenario_Support.lua:13-16
--        四条通知全部是 NotificationTypes.USER_DEFINED_1~4；
--        工坊 32 个订阅里除本 mod 外，零个文件出现 KIND_NOTIFICATION。
--
-- 原因：NotificationTypes 是游戏启动早期按**基础库**固化的枚举，mod 后来
-- UpdateDatabase 插入的 Types 行不会刷新它。这是 Civ6 modding 的通则——
-- mod 新类型只能用 GameInfo 查，不能用枚举（UNITS/BUILDINGS 同理）。
--
-- 但**引擎本身认这个类型**：GameInfo.Types 查得到它，说明它已进引擎的类型注册表；
-- 而通知的过期/图标/可见性本来就是 Notifications 表驱动的纯数据。
-- 所以拿 Types.Hash 当运行时数值发出去，是正确路径——这个 Hash 就是枚举里
-- 那些整数同域的东西（USER_DEFINED_1 = -1636606976，同一个 32 位空间）。
--
-- 三级回退，任何一级都有日志，不静默：
--   ① NotificationTypes[去前缀名]        —— 若将来引擎支持动态枚举
--   ② GameInfo.Types[全名].Hash          —— 自建类型的数值（当前主路径）
--   ③ WONDER_COMPLETED                   —— 原版常驻槽兜底
--
-- 为什么兜底不再用 USER_DEFINED_1：
--   · 它 ExpiresEndOfTurn=1，正是「只挂一回合」的病根；
--   · 它的图标名 ICON_NOTIFICATION_USER_DEFINED_1 与工坊 3810795757
--     (Civilization Assimilation) 撞名，Database.log 里那条
--     `UNIQUE constraint failed: IconDefinitions.Name, IconDefinitions.Atlas` 就是它；
--   · NOTIFICATION_WONDER_COMPLETED 实测 0/0（常驻），图标本来就是奇观，
--     UI handler 是 MakeDefaultHandlers()（NotificationPanel.lua:190），
--     只额外挂了一条「他国建成奇观」音效（:260）——对「他国动工奇观」正合适，
--     没有任何点击逻辑依赖，借它不会出错。
local function ResolveNotifyType()
    local ok, t = pcall(function() return NotificationTypes[NOTIFY_KEY] end)
    if ok and type(t) == "number" then return t, NOTIFY_KEY end

    ok, t = pcall(function() return NotificationTypes[NOTIFY_FULLNAME] end)
    if ok and type(t) == "number" then return t, NOTIFY_FULLNAME end

    ok, t = pcall(function()
        local row = GameInfo.Types[NOTIFY_FULLNAME]
        if row ~= nil then return row.Hash end
    end)
    if ok and type(t) == "number" then return t, "Types.Hash" end

    return nil, nil
end

-- 兜底槽也包一层：若某些环境下 NotificationTypes 整个不可用，
-- 这行不能把整个脚本带崩（那样连扫描都不会跑，比没通知更糟）。
local NOTIFY_FALLBACK = nil
pcall(function() NOTIFY_FALLBACK = NotificationTypes.WONDER_COMPLETED end)

local NOTIFY_TYPE, NOTIFY_SRC = ResolveNotifyType()
if NOTIFY_TYPE == nil then
    if NOTIFY_FALLBACK ~= nil then
        NOTIFY_TYPE, NOTIFY_SRC = NOTIFY_FALLBACK, "WONDER_COMPLETED(兜底)"
    else
        -- 连原版枚举都读不到：本局不可能发通知，但扫描照跑，
        -- 日志里会一直写「无可用类型」，不会静默。
        NOTIFY_TYPE, NOTIFY_SRC = nil, "无可用类型"
    end
end

-- 已通知过？
--   主用 Game:GetProperty（随存档保存，读档不重播）；
--   万一该 API 不可用，退回本局内存表——总比每回合重复通知强。
local m_seen = {}

local function AlreadyNotified(sKey)
    local ok, v = pcall(function() return Game:GetProperty(sKey) end)
    if ok and v ~= nil then return true end
    return m_seen[sKey] == true
end

local function MarkNotified(sKey)
    m_seen[sKey] = true
    pcall(function() Game:SetProperty(sKey, 1) end)
end

-- 文明显示名。
--   ⚠ Player 对象上**没有** GetCivilizationShortDescription 方法。
--   v7.22 写成 Players[i]:GetCivilizationShortDescription() 时被 pcall 吞成 false，
--   结果十条通知的文明名全是「?」——不报错、只是难看，最难查的一类错。
--   正确位置是 PlayerConfigurations[i]（Base/Assets/UI/DiplomacyActionView.lua:542）。
--
--   v7.24 加两道兜底，并把「还是 LOC_ 开头」也视为失败：
--     PlayerConfigurations 的取值是**本地化键**（原版一律外面再套 Locale.Lookup，
--     见 DiplomacyActionView.lua:542 / MinimapPanel.lua:900），若某天取到的是空串
--     或原样返回的键，就直接换第二条路：文明类型 → GameInfo.Civilizations.ShortName。
--     宁可显示「他国」，也不能把 LOC_CIVILIZATION_JAPAN_NAME 甩给玩家。
local function CivName(iPlayerID)
    local ok, s = pcall(function()
        return Locale.Lookup(PlayerConfigurations[iPlayerID]:GetCivilizationShortDescription())
    end)
    if ok and type(s) == "string" and s ~= "" and s:sub(1, 4) ~= "LOC_" then
        return s
    end

    local ok2, s2 = pcall(function()
        local sCiv = PlayerConfigurations[iPlayerID]:GetCivilizationTypeName()
        local kInfo = GameInfo.Civilizations[sCiv]
        if kInfo == nil then return nil end
        return Locale.Lookup(kInfo.ShortName)
    end)
    if ok2 and type(s2) == "string" and s2 ~= "" and s2:sub(1, 4) ~= "LOC_" then
        return s2
    end

    return Locale.Lookup("LOC_NHS_UNKNOWN_CIV")
end

-- 城市显示名。
--   AI 城市的 City:GetName() 返回的是 LOC key（Lua.log 实测为 LOC_CITY_NAME_TOKYO），
--   必须再过一道 Locale.Lookup 才是玩家看到的成品文字。
local function CityName(pCity)
    local ok, s = pcall(function() return Locale.Lookup(pCity:GetName()) end)
    if ok and s ~= nil and s ~= "" then return s end
    return "?"
end

-- 玩家是否拥有某个 trait。
--   注意：Player 对象上没有 HasTrait 方法。原版的 HasTrait 是 UI 层的全局函数
--   （Base/Assets/UI/Scripts/GameCapabilities.lua:16），实现方式是查
--   PlayerConfigurations 的领袖/文明，再比对 GameInfo.LeaderTraits。
--   这里照抄同一套查法，搬进 gameplay 作用域，避免依赖 UI 脚本。
local function PlayerHasTrait(iPlayerID, sTrait)
    local ok, has = pcall(function()
        local config = PlayerConfigurations[iPlayerID]
        if config == nil then return false end

        local sLeader = config:GetLeaderTypeName()
        if sLeader ~= nil then
            for row in GameInfo.LeaderTraits() do
                if row.LeaderType == sLeader and row.TraitType == sTrait then
                    return true
                end
            end
        end

        local sCiv = config:GetCivilizationTypeName()
        if sCiv ~= nil then
            for row in GameInfo.CivilizationTraits() do
                if row.CivilizationType == sCiv and row.TraitType == sTrait then
                    return true
                end
            end
        end

        return false
    end)
    return ok and has
end

-- ---------------------------------------------------------------------------
-- 通知
--   标题 LOC_NHS_WATCH_TITLE / 正文 LOC_NHS_WATCH_BODY 定义在 text/nhs_text.xml
--   占位符 {1_CivName} {2_CityName} {3_WonderName}，按**序号**对应下面三个入参
--   （Locale.Lookup 按序号替换，占位符里写的名字只是给人看的；
--    英文正文因此可以把 {3_WonderName} 写在 {2_CityName} 之前来顺英语语序）
-- ---------------------------------------------------------------------------
local function Notify(iCivID, pCity, kBuildingInfo)
    local sCiv    = CivName(iCivID)
    local sCity   = CityName(pCity)

    -- 奇观名取不到会让整个 Scan 抛错、连带同回合其余城市都不处理，所以兜一层
    local sWonder = "?"
    local okName, sW = pcall(function() return Locale.Lookup(kBuildingInfo.Name) end)
    if okName and sW ~= nil then
        sWonder = tostring(sW)
    end

    local sTitle = Locale.Lookup("LOC_NHS_WATCH_TITLE")
    local sBody  = Locale.Lookup("LOC_NHS_WATCH_BODY", sCiv, sCity, sWonder)

    -- 坐标只用于点击通知时跳转。AI 城市可能还没被玩家探明，
    -- 取不到就传 -1（原版对 -1 的处理就是「不可定位」，不会报错）
    local iX, iY = -1, -1
    pcall(function() iX, iY = pCity:GetX(), pCity:GetY() end)

    local iMe = Game.GetLocalPlayer()
    local sUsed = NOTIFY_SRC

    -- 连原版枚举都取不到（极端环境）：不发，但留痕，不假装成功
    if NOTIFY_TYPE == nil then
        Log("no notification type available: " .. tostring(sCiv) .. " / " .. tostring(sWonder))
        return false
    end

    local ok, err = pcall(function()
        NotificationManager.SendNotification(iMe, NOTIFY_TYPE, sTitle, sBody, iX, iY)
    end)

    -- 自建类型若被引擎拒绝（pcall 抛错），立刻换原版常驻槽重发一次。
    -- 只在**明确抛错**时重发：正常返回就认为成功，避免同一条通知出现两遍。
    if (not ok) and NOTIFY_FALLBACK ~= nil and NOTIFY_TYPE ~= NOTIFY_FALLBACK then
        local ok2, err2 = pcall(function()
            NotificationManager.SendNotification(iMe, NOTIFY_FALLBACK, sTitle, sBody, iX, iY)
        end)
        if ok2 then
            ok, err = true, nil
            sUsed = "WONDER_COMPLETED(重发)"
        else
            err = tostring(err) .. " / fallback: " .. tostring(err2)
        end
    end

    if ok then
        -- 一并打出实际数值，实机回来一眼能看出走的是哪一级解析
        Log(string.format("notified[src=%s type=%s]: %s / %s / %s",
                          tostring(sUsed), tostring(NOTIFY_TYPE), sCiv, sCity, sWonder))
    else
        Log("SendNotification failed: " .. tostring(err))
    end
    return ok
end

-- ---------------------------------------------------------------------------
-- 本地玩家是否也在建这座奇观（WATCH_ALL_AI = false 时用）
-- ---------------------------------------------------------------------------
local function LocalPlayerIsBuilding(sBuildingType)
    local pMe = Players[Game.GetLocalPlayer()]
    if pMe == nil then return false end

    local building = false
    for _, pCity in pMe:GetCities():Members() do
        local ok, sNow = pcall(function()
            return pCity:GetBuildQueue():CurrentlyBuilding()
        end)
        if ok and sNow == sBuildingType then
            building = true
            break
        end
    end
    return building
end

-- ---------------------------------------------------------------------------
-- 主扫描
-- ---------------------------------------------------------------------------
local function Scan()
    local iMe = Game.GetLocalPlayer()
    local pMe = Players[iMe]
    if pMe == nil then return end

    -- 整个 mod 只对秦始皇生效，不是这个 trait 的人不该被这套通知打扰
    if not PlayerHasTrait(iMe, ME_TRAIT) then
        Log("本地玩家无 " .. ME_TRAIT .. "，跳过")
        return
    end

    local nCity, nQueueOK, nWonder, nNew = 0, 0, 0, 0

    for i = 0, GameDefines.MAX_MAJOR_CIVS - 1 do
        local pOther = Players[i]
        if pOther ~= nil and i ~= iMe and pOther:IsAlive() and pOther:IsMajor() and not pOther:IsHuman() then
            local bMet = true
            if REQUIRE_MET then
                local okMet, met = pcall(function() return pMe:GetDiplomacy():HasMet(i) end)
                bMet = okMet and met
            end

            if bMet then
                for _, pCity in pOther:GetCities():Members() do
                    nCity = nCity + 1

                    local okQ, sNow = pcall(function()
                        return pCity:GetBuildQueue():CurrentlyBuilding()
                    end)

                    if okQ and sNow ~= nil then
                        nQueueOK = nQueueOK + 1
                        local kInfo = GameInfo.Buildings[sNow]
                        if kInfo ~= nil and kInfo.MaxWorldInstances == 1 then
                            nWonder = nWonder + 1
                            if (not WATCH_ALL_AI) and (not LocalPlayerIsBuilding(sNow)) then
                                -- 只关心竞争，而我没在建，忽略
                            else
                                local sKey = PROP_PREFIX .. tostring(i) .. "_" .. sNow
                                if not AlreadyNotified(sKey) then
                                    -- 发送成功才写标记：先标记后发送的话，一次失败就永久哑掉
                                    if Notify(i, pCity, kInfo) then
                                        MarkNotified(sKey)
                                        nNew = nNew + 1
                                    end
                                end
                            end
                        end
                    end
                end
            end
        end
    end

    Log(string.format("turn=%s scan: ai_cities=%d queue_readable=%d wonders=%d new=%d type=%s",
                      tostring(CurrentTurn()), nCity, nQueueOK, nWonder, nNew,
                      tostring(NOTIFY_SRC)))
end

-- 每回合只扫一次。
--   PlayerTurnActivated 与 OnGameTurnStarted 都会调 Scan，同一回合内可能都触发，
--   用回合号做闸门避免重复；取不到回合号就不设闸门（宁可多扫，不可不扫）。
--
--   ⚠ v7.27：加 sWhy 参数与前三次诊断。
--     起因是实机日志：一局玩到 34 回合，Lua.log 里只有 3 条 `loaded`，
--     **零条** scan 记录（连"本地玩家无 TRAIT... 跳过"都没有）——
--     说明 Scan 压根没被调用过，不是被 trait 门槛挡住的。
--     根因就在下面的 OnGameTurnStarted：主入口绑定成功后它反而设了 IsTurnActive 门槛，
--     而该门槛在本环境里恒假时，两条路同时哑掉，且一行日志都不留。
local m_lastScanTurn = nil
local m_scanCount = 0

local function ScanOnce(sWhy)
    local t = CurrentTurn()
    if t ~= nil then
        if t == m_lastScanTurn then return end
        m_lastScanTurn = t
    end

    m_scanCount = m_scanCount + 1
    if m_scanCount <= 3 then
        Log(string.format("scan #%d fired by %s at turn %s",
                          m_scanCount, tostring(sWhy), tostring(t)))
    end

    local ok, err = pcall(Scan)
    if not ok then
        Log("scan error: " .. tostring(err))
    end
end

-- ---------------------------------------------------------------------------
-- 绑定
-- ---------------------------------------------------------------------------
-- 主入口：本地玩家的回合激活时扫描。
--   这时通知栏处在可交互阶段、玩家正看着屏幕，通知不会被 AI 的行动演出淹没。
--   事件表名要试两次：游戏自带的同类写法用的是 Events.PlayerTurnActivated
--   （Base/Assets/Scenarios/Tutorial/Tutorial.lua:119），而 gameplay 脚本习惯 GameEvents；
--   两者哪个存在就走哪个，都不存在则只靠下面的 OnGameTurnStarted 兜底。
--   m_turnEvent 必须先声明：Lua 里内层函数只能看见**定义之前**的 local，
--   写在后面会变成全局变量，upvalue 捕获不到（调试时极难看出）。
local m_turnEvent = "none"

local function OnPlayerTurnActivated(iPlayerID, bFirstTurn)
    if iPlayerID ~= Game.GetLocalPlayer() then return end
    ScanOnce("PlayerTurnActivated")
end

-- 兜底：OnGameTurnStarted 对所有文明都触发（原版就这么用）。
--
--   ⚠ v7.27 改法：**无条件扫**，不再问 IsTurnActive。
--     上一版写的是「主入口绑上了就要求 IsTurnActive 为真」，实测把两条路一起堵死：
--     PlayerTurnActivated 在这个环境下没触发（34 回合零日志），而 IsTurnActive 也
--     没给出 true —— 结果一整局一次都没扫，且完全静默。这正是用户长期反馈
--     「只提示建成、不提示动工」的真正原因（比通知类型那层更致命）。
--     现在靠 ScanOnce 里的回合号闸门去重，扫多了也就多一次遍历，扫漏了才是事故。
--
--   代价说明：本事件在 AI 回合开始时也会触发，那时 AI 本回合的生产可能尚未结算，
--   所以新模式最快也要下一回合才看得到。1 回合延迟换「一定能扫到」，值。
local function OnGameTurnStarted(iTurn)
    ScanOnce("OnGameTurnStarted")
end

if pcall(function() GameEvents.PlayerTurnActivated.Add(OnPlayerTurnActivated) end) then
    m_turnEvent = "GameEvents.PlayerTurnActivated"
elseif pcall(function() Events.PlayerTurnActivated.Add(OnPlayerTurnActivated) end) then
    m_turnEvent = "Events.PlayerTurnActivated"
end
GameEvents.OnGameTurnStarted.Add(OnGameTurnStarted)

Log(string.format("loaded (notify type = %s, turn event = %s, fallback = OnGameTurnStarted/unconditional)",
                  tostring(NOTIFY_SRC), m_turnEvent))
