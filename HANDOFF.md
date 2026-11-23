# 交接指南 —— 换一台电脑继续做

> 项目：核动力圣地 / Nuclear Holy Site（文明6 Mod，秦始皇专属）
> 版本：v7.38（mod version 38）· 交接时间：2026-11-20，最后更新 2026-11-22
> 读者：① 换机器后的你　② 新机器上的 AI 助手（它看不到之前的对话）

---

## 0. 一句话现状

**代码和验证都做完了，缺的只有"实机跑一局"。**
v7.38 的 17 个 SQL 文件已在真实游戏库结构上全部执行通过，`run_mod_sql.py` 201 条落地断言全绿、`verify_mod.py` 243 条静态检查 0 错 2 警告（1 条刻意保留 + 1 条"该重启游戏了"）。
**v38 待实机验证**——v37 已经进过游戏，结论是「零效果」，整个写法被推翻重做（见第 9 节 v7.38）。这件事说明：离线库全绿 + 静态校验全绿，仍然不等于引擎会采纳。
判据用 `python check_loaded.py`：现在它会列出三类问题——`[缺失]`（从未加载）、`[过期]`（加载过但之后又改了，游戏里跑的是旧内容）、以及 **modinfo 自身过期**（改的若是 LoadOrder，整个建库顺序都还是旧的）。

> **v35 的教训值得先读一遍**（见第 9 节最后一条）：`run_mod_sql.py` 跑在离线合并库上，它只能证明 SQL 正确，**不能证明游戏里执行时源数据已经存在**。本轮 30 条修饰器就是这样丢的——文件全加载、零报错、双校验全绿，游戏库里却少了半套冻土农场。现在 `verify_mod.py` 第 19 节会直接去读游戏建出的 `DebugGameplay.sqlite` 对账。

> 如果你（或新 AI）想先花 10 分钟了解设计，看 `README.md` 第 1–3 节。
> 想知道"哪些结论有证据、哪些是推断"，看 `VERIFICATION.md` 和 `README.md` 第 0 节的诚实声明表。

---

## 1. 带走什么

**两个 zip，作用不同，别混：**

| 文件 | 大小 | 给谁 | 用途 |
|---|---|---|---|
| `civ6-nhs-v7-handoff.zip` | ~1.4 MB | **新机器上的你 + AI** | 全部东西：源码、文档、验证脚本、预建验证库 |
| `NuclearHolySite-v7-mod-only.zip` | ~20 KB | **游戏本体** | 只有 mod 本体，解压即得 `NuclearHolySite/`，直接丢 Mods 目录 |

交接包里有什么：

| 路径 | 作用 | 能不能丢 |
|---|---|---|
| `mod/` | **Mod 本体**：`.modinfo` + 9 个 SQL + 1 个可选诊断 lua | ❌ 核心 |
| `README.md` | 设计说明 + 数值曲线 + 风险清单 | ❌ |
| `VERIFICATION.md` | 每条原版 ID 的文件:行号出处 | ❌ |
| `HANDOFF.md` | 本文 | — |
| `verify_mod.py` | 离线静态校验（10 组检查） | ❌ |
| `run_mod_sql.py` | 在真实库结构上跑 SQL + 断言 | ❌ |
| `db/gameplay_verify.sqlite` | **预建验证库**（真实 schema + 42020 行游戏数据） | 可重建，但重建要游戏文件 |
| `build_game_db.py` | 重建上面那个库（**硬编码了本机 Steam 路径**） | ⚠️ 换机要改第 24 行 |
| `civ6_nhs_balance_v6.py`、`balance_results_v5.json`、`config/*.csv` | 数值模型与产出数据 | 可丢 |
| `civ6_nhs_balance*.py`（v1–v5） | **历史版本，模型迭代过程**。只在你需要复盘"为什么是这个数"时才看 | 可丢 |
| `civ6-balance-lab.html` | 早期做的文明6 数值讲解页，与本 mod 无关 | 可丢 |

**没带的东西**：`.workbuddy/`（本机会话缓存，路径绑定、换机无意义）。所以新机器上没有对话历史，靠本文 + README 恢复上下文。

---

## 2. 新机器需要什么

| 项 | 要求 | 说明 |
|---|---|---|
| 系统 | Windows | 验证脚本与游戏路径都是 Windows 写法 |
| Python | 3.8+ | **零第三方依赖**，纯标准库（sqlite3 / xml / re / csv / zlib） |
| 文明6 | 本体 + 迭起兴衰 + 风云变幻 | 实机测试必需；只改代码不测则不必装 |
| WorkBuddy | — | 继续对话用 |

---

## 3. 开箱三步

```bash
# 1) 解压到任意目录，比如 D:\civ6-nhs\，然后进去
cd /d/civ6-nhs

# 2) 三个校验，确认环境没问题
python verify_mod.py       # 期望：0 错，仅剩刻意保留的 WARN
python run_mod_sql.py      # 期望：全部语句执行、全部断言通过
python lua_check.py        # 期望：全部 [ OK ]（无 Lua 改动可跳过）
```

> `run_mod_sql.py` 每次都会从 `db/gameplay_verify.sqlite` 复制一份到 `db/mod_test.sqlite` 再跑，**不会污染原库**，可反复运行。
> 如果 `db/gameplay_verify.sqlite` 丢了，先改 `build_game_db.py` 第 24 行的 `GAME` 路径，再 `python build_game_db.py`。

### `lua_check.py` 是什么（不需要装 Lua）

Civ6 用的**不是标准 Lua**，是 Havok Script（Firaxis 的 Lua 5.1 分支，`Base\Binaries\Win64Steam\HavokScript_FinalRelease.dll`）。
本机没有、也不需要装任何 Lua 解释器：脚本直接 `ctypes` 加载这个 DLL，调用它导出的
`luaL_newstate` / `luaL_loadbuffer` / `lua_tolstring`，**用游戏自己的编译器做语法检查**，判定与游戏内加载完全同源。

实测该 DLL 确实是 5.1 语义：`goto` 报 `= expected near 'done'`，`7 // 2` 报 `unexpected symbol near '/'`。
（所以不要用 Lua 5.4 解释器来校验——它会把这两类非法写法放过。）

```bash
python lua_check.py --selftest      # 反向测试：先证明校验器真能抓错，再信它的结论
python lua_check.py                 # 默认查 mod/lua + AgriculturalDistrict
python lua_check.py -p 某目录        # 指定路径，可重复 -p
python lua_check.py --all-mods      # 全部已启用 mod 的 .lua
```

**边界（必须知道）：它只验语法，不验语义。** 变量名写错、`nil` 判断漏了、API 名字拼错，
只要语法成立就判 OK —— 这些只能靠实机 `Logs/Lua.log` 暴露。
另外若游戏大版本更新改了导出表，脚本会明确报 `[FATAL] ... 缺少预期导出符号` 并退出，
不会静默当作通过；此时需要重新适配，不要绕过去。

```bash
# 3) 装进游戏（见下一节）
```

---

## 4. Mod 怎么装（三种方式，选一种）

**方式 A：本地 Mods 目录（推荐，改完立即生效）**

> **最省事**：直接用 `NuclearHolySite-v7-mod-only.zip`，解压出来就是一个 `NuclearHolySite/` 文件夹，
> 整个丢进 `…\Sid Meier's Civilization VI\Mods\` 即可，不用手动对结构。

目录必须长这样（`.modinfo` 在文件夹根，不能多套一层）：

```
…\Sid Meier's Civilization VI\Mods\NuclearHolySite\
    NuclearHolySite.modinfo
    sql\nhs_01_core.sql ... nhs_09_wonder_era.sql
    lua\nhs_info.lua
```

这个 `Mods` 目录在哪，取决于你的「文档」文件夹位置：

| 情况 | 路径 |
|---|---|
| 文档在系统盘 | `%USERPROFILE%\Documents\My Games\Sid Meier's Civilization VI\Mods\` |
| 文档被移到 D 盘（**本机就是这种**） | `D:\Documents\My games\Sid Meier's Civilization VI\Mods\` |
| 开了 OneDrive 同步 | `…\OneDrive\Documents\My Games\…` |

本机 v7 已经装在上面那条 D 盘路径里了 —— **但新机器不会有，必须重新拷一次**。
找不到自己的 Mods 目录？游戏主菜单 →「额外内容」→ 上面会显示 Mod 目录路径，点一下能直接打开。

**方式 B：Steam 创意工坊目录** —— 不推荐，会被 Steam 覆盖，只适合最终发布。

**方式 C：直接丢进 DLC 目录** —— 不推荐，跟本体更新冲突。

装好后：游戏主菜单 →「额外内容」→ 确认列表里有「核动力圣地 · Nuclear Holy Site (秦始皇专属)」且已勾选。
**开新局**，领袖必须选**中国 · 秦始皇**（不是忽必烈），否则本 mod 一层都不生效 —— 这是 v7 的刻意设计。

---

## 5. 给新机器上 AI 的开场白（直接复制粘贴）

```
我在做文明6（Civ6）的核动力圣地 mod，项目在 <解压路径>。当前是 v7。

先读这三个文件再动手，不要跳过：
- HANDOFF.md（交接状态与待办）
- README.md 第 0、2.9 节（诚实声明 + 唯一的未验证逻辑环节）
- VERIFICATION.md（每条原版 ID 的出处）

硬约束（改动前必须遵守）：
1. 只对「人类玩家 + 中国·秦始皇」生效。两层锁：traits 挂 LEADER_QIN + OwnerRequirementSetId='PLAYER_IS_HUMAN'。
2. 不要凭记忆写原版 ModifierId / TraitType —— 一律用「INSERT ... SELECT FROM 原版行」克隆，或先在 db/gameplay_verify.sqlite 里查证。
3. 改完必须跑 python verify_mod.py 和 python run_mod_sql.py，两个都绿才算改完。
4. 数值取向是「偏爽」但要有依据，改数要更新 config/balance_params.csv 并说明理由。
5. **新增任何 `UpdateDatabase` 组件，必须带 `<Properties><LoadOrder>500</LoadOrder></Properties>`。**
   不写就是 0，会排在官方资料片（100）之前建库；那时被克隆的源 trait/belief 尚未插入，
   `INSERT OR IGNORE ... SELECT` 命中 0 行且**不报错**，整层修饰器静默消失。v35 就是栽在这里。
   同理：**`run_mod_sql.py` 全绿不代表游戏里生效**——它跑的是离线合并库，源数据早就齐了。
6. **判断「是否生效」必须看游戏自己建出来的东西**：`Cache/DebugGameplay.sqlite` 里有没有那些行、
   `Logs/Modding.log` 里加载了哪些文件、`check_loaded.py` 报不报 `[缺失]/[过期]`。
   离线库只能证明 SQL 正确，不能证明执行时拿得到源数据。

当前待办：
- 实机测试（清单在 README 4.2）
- 重点确认两件数据层看不出来的事：奇观加速按钮是否真的全时代可用（README 2.9）、移民是否吃到移动加成
```

---

## 6. 进度台账

### ✅ 已完成并有证据

- 十六个 SQL 文件全部写完，在**真实游戏 schema**（310 表）+ **真实数据**（42020 行）上执行通过
- 八条 trait 只挂 `LEADER_QIN`，`CivilizationTraits` 为 0 行（执行验证，非推断）
- 克隆层数量核对：母亲 5 个 / 修道院 6 个（**游戏库实际 4 个**，见下）/ 极光之舞 6 个 / 经文 1 个 modifier / 劳雷尔 26 个（v7.30）
- 全库共 **67 个 NHS Modifier**，全部挂 `PLAYER_IS_HUMAN`（含 3 条经组合 Set 间接满足的宜居阶梯；v7.33 砍「每信徒 +1 产能」后由 62 减 1，v7.34 加 3 档后为 64，v7.38 换成科技规模三档后为 67）
  **注意 67 是离线合并库的数，游戏库应为 65**：`TRAIT_HOLY_SITE_RIVER_FOOD` / `..._HOUSING` 这两条只存在于「全 DLC 合并」的离线库里，游戏里叫 `TRAIT_HOLY_SITE_RIVER_2HOUSING`。这不是 bug，`nhs_05` 是全量克隆（源有几条克隆几条），断言也只要求 `> 0` 而非 `= 6`。v35 差点因为这个差异去改一个好文件。
- 信条克隆保留 `REQUIREMENT_CITY_FOLLOWS_RELIGION` 门槛；原版「每信徒 +1 产能」已在克隆源头剔除（v7.33）
- `.modinfo` 用原生 `<Mod><Properties><InGameActions>` 写法（对照游戏自带 43 个 modinfo，0 个用旧式 `<Modules>`）
- 产出曲线：新手苔原产能 **1.56 / 1.02 / 0.65**（远古/中古/现代），熟练 1.72 / 1.20 / 0.81
- **Lua 语法校验打通（2026-11-22）**：`lua_check.py` 用 `ctypes` 直接加载游戏自带 `HavokScript_FinalRelease.dll`，调 `luaL_newstate`/`luaL_loadbuffer`/`lua_tolstring`，**零安装、与游戏同源**。实测该运行时是 Lua 5.1 语义（`goto`、`//` 均报错）。反向测试 8/8（缺 `end`、括号/字符串未闭合、多余 `end`、`goto`、`//` 全部抓出）；全部已启用 mod 的 **30 个 `.lua` 语法 0 失败**。**只验语法不验语义**

### ⚠️ 未验证（换机器后要补的）

| 项 | 怎么验 |
|---|---|
| **负百分比折扣是否生效**（v7.38 核心，优先级最高） | 读档后鼠标停在首都「科研」数字上，产出明细里应出现**负值修正**；顶栏科研应从 335 降到 **185~210**。若仍 335 → 三条 modifier 整体没被采纳，先看 `Database.log` 有无 `NHS_TECH_SCALE` 报错 |
| 三档累计是加还是乘 | 21 人口城应 −53%、12 人口城应 −38%、6 人口城应 −18%。若实际约为 −44% / −31% / −15% → 引擎按乘法叠加（0.82×0.80×0.85），把 L2 的 `−20` 提到 `−30` 补齐；若三档数字完全一样 → `SubjectRequirementSetId` 没生效 |
| **v37 的 per-population 负值已被证否** | 已实测：335.2 一回合纹丝不动，实机库类型/参数/挂载全对。记录在 `nhs_18` 文件头，**不要再退回那个写法** |
| **`Inverse=1` 是否被引擎采纳**（v7.36 核心） | 文艺复兴之后的存档里，给在建奇观用一次建造者，进度应跳 **约 15%**（不是 30%）。若仍是 30% → 换减法方案（`Amount=-15` 去掉 `Inverse`，见 `nhs_08` 第 1b 节兜底） |
| 加速按钮是否任意时代奇观都有 | `MaxEra=-1`（v7.36）。之前推断依据是"玩家有 `MODIFIER_PLAYER_ADJUST_UNIT_WONDER_PERCENT`"，C++ 判据未见。**实机造工人对工业/现代奇观看按钮亮不亮**。`MaxEra` 已确认卡的是**奇观时代**（官方文案 + Zigzagzigal 指南双证），不是玩家时代 |
| 移民是否吃到 +2 移动 | `COLLECTION_PLAYER_UNITS` 是否覆盖民用车。不行就改 `UNIT_TAG_MATCHES` |
| 实机手感 / AI 是否变强 | 开一局神级，记录前 50 回合圣地相邻与奇观进度 |
| 多人局双秦始皇 | 第二个玩家不该拿到加成（`PLAYER_IS_HUMAN` 是第二道锁） |
| **AI 城市的 `GetBuildQueue():CurrentlyBuilding()` 能否读到**（v7.17 唯一不确定项） | 开一局到 AI 开始造奇观，看 `Logs/Lua.log` 里 `[NHS-Wonder] turn scan:` 那行的 `queue_readable`。为 0 即 API 受限，需换方案 |
| AgriculturalDistrict 那 6 处判空（2026-11-22） | **语法已验过**（`lua_check.py` 全 OK），但**语义未验**：需招募马库斯/陆羽/陈振龙等伟人且站在无资源地块上，`Lua.log` 不应再出现 `Agronomist*.lua` 的 `Runtime Error` |
| AgriculturalDistrict 补的 3 条本地化 | 重启游戏后，粮食产出来源 tooltip 不应再显示 `LOC_BUILDING_MACHU_PICCHU_FOOD` 原文 |

### ❌ 已知做不到的

"全程把强度压在 0.9~1.1"——**数学上不成立**。AI 吃 +100% 是指数，本 mod 是线性加数。已如实标注，不要试图用调数糊过去。

---

## 7. 改动入口速查

| 想改什么 | 去哪 |
|---|---|
| 圣地固定产出（产能/食物/信仰/文化/住房） | `mod/sql/nhs_01_core.sql` |
| 半价圣地、后期百分比缩放（默认注释掉） | `mod/sql/nhs_02_advanced.sql` |
| 界面上的中文文案 | `mod/sql/nhs_03_locale.sql`（**改数值必须同步改这里**，v6 曾漏改导致文案过期） |
| 俄罗斯母亲层 | `mod/sql/nhs_04_mother_russia.sql` |
| 国王的修道院 | `mod/sql/nhs_05_monasteries.sql` |
| 极光之舞 / 职业道德 / 耶稣会教育 / 经文 | `mod/sql/nhs_06_beliefs.sql` |
| 侦察兵 +3、移民 +2 移动 | `mod/sql/nhs_07_movement.sql` |
| 城名（秦郡）与首都名 | `mod/sql/nhs_10_city_names.sql`（**两张表都要改**：`CityNames` 管第二座城起，`CivilizationLeaders.CapitalName` 管首城） |
| 宜居度（全城 +1 / 圣地城 +2） | `mod/sql/nhs_13_amenities.sql` |
| 特色单位锐士 / 斥候 | `mod/sql/nhs_14_units.sql`（整行克隆，改战力就改克隆语句里的字面量；斥候移动在文件末尾那段 modifier） |
| 工人加速奇观（文艺复兴前 30%、之后 15%） | `mod/sql/nhs_08_wonder_boost.sql`：`Amount` 管幅度（15，与原版 15 叠加），第 1b 节的 `NHS_REQ_NOT_RENAISSANCE` 管分档（`EraType` 改早/改晚即移动分界点） |
| 全时代奇观解禁 | `mod/sql/nhs_09_wonder_era.sql`（**`MaxEra=-1`**，v7.36 由 3 放开；`MaxEra` 卡的是**目标奇观的时代**，不是玩家时代。全局表，危险层，已单独隔离） |
| 换成忽必烈也能用 | 各文件 `LEADER_QIN` → 加 `LEADER_KUBLAI_KHAN` |
| 想开游戏内诊断输出 | `mod/lua/nhs_info.lua` 顶部注释里有 `AddGameplayScripts` 写法 |
| 改了任何 `.lua` | 改完必跑 `python lua_check.py`——借游戏自带 Havok Script 编译器，与游戏判定同源；`--selftest` 先验证校验器本身可信 |

---

## 8. 版本历史（一行一条）

- v1：初版，只对人类生效（`CivilizationTraits`）→ 模型低估，废弃
- v2–v5：数值模型迭代，产能从 +3 一路调到 +0（产能改由职业道德按相邻驱动）
- v6：加俄罗斯母亲 / 国王的修道院 / 四选全开 / 双倍脚程 / 全时代奇观加速
- **v7（当前）**：从"所有人类玩家"收缩为"只对秦始皇"，消灭 AI 秦始皇的全时代解禁泄漏
- **v7.1（本地修复 2026-11-20）**：`.modinfo` 的 `<Mod id>` 原为 `9f3c1a70-nhs-4b21-9d8e-202611200001`（第二段 `nhs` 非法 GUID），游戏会静默跳过 → 实机整层失效。已改为合法 GUID `9F3C1A70-4E48-4B21-9D8E-202611200001`，version 1→2。静态/SQL 双校验仍全绿
- **v7.2（本地修复 2026-11-20，真正根因）**：实机 mod 进了存档但 9 个 SQL 一条未执行。查本次运行库 `AppData\Local\Firaxis Games\...\Cache\DebugGameplay.sqlite`：NHS trait 0 个、移动 modifier 0 个。根因 = `.modinfo` 缺 `<Files>` 节点！游戏自带 42/42 个 modinfo 都有 `<Files>` 显式登记全部文件，本 mod 是唯一没有的。已补 `<Files>`（10 个文件）+ `EnabledByDefault`/`ShowInBrowser`。**教训：清单必须有 `<Files>`，否则列表可见、GUID 进存档，但文件不被读取执行**
- **v7.3（本地修复 2026-11-20）**：补 `<Files>` 后 SQL 真正执行了，但实机弹"内容加载失败"。本次 `Database.log` 报 5 条外键错误：`NHS_MOD_CITY_YIELD`/`NHS_MOD_CITY_HOUSING`/`NHS_MOD_DISTRICT_COST` 未注册 KIND_MODIFIER，`EFFECT_ADJUST_HOUSING`/`EFFECT_ADJUST_DISTRICT_COST` 不存在。修复：① 核心层/进阶层把 3 个 NHS_MOD_* 在 Types 注册为 KIND_MODIFIER；② 住房 Effect 改官方 `EFFECT_ADJUST_POLICY_HOUSING`（参数 Amount 不变）；③ 半价圣地段整段禁用（唯一相近的 `EFFECT_ADJUST_ALL_DISTRICTS_PRODUCTION` 语义是产能加速，填负值反成减速，不能冒充成本减半）。④ `run_mod_sql.py` 新增外键校验（ModifierType/CollectionType/EffectType），并从游戏真实库导出 `db/game_types_baseline.txt`（460 Effect + 41 Collection）作校验基准——堵住"离线全绿但实机报错"的校验盲区。**教训：自定义 DynamicModifier 三字段都要能在 Types 解析，验证库不灌引擎级类型，必须单独维护白名单**
- **v7.4（本地修复 2026-11-20）**：外键修复后游戏能进读取界面，但"特征与能力"界面显示 6 行原始英文键名（`LOC_TRAIT_NHS_*`）。根因 = 本地化走了错误通道：`nhs_03_locale.sql` 挂在 `<UpdateDatabase>` 下，而 Gameplay 库**没有 LocalizedText 表**，日志报 `[Gameplay] ERROR: no such table: LocalizedText`，24 条文案全部静默失败。另：原 SQL 语言代码写的是 `zh_CN`，游戏实际认 `zh_Hans_CN`。修复：① 新建 `mod/text/nhs_text.xml`（`<BaseGameText>` 英文 + `<LocalizedText Language="zh_Hans_CN">` 中文，各 12 条）；② modinfo 的 `NHS_DB_LOCALE` 改为 `<UpdateText id="NHS_TEXT">`；③ 删除 `sql/nhs_03_locale.sql`（备份在 `backups/nhs_03_locale.sql.retired`），`<Files>` 同步改为登记 XML；④ version 2→3 强制重新解析清单；⑤ 两个校验脚本改为校验 XML 的 Tag 数与语言代码。**教训：Civ6 本地化只能走 UpdateText + XML（默认语言用 BaseGameText/Row，其他语言用 LocalizedText/Replace + Language），SQL 里的 LocalizedText 在 Gameplay 库不存在；简体中文代码是 zh_Hans_CN**
- **v7.5（文案改名，2026-11-20）**：按用户要求重命名 5 项并清理描述冗余。改名只动 `mod/text/nhs_text.xml` 的 `LOC_TRAIT_NHS_*` 文案，**tag 与 SQL 的 `Traits.Name/Description` 引用一律不变**（否则要重跑全部 SQL）。对照表：`NHS_NAME` 核动力圣地→**横渠**、`NHS_MR` 俄罗斯母亲→**披荆斩棘**、`NHS_MK` 国王的修道院→**江河淮济**、`NHS_BEL` 核动力信条→**勤劳**、`NHS_BUILDER` 御用工匠→**奇观狂魔**；`NHS_MOVE` 疾行拓荒者未要求改名，保留。描述统一删去实现层注脚（"AI 拿不到"、"克隆自原版"、"本 Mod 追加 15%"、"若你不是秦始皇则完全无效"、"别在游戏里再选一遍会拿双份"、"已按游戏数据核实"）与名称后的"（秦始皇专属）"后缀，只留机制与数值。modinfo 的 `<Teaser>`/`<Description>` 同步改用新名，version 3→4 强制重读文本。**教训：改名只改 XML 文案，不动 tag 名——tag 是 SQL 外键引用，改 tag 等于改数据结构**
- **v7.6（改名 + 秦郡城名，2026-11-20）**：① mod 标题改为「皇帝之威 · Majesty of the First Emperor」，Teaser/Description 改为吹秦始皇的文案；② `NHS_MOVE` 疾行拓荒者→**筚路蓝缕**（英文 Enduring Pioneers），主特性描述内的引用同步；③ 新增 `mod/sql/nhs_10_city_names.sql`：`DELETE FROM CityNames WHERE CivilizationType='CIVILIZATION_CHINA'` + 插入 41 个秦郡名（ID 900001~900041，避开原版最大 ID 1705；SortIndex 0~40；首城咸阳）。41 个 `LOC_CITY_NAME_QIN_*` 的中英文案写在 `text/nhs_text.xml`（现共 53 个 tag）。modinfo 加 `NHS_DB_CITY_NAMES` 动作 + `<Files>` 登记，version 5→6。④ 校验器：`verify_mod.py` 的 `KNOWN_TABLES` 补 `CityNames`，并把"残留 CIVILIZATION_CHINA"的警告改为只检查 `CivilizationTraits` 插入语句（否则城名替换会误报）；`run_mod_sql.py` 增 3 条城名断言（≥40 行、首城咸阳、tag 文案齐全）。**已知边界：CityNames 按 CivilizationType 分组，无 LeaderType 先例（原版 1677 行 LeaderType 全 NULL），因此秦地名会作用于所有中国（含 AI 忽必烈），纯外观不影响数值**
- **v7.7（第七层「驰道」，2026-11-20）**：新增 `mod/sql/nhs_11_roads.sql`——新建城市立刻与首都连通道路。**关键做法：克隆原版罗马「条条大路通罗马」的机制，不自造 Modifier**。原版链路：`TRAIT_CIVILIZATION_ALL_ROADS_TO_ROME` → `TRAIT_FREE_ROADS_TO_CAPITAL`（ModifierId）→ `MODIFIER_PLAYER_CITIES_GRANT_ROAD_TO_CAPITAL`（ModifierType）→ `EFFECT_GRANT_CITY_ROAD_TO_CAPITAL`（Effect）。我们只复制 ModifierId 为 `NHS_ROAD_TO_CAPITAL`、复用原版 ModifierType，**不写 DynamicModifiers**（原版已注册，重复写撞主键），无参数（该 Modifier 本身不吃参数），加 `PLAYER_IS_HUMAN` 门槛，挂到新 trait `TRAIT_NHS_IMPERIAL_ROAD`，走 LeaderTraits 只发给 LEADER_QIN。modinfo 加 `NHS_DB_ROADS` 动作，version 6→7。文案：`LOC_TRAIT_NHS_ROAD_NAME/DESC`（中文「驰道」）。校验器：两个脚本的 `NHS_TRAITS` 清单补第 7 个 trait，`run_mod_sql.py` 新增 6 条驰道断言（ModifierType/EffectType/CollectionType/人类门槛/无参数/挂载关系）。**方法论：Civ6 的 gameplay Lua 拿不到 RouteBuilder（只在 UI/Tuner 层暴露），铺路必须走数据层 Modifier，不能写 Lua**
- **v7.8（第八层「法令一统」，2026-11-20）**：新增 `mod/sql/nhs_12_edicts.sql`——自开局起额外 +1 通配符政策槽。**同样克隆原版，不自造 Modifier**。原版链路：`TRAIT_CIVILIZATION_PLATOS_REPUBLIC`（希腊「柏拉图理想国」）→ `TRAIT_WILDCARD_GOVERNMENT_SLOT`（ModifierId）→ `MODIFIER_PLAYER_CULTURE_ADJUST_GOVERNMENT_SLOTS_MODIFIER`（ModifierType）→ `EFFECT_ADJUST_PLAYER_GOVERNMENT_SLOT_TYPE`（Effect），CollectionType 为 `COLLECTION_OWNER`（天然只作用玩家本人）。该 Modifier 只吃 `GovernmentSlotType=SLOT_WILDCARD` 一个参数，数量沿用 Effect 默认值 1（紫禁城同写法），**不需要 Amount**。复制 ModifierId 为 `NHS_WILDCARD_SLOT`，加 `PLAYER_IS_HUMAN`，挂到新 trait `TRAIT_NHS_EDICTS`，走 LeaderTraits 只发给 LEADER_QIN。modinfo 加 `NHS_DB_EDICTS` 动作 + `<Files>` 登记，version 7→8。文案：`LOC_TRAIT_NHS_EDICT_NAME/DESC`（中文「法令一统」，英文 Unified Statutes）。校验器：`NHS_TRAITS` 补第 8 个 trait，`run_mod_sql.py` 新增 7 条法令断言。**边界：槽位来自 Effects 层而非 `Government_SlotCounts`，换政体不丢；但「槽位」与「政策卡」是两件事——槽位开局就有，可插哪些卡仍受已解锁政策限制（原版规则，本层不绕过）**
- **v7.9（介绍重写，2026-11-20）**：modinfo 的 `Teaser`/`Description` 按八项特征重写为「一曰…八曰…」体例，每项带实际数值（横渠 +1食物/+2信仰/+1文化/+2住房、披荆斩棘 苔原+1信仰+1产能+5格疆土、江河淮济 大相邻+等值食物+2住房+文化炸弹、勤劳 四张信条/政策、筚路蓝缕 3→6 与 2→4、奇观狂魔 30% 不限时代、驰道 新城通都、法令一统 +1 通配槽），结尾保留「唯中国·秦始皇可承」。version 8→9（mod 浏览器按版本号缓存介绍文案，不升版看不到新文本）
- **v7.10（八项名称统一四字，2026-11-20）**：三个二字名改为四字，均保留原名前两字以便识别——**横渠→横渠立心**（张载横渠四句「为天地立心」）、**勤劳→勤则不匮**（《左传》「民生在勤，勤则不匮」）、**驰道→驰道通都**（秦驰道起咸阳、通各郡）。其余五项（披荆斩棘/江河淮济/筚路蓝缕/奇观狂魔/法令一统）本是四字未动。只改 `text/nhs_text.xml` 的 `<Text>` 值，tag 名一律未动（tag 是 SQL 外键）。主特性描述内的引用、modinfo 的 Teaser/Description 同步换名，version 9→10。`verify_mod.py` 新增四字断言（扫描全部 `LOC_TRAIT_NHS*_NAME` 的 zh_Hans_CN 文本，长度≠4 即报错）
- **v7.11（首项改名，2026-11-21）**：**横渠立心 → 天命玄鸟**（英文 Hengqu → Heaven-Sent Swallow）。动机：原名为张载（北宋）横渠四句，是八项中唯一宋代典故，与其余先秦典（《左传》）和秦制（驰道/法令）不同代。新名取《诗·商颂·玄鸟》「天命玄鸟，降而生商」原句前四字；秦人族源亦有玄鸟陨卵之说（《史记·秦本纪》女脩吞玄鸟卵生大业），用于秦始皇不算误植。**已知代价：玩家第一联想多为商族起源**。只改 `text/nhs_text.xml` 的 `<Text>` 值（中英各一）与 modinfo `<Description>` 的「一曰…」，tag 未动，version 10→11。`README.md`/`VERIFICATION.md` 无此名，无需同步。
- **v7.12（第六项改名，2026-11-21）**：**奇观狂魔 → 物勒工名**（英文 Wonder Maniac → The Maker's Name）。动机：原名是现代网络语，与其余七项的先秦典（《左传》）和秦制（驰道/法令）不同层。新名出《礼记·月令》「物勒工名，以考其诚，功有不当，必行其罪」，即器物与工程刻施工者名、质量终身追溯；秦有实物实证（兵器铭文「相邦吕不韦造／工师／丞／工」四级署名、兵马俑坑砖瓦工匠名、睡虎地秦简《工律》同型器物尺寸必等的标准化生产）。字面暗合机制：建造者亲手把进度打进奇观。改动：`text/nhs_text.xml` 的名称、主特性描述内的七项列举（中英各一）、文件头注释；modinfo `<Description>` 的「六曰…」，version 11→12。tag 未动。
- **v7.13（宜居度层，2026-11-21）**：实机反馈「很缺宜居度」。**先定根因再改数**：本 mod 的食物 +1、住房 +2 与职业道德（相邻信仰转产能）把人口推得比原版快，而宜居度供给端（奢侈品/娱乐区/奇观）一点没变；Civ6 每 2 人口 1 点需求，人口越快缺口越大——这是设计的必然副作用，不是数值 bug。新增 `sql/nhs_13_amenities.sql`：① `NHS_CITY_AMENITY` = `MODIFIER_PLAYER_CITIES_ADJUST_POLICY_AMENITY`（EFFECT_ADJUST_POLICY_AMENITY / COLLECTION_PLAYER_CITIES，Amount 1，**不挂 SubjectRequirement**，模板为政体「数字民主」的 `DIGITAL_DEMOCRACY_CITY_AMENITIES`）；② `NHS_HOLY_SITE_AMENITY` = `MODIFIER_CITY_DISTRICTS_ADJUST_DISTRICT_AMENITY`（EFFECT_ADJUST_DISTRICT_AMENITY / COLLECTION_CITY_DISTRICTS，Amount 1，SubjectRequirementSet **复用原版 `DISTRICT_IS_HOLY_SITE`**，模板为信条「河神」`RIVER_GODDESS_HOLY_SITE_AMENITIES_MODIFIER`，先例 `DIVINE_SPARK_HOLY_SITE_MODIFIER` 证明该 reqset 在区域收集器下可用，故本层不新建 Requirement）。两条均加 `PLAYER_IS_HUMAN`，挂核心特性 `TRAIT_NHS_NUCLEAR_HOLY_SITE`——**不新增第 9 条特性**，八威仪结构与介绍体例保持不变。合计：有圣地的城 +2，无圣地的城 +1。文案同步 `LOC_TRAIT_NHS_DESC` 中英与 modinfo「一曰…」，version 12→13。校验器：两脚本 `SQL_FILES` 增至 12 个文件；`verify_mod.py` 新增 [AM] 静态断言（重点防「圣地那条漏 SubjectRequirementSetId」——COLLECTION_CITY_DISTRICTS 不收窄会给每座城的每个区域都 +1，数值直接失控）；`run_mod_sql.py` 新增 12 条宜居度断言（Effect/Collection/门槛/reqset 存在性/Amount/挂载数）。**待实机确认：宜居度面板里每城是否 +1、圣地城是否 +2**
- **v7.14（首都信仰，2026-11-21）**：按用户要求加「首都每回合 +1 信仰」。**不新建 ModifierType**——原版已有 `MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE`（= `COLLECTION_PLAYER_CAPITAL_CITY` + `EFFECT_ADJUST_CITY_YIELD_CHANGE`），收集器本身就只指向首都；同写法的原版用例有三个：政体「专制」遗产 `AUTOCRACY_FAITH`（Amount 1 / YIELD_FAITH）、城邦宗教宗主 `MINOR_CIV_RELIGIOUS_YIELD_FOR_CAPITAL`（Amount 2）、城邦科技宗主 `MINOR_CIV_SCIENTIFIC_YIELD_FOR_CAPITAL`。写在 `nhs_01_core.sql` 新增第 4b 节：ModifierId `NHS_CAPITAL_FAITH`，Amount 1，`OwnerRequirementSetId = PLAYER_IS_HUMAN`，**不挂 SubjectRequirement**（收集器已限定首都，多挂反而可能收错），挂核心特性 `TRAIT_NHS_NUCLEAR_HOLY_SITE`。设计口径：这是"保底"，只加首都、不随城市数增长；有圣地的首都实际是 +3（核心层 +2 与首都 +1 叠加）。文案同步 `LOC_TRAIT_NHS_DESC` 中英与 modinfo「一曰…」，version 13→14。校验器：`verify_mod.py` 新增 [CAP] 静态断言（防"用城市收集器变成全城加信仰"）；`run_mod_sql.py` 新增 8 条首都断言（ModifierType/Collection/Effect/人类门槛/无 Subject/产出类型/Amount/挂载）。**待实机确认：首都产出面板的信仰构成里出现 +1**

- **v7.15（首城名修复，2026-11-21）**：实机反馈「初始坐地首都名字仍然是西安」。排查链：① `nhs_10_city_names.sql` 执行成功（Modding.log 明示 `UpdateDatabase - Loading sql/nhs_10_city_names.sql`，无报错）；② 本次运行库 `Cache/DebugGameplay.sqlite` 里 `CityNames` 中国 = 41 个 `LOC_CITY_NAME_QIN_*`（+1 个外部 mod 的 `SHEN_DU`），**一条 `LOC_CITY_NAME_XIAN` 都不剩**——数据层没问题；③ 但 `DebugLocalization.sqlite` 里 `LOC_CITY_NAME_XIAN` 仍解析为「西安」。**真正根因：Civ6 首城名不走 `CityNames`，走 `CivilizationLeaders.CapitalName`**，见 `Base/Assets/Gameplay/Data/Civilizations.xml:196` `<Row CivilizationType="CIVILIZATION_CHINA" LeaderType="LEADER_QIN" CapitalName="LOC_CITY_NAME_XIAN"/>`。第一座城（首都）用这张表的 `CapitalName`，**第二座城起才从 `CityNames` 取**，所以只替换 CityNames 时首城永远回到西安。修复：`nhs_10_city_names.sql` 追加第 2 段 `UPDATE CivilizationLeaders SET CapitalName='LOC_CITY_NAME_QIN_XIANYANG' WHERE CivilizationType='CIVILIZATION_CHINA' AND CapitalName='LOC_CITY_NAME_XIAN'`——条件用「首都名=西安」而非硬编码 LeaderType，可同时覆盖原版两个秦始皇变体（`LEADER_QIN` / `LEADER_QIN_ALT`，后者来自资料片），且不会误改永乐（BEIJING）、武则天（SHEN_DU）、忽必烈（BEIJING）等其他中国领袖。version 14→15。校验器：`verify_mod.py` 的 `KNOWN_TABLES` 补 `CivilizationLeaders`，新增 [城名] 静态断言（缺 UPDATE 即报错）；`run_mod_sql.py` 原「首城为咸阳」断言改名为「CityNames 首项」（它测的其实是第二座城），另增 3 条真断言（`CapitalName` 已改、无中国领袖残留 `LOC_CITY_NAME_XIAN`、文案齐全）。**教训：Civ6 里「首城名」与「城名列表」是两张表两套机制，改城名必须同时改 `CivilizationLeaders.CapitalName`，否则首城永远是原版名。已建城市的名字在建立时固定，改表只对新开局生效。** **附带事实：`Civilizations.RandomCityNameDepth` 中国=10，所以第二座城起是从前 10 个秦郡名里随机取，不严格按 SortIndex 梯队顺序；若要求严格按序，需把它改成 1（尚未改，待用户定）**

- **v7.16（特色单位「锐士」「斥候」，2026-11-21）**：按用户要求把开局勇士改为特色单位「锐士」、侦察兵改为特色单位「斥候」。**关键判断：这个需求能纯用数据层做到，不需要 Lua。** 依据是原版阿兹特克：开局拿的是鹰武士 `UNIT_AZTEC_EAGLE_WARRIOR`，但 `MajorStartingUnits` 里根本没有鹰武士这一行，只有 `UNIT_WARRIOR`——说明引擎发放起始单位时会检查 `UnitReplaces`，若有替换该单位的特色单位就直接发特色单位（盖尔枪兵 replaces 勇士、克里斥候 replaces 侦察兵同理）。新增 `mod/sql/nhs_14_units.sql`：① `Types` 注册 `UNIT_NHS_RUISHI` / `UNIT_NHS_SCOUT` 为 `KIND_UNIT`；② **整行克隆原型**（`Units` 67 列逐列写出，只把 `UnitType`/`Name`/`Description`/`TraitType` 换成字面量，其余 `SELECT "列名"` 原样照抄），不手写数值，避免漏字段；③ 克隆 `UnitAiInfos`（锐士 4 条 / 斥候 2 条）与 `UnitUpgrades`（锐士→剑士、斥候→游骑兵）；④ `UnitReplaces` 建替代关系（**注意列名是 `CivUniqueUnitType` 而不是 `UnitType`**）；⑤ 斥候单独一份移动修饰。`TraitType` 挂 `TRAIT_NHS_NUCLEAR_HOLY_SITE`（天命玄鸟），该 trait 已由 LeaderTraits 只发 LEADER_QIN，故只有秦始皇能造；**刻意不新建 trait**，以免打破「八威仪」结构。数值与原型完全一致（锐士 20/40、斥候 10/30），只换名不加强。**踩到的坑：斥候克隆出来只有 3 移动**——`nhs_07` 的「侦察兵 3→6」不是改 `Units.BaseMoves`，而是加了 `NHS_SCOUT_MOVEMENT`（`MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT` + 门槛 `UnitType='UNIT_SCOUT'`），新单位匹配不到那条门槛。故在 `nhs_14` 里补 `NHS_UNIQUE_SCOUT_MOVEMENT`（同类型 modifier，门槛换成 `NHS_REQSET_UNIT_NHS_SCOUT`，Amount 3，挂同一 trait 筚路蓝缕）。文案：`LOC_UNIT_NHS_RUISHI_NAME/_DESCRIPTION`（锐士 / Elite Warrior，引《荀子·议兵》「魏氏之武卒不可以遇秦之锐士」）、`LOC_UNIT_NHS_SCOUT_NAME/_DESCRIPTION`（斥候 / Outrider）。modinfo 加 `NHS_DB_UNITS` 动作 + `<Files>` 登记，`<Description>` 第五项改为「开局勇士即为锐士、侦察兵即为斥候，斥候移速 3→6，移民 2→4」，version 15→16。校验器：两脚本 `SQL_FILES` 增至 13 个；`verify_mod.py` 的 `KNOWN_TABLES` 补 `UnitReplaces`/`UnitAiInfos`/`UnitUpgrades`；`run_mod_sql.py` 新增 19 条单位断言（建单位/挂 trait/克隆完整/替代关系/AI 标签/升级链/基础移动仍 3/移动修饰类型与门槛与数值/挂载点/战力）。**已知边界：Civ6 标准开局只有开拓者 + 勇士，没有侦察兵**（`MajorStartingUnits` 的 ERA_ANCIENT 只有 SETTLER/WARRIOR/BUILDER），所以「斥候」只影响生产列表，开局本来就不会有侦察兵。

---

- **v7.17（奇观监听通知，2026-11-21）**：需求「AI 开始建造某个奇观时给玩家通知」。**先查了原生机制到底有没有，结论是没有**：① 真实运行库 `Cache/DebugGameplay.sqlite` 的 `Notifications` 表共 212 行，奇观类只有 `NOTIFICATION_WONDER_COMPLETED`（建成）和 `NOTIFICATION_WONDER_FAILED`（被抢先），**没有「开始建造」**；② 全量 grep 本体 + 资料片的 Lua，`GameEvents` 里只有 `BuildingConstructed` / `Events.WonderCompleted`，**没有任何「开始生产」事件**——原版把「对手在建什么」当隐藏情报（只能靠间谍摸），所以只在这两个结果点通知。**结论：这件事数据层做不到，只能写 gameplay 脚本轮询生产队列。** 三个环节全部用原生 API、无一自造：① 判定奇观用 `GameInfo.Buildings[t].MaxWorldInstances == 1`（真实库恰好 54 行，正是全世界奇观；普通建筑为 -1），不维护奇观名单；② 轮询点用 `GameEvents.OnGameTurnStarted`（官方 AlexanderScenario / AustraliaScenario / BlackDeathScenario / CivRoyale 四个 DLC 场景同款）；③ 发通知用 `NotificationManager.SendNotification(playerID, type, 标题, 正文, x, y)`，**gameplay 脚本里可直接调用**，范式见 `DLC/BlackDeathScenario/Scripts/BlackDeathScenario_Support.lua:28`，且官方场景顶层就用 `NotificationTypes.USER_DEFINED_1` 说明该枚举加载即可用。**通知槽复用原版预留的 `NOTIFICATION_USER_DEFINED_1..9`**（`Base/Assets/Gameplay/Data/Notifications.xml:52-60` 注册 Types、`165-173` 注册 Notifications 行），因此不必自建通知类型、不必写 Message/Summary 登记行；但这些槽**不带图标**，引擎按 `"ICON_" .. NotificationType` 找图，缺了就每条通知刷一次 `[DataError] IconManager is unable to find the icon "ICON_NOTIFICATION_USER_DEFINED_1" at size "40"`，故新增 `data/nhs_icons.xml` 用 `<UpdateIcons>` + `IconDefinitions` 把该名映射到 `ICON_ATLAS_NOTIFICATIONS` 的 Index 3（= `ICON_NOTIFICATION_CHOOSE_CITY_PRODUCTION`，语义最近），先例是创意工坊 3810795757 的 `Data/Assimilation_Icons.xml`。**踩到的坑（本层最危险的一处）：`Player` 对象上没有 `HasTrait` 方法。** 原版 `HasTrait` 是 **UI 层**的全局函数（`Base/Assets/UI/Scripts/GameCapabilities.lua:16`），实现是查 `PlayerConfigurations[id]` 的 `GetLeaderTypeName()` / `GetCivilizationTypeName()` 再比对 `GameInfo.LeaderTraits` / `CivilizationTraits`。最初写成 `pPlayer:HasTrait(...)`，外面套的 `pcall` 把报错吞成 `false`，表现就是「整套通知静默不工作、日志里也没有任何异常」——已改成照抄官方查法并在 `verify_mod.py` 里加反向断言，同时该断言只扫有效代码行（注释里保留了这句错误写法当教训）。**去重**用 `Game:SetProperty/GetProperty`（先例 `DLC/CivRoyaleScenario/Scripts/CivRoyaleScenario_StartScript.lua:173`），每个「文明 + 奇观」组合写一条属性，随存档保存，读档不会把正在建的再播一遍；`Game` 属性不可用时退回本局内存表。**新增文件**：`lua/nhs_wonder_watch.lua`（主逻辑，含 `WATCH_ALL_AI` / `REQUIRE_MET` / `DEBUG_LOG` 三个开关）、`data/nhs_icons.xml`（图标补丁）；`text/nhs_text.xml` 增 `LOC_NHS_WATCH_TITLE`（奇观动工 / A Wonder Has Been Started）与 `LOC_NHS_WATCH_BODY`（`{1_CivName}已在{2_CityName}动工兴建{3_WonderName}。`），占位符按位置对应三个实参。modinfo 增 `<AddGameplayScripts>` 与 `<UpdateIcons>` 两个动作 + `<Files>` 两条登记，`<Description>` 末尾加「另附奇观监听：他国动工兴造奇观之日即有奏报入朝，唯已相遇者方在报中」，version 16→17。**按用户选择**：所有 AI 开建都通知、但只通知已相遇文明（`HasMet` 判定，避免泄漏未知大陆）。**校验器**：`verify_mod.py` 新增第 12 节共 9 条断言（文件存在 / AddGameplayScripts 已注册 / UpdateIcons 已注册 / 槽位与图标名一一对应 / 两个文本 tag 中英各一份 / lua 引用的 `LOC_NHS_*` tag 必须真实存在 / 正文占位符个数与 `Locale.Lookup` 实参个数一致 / `OnGameTurnStarted` 已绑定 / 禁止 `xxx:HasTrait(`）。**待实测（本层唯一不确定项）**：读 **AI** 城市的 `GetBuildQueue():CurrentlyBuilding()` 是否可读——找到的先例都是读本玩家城市（工坊 `QinSpeedGameplay.lua`、`Cheat_Menu_Panel_Script.lua`），没有直接读 AI 在建项的现成样本。代码全程 `pcall` 保护 + 每回合打印 `[NHS-Wonder] turn scan: ai_cities=.. queue_readable=.. wonders=.. new=..`，实机看 `Logs/Lua.log` 即可判定：`queue_readable` 若为 0 就是 API 受限，需换方案（例如改为监听 `BuildingConstructed` 反推）。**已知边界（刻意）**：回合粒度不是实时；只看当前生产项、看不到队列后段；AI 取消后重开同一奇观会再报一次。

- **v7.18（锐士/斥候图标，2026-11-21）**：实机反馈两个特色单位没有图标（空白框）。**根因是纯缺失**：`nhs_14_units.sql` 只克隆了 `Units` 行，而 Civ6 的单位图标不由 `Units` 表决定，靠 `IconDefinitions` 按名字查图集，我们从没登记过 `ICON_UNIT_NHS_*`。**先查清解析链再动手**：① 地图旗帜取 `"ICON_" .. UnitType`（`Base/Assets/UI/UnitFlagManager.lua:524`）；② 单位面板/生产列表/百科取立绘四连（`UI/PortraitSupport.lua:96` 的 `GetUnitPortraitIconNamesFromDefinition`），顺序为 `ICON_<民族性>_<单位>_PORTRAIT_<时代>` → `ICON_<民族性>_<单位>_PORTRAIT` → `ICON_<单位>_PORTRAIT_<时代>` → `ICON_<单位>_PORTRAIT`，`UI/ProductionHelper.lua:54` 用 `TrySetIcon` 逐个试取第一个存在的；中国民族性实测为 `ETHNICITY_ASIAN`（`Civilizations.Ethnicity`），时代后缀实测为 `_PORTRAIT_ERA_ANCIENT` 形式（`Game.GetEras` 分支）。**贴图格式不是猜的**：游戏自己的单位图集（Units256.dds 等）打包在资源包里、本机无解包工具，故以创意工坊 1369684991 为格式模板——它的 `Icons/*.dds` 是**未压缩 A8R8G8B8**（`pfFlags=0x41`、`bitCount=32`、掩码 `R=0xff0000 G=0xff00 B=0xff A=0xff000000`，文件内字节序 B,G,R,A），且用 `<ImportFiles id="Res2_Icons_Import">` 把 dds 送进引擎；**这一步最容易漏**——图集注册成功但贴图没导入，图标照样空白。**做法**：新增 `tools/make_unit_icons.py`（纯标准库，无 PIL/numpy），用 SDF 式图元 + 4× 超采样自绘两枚字形：锐士 = 盾 + 斜置长矛（先秦步兵识别符号），斥候 = 马首侧影（斥候为轻骑侦骑）；输出两套图集 `ICON_ATLAS_NHS_UNITS`（256/80/50/38/32/22，纯字形，给旗帜与小图标）与 `ICON_ATLAS_NHS_PORTRAITS`（256/200/95/70/50/38，带深棕圆牌 + 金环，给立绘位），每图横排 2 格（`IconsPerRow=2`、`IconsPerColumn=1`，Index 0 锐士、1 斥候），共 12 个 dds、约 2.0 MB。`data/nhs_icons.xml` 增 12 条 `IconTextureAtlases` + 12 条 `IconDefinitions`（2 个旗帜名 + 8 个立绘名 + `_WHITE` 保险名），modinfo 增 `<ImportFiles id="NHS_ICON_TEXTURES">` 并在 `<Files>` 同步登记，version 17→18。**两个设计细节有实证支撑**：① 小尺寸笔画按目标像素兜底（`MIN_HALF_PX=1.3`），否则按 256 设计的矛杆缩到 22px 只剩半像素、整根消失；② 眼、鼻孔、盾心浮雕在 <40px 时不绘制，否则退化成脏点。**校验器**：`verify_mod.py` 新增第 13 节 4 组断言——12 个 dds 齐全且头部合规（DDS 魔数 / 宽=2×高 / pf 0x41 / 32 位 / 四掩码全对）、`<ImportFiles>` 与 `<Files>` 各 12 条不漏、两套图集的尺寸集合与文件名规则与实际档位一致、12 个图标名的 Atlas/Index 全部对得上（立绘名缺一个就会断回退链）。**待实机确认**：旗帜上是否出现锐士/斥候字形、生产列表是否显示徽章立绘；若仍空白，看 `Logs/Database.log` 有无 `IconManager is unable to find the icon`，以及 `Filename` 是否需带 `icons/` 前缀（当前按工坊先例用裸文件名）。

- **v7.19（图标改用原版图集，2026-11-21）**：实机反馈「你画的图标有点丑」。**不再自绘，改为同名映射原版图集**——引擎只按名字找图标、不关心图来自哪个图集，因此把 `ICON_UNIT_NHS_RUISHI` 直接指到原版格子即可，零贴图、零 `ImportFiles`、零 DDS 格式风险，且与官方美术同像素风格。**选型（用户拍板）**：锐士 → 阿兹特克鹰武士 `ICON_UNIT_AZTEC_EAGLE_WARRIOR`（同为远古近战、同为「勇士的替代单位」，时代与定位完全对应）；斥候 → 原版侦察兵 `ICON_UNIT_SCOUT`。**索引逐条查证、不凭记忆**：`Base/Assets/UI/Icons/Icons_Units.xml` 第 32 行 SCOUT=19、第 38 行 EAGLE_WARRIOR=25、第 133/139 行为对应 `_FOW`；`Icons_UnitPortraits.xml` 第 77 行 SCOUT=17、第 83 行 EAGLE_WARRIOR=23、第 178/184 行为 `ETHNICITY_ASIAN` 版本。**顺带补上一个 v7.18 的漏**：原来只登记旗帜与立绘名，没登记 `_FOW`（战争迷雾版本），未探索区域本会是空框，这次一并补上。**清理**：删除 `mod/icons/` 全部 12 个 DDS（备份在 `backups/icons_v18/`）、modinfo 移除 `<ImportFiles id="NHS_ICON_TEXTURES">` 与 `<Files>` 里 12 条贴图登记，mod 文件数 30 → 18。**校验器重写第 13 节**：不再查 DDS 头，改为①自绘贴图必须彻底退场（残留即报错）、②14 个图标名必须齐备且指向预期格子、③**打开游戏本体 XML 实时对账**——把每个名字的参考图标（鹰武士/侦察兵）在 `Icons_Units.xml`、`Icons_UnitPortraits.xml` 里的真实 Atlas/Index 读出来比对，任何一位写错都会报「与游戏本体不符」，`CIV6_DIR` 环境变量可覆盖默认 Steam 路径。校验结果：0 错 2 警告（沿用原有权衡），14 个名字全部与本体一致。**待实机确认**：旗帜、生产列表、单位面板、战雾下四处的图标是否都换成官方风格（需重启游戏 + 重开新局，图标在开局时注册）。

- **v7.20（补全锐士/斥候的原版特征，2026-11-21）**：用户要求「把这两个特色单位原本的特征也添加上，只换个名字就行」。**做法是先穷举、再决定**：对 `Cache/DebugGameplay.sqlite` 里全部 **447 张表、逐列**扫描值等于 `UNIT_WARRIOR` / `UNIT_SCOUT` 的引用点，共 11 处——`Units`、`Types`、`UnitAiInfos`、`UnitUpgrades`、`UnitReplaces`、`TypeTags`、`MajorStartingUnits`、`BonusMinorStartingUnits`、`Boosts`(2)、`ModifierArguments`(1)、`RequirementArguments`(1)。逐项判定后确认**唯一真实缺口是 `TypeTags`**：原版 `UNIT_WARRIOR` 带 `CLASS_MELEE`，`UNIT_SCOUT` 带 `CLASS_RECON` + `CLASS_REVEAL_STEALTH`，而克隆出来的锐士/斥候一条都没有。**后果全是静默的**：锐士不算近战单位 → 按 `CLASS_MELEE` 判定的政策卡与加成全部落空、生产列表分类掉进「其他」、AI 兵种配比认不出它；斥候缺 `CLASS_REVEAL_STEALTH` 就**看不见隐形单位**（这正是侦察兵的能力来源）。补法是照抄原型行 `INSERT OR IGNORE ... SELECT`，原版将来增删标签自动跟随。**其余引用点经核对不需要动**：`MajorStartingUnits` / `BonusMinorStartingUnits` 由引擎按 `UnitReplaces` 自动换发（阿兹特克鹰武士先例）；`Boosts` 的两条「用侦察兵发现自然奇观 / 遇见文明」在原版里**也没有**为克里斥候 `UNIT_CREE_OKIHTCITAW` 补行，说明判定不依赖 `Unit1Type`（它只是 UI 提示），保持一致不补；`Units_XP2` 里 `UNIT_WARRIOR` / `UNIT_SCOUT` **本身无行**（鹰武士同样无行），默认值即正确，故不克隆。`Units` 表 67 列已逐列全克隆（核对过无漏列）。**校验**：`run_mod_sql.py` 新增断言「TypeTags 必须与原型逐条相同」，实跑输出 `锐士 CLASS_MELEE` / `斥候 CLASS_RECON、CLASS_REVEAL_STEALTH`；`verify_mod.py` 的合法表白名单补 `TypeTags`。两脚本均 0 错（仍为原有 2 条刻意保留的警告），version 19→20。

- **v7.21（锐士「击敌获工」，2026-11-21）**：用户提出「一个特色单位击败敌人后有几率获得工人」——指的是鹰武士。**机制已逐层查清**：`TypeTags` 里 `CLASS_CAPTURE_WORKER` 的 Vocabulary 是 `ABILITY_CLASS`，而 `ABILITY_CAPTIVE_WORKERS` 在 `TypeTags` 里以 `Tag='CLASS_CAPTURE_WORKER'` 登记自身，因此单位认领同名 Tag 即自动获得该能力（`UnitAbilities.xml:177`）；能力再经 `UnitAbilityModifiers` 挂 `CAPTURE_COMBAT_UNITS_AS_WORKERS` → `MODIFIER_UNIT_ADJUST_COMBAT_UNIT_CAPTURE`（Collection `COLLECTION_UNIT_COMBAT` / Effect `EFFECT_ADJUST_UNIT_COMBAT_UNIT_CAPTURE`），参数 `CanCapture=1`、`UnitType=UNIT_BUILDER`。**所以只需一行标签，不必自建能力或 modifier**：`INSERT OR IGNORE INTO TypeTags VALUES ('UNIT_NHS_RUISHI','CLASS_CAPTURE_WORKER')`。**这是用户点名要的加强项，不是勇士的原版特征**，故在 `nhs_14_units.sql` 里单独成节（7.2）与「照抄原型」分开，便于日后一眼分辨。几率问题如实记：官方 modifier 描述是 `{1_Amount}% chance of capturing enemy`，但鹰武士这条**没有给 Amount 参数**，实际概率由引擎内置判定，数据层读不出来。同步改了文案（`LOC_UNIT_NHS_RUISHI_DESCRIPTION` 中英各加一句）与 modinfo `<Description>` 第五威仪一句「锐士克敌有几率俘其卒为工匠」。**校验**：`run_mod_sql.py` 加四层断言（标签在位 / Vocabulary 是 ABILITY_CLASS / 能力→修饰链通到 `CAPTURE_COMBAT_UNITS_AS_WORKERS` / 产物是 `UNIT_BUILDER`），并把 v7.20 的「标签必须与原版逐条相同」改成「必须覆盖原版全部标签 + 多出的只能来自白名单」，否则这条加强会被自己的断言拦下。两脚本 0 错，version 20→21。

- **v7.22（城名池剔除「神都」，2026-11-21）**：用户实机看到第二座城叫「神都」，要求去掉。**根因不在我们的列表里**——41 个秦郡名（900001~900041）没有它；它来自资料片 `DLC/RulersOfChina/Data/RulersOfChina_Civilizations.xml:11-13`，是「中国统治者包」给武则天往同一个 `CIVILIZATION_CHINA` 城名池塞的一行 `<CityName>LOC_CITY_NAME_SHEN_DU</CityName>`（无显式 ID，运行时自动分配到 **900692**）。**为什么 v7.6 的全量 DELETE 没删掉它**：实测 `DebugGameplay.sqlite` 里最终恰好是「我们 41 行 + 神都 900692」，说明该 DLC 的 `UpdateDatabase` 在 mod **之后**加载，`DELETE` 删不到尚未存在的行——这解释了「城名全替换了却仍冒出神都」这个现象，也提示以后凡是官方 DLC 自带的内容，都不能只靠一次 DELETE。**两条路都堵上**：① `nhs_10_city_names.sql` 增加 `DELETE FROM CityNames WHERE CityName='LOC_CITY_NAME_SHEN_DU'`（加载顺序若反过来则生效）；② `nhs_text.xml` 把 `LOC_CITY_NAME_SHEN_DU` 的中英文案用 `<Replace>` 改成「雍城 / Yongcheng」——`UpdateText` 通道一定最后应用，这条是必杀，无论数据行在不在，玩家看到的都不会是神都。顺带覆盖武则天作为 AI 时的首都（她的 `CapitalName` 同为 SHEN_DU）；选「雍城」是因秦德公迁都于此、秦都近三百年，与整套秦郡名同源。**校验**：`verify_mod.py` 新增 11.2 节四条断言（SQL 补删语句存在 / 41 行 INSERT 里不得混入 SHEN_DU / 中英两处 Replace 存在且值分别为雍城与 Yongcheng），两脚本 0 错，version 21→22。

- **v7.23（奇观监听：从「发了」到「看得见」，2026-11-21）**：用户反馈「似乎还是只提示建成奇观而没有提示 AI 开始建造奇观」。**先看日志再动手**：`Logs/Lua.log` 里 `[NHS-Wonder] notified:` 出现 **10 次**，`turn scan: ai_cities=28 queue_readable=28` 一路正常——**功能其实一直在跑，问题是「发了但看不见 / 看不懂」**。逐个拆出四处哑巴故障：① **发送时机错**：绑的是 `GameEvents.OnGameTurnStarted`，而它对**每个文明**都触发（一场约 25 回合的局扫了 178 次），于是通知几乎都在 AI 行动阶段生成，玩家回合开始前它已躺在栏里；② **原版预留槽 `NOTIFICATION_USER_DEFINED_1` 的 DB 行写死 `ExpiresEndOfTurn=True`**（`Notifications.xml:52-60`）→ 当回合结束即被清除，且 `Icon` 列为空、九个槽是全 mod 公共资源，堆叠时互相淹没；③ **文明名全是「?」**：`Players[i]:GetCivilizationShortDescription()` 这个方法在 gameplay 侧**不存在**（正确位置是 `PlayerConfigurations[i]`，见 `DiplomacyActionView.lua:542`），`pcall` 把错误吞成 false，于是十条通知全是「?已在LOC_CITY_NAME_TOKYO动工兴建…」；④ **城市名没本地化**：AI 城市的 `City:GetName()` 返回 LOC key，必须再过 `Locale.Lookup`；⑤ 英文正文占位符顺序与传参相反（`{2_WonderName}` 写在 `{3_CityName}` 前），英文会读成「has begun building <城> in <奇观>」。**修法**：改用**自建通知类型** `NOTIFICATION_NHS_WONDER_STARTED`（新文件 `data/nhs_notifications.xml`），照 DLC 两步注册 —— `<Types><Row Type=... Kind="KIND_NOTIFICATION"/>`（**少了这一步 Lua 里枚举是 nil**，见 `DLC/Babylon/Data/Babylon_Heroes_MODE.xml:104-105`）+ `<Notifications><Row .../>`（:820）；列值定为 `ExpiresEndOfTurn=False` + `ExpiresEndOfNextTurn=True`（先例 `Notifications.xml:146-150` 的 NETWORK 组）、`GroupType` 写自己的类型名独占一组（**原版把 GroupType 当任意字符串当分组键**，`Notifications.xml:163` 即 `GroupType="NOTIFICATION_TECH_DISCOVERED"`，库里没有 NotificationGroups 表；不要写 "USER"，那是九个预留槽共用的组）、`VisibleInUI` / `ShowIconSinglePlayer` 必须 True（为假则通知栏不生成条目＝完全看不见）。图标按原版回退链 `"ICON_"..类型名` 提供 `ICON_NOTIFICATION_NHS_WONDER_STARTED` → `ICON_ATLAS_NOTIFICATIONS` Index 57（= `ICON_NOTIFICATION_WONDER_COMPLETED` 那张奇观图，一眼认得出是奇观）；旧的 `USER_DEFINED_1` 映射保留作退路。**另外两处 API 名字是查出来的、不是猜的**：`Game.GetGameTurn()` 在游戏自带几百个 Lua 脚本里**一次都没出现**，正解是 `Game.GetCurrentGameTurn()`；`PlayerTurnActivated` 的官方写法是 `Events.PlayerTurnActivated`（`Scenarios/Tutorial/Tutorial.lua:119`），gameplay 侧未必有同名 `GameEvents` 事件，故两条都试、谁存在用谁。触发改为「本地玩家回合激活」为主 + `OnGameTurnStarted` 兜底（后者用 `Players[me]:IsTurnActive()` 判是否轮到自己，取不到该 API 就不设门槛直接扫）。去重前缀从 `NHS_WS_` 改成 **`NHS_WS2_`**：旧标记已写进存档，不换前缀的话同一存档里永远等不到新通知（正好会让人误判功能仍坏）。**校验**：`verify_mod.py` 第 12 节从 9 条扩到 18 条，重点新增「自建类型三件齐（Types/Notifications/图标）」「四个列值逐项核对」「发送成功才 MarkNotified」「禁止 `Players[...]:GetCivilizationShortDescription`」「城市名必须过 Locale.Lookup」「禁止 `Game.GetGameTurn()`」「两种回合事件都试」等断言。两脚本 0 错，version 22→23。

- **v7.24（农场加信仰 + 冻土加信仰失效根因 + 通知常驻，2026-11-21）**：三条需求一起处理，其中前两条的"没生效"根因都不在数值上。

  **(0) 最重要的先决判断：用户这一轮看到的现象全部来自一个 v19 时代的旧会话。** 证据三处：① `Logs/` 目录建立于 12:43，`Lua.log` 的四次 `loaded` 都没有 v7.23 才有的 `(notify type = ...)` 后缀；② `Modding.log` 里组件顺序是 `NHS_DB_UNITS → NHS_WONDER_WATCH`，**没有 `NHS_DB_NOTIFICATIONS`**（v7.23 才加），`DebugGameplay.sqlite` 的 `Types` 里也确实查不到 `NOTIFICATION_NHS_WONDER_STARTED`；③ 实机库里 `UNIT_NHS_RUISHI` **一条 TypeTags 都没有**（v20 才加）、`NHS_BL_WORK_ETHIC_*` 不存在。**结论：v20~v23 的改动当时一条都没进游戏，必须完全退出并重启**。教训：用户报"功能没生效"时，先比对"日志/运行库的新旧特征"与"工作区版本"，能避免在错误前提上改代码。

  **(1) 通知「未知文明 + 只显示一回合」**：前者是 v7.23 已修但未生效（旧会话），后者本次再修——v7.23 写的是 `ExpiresEndOfNextTurn="True"`（只留到下一回合末），实测观感仍是"一闪就没"，**改为 `False`（与 `NOTIFICATION_WONDER_COMPLETED` 完全一致：EndOfTurn=0 / EndOfNext=0，常驻直到玩家自己点掉）**。同时把 `CivName()` 加两道兜底：结果若仍是 `LOC_` 开头视为失败 → 退到 `PlayerConfigurations[i]:GetCivilizationTypeName()` + `GameInfo.Civilizations[].ShortName` → 最后 `LOC_NHS_UNKNOWN_CIV`（中「他国」/英「Another civilization」）。依据：`PlayerConfigurations` 的这些取值是**本地化键**，原版一律外面再套 `Locale.Lookup`（`DiplomacyActionView.lua:542`、`MinimapPanel.lua:900`）。

  **(2) 农场 → 圣地 +1 信仰**：**不自创 ModifierType**，直接抄原版成例 `THEODORA_HOLY_SITE_ADJACENCY_FARM`（拜占庭狄奥多拉）——`MODIFIER_PLAYER_CITIES_IMPROVEMENT_ADJACENCY`（= `COLLECTION_PLAYER_CITIES` + `EFFECT_IMPROVEMENT_ADJACENCY`），参数 `Amount 1 / DistrictType DISTRICT_HOLY_SITE / ImprovementType IMPROVEMENT_FARM / YieldType YIELD_FAITH`，只把 `Description` 换成本 mod 的 `LOC_NHS_DISTRICT_FARM_FAITH`（原版那个 tag 在 `DebugLocalization` 里查不到文本）。写在 `nhs_01_core.sql` 新增第 4c 节并挂核心特性。**刻意不用 `COLLECTION_ALL_CITIES`**：原版库里 35 条同类用法**全部**挂了 SubjectRequirement（如极光之舞的 `CITY_FOLLOWS_PANTHEON`），不带门槛极可能把信仰发给 AI；`PLAYER_CITIES` 收集器天生只收自己的城市。校验里加了一条"与原版狄奥多拉那条逐项相同（`TilesRequired` 缺省按 1 归一化）"的对账。

  **(3) 勤则不匮「冻土加信仰」不生效——与有没有选极光之舞无关**：我们从来不是给玩家挂信条，而是把信条的 Modifier 克隆到 trait 上。真因是克隆体原样继承了 `SubjectRequirementSetId = CITY_FOLLOWS_PANTHEON_REQUIREMENTS`，**没立万神殿时判定为假，整条静默失效**（不报错）。而门槛又不能一删了事：原版正是靠它把 `COLLECTION_ALL_CITIES`（全世界城市）收回到自己的城市。**改法**：`nhs_06_beliefs.sql` 新增第 1b 节，把两条 Aurora 克隆体的 `ModifierType` 改成原版现成的 `MODIFIER_PLAYER_CITIES_TERRAIN_ADJACENCY`（印尼「香料群岛」35 条同款写法，全部不带 SubjectRequirement）并把门槛置空 → 开局即有，与你选不选万神殿无关。**副作用（刻意接受并写进文案）**：若你自己又选极光之舞作万神殿，会叠成相邻冻土 +2。

  **顺带修掉两个校验器自身的坑**：① `build_game_db.py` 的 `GAME` 还是旧的 `D:\Program Files (x86)\...`（本机实际在 `D:\SteamLibrary\...`），且 `LOAD_ORDER` 只列了 Base + Indonesia_Khmer + 两个资料片，**漏掉 Byzantium_Gaul 等 30 多个 DLC**，导致 `MODIFIER_PLAYER_CITIES_IMPROVEMENT_ADJACENCY` 这种"某 DLC 才引入"的原版类型在验证库里查无此人（实机明明有）；现改为扫全部 `DLC/*/Data`、资料片固定排最后，`CIV6_DIR` 可覆盖路径，`DynamicModifiers` 866 → 995。② 建库时列名裸写 `Index` 撞 SQLite 关键字（`near "Index": syntax error`），2213 条行级错误里绝大多数是这个；列名统一加引号后降到 64 条。③ `run_mod_sql.py` 原来只断言「NHS_BL_ 前缀条数 > 0」，**独独漏了职业道德**（v19 的实机库里它确实整条不见了，而 `INSERT OR IGNORE ... SELECT` 是静默的，一行没插也不报错），现补"克隆体落地 + 参数完整 + 门槛仍为 WORK_ETHIC_ADJACENCY_PRODUCTION_REQUIREMENTS"三条。

  **校验**：`verify_mod.py` 新增 5d（农场四要素 + 挂载）、5e（极光之舞改写的 UPDATE + 禁止残留 `MODIFIER_ALL_CITIES_TERRAIN_ADJACENCY`）、14（`LOC_NHS_DISTRICT_FARM_FAITH` 中英齐备 + `{1_num}` 占位 + 主描述里出现「农场相邻」）；`run_mod_sql.py` 新增 20 余条断言（农场/冻土/职业道德）。两脚本 **0 错**（仍为原有 2 条刻意保留的权衡警告），version 23→24，安装目录 19 文件逐字节一致。**待实机确认**：① 通知标题「奇观动工」、正文是完整文明名与城市名、且不再自动消失；② 圣地相邻农场后信仰 +1（圣地面板相邻加成里会多一行）；③ 无需万神殿即有冻土信仰。

- **v7.25（开局出生地形偏置：冻土 / 河流 / 平原，2026-11-21）**：用户要求「开始新游戏选秦始皇时，出生地形关联到冻土、河流、平原」。**先读源码再写数据**：出生点由 `Base/Assets/Maps/Utility/AssignStartingPlots.lua` 在地图生成期分配，`__InitStartBias`（:1122）按 `Tier` 分轮处理，同轮内固定按 Resources → Features → Terrains → Rivers 执行；`__StartBiasTerrains`（:1616）把**同一 Tier 的所有地形并成一个集合**，统计每个候选点 `range=3` 内命中格数——注意循环写作 `for dx = -range, range-1`，实际窗口是 **6×6 方块（36 格）而非圆形 3 环**——命中数 >1 个候选时按格数**降序**排序（`__SortByArray` 取 `greatestValue`），只有恰好 1 个候选符合才锁定；`__StartBiasRivers`（:1536）在地形之后执行，先 `range=1` 贴河、无则放宽到 `range=3`，**一旦存在靠河候选就只保留靠河的（硬筛）**；任何一环无符合项时函数直接返回、不惩罚。据此新增 `mod/sql/nhs_15_start_bias.sql`：`StartBiasTerrains` 四行（`TERRAIN_TUNDRA` / `TERRAIN_TUNDRA_HILLS` / `TERRAIN_PLAINS` / `TERRAIN_PLAINS_HILLS`，**同为 Tier 1**）+ `StartBiasRivers` 一行（Tier 1）。**三条硬约束的理由**：① 冻土与平原必须同 Tier，分轮会让后一轮被前一轮的候选收敛架空；② 丘陵变体必须单列（统计只认完全相同的字符串，漏了则整片丘陵不计分）；③ 河流必须与地形同 Tier（Rivers 排在 Terrains 之后才有"再筛"的意义）。**两个必须如实说明的边界**：**其一**，`StartBias*` 四张表主键里**只有 `CivilizationType`、没有 `LeaderType`**（实测 PRAGMA），所以无法只对秦始皇或只对人类玩家生效——按文明生效，中国各领袖（含 AI）都有；**其二**，`TERRAIN_TUNDRA` 与 `TERRAIN_PLAINS` 是互斥地形，同一格不能既是冻土又是平原，"三者关联"的真实含义是"出生点是其一、窗口内两种都多、且靠河"。
  **仿真取证**：新增 `tools/sim_start_bias.py`，把三段算法按源码逐行移植（含 6×6 窗口偏移、降序排序、Rivers 降级与硬筛），在 20×12 人造地图上跑四场景——A 交界带满分胜出 / B 无冻土退到平原 / C 全图无河不惩罚 / D 全无冻土平原时仅河流生效，四项全绿。**仿真同时纠正了一个此前的判断**：纯冻土点与纯平原点在带足够宽时**同样满分**，即冻土与平原在打分上**平权**，谁胜出取决于候选原始顺序——所以这条偏置的真实保证是"不落沙漠/雪地/纯草原，且尽量靠河"，**不是**"一定落冻土"。想要冻土绝对优先的改法（把平原两行改 Tier 2）与代价（冻土只在极地边缘时会被扔去极地）写在 SQL 文件末尾的调参旋钮里。
  **校验**：`verify_mod.py` 新增第 15 节 11 条断言（禁 `LeaderType` / 两表都写 / 四地形齐 / Tier 全为 1 / 河流 Tier 与地形同轮 / modinfo 已装载），`KNOWN_TABLES` 补两表；`run_mod_sql.py` 新增 5 条断言（四地形齐备 / Tier 统一 / 河流一行且同轮 / 地形名真实存在于 `Terrains` 表 / 重复加载幂等）——最后一条防的是"地形名写错不报错、只是永远不计分"。两脚本 **0 错**（仍为原有 2 条刻意保留的权衡警告），version 24→25，安装目录 20 文件逐字节一致。**生效条件**：仅新开局的地图生成阶段；读档不会重新分配出生点。



- **v7.26（文明6 假死诊断 + 通知类型真实机制更正 + 图标槽撞名，2026-11-21）**：用户报"文明6假死"。查 `dumps/C345C409D29E786116/`（有完整 crash dump + 三份日志附件）。

  **(0) 崩溃根因不在本 mod，是引擎渲染资源表打满。** 证据在同秒：① `Renderer.log` 15:13:14 一秒内 27 条 `Error: ResourceList.AddResource(), attempting to add more than 8192 items.`；② 同秒 `Unable to locate appropriate Pipeline State Object. SP: 21 SM: 0 Vertex Format: 64 Topology: 3`；③ `header.json` 15:13:15 `EXCEPTION_ACCESS_VIOLATION / Error reading address 0xCC`（0xCC 是 MSVC 未初始化内存填充值），调用栈顶在 `CivilizationVI_DX12.exe`、穿过 `D3D12Core.dll`，dump 模块表含 `IconCodecService.dll`。即：资源槽耗尽 → 新建纹理拿空句柄 → 解引用 → 崩。**不是 Lua 逻辑错，不是 SQL 错，也不是显存不足**（日志无 `device removed` / `OutOfMemory` / `DXGI_ERROR`；RTX 3080 Ti / 32G）。触发条件是"长局 + 重资产 mod 堆叠"：本局 **265 回合**（崩溃前刚生成 `AutoSave_0265`）、**32 个工坊订阅**、全 DLC —— 社区实测原版全 DLC 本身已有约 6869 个 XLP 条目，8192 是硬上限。本 mod 只加 2 个单位（美术复用原版）+16 条图标映射，`Lua.log` 里 194 条 `Runtime Error` **全部**来自工坊 `3516350860`（Agronomist 农学家，每回合刷 181 次）。**修法**：装 Assets Limit Fix（把各资源表提到 65535）。⚠ 本轮发现它**只是订阅、从未启用**：`Modding.log` 里搜 `3806322238` 命中 0 次，`DatabaseDLL_FinalRelease.dll` 仍是 11/20 22:21 的原版、且没有 `_Orig` 备份 → 需在模组界面勾选启用 → 开一局（进地图）→ **重启游戏**才完成安装。

  **(1) 「通知只显示一回合」的真正病因：自建通知类型从未生效。** v7.23/v7.24 的前提是"`<Types>` 注册 `KIND_NOTIFICATION` → Lua 的 `NotificationTypes` 多一个键"，**实测不成立**。三条硬证据：① `Lua.log` 五次全是 `loaded (notify type = USER_DEFINED_1, ...)`，一路退回旧槽，而旧槽 `ExpiresEndOfTurn=1` —— 所以"只挂一回合"是必然；② 数据库侧其实全对，`DebugGameplay.sqlite` 里 `Types` 有 `NOTIFICATION_NHS_WONDER_STARTED`（`Hash=-911488681`，`KIND_NOTIFICATION`）、`Notifications` 行两个过期标志都是 0，即"数据对了、Lua 看不见"；③ 官方 DLC 自己也从不用自建类型——`DLC/BlackDeathScenario/Scripts/BlackDeathScenario_Support.lua:13-16` 四条通知全是 `USER_DEFINED_1~4`，工坊 32 个订阅里除本 mod 外零个文件出现 `KIND_NOTIFICATION`。**机制**：`NotificationTypes` 是启动早期按**基础库**固化的枚举，mod 后插的 `Types` 行不刷新它（Civ6 通则：mod 新类型只能 `GameInfo` 查、不能用枚举）。**修法**：三级解析 `ResolveNotifyType()` —— ① `NotificationTypes[去前缀名]` → ② `NotificationTypes[全名]` → ③ `GameInfo.Types[全名].Hash`（当前主路径，Hash 与枚举同属 32 位空间，如 `USER_DEFINED_1 = -1636606976`）；兜底从 `USER_DEFINED_1` 换成 **`WONDER_COMPLETED`**（原版 0/0 常驻、图标本就是奇观、UI handler 是 `MakeDefaultHandlers()` 只挂一条"他国建成奇观"音效，NotificationPanel.lua:190/260，无语义依赖）。`Notify()` 里加"pcall 抛错才用兜底重发"，避免双通知。

  **(2) 图标槽撞名。** `Database.log` 每周目一条 `UNIQUE constraint failed: IconDefinitions.Name, IconDefinitions.Atlas`，值是 `(ICON_NOTIFICATION_USER_DEFINED_1, ICON_ATLAS_NOTIFICATIONS, 4)`，来自工坊 `3810795757`（Civilization Assimilation）的 `Assimilation_Icons.xml` —— 我们 `nhs_icons.xml` 早先也登记了同一个名字（Index 3），`(Name, Atlas)` 是联合主键，谁先插谁赢，对方那行直接插不进去。本 mod 已不用该槽，**删掉该行**，让 Assimilation 的 Index 4 正常落库。

  **校验器同步纠正**：`verify_mod.py` 第 12.4 节原文写"生成 NotificationTypes 枚举"是错的，已改；12.4b 从"两槽都要有图标"改成"自建图标必须在、`ICON_NOTIFICATION_USER_DEFINED_1` 必须不在"；12.4c 新增"必须用 `GameInfo.Types` + 必须有 `WONDER_COMPLETED` 兜底 + 代码里不得残留 `USER_DEFINED_1`"。⚠ 这两条检查**必须用正则匹配真正的 `<Row>` / 剥掉注释后再看 Lua**，否则会被说明性注释误伤（又踩了一次"文本包含不可靠"的坑）。两脚本 **0 错**（仍为原有 2 条权衡警告），version 25→26，安装目录 20 文件逐字节一致。**实机确认点**：`Lua.log` 应出现 `loaded (notify type = Types.Hash, ...)`，且通知不再当回合消失。

  **同日补充（v7.27，实机日志又暴露一个更致命的问题）**：装好 Assets Limit Fix 后用户开新局跑到 34 回合。日志三处结果——**好消息**：`DLL` 替换成功（原版 931104 字节备份为 `DatabaseDLL_FinalRelease_Orig.dll`，新 `DatabaseDLL_FinalRelease.dll` 198656 字节，`Civ6AssetsLimitFix.log` 记 `install` → 后续两次 `up to date`）；`Database.log` 里 `IconDefinitions` 的 UNIQUE 冲突 **0 条**（此前每周目 1 条）；`Lua.log` 三次全是 `loaded (notify type = Types.Hash, ...)`，说明 Hash 那级解析走到了。**坏消息**：34 回合里 `Lua.log` **零条 scan 记录**，连「本地玩家无 TRAIT 跳过」都没有 —— 说明 `Scan` 压根没被调用，不是被 trait 门槛挡的。根因是 v7.23 引入的兜底逻辑：`OnGameTurnStarted` 在主入口绑定成功（`m_turnEvent ≠ "none"`）时**反而**要求 `Players[me]:IsTurnActive()` 为真；实测该值不给 true，而 `PlayerTurnActivated` 也没触发，两条路同时哑掉、一行日志不留。这正是「只提示建成、不提示动工」的真正病根，比通知类型那层更致命。**修法**：`OnGameTurnStarted` 改为无条件 `ScanOnce("OnGameTurnStarted")`，去重交给 `ScanOnce` 里既有的回合号闸门；`ScanOnce(sWhy)` 增加来源参数，前 3 次触发打印 `scan #n fired by <来源> at turn <t>`，`loaded` 行也加上 `fallback = OnGameTurnStarted/unconditional`。代价：该事件在 AI 回合开始也触发，AI 本回合生产可能未结算完，最快下一回合才看得到 —— 1 回合延迟换「一定扫得到」，值。version 26→27，两脚本 0 错，安装 20 文件一致。**新的实机确认点**：日志应出现 `scan #1 fired by ...`，若始终没有，说明两个事件都没绑上，需要换 `Events.OnGameTurnStarted` 再试。

- **v7.28（数值平衡：前期补启动、后期砍乘数，2026-11-21）**：实机测试通过后用户反馈「初期太弱，中后期圣地起来后又太强」。**诊断结论：不是数值高低，是曲线形状**，两条根因都要能算得出来才算说清：
  **(1) 前期弱是结构性的。** 八威仪里六条挂在「有圣地」或「已创教」之后——圣地要占星术 + 54 锤，创教要圣地上线后再攒大预言家，于是前 30~70 回合玩家实际只拿到 +1 宜居、首都 +1 信仰、冻土 +1 信仰 +1 产能、一格通配符。而 `nhs_15` 的出生偏置把人放在冻土带（冻土平地不能建农场，全场粮食最差的出生点之一）——**偏置制造了负项，却没有配套正项**。
  **(2) 后期强是复利结构。** 同一份「圣地相邻值」被兑现三次：来源放大（极光无条件 +1/冻土格、河流大相邻 +2、农场 +1、山脉标准）把相邻值从原版典型 3~4 抬到 8~12（约 3 倍）→ 经文 ×2 再兑一次信仰 → 职业道德 1:1 再兑一次产能。**一份相邻值 = 信仰两次 + 产能一次**。
  **(3) 顺带查出一条隐藏产能轴（本轮最重要的发现）。** 克隆 `BELIEF_WORK_ETHIC` 时把**两条** Modifier 都带进来了：`WORK_ETHIC_ADJACENCY_PRODUCTION_2`（相邻转产能，GS 现行）+ `WORK_ETHIC_FOLLOWER_PRODUCTION`（→ 原版 `WORK_ETHIC_FOLLOWER_PRODUCTION_MODIFIER` = `EFFECT_ADJUST_FOLLOWER_YIELD_MODIFIER` / Amount=1 / YIELD_PRODUCTION，即 **+1 产能/信徒**）。后者是 GS 改版没删干净的历史遗留行（`Base/Assets/Gameplay/Data/Beliefs.xml:483` 基础库 + `DLC/Expansion2/Data/Expansion2_Beliefs.xml:1145` 资料片各挂一次，基础库那行未删），我们照单全收，于是产能多了一条**随人口线性增长**的轴：10 城 × 12 人口 = +120 产能/回合，比相邻那条还大。另注：该 attach 用 `COLLECTION_ALL_CITIES` + `CITY_FOLLOWS_RELIGION_REQUIREMENTS`，**信奉你宗教的 AI 城也会拿到**（原版固有行为，非本 mod bug）。
  **手术方案（新建 `mod/sql/nhs_16_tuning.sql` 作"平衡旋钮总表"）**：一、`MODIFIER_PLAYER_CITIES_ADJUST_DISTRICT_PRODUCTION` + `DistrictType=DISTRICT_HOLY_SITE` + Amount=50 → 圣地建造 +50%（54 锤按 36 锤结算），引擎早 6~8 回合上线；**Amount 是百分比的铁证**是政策「天空与星辰」`POLICY_SKY_AND_STARS` 同型同 Amount=30，葡/法文本均写「+30% 太空港与机场产能」（`DLC/Byzantium_Gaul/Text/..._Translations_Text_MODE.xml:247 / :585`）。二、首都 +2 食物、三、首都 +1 产能（均走 `MODIFIER_PLAYER_CAPITAL_CITY_ADJUST_CITY_YIELD_CHANGE`，与既有 `NHS_CAPITAL_FAITH` 同构；原版用例 `PHARAOH_FOOD`/`PHARAOH_PRODUCTION` Amount=2、`MONARCHY_PRODUCTION` Amount=1）；**重量放在食物上**是因为冻土城瓶颈是粮食不是锤子（冻土丘 1 食 1 锤、冻土平 1 食 0 锤且不能建农场），产能给到 +2 会与圣地 +50% 同向叠加成"第 6 回合圣地就出来"。四、经文由 100% 降到 50%（`UPDATE ModifierArguments SET Value='50' WHERE ModifierId LIKE 'NHS_PL_SCRIPTURE%' AND Name='Amount'`）——砍的是唯一那个"免费乘 2"，且它不占政策位。另在 `nhs_09_wonder_era.sql` 把 `UnitCommands.MaxEra` 由 9 收到 **3（到中世纪）**：30% × 4 次（中国建造者 +1）= 120%，**一个建造者直接包圆任意奇观**，且奇观造价远古→信息涨约 5 倍而建造者只涨约 2 倍，越晚越离谱；只收时代不动幅度，是因为 30% 是玩家看得见的手感、时代上限才让后期失衡。**「去掉每信徒 +1 产能」默认写成注释块**（三行 DELETE，顺序必须 关联表→参数→主表），留给用户当第二把刀，无需重开新局即可启用。
  **同时纠正两处会误导自己的断言**：`run_mod_sql.py` 原断言 `MaxEra >= 8`（越大越好），现在收紧时代本身就是设计，改为 `== 3`；`verify_mod.py` 原把 `MaxEra >= 8` 判为 info，改为 warn 并说明"会让一个建造者 4 次包圆任意奇观"。**新踩的坑**：`verify_mod.py` 里的 `raw{}` 只装了 `SQL_FILES`，用 `raw.get(TEXT_FILE)` 恒为空串，导致三条"文案↔数值对账"断言全部误报"文案未改"——改为单独读盘。
  **校验**：`verify_mod.py` 新增第 16 节 15 条（含**执行序检查**：`nhs_16` 必须排在 `nhs_06` 之后，否则 UPDATE 命中 0 行且不报错——这正是本项目踩过的"静默丢行"同类坑；以及文案↔数值对账）；`run_mod_sql.py` 新增 19 条落地断言（逐项查参数，不只数条数：三条新 Modifier 的类型/参数/门槛/挂载 + 经文克隆体仍在但 Amount 已变 50）。两脚本 **0 错**（仍为原有 2 条权衡警告），version 27→28，安装目录 **21** 文件逐字节一致。**生效条件**：四条改动均读档即生效（新增行 + UPDATE 已克隆参数），不需要重开；唯 `MaxEra` 改的是加载期数据，若存档已在文艺复兴之后，本局看不到变化。

- **v7.29（首都产能 1 → 2，2026-11-21）**：用户看完方案后确认「主要需要首都加产能食物帮助我顶过前期」，并进一步要求把产能直接给 2。**这是对 v7.28 自身判断的一处更正**：v7.28 担心「产能 +2 会与圣地 +50% 同向叠加成第 6 回合圣地就出来」，重算后该担心不成立——首都开局约 3 锤，+2 后 5 锤，圣地 54 锤经 50% 加速按 36 锤结算，36/5 ≈ **7 回合**，不是 6；而且这笔账只在首都成立，分城没有这条加成，前期扩张节奏不受影响。真正会失控的是"食物 +3 以上"（拉动人口导致宜居度红脸，`nhs_13` 只补到刚好够用），所以**只动产能、不动食物**。
  **改动落点**：`nhs_16_tuning.sql` 第三节 `NHS_CAPITAL_PROD` 的 `Amount` 由 `'1'` 改 `'2'`；同文件三处说明性文字同步（头部旋钮清单、`【数值口径】`整段重写为"食物 2、产能 2"并给出 3 锤→5 锤的推导、文末速查把"由 1 改 2"改为"由 2 再提到 3"）；`nhs_text.xml` 中英文主描述 `+1 产能` → `+2 产能`；`modinfo` 的 `<Description>` 同步；version 28→29。
  **校验加强**：`run_mod_sql.py` 的期望值表 `NHS_CAPITAL_PROD.Amount` 由 `"1"` 改 `"2"`（不改正则会直接报错，这是好事）；`verify_mod.py` 第 16 节新增两条——① 文案必须出现 `+2 产能`/`+2 Production`（数值改了但说明没改属同类静默错误），② 用正则 `NHS_CAPITAL_PROD'\s*,\s*'Amount'\s*,\s*'(-?\d+)'` 在**已剥注释**的 SQL 上取实际值并断言等于 2。两脚本 **0 错**，安装目录 **21** 文件一致。三条新增加成均为 `INSERT OR IGNORE` 新建行，**读档即生效**，不需要重开新局。

- **v7.30（冻土农场：克隆加拿大劳雷尔全套，2026-11-21）**：用户问「可以在冻土建农场的是什么特征」，查库确认答案唯一——**加拿大领袖劳雷尔的领袖特性 `TRAIT_LEADER_LAST_BEST_WEST`**（The Last Best West，挂 `LEADER_LAURIER`，GS 内容）。原文（`DLC/Expansion2/Text/en_US/Expansion2_ConfigText.xml:149`）：冻土可建农场；**解锁 Civil Engineering 后**冻土丘陵也可建；雪原/冻土（含丘陵）上矿场与伐木场 +2 产能、营地与农场 +2 食物、战略资源累积 +100%、买地便宜 50%。**注意 Civil Engineering 是市政**（`CIVIC_CIVIL_ENGINEERING`，`EraType=ERA_INDUSTRIAL`，Cost=920），不是科技——按科技找会一条都查不到。
  **机制（本轮最关键的一条，值得单独记住）**：农场的地形白名单 `Improvement_ValidTerrains` 只有 4 行（GRASS/GRASS_HILLS/PLAINS/PLAINS_HILLS）。想放开冻土，**绝不能往这张表插行**——它是全局静态表，一插所有文明（含 AI）立即生效，直接违背本 mod「只对秦始皇生效」的硬约束。原版的正确做法是 `MODIFIER_PLAYER_CITIES_ADJUST_IMPROVEMENT_VALID_TERRAIN`（=`EFFECT_ADJUST_IMPROVEMENT_VALID_TERRAIN`，`COLLECTION_PLAYER_CITIES`，参数 `ImprovementType` + `TerrainType`）；**全库只有 2 个 Modifier 用这个 Effect**，正是加拿大的 `TUNDRA_FARMS` 与 `TUNDRA_HILLS_FARMS`（后者挂 `SubjectRequirementSetId=PLAYER_HAS_CIVIL_ENGINEERING`，该 requirement set = `REQUIREMENT_PLAYER_HAS_CIVIC` + `CIVIC_CIVIL_ENGINEERING`）。因为是 Modifier，才能被 Trait 门控、才能挂人类门槛。
  **实现（用户选「照抄加拿大全套」）**：新建 `mod/sql/nhs_17_last_best_west.sql`，沿用 `nhs_04` 的克隆套路——`INSERT OR IGNORE INTO Modifiers ... SELECT 'NHS_LBW_'||m.ModifierId, m.ModifierType, 'PLAYER_IS_HUMAN', m.SubjectRequirementSetId FROM Modifiers m JOIN TraitModifiers tm ...`，再克隆 `ModifierArguments`，最后挂到 **`TRAIT_NHS_MOTHER_RUSSIA`（披荆斩棘，冻土那条威仪）**，不新增第九个 trait。实测克隆 **26 条 Modifier / 52 条参数**（tundra 14 + snow 12）。**必须排在 `nhs_04` 之后**——挂载目标 trait 是 nhs_04 建的，排前面外键失败会被 `OR IGNORE` 静默吞掉。
  **反向断言（这层的核心价值）**：`verify_mod.py` 新增第 17 节 8 条，其中第 ⑤ 条是**反向**的——一旦检测到 `INSERT/UPDATE Improvement_ValidTerrains` 就报错；`run_mod_sql.py` 新增第 6c 节 8 条，含「克隆数与源数相等」「参数数与源数相等」（防 `INSERT OR IGNORE ... SELECT` 静默丢行）、「26 条全挂到披荆斩棘」「全局表仍为 4 地形」「丘陵保留土木工程门槛」。另验证 17 个 `SubjectRequirementSetId` 全部在 `RequirementSets` 里存在、`TerrainType` 参数全部合法（无悬空外键）。两脚本 **0 错**，version 29→30，安装目录 **22** 文件一致。文案同步：`LOC_TRAIT_NHS_MR_DESC` 中英（写明可建农场与各项 +2）、modinfo `<Description>` 二曰披荆斩棘。
  **实机看点**：建造者站在冻土平地上，建造菜单里应出现「农场」；冻土丘陵要等土木工程（工业时代市政）。**注意：这里原先写的"读档即生效"是错的，见 v7.31。**

- **v7.31（加载假象：v7.28~v7.30 三个版本从未被游戏加载，2026-11-21）**：用户反馈「读档了但不能在冻土建农场」。查证结果不是 SQL 问题，是**文件从未被引擎读取**。
  **铁证链**：① `CivilizationVI_DX12` 进程启动时间 **21:54:30**（已连续运行 118 分钟）；② `nhs_16_tuning.sql` 写入 **22:36**、`nhs_17_last_best_west.sql` 与 `modinfo` 写入 **23:45**——全部晚于进程启动；③ `Modding.log` 里 `UpdateDatabase - Loading sql/nhs_15_start_bias.sql` 出现 **7 次**（每次启动一次，最近一次就在本次），而 `nhs_16` / `nhs_17` **零次**；④ `DebugGameplay.sqlite` 里 `NHS_LBW_%` **0 行**、`NHS_CAPITAL_PROD` **0 行**，但 `MaxEra=3`（v7.28 的 nhs_09 效果，因为 nhs_09 是老文件，21:54 启动时已加载）——同一个版本的两处改动一有一无，正好卡在「启动前 / 启动后」这条线上。
  **机制（本项目最隐蔽的一类失败，必须记死）**：Civ6 只在**进程启动**时解析一次 modinfo 的 `<InGameActions>` 并缓存动作列表。之后在游戏内**读档、回主菜单、重开新局**，都只是重放这份缓存，不会再读一次 modinfo。所以「改完文件 → 游戏内读档」在数据库层**永远不会生效**，而且 `Database.log`、`Lua.log`、外键校验（日志里 `Passed Validation`）**全都不报错**：文件、断言、离线库全绿，游戏里什么都不变。这与此前踩过的「静默丢行」「注释误判」属同一族：**没有任何一方会告警的失败**。
  **工具**：新增 `check_loaded.py`，读 `Modding.log` 切出最后一次启动的加载块，与 modinfo 声明的 `<InGameActions>` 文件清单对账，列出「缺失 / 已加载但已不再声明」。踩坑一处：脚本类动作的日志动词是 `GameplayScripts - Registering` 而非 `... - Loading`，第一版漏掉了 Lua 导致误报。已接入 `verify_mod.py` 第 18 节，只出 WARN（工作区文件本身没错，是游戏该重启了）。
  **正确验证流程（此后一律照此）**：完全退出游戏进程（不是回主菜单）→ 重新启动 → **新开一局**。数据库类改动读档不够，因为存档内已固化旧规则；只有纯 Lua 改动可以读档验证。`nhs_16`（圣地建造 +50%、首都 +2 食物 +2 产能、经文 50%）与 `nhs_17`（冻土农场全套）都属数据库层，必须新局。

- **v7.32（把版本号搬到 mod 管理器可见处，2026-11-21 / mod version 32）**：用户问「能否在游戏的 mod 管理器中看到版本号」。
  **查证结论：原生看不到。** `Base/Assets/UI/FrontEnd/Mods.lua:454` 是 `Controls.ModIdVersion:SetText(info.Id)`——控件名虽叫 `ModIdVersion`，实际写的是 **GUID**，`version` 属性压根不进 UI。详情面板可显示的字段只有：`Name`（标题）、`Id`（GUID）、`SourceFileName`、`Description`（优先，缺则退回 `Teaser`）、`Authors`、`SpecialThanks`、`Created`、`Ownership`、`AffectsSavedGames`、`SinglePlayer`、`Multiplayer`（`Mods.xml:90-135` 控件定义）。其中 `Created` 来自 `info.Created`（引擎读文件时间，**不是 modinfo 可配置字段**，写 `<Created>` 无效）。
  **做法**：把版本号同时写进 `<Name>`（`…（v32）`，mod 管理器列表行与详情标题都显示）和 `<Description>` 开头（`【v32 · 2026-11-21】`，详情面板显示）。这同时解决了 v7.31 那个问题——**版本号成了"游戏到底读没读到新文件"的可视化探针**：不重启就永远显示旧号。
  **防漂移断言**（`verify_mod.py` 第 1b 节 4 条）：标题与描述里的号必须等于 `version` 属性，且不许残留学号。已做**反向测试**：把标题临时改回 `（v30）`，脚本如期报 2 条错（"标题里没有 v32" + "残留旧版本号 v30"），退出码 1；测试后自动还原。
  **版本号对齐**：v7.31 那轮只动工具、没升 `version`（仍是 30），造成序号与属性错位；本轮直接对齐到 **32**，恢复历史惯例（v7.28=version 28 等）。22 文件一致，双校验 0 错。

- **v7.33（砍掉「每信徒 +1 产能」，2026-11-22 / mod version 33）**：用户判断「主要问题是前期太弱而后期肯定会很强」，决定现在就砍，不等实机试玩。
  **砍的是什么**：原版 `BELIEF_WORK_ETHIC` 下挂着**两条** Modifier——`WORK_ETHIC_ADJACENCY_PRODUCTION_2`（相邻信仰 → 等量产锤，`MODIFIER_ALL_DISTRICTS_ADJUST_YIELD_BASED_ON_ADJACENCY_BONUS`）与 `WORK_ETHIC_FOLLOWER_PRODUCTION`（每信徒 +1 产能，`MODIFIER_ALL_CITIES_ATTACH_MODIFIER`，指向 `WORK_ETHIC_FOLLOWER_PRODUCTION_MODIFIER`，即 `EFFECT_ADJUST_FOLLOWER_YIELD_MODIFIER` / Amount=1 / YIELD_PRODUCTION）。我们此前克隆信条时把两条照单全收，于是产能引擎多了一条**随人口线性增长、没有上限**的轴：10 城 × 12 人口 = +120 产能/回合，比相邻那条还大；而相邻那条被「城市能挨着几格好地形」锁死，不会失控。这是 GS 改版留下的历史遗留行，不是设计意图。
  **附带解决的泄漏**：那条 attach 的门槛是 `COLLECTION_ALL_CITIES` + `CITY_FOLLOWS_RELIGION_REQUIREMENTS`，所以**信奉你宗教的 AI 城市也会拿到 +1 产能/信徒**。砍掉后一并消失。
  **实现（双保险，互为兜底）**：① 源头——`nhs_06_beliefs.sql` 的克隆语句加 `AND m.ModifierId <> 'WORK_ETHIC_FOLLOWER_PRODUCTION'`，从根上不生成；② 兜底——`nhs_16_tuning.sql` 文末三行 `DELETE`（`TraitModifiers` → `ModifierArguments` → `Modifiers`，顺序不能反）由注释改为启用。有了 ①，②理论上是空操作；保留 ② 是因为加载顺序一旦被人改动（如 modinfo 里 `nhs_16` 被挪到 `nhs_06` 之前），只有 ② 还能在静态层提醒。
  **断言（4+3 条，全部做过反向测试）**：`verify_mod.py` 新增第 16b 节 5 条（克隆必须排除 / 相邻那条不许误删 / 三行 DELETE 必须**未注释**且顺序正确 / 文案必须说明已剔除）；`run_mod_sql.py` 在真实库上新增 3 条——`NHS_BL_WORK_ETHIC_FOLLOWER_PRODUCTION` 行数必须为 0、`TraitModifiers` 里不许留孤儿、**原版** `WORK_ETHIC_FOLLOWER_PRODUCTION` 行数必须仍为 1（证明 DELETE 条件没写宽）。反向测试：同时去掉排除条件 + 注释掉三行 DELETE 后，`verify_mod.py` 报 2 错、`run_mod_sql.py` 报 2 错（"仍然存在 1 条" + "外键残留"），还原后全绿。另外单独验证了只去掉排除条件时，兜底 DELETE 确实能救回来（`run_mod_sql` 仍 0 错）——这就是双保险的实际效果。
  **判断"有没有被注释"必须用剥注释后的文本**：本项目已在"文本包含会误伤注释"上踩过三次（`verify 12.4c` 的 `USER_DEFINED_1`、`nhs_16` 的 Amount、本次的 DELETE），一律先 `strip_comments` 再正则。
  **强度变化**：前期几乎无感（人口少、信条还没到手）；中期少 +5~15 产能/城；后期少 60~120 产能/回合，且不再随人口复利。圣地相邻那条保留，所以「选址好 → 有产能」的正反馈还在，只是不再白送。version 32→33，22 文件一致，双校验 0 错，旧版全量备份在 `backups/NuclearHolySite_v32_full/`（**不要放在游戏 Mods 目录下**：同 GUID 的两个 modinfo 会被扫成两个 mod）。
  **这项仍属数据库层，必须完全退出进程 → 重启 → 新开一局**；且 v32/v33 都尚未实机跑过。

- **v7.34（宜居度按城市数阶梯，2026-11-22 / mod version 34）**：用户反馈「宜居度中后期逐渐紧缺」。
  **根因不是给得少**。查库后确认原版有两条**硬扣**，都随城市数恶化、且没有任何 Modifier 能直接改：
  ① 城市数量惩罚：约每 2 座城，所有城市 −1 宜居（硬编码）；
  ② 奢侈品只供应 4 座城（`Resources.Happiness=4`，全库 35 种奢侈品里 32 种为 4，只有肉桂/丁香/香水为 6）——**第 5 座城起完全断供，是断崖不是缓坡**。
  两条叠加：4 城以内宽裕，第 5 座一落成，边远城净值直接掉一大截，之后每 2 城再 −1，一路滑向 −5（−30% 非食物产出、停止增长）。而 v33 只给固定 +2，等于把整条曲线抬高 2 格，越往后越不够——这正是「逐渐紧缺」的手感来源。
  **做法（用户选「档 2」）**：新建 **5 / 9 / 13 座城各 +1** 三档阶梯（叠加，上限 +3；加原有两条共 +5），**4 城以内完全不触发**，所以前期曲线一点不动。
  实现用现成零件：`REQUIREMENT_PLAYER_HAS_AT_LEAST_NUMBER_CITIES`（参数 `Amount`）+ 已在用的 `MODIFIER_PLAYER_CITIES_ADJUST_POLICY_AMENITY`。
  **组合 Set 是这轮的关键技巧**：`OwnerRequirementSetId` 只能给一个 Set，而这一层要同时满足「是人类」+「至少 N 城」，于是照原版 `PLAYER_IS_HIGH_DIFFICULTY_HUMAN` 的写法，把 `REQUIRES_PLAYER_IS_HUMAN` 与城市数 Requirement 放进同一个 `REQUIREMENTSET_TEST_ALL` Set。
  **因此两个校验器的「人类门槛」检查都必须放宽**：原来只认字面 `OwnerRequirementSetId='PLAYER_IS_HUMAN'`，现在改为「或指向一个**成员里真的含** `REQUIRES_PLAYER_IS_HUMAN` 的 Set」。放宽时特意**去查 Set 的成员行**而不是看名字里有没有 HUMAN——名字是人取的，改名就能假通过。
  **避开的两个陷阱**：① 不要改 `Resources.Happiness`（全局静态表，AI 也吃，违反硬约束）；`EFFECT_ADJUST_OWNED_LUXURY_EXTRA_AMENITIES` 在库里只有一个**没有 trait 挂载的孤儿行**（`TRAIT_OWNED_LUXURY_EXTRA_AMENITIES`，Amount=2），语义未被任何原版内容验证，不敢用。② 给娱乐区加宜居无效——只在建了娱乐区后生效，而最缺宜居的恰恰是没建娱乐区的边远新城。
  **断言（静态 17 条 + 落地 13 条，3 项反向测试）**：`verify_mod.py` 新增 5b2 节（阈值、判定类型、组合 Set 成员、挂载、文案同源）；`run_mod_sql.py` 在真实库上新增阶梯段（三个 Amount、三个 Set 成员集合、三个 Modifier 的 Set 与 Amount、三档挂载数）。
  **反向测试暴露了一个死断言**：第一版「不许带 Inverse」写成检查**行内有没有 "Inverse" 字样**——但列名写在 INSERT 的列清单里、不在 VALUES 行里，于是注入 `Inverse=1` 后断言仍然通过。改成解析列清单→定位 Inverse 的**值**之后，注入才如期报错。教训：**任何「反向」断言必须真做反向测试**，否则它只是装饰。
  另两个坑：`Amount` 不能用「匹配到名字后 200 字符窗口」查（三个 INSERT 块隔得太远，恒查不到）；`RequirementSetRequirements` 必须**合并所有该表的 INSERT 块**再比对成员（本 mod 在 nhs_01 里还有一条，用 `re.search` 取第一条会拿到它，导致「成员为空」误报 3 条）。
  **顺带修了 `check_loaded.py` 的一个盲点**：它原先只比对**文件名**，于是「以前加载过、这轮又改了内容」会显示 `[OK]`——v34 正撞上：`nhs_13` 改到 00:13，进程 21:54 就起来了，对账却是 OK。新增 `stale_files()`：文件 mtime 晚于 `Modding.log` mtime ≈「改完没再启动」，标记 `[过期]` 并让 `verify` 出 WARN。这是近似判据（touch 也会触发），所以只提示不下结论。
  version 33→34，22 文件一致，双校验 0 错（`run_mod_sql` 180 条 ✓、`verify` 209 条 ·、4 条 WARN 全是"该重启了"）。文案同步：`LOC_TRAIT_NHS_DESC`「疆域达 5、9、13 座城时各再 +1 宜居度（合计最多 +5）」+ modinfo 一曰天命玄鸟。

- **v7.35（建库顺序 LoadOrder —— 本轮最严重的一次静默失效，2026-11-22 / mod version 35）**
  不是新功能，是修一个**从 v7.27 起就一直存在、且双校验完全看不见**的结构性错误。
  **症状**：用户 00:31 那局，`check_loaded.py` 报 22 个文件全部加载，`Database.log` 零报错，离线 `run_mod_sql.py` 180 条全绿。但直接查游戏建出的 `DebugGameplay.sqlite`，NHS Modifier 只有 **35 条，离线库是 64 条**，差 29 条：
  | 缺失 | 条数 | 后果 |
  |---|---|---|
  | `NHS_LBW_*` | 26 | 冻土上仍然建不了农场（用户早就报过「读档了但还是不能建」，当时归因错了） |
  | `NHS_BL_WORK_ETHIC_ADJACENCY_PRODUCTION_2` | 1 | **「勤则不匮」的产能转化本体从未生效** |
  | `NHS_MK_*` | (2) | 不是缺失，是**离线基线多算了 2 条**（见下） |
  **根因是执行顺序，不是 SQL 写错**。官方资料片的建库组件带 `<Properties><LoadOrder>100</LoadOrder></Properties>`（`Expansion2Core` 甚至是 −100），而 modinfo 不写 LoadOrder 时取 **0**，即排在所有官方内容**之前**。实测时间线：我们 16 个 SQL 在 `4277314.849–871` 全部跑完，`Expansion1_Leaders_Major` 到 `4277314.977`、`Expansion2_Leaders.xml` 到 `4277315.370` 才插入。于是
  `INSERT OR IGNORE INTO Modifiers … SELECT … FROM TraitModifiers WHERE TraitType='TRAIT_LEADER_LAST_BEST_WEST'`
  命中 **0 行**——`INSERT…SELECT` 匹配不到源行时**不报错**，这就是全部线索都没有的原因。加拿大属 Expansion1、`BELIEF_WORK_ETHIC` 属 Expansion2，所以只有这两层受影响；俄罗斯母亲 / 希腊 / 罗马三部特性都在 base game，故 `NHS_MR_` 5 条、`NHS_WILDCARD_`、`NHS_ROAD_` 全部完好——**这个分布本身就是根因的旁证**。
  **离线库为什么永远发现不了**：`db/mod_test.sqlite` 是「全 DLC 先合并 → 再跑我们的 SQL」，源数据早就齐了。**这是本项目验证体系的最大盲区：离线验证只证明 SQL 正确，不证明它在游戏里能拿到源数据。**
  **修法**：给全部 17 个 UpdateDatabase 组件加 `<Properties><LoadOrder>500</LoadOrder></Properties>`。取 500 的依据是实测：官方最大 100，当前 16 个第三方 mod 用了 200/300/999/1000/5210/9999/10000/800000 等，**无人用 500**，既晚于官方又不插进别人的流程。同一 LoadOrder 下按 modinfo 声明顺序执行（已由日志 + 反向测试双重确认），所以 `nhs_01 → nhs_17` 的先后由排版保证。
  **`NHS_MK_` 那 2 条是误判，已纠正**：`TRAIT_HOLY_SITE_RIVER_FOOD` / `..._HOUSING` 在**离线合并库**里有、在**游戏库**里本就没有（游戏里叫 `TRAIT_HOLY_SITE_RIVER_2HOUSING`）。所以 `nhs_05` 一个字没改——它写的是 `JOIN TraitModifiers WHERE TraitType=…` 全量克隆，源有几条就克隆几条，这是正确写法。`run_mod_sql.py` 的修道院断言本来就是 `n_mk > 0` 而非写死 6，所以不受影响。**差点因为「离线有 6 条」去改 SQL，那会把一个好文件改坏。**
  **断言（`verify_mod.py` 新增第 19 节，全部做过反向测试）**：
  ① 静态：每个 UpdateDatabase 组件必须带 LoadOrder 且 > 100（官方最大值），并把组件声明顺序的依赖关系也查一遍（`NHS_DB_CORE` → `NHS_DB_LAST_BEST_WEST`，后者挂到前者的 `TRAIT_NHS_*`）。
  ② 实机：直接打开 `Cache/DebugGameplay.sqlite` 查克隆层条数——**这是本项目第一次让校验器去看游戏真正建出来的库**，而不是看离线代餐。
  反向测试三项：删掉 CORE 的 LoadOrder + 把 UNITS 改成 50 → 报 1 条 ERROR 且点名两个组件；把 `NHS_DB_LAST_BEST_WEST` 挪到 `NHS_DB_CORE` 之前 → 报 2 条 ERROR。**第二项还暴露了我自己写的报错文案说反了**（原文写「排在 X 之后，但后者依赖它」，实际是「排在 X 之前」），已修正——文案说反比不报更糟，会把人引向错误的排查方向。
  **`check_loaded.py` 补上第二个盲点**：它原先只查 `declared_files()`（modinfo 声明的内容），**不查 modinfo 自身**。而 v35 的改动全在 modinfo 里，它却照样报「全部已加载，且没有改动早于最后一次启动的文件」——恰恰是**最需要重启**的那类改动被漏掉了。现在 modinfo 排在文件列表第一行单独显示 `[OK]/[过期]`，并在过期提示里说明它的特殊危害。同样做了反向测试：把 mtime 调早到 log 之前 → 显示 `[OK]` 且退出码 0；恢复 → `[过期]` 且退出码 1。
  version 34→35，22 文件一致（只有 modinfo 变），`run_mod_sql` 180 条 ✓、`verify` 216 条 ·、4 条 WARN（2 条刻意保留 + 2 条"该重启了"，其中一条正是实机库缺 `NHS_LBW_`，即**校验器现在会自己喊出这个问题**）。
  **必须完全退出进程 → 重启 → 新开一局**（本次改的是执行顺序，读档绝对无效）。验收判据：重开后 `python verify_mod.py` 第 19 节应变成「实机库三个克隆层均完整，LoadOrder 生效」，且冻土上能建农场。

- **v7.36（奇观加速：全时代放开 + 后期幅度减半，2026-11-22 / mod version 36）**
  用户要「文艺复兴时代依然可以加速奇观，但进度由 30% 削减到 15%」。两个口径问清后定为：
  **时代全开（`MaxEra = -1`）+ 幅度两档（文艺复兴之前 30%、之后 15%）**。
  **做法**：`nhs_09` 把 `MaxEra` 由 3 改为 **-1**；`nhs_08` 新增第 1b 节——
  `REQUIREMENT_PLAYER_ERA_AT_LEAST` + **`Inverse=1`**（语义：尚未进入该时代），`EraType=ERA_RENAISSANCE`，
  与本层那 `+15%` 的 modifier 绑定（`OwnerRequirementSetId = NHS_RS_WONDER_BOOST`，`TEST_ALL` 合集
  `REQUIRES_PLAYER_IS_HUMAN` + 时代需求）→ 进文艺复兴后本层失效，只剩原版 15%。
  **为什么用 Inverse 而不是"文艺复兴后减 15"**：减法依赖"百分比累加接受负数"，若引擎单条 clamp(≥0) 就静默失效；
  且 Inverse 的失败方向更安全 —— 不生效时是全程 30%（回到 v7.28 手感），而不是掉到 0%。
  **`MaxEra` 填 -1 而不是 9 的依据**：该表 41 条指令全是 -1 且全时代可用（升级/晋升/唤醒…），即 -1 = 不限；
  9 在 `era <= MaxEra` 下等效，但新增时代会漏。
  **踩到的两个坑**：① `verify_mod.py` 原正则 `MaxEra\s*=\s*(\d+)` **抓不到负号**，改 `-1` 后会被误报成"没找到更新语句"，已改 `(-?\d+)`；
  ② 我一度以为 `RequirementArguments` 漏写 `Type` 会静默失效，查 schema 才发现该列 `DEFAULT "ARGTYPE_IDENTITY"`，
  漏写落库值相同 —— **原注释是错的，已改**，反向测试也换了真正的缺陷（写成 `ARGTYPE_NUMBER`）才抓到。
  **反向测试 4 组全部有效**：`Inverse 1→0`、`MaxEra -1→3`、`Type 写成 ARGTYPE_NUMBER`、`EraType 写成 ERA_INDUSTRIAL`、
  `Set 漏人类门槛`、`RequirementSets 漏建`，全部报 ✗ 且点名。**第一版反向测试本身写错了**（判据是"命中含 `[奇观]` 的行"，
  结果命中的全是 ✓ 通过行），已改成"是否出现 ✗ 行"重做。
  version 35→36，22 文件一致，`run_mod_sql` **185 条** ✓、`verify` 0 错（2 条 WARN = 1 条刻意保留的 AI 泄漏说明 + 1 条"4 个文件该重启了"）。
  **未验证（核心）**：`Inverse` 是否被引擎采纳 → 文艺复兴之后应只有 15%。若仍是 30%，按 `nhs_08` 第 1b 节兜底改减法。

- **v7.37（帝国规模：科技不再随人口等比膨胀，2026-11-22 / mod version 37）**
  用户要「加一个惩罚值，人口越多对科技的惩罚越多，形成相对平衡，不超越 AI 太多」。
  **先纠正了问题归因**：t300 实测科研为最强 AI 的 6.62 倍，但拆成 `城市数 2.33 × 每城 2.84 × 每人口 1.19`
  之后可见**每人口科研只高 19%**（1.92 对 1.13），真正拉开差距的是人口总量 2.49 倍。
  所以不砍任何乘数，只让「人口」这条轴自己收敛 —— 这与用户"科技×人口的系数"的判断一致。
  **做法**：新增 `nhs_18_tech_scaling.sql`，两条
  `MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_PER_POPULATION`（`COLLECTION_PLAYER_CITIES` +
  `EFFECT_ADJUST_CITY_YIELD_PER_POPULATION`）：基础档 **−0.25 科研/人**（全城），
  大城档 **−0.75 科研/人**（`SubjectRequirementSetId = NHS_REQS_CITY_POP_10`，即人口 ≥10），合计 −1.0/人。
  两条都挂 `PLAYER_IS_HUMAN` + `TRAIT_NHS_NUCLEAR_HOLY_SITE`，AI 科研节奏完全不变。
  **机制依据**：原版 **永乐** `YONGLE_SCIENCE_POPULATION` 就是同一个 modifier + 同一个"人口≥10"门槛，
  只是 `Amount` 为正（+1/人）；本层把符号取负。另有 `BARAYS_FAITH_POPULATION`(1)、`THEOCRACY_RELIGIOUS_PEOPLE`(.5)、
  `COMMUNISM_PRODUCTIVE_PEOPLE`(.6) 三个原版同型用例，说明 `Amount` 是普通数值。
  **为什么分两档而不是一条 "−1/人"**：单条线性会让 3 人口新城也按人均扣，新城科研只有 3~4 点，
  扣完接近 0，界面会出现"科研 0"的城；而真正要压的是人口几十的大城。两档叠加后
  小城 −0.25、大城 −1.0，天然形成"人口越多越重"的形状，且**惩罚随时间自动加重**
  （早期大城少 → 触发第二档的城少），不需要额外加时代门槛。
  **为什么复用 `REQUIREMENT_CITY_HAS_X_POPULATION` 而自建 Set**：原版 `STADIUM_10_POPULATION_REQUIREMENTS`
  与 `CITY_HAS_HIGH_POPULATION` 结构完全相同（一条该 Requirement、`Amount=10`、`TEST_ALL`），
  但名字分别叫"体育场""高人口"，挂在科研惩罚上会误导；自建 `NHS_REQ_CITY_POP_10` / `NHS_REQS_CITY_POP_10`。
  **不动文化/产能的理由**：同一份数据里文化 2.54 倍（每人口 0.46 倍）、产能 4.38 倍（每人口 0.79 倍），
  两者每人口都**低于** AI，不是乘数超模。给它们也加惩罚会把"人多"从"有成本"变成"纯负收益"，与冻土农场设定打架。
  **数值验算**（t300，172 人口 / 331 科研）：按 ≥10 人口城承载 50%/70%/85% 三个假设，
  总扣 108/133/153 → 科研 223/198/178，对玛雅(78) 的 **2.9/2.5/2.3 倍**（改前 6.6 倍）。
  目标定 2.5 倍而非 1 倍：科技存量 37 对 23 是既成事实，且「皇帝之威」的爽感是设计目标之一。
  旋钮在 `nhs_18` 文件头（温和 −0.15/−0.45、推荐 −0.25/−0.75、激进 −0.35/−1.05）。
  **反向测试各 6 组全部有效**（判据只认 ✗ 行）：负号丢失、数值漂移、扣错产出（YIELD_CULTURE）、
  Owner 门槛写错、漏挂大城档、混入 UPDATE —— `run_mod_sql` 与 `verify_mod` 两侧都逐组报 ✗ 且点名。
  version 36→37，**23 文件**逐字节一致，`run_mod_sql` **197 条** ✓、`verify` 236 条 0 错
  （3 条 WARN = 1 条刻意保留的 AI 泄漏说明 + 2 条"该重启了"）。
  **未验证（核心）**：原版六个同型用例 `Amount` 全为正数，**没有负数先例**，负值能否被引擎接受离线库看不出来。
  验收：读档后城市科研浮窗应出现负值来源，总科研降约 40%；若完全没变 → 按 `nhs_18` 末尾【兜底方案】换成负百分比。
  **→ 实机结果：完全没变（见 v7.38）。这一版整体作废。**

- **v7.38（帝国规模改走负百分比，2026-11-22 / mod version 38）**
  用户实机读档后报「仍然是 335.2」，与改前 334.9 只差两回合自然增长 —— v7.37 **零效果**。
  **诊断**：`Cache/DebugGameplay.sqlite` 里两条 modifier 的 `ModifierType`、`Amount` 字符串（`'-0.25'` / `'-0.75'`）、
  `TraitModifiers` 挂载、`NHS_REQS_CITY_POP_10` 门槛、`RequirementArguments` 全部正确落库，`Database.log` 无相关报错。
  落库全对而效果为零，唯一解释是 `EFFECT_ADJUST_CITY_YIELD_PER_POPULATION` 在引擎侧不接受负 `Amount`
  （大概率内部 `max(0, ...)`）。**这个结论离线库查不出来，只有实机能证明。**
  **做法**：整层换成 `MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER`（负百分比），三档叠加：
  `NHS_TECH_SCALE_L1` 全城 **−18%**；`L2` 人口≥10 **再 −20%**（累计 −38%）；`L3` 人口≥16 **再 −15%**（累计 −53%）。
  新增 `NHS_REQ_CITY_POP_16` / `NHS_REQS_CITY_POP_16`（与 ≥10 那条同构）。
  **机制依据（两条原版用例合起来正好覆盖全部三件事）**：
  ① `DECENTRALIZATION_HIGHPOP_GOLD` = 同一 modifier + `CITY_HAS_7_OR_MORE_POP_REQUIREMENTS` + `Amount=-15`
  →「人口 ≥N 的城市该类产出 −X%」原版就这么写；
  ② `TRAIT_SCIENCE_DECREASE`（巴比伦）= 同一 modifier + **挂 `TraitModifiers`** + `Amount=-50` → trait 挂负科研有先例；
  另 `PERSIA_PRODUCTION_PENALTY -100`、`MINOR_CIV_PRODUCTION_PENALTY -50`、`INQUISITION_SCIENCE_MODIFIER -15`
  说明负百分比是本 modifier 的常规用法，不像 v37 那样是「无先例推断」。
  **为什么是三档**：引擎没有「按人口给百分比」的修饰器（v37 已证明那条路走不通），只能分段。
  三档加和后仍保留「跨过 10 / 16 斜率再抬一档」的形状，避免「到 10 就封顶」。
  **数值验算**（t300，331 科研，会稽 21 人口单城 121.7 占全国 37%）：
  按 ≥16 承载 50%/35%/65% 三种假设 → 总科研 **195 / 207 / 184**，对玛雅(78) 的 2.4~2.7 倍（改前 6.6 倍）。
  **反向测试**：`run_mod_sql` **7/7**、`verify_mod` **8/8** 全部被抓（判据只认 ✗ 行）——
  负号丢失、扣错产出、Owner 门槛写 NULL、分档点写错（16→13）、漏挂 L3、单档漂移致累计变、退回 v37 旧写法。
  version 37→38，**23 文件**逐字节一致，`run_mod_sql` **201 条** ✓、`verify` **243 条** 0 错 2 警告。
  **本轮两次自我纠错**：
  ① `verify_mod` 抓 Modifiers 声明的正则只认 `'[A-Z_0-9]+'`，把 `NULL` 当成「少一条声明」，
     报错指向「三档缺一档」而不是「Owner 没写」—— 已改成显式接受 `NULL`，现在两层都点名 `Owner 门槛为 NULL`。
  ② 反向测试第 5 组判据又写成了另一句文案（实际被 GATE 检查先抓到），与 v7.37 是同一个错。
     **教训定死：判据必须照抄「实际输出的 ✗ 行」，不能凭印象写期望文案。**
  **未验证**：三档百分比是加和（−53%）还是相乘（−44.2%），以及引擎是否真的对 `ADJUST_CITY_YIELD_MODIFIER` 采纳负值。
  验收判据已写进 `nhs_18` 文件末尾，含「只降到 280 → 把 L2 从 −20 提到 −30」的具体补救。

- **v7.39（诊断脚本，2026-11-22）**：v7.37/v7.38 两轮「落库全对、实机零效果」，数据库层已无可查，
  改从运行时读数：`lua/nhs_info.lua` 挂 `AddGameplayScripts id="NHS_SCRIPT"`，脚本加载即无条件 `print` 一次，
  另绑 `GameEvents.OnGameTurnStarted`，输出 isHuman / leader / hasTrait / `GetTechs():GetScienceYield()` /
  逐城「名字+人口+`GetYield(YIELD_SCIENCE)`」/ 斥候与移民移动力。version 38→39。
  **这一版实机一行日志都没出，真实原因（与上一版的「UI 事件绑错」是两回事，别混为一谈）**：
  游戏进程 15:01 启动，而本文件 15:05 才写进 Mods 目录 —— `Lua.log` 里连 `loaded` 都没有，
  但 `Modding.log` 有 `GameplayScripts - Registering .../nhs_info.lua`。
  **教训：`Registering` 只说明进了注册表，不代表运行的是磁盘上的最新内容；改脚本必须完全退出进程再启动，
  并在标题栏确认版本号已是新值。**

- **v7.40（规模层换加算类，2026-11-22）**：用户回报会稽（21 人口）城市面板科研 **121.7，与 v38 改前完全相同**
  → 负百分比这条路也被否掉。**排障结论（不是猜的，是逐项比出来的）**：
  实机库 `Cache/DebugGameplay.sqlite` 里三条 `NHS_TECH_SCALE_*` 的 `ModifierType` / `Owner` / `Subject` /
  `Amount` / `TraitModifiers` 全部正确，`DynamicModifiers` 那行 `COLLECTION_PLAYER_CITIES +
  EFFECT_ADJUST_CITY_YIELD_MODIFIER` 也在，`Database.log` 无报错 —— 数据层无懈可击而效果为零。
  v37（`PER_POPULATION` 负值）与 v38（负百分比）**唯一的共同点是「乘算类 effect」**，
  而本 mod 里天天在生效的圣地加成用的是**加算类** `EFFECT_ADJUST_CITY_YIELD_CHANGE`
  （`NHS_MOD_CITY_YIELD`，`nhs_01_core.sql:88`），连「trait + `PLAYER_IS_HUMAN` + `COLLECTION_PLAYER_CITIES`」
  这套形状都一模一样，只差 effect。**所以整层换路：放弃一切百分比，改用加算类固定值削减。**
  三档：`L1` 全城 **−4 科研/回合**；`L2` 人口≥10 **再 −14**（累计 −18）；`L3` 人口≥16 **再 −32**（累计 −50）。
  **为什么不是等距**（如 −10/−20/−30）：必须保证任何一档都不会把小城科研压到 0 ——
  t300 实测 <10 人口的城市单城科研只有 6~13，第一档最多给 −4。
  **代价已写进文件头**：固定值不随城市科研增长自适应，t400 之后相对力度会衰减；
  若日后要跟上，唯一可行的补法是**再加更高的人口门槛（22/28）**，不是回头再试百分比。
  **校验器同步**（三层都改了，缺一层就会「改了等于没改」）：
  ① `run_mod_sql.py` 的期望从「−18/−20/−15 累计 53%」改为「−4/−14/−32 累计 50」，
  并新增断言「`NHS_MOD_CITY_YIELD` 的 `DynamicModifiers` 必须真是 `COLLECTION_PLAYER_CITIES +
  EFFECT_ADJUST_CITY_YIELD_CHANGE`」；
  ② `verify_mod.py` 同步期望，另加一条「`nhs_01` 里 `NHS_MOD_CITY_YIELD` 不许被改成乘算类」；
  ③ 原「拿原版库查 `_YMOD` 是否存在」的检查会误报自建类型，已改为只查要求类型与需求集。
  **反向测试 8/8 全抓**（判据照抄 ✗ 行）：负号写丢 → `✗ Amount 不符`；退回乘算类 → `✗ 修饰器类型不对`；
  L3 门槛挂错 → `✗ Subject 门槛为 NHS_REQS_CITY_POP_10`；累计漂移 → `✗ 累计削减为 −38，设计值 −50`；
  YieldType 写成文化 → `✗ YieldType 为 YIELD_CULTURE`；`nhs_01` 改成乘算 effect → `✗ 不再是 …+EFFECT_ADJUST_CITY_YIELD_CHANGE`；
  Owner 写 NULL → `✗ Owner 门槛不是 PLAYER_IS_HUMAN`；挂载整行删 → `✗ 只挂到 2 条`。
  version 39→40，**23 文件**逐字节一致，`run_mod_sql` **202 条** ✓、`verify` **243 条** 0 错 2 警告、`lua_check` 6/6。
  **待实机验证（判据已写进 `nhs_18` 文件末尾）**：会稽科研应从 121.7 变成 **71.7**，顶栏从 335 落到 **165~205**。
  **若仍是 121.7，则不要再换第四种 effect** —— 那说明问题不在 effect，而在「存档建立后新加的 CITY 层修正
  不被追溯」，唯一解法是**新开一局**验证。这条是留给下一轮的硬判据。

> ⚠ **上一条 v7.40 的结论已在 v7.42 被推翻**：不是「乘算类 effect 不被采纳」，
> 而是「这三轮都在老存档上测」。看下面的 v7.41 / v7.42 再动手，别按 v7.40 的思路去挑 effect。

- **v7.41（定位探针，2026-11-22）**：把三条 `NHS_TECH_SCALE_*` 的 `Amount` 全改成 **+20（正值）**，
  其余（`ModifierType` / `Owner` / `Subject` / `TraitModifiers`）一律不动——
  若是「引擎丢弃负值」，正值必然生效、科研暴涨。**实测逐城科研一分未动**：
  会稽（21 人口）`sci=121.76`，与改前完全相同；同一次 `Lua.log` 里
  `GameInfo.Modifiers[L1/L2/L3]` 三条全为 `true`，即「**库里有、身上没有**」。
  这一版同时修掉上一版诊断脚本的两个 `nil` 调用：`Game.GetTurn()` 不存在
  （正解 `Game.GetCurrentGameTurn()`）、`Player:HasTrait()` 不存在
  （改查 `PlayerConfigurations:GetLeaderTypeName()` + `GameInfo.LeaderTraits`）。
  结论：与 effect 类型无关、与符号无关，是**这条 modifier 根本没挂到玩家身上**。

- **v7.42（根因定论 + 回退百分比，2026-11-22）**：
  **根因**：Civ6 在**建局那一刻**把玩家已挂载的 trait modifier 集合写进存档；
  此后往 mod 里新增的 modifier 只会进游戏库（`GameInfo` 查得到），
  **不会追溯挂到已经在跑的存档上**。
  · 铁证 ①：v7.41 的 +20 探针（正值）零效果，而库里类型/参数/挂载全对。
  · 铁证 ②：反面对照——本 mod 的「移民 +2 移动」（`MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT`，
    同样 `PLAYER_IS_HUMAN`、同样挂 trait）在**同一存档里一直有效**（移民 6 移动），
    差别只有一个：那条 modifier 在该存档建立**之前**就已存在。
  · 这是 `HANDOFF.md` 第 7 条（改 SQL 层必须「完全退出进程 → 重启 → 新开一局」）本就写明的规矩，
    v37~v41 违反了它 → **v37/v38/v40 三轮的「零效果」结论一并作废**。
  **设计回退**：回到负百分比 `−18 / −20（人口≥10）/ −15（人口≥16）`，累计 **−53%**。
  理由：百分比自适应（科研涨了折扣自动跟上），且与巴比伦 `TRAIT_SCIENCE_DECREASE`
  （−50% 科研）、权力下放（−15%、人口≥7 门槛）**同形同 effect**，是原版在跑的东西；
  v40 的固定值（−4/−14/−32）是在「误判百分比无效」前提下的妥协，前提已推翻，弃用。
  **预期**：t300 数据下总科研 335 → 198~223（对最强 AI 的 2.5~2.9 倍，改前 6.6 倍）。
  **校验器三层同步**：`run_mod_sql.py`（`_YMOD` = 原版负百分比类型、`_tiers` = −18/−20/−15、`_CUM` = 53、
  `DynamicModifiers` 必须映射到 `EFFECT_ADJUST_CITY_YIELD_MODIFIER`）、
  `verify_mod.py`（`_TIERS` 同步、去掉探针开关、把「拿原版库查 `_YMOD`」的检查**加回来**——
  它现在又是原版类型了，这是唯一能抓「类型名拼错」的检查）、
  `nhs_text.xml` / `modinfo` 文案（「−18%/累计 −38%/累计 −53%」）。
  **反向测试 8/8 全抓**（判据只认 ✗ 行）：
  负号写丢 → `✗ Amount 不符（实际, 应为）：{'…L1': (18.0, -18)}`；
  退回 v40 加算类 → `✗ 修饰器类型不对`；L3 门槛挂错 → `✗ L3 的 Subject 门槛为 NHS_REQS_CITY_POP_10`；
  累计漂移（−20→−10）→ `✗ 三档累计折扣为 −43%；设计值 −53%`；
  YieldType 写成文化 → `✗ YieldType 为 YIELD_CULTURE`；Owner 写 NULL → `✗ Owner 门槛不是 PLAYER_IS_HUMAN`；
  挂载整行删 → `✗ 只挂到 2 条`；修饰器名拼错 → `✗ L1 的修饰器为 …_MODIFER`。
  **诊断脚本升级（`nhs_info.lua` v7.42）**：打印 ①`GameInfo` 里三条的真实 `ModifierType`
  ②`GetScienceYieldToolTip()` 的科研明细 ③人类逐城科研 ④**全玩家对照**（人类 + 每个 AI 的科研/城数）
  ⑤单位 `max` 移动力（列名是 `BaseMoves`，不是 `Moves`——上一版打出 `基础=nil` 就是这个原因）。
  ④ 是新增的关键项：新开局时 AI 首都是天然对照组，人类应比它低约 18%。
  version 41→42，**23 文件**逐字节一致，`run_mod_sql` **202 条** ✓、`verify` **243 条** 0 错 2 警告、
  `lua_check` 6/6、反向测试 **8/8**。
  **验收方式已改**：不能再拿 t303 老存档看（那里永远没有这条 modifier）。
  必须**完全退出 → 重启 → 新开一局**，前 3 回合看 `Lua.log` 的
  `[NHS-DIAG] 对照 · 全玩家科研`：人类首都与 AI 首都同为 1 人口、都只有宫殿 +2 科研，
  人类那一行应约 **1.64**、AI 仍 **2.00**。
  ⚠ 上面这个 1.64 / 2.00 的判据已在 v7.43 被更正（AI 有难度加成，人类必然更低；
    正确对照物是城邦，实测基础值 2.30 而非 2.00）。

- **v7.43（✅ 规模层实机验证通过，2026-11-22）**：用户新开一局（神级/马拉松）打了 4 回合，
  `Lua.log` 拿到决定性读数：
  · 人类首城（咸阳，pop 1）`sci = 1.89`
  · 城邦单城基准（n=5，pop 1）`sci = 2.30` —— 城邦**不吃难度加成、也不吃本 trait**，
    因此它们的单城值就是「这个版本的无修正基础值」，是纯净对照组
  · 比值 **1.89 / 2.30 = 0.8217 → 折扣 17.8%**，与设计 −18% 吻合
  · 同一份日志里老存档（t303）会稽仍是 **121.76**（= 0%）
  → **v37/v38/v40 三轮「零效果」彻底结案**：不是 effect 不被接受，是三轮都在老存档上测。
  → `GameInfo: L1/L2/L3 = MODIFIER_PLAYER_CITIES_ADJUST_CITY_YIELD_MODIFIER` 三行全对，
     `isHuman=true` `leader=LEADER_QIN` `traitQin=true`，`UNIT_SETTLER max=4 基础=2`（trait 链路旁证）。
  · **判据口径纠正（重要）**：原先写「人类首都比 AI 低 18%」是**错的**——
    AI 带神级难度加成（实测 +40%~+50%），人类必然低于 AI，与本层无关。
    正确判据是 **「人类首城 / 城邦单城均值」**，比值直接读出吃了几档：
    `−18%` = 只 L1；`−38%` = L2 也在；`−53%` = 三档全叠。
  · **诊断脚本 v7.43**：删掉 `PlayerTechs:GetScienceYieldToolTip()`（**UI 上下文方法**，
    玩法脚本里是 nil，v7.42 那个 `function expected instead of nil` 就是它，
    报错还把整段 traceback 灌进日志），改为直接计算并打印
    `折扣实测: 人类首城 … | 城邦基准 n=… 均=… | 比值=0.xxx（−xx.x%）`。
    这样中期复核时不用心算，一眼能看出当前吃了几档。
  · version 42→43（**只动诊断脚本与注释，SQL 与数值一行未改，不必重开新局**）。
  · `run_mod_sql` 202 ✓、`verify` 243 条 0 错 2 ⚠、`lua_check` 6/6、23 文件逐字节一致。
  · **剩下的待办**：等人类城市人口到 10 / 16，看那行比值是否变成 −38% / −53%；
    全三档确认后删掉 modinfo 里的 `NHS_SCRIPT` 动作块。

- **v7.44（L2 实机验证通过 + 查明叠加方式是加法，2026-11-22）**：用户打到 t80，咸阳人口 10。
  日志给出本项目**最干净的一组对照**（同一座城、只多一个人口、其余全不变）：
  · t79 咸阳 pop 9 `sci = 11.23` → 反推无折扣 `11.23 / 0.82 = 13.695`
  · t80 咸阳 pop 10 `sci = 8.68` → 反推无折扣 `8.68 / 0.62 = 14.000`
  · 两值差 **0.305**，恰好是一个人口的科研贡献（每人口约 0.30）→ 折扣整档 −18% → −38%。
  **顺带查明叠加方式（这条对以后调数值是关键）**：Civ6 的多个 `CITY_YIELD_MODIFIER`
  按**加法**叠加，不是乘法 ——
  乘法预测 `14.000 × 0.82 × 0.80 = 9.18`（实测不是）；加法预测 `14.000 × 0.62 = 8.68`（实测吻合）。
  所以累计值就是三个 `Amount` 直接相加，改档时按算术推，不要再乘百分比。
  **诊断脚本 v7.44 两处修正**：
  ① 城邦基准的「城邦城数=0」——pid 不能从 10 扫起（本局 Armagh 是 pid=2），且
     `Player:IsMinorCiv()` 返回 false 不可用，改为扫 0..63 并看 leader 名里有没有 `MINOR_CIV`；
  ② 新增**逐城跨门槛跳变记录**（`g_cityHist`）：人口变化时打印
     `↳ pop 9→10  sci 11.23→8.68（−22.7%）★跨 L2 门槛(10)`。
     这条比城邦对照更可靠——城邦中期建了第二城，样本自然消失，而跳变永远可用。
  ③ 外推 L3：人口 16 时若无折扣约 15.83，`× 0.47 ≈ 7.44`。
  version 43→44（**仍只动诊断脚本与注释，SQL 与数值一行未改，不必重开新局**）。
  现状：t82 人类 3 城共 20.35，最强 AI（吉尔伽美什）6 城 33.80 = 60%。
  **这个差距主因是城数 3 对 6，不是折扣**——折扣只把首城从 13.70 压到 11.23，
  折算下来让人类从「AI 的 67%」变成「60%」，影响约 7 个百分点。
  待办只剩：人口 16 时确认 −53%，然后删掉 `NHS_SCRIPT` 动作块。

- **v7.45（✅ L3 通过，规模层三档全部验收完成，2026-11-22）**：用户报咸阳 pop 16 科研 **7.40**。
  日志里 pop 15 最后一次落盘是 **9.61**，据此反推：
  · pop 15 无折扣 `9.61 / 0.62 = 15.500`
  · pop 16 无折扣应为 `15.500 + 0.305 = 15.805`，`× 0.47 = 7.43`
  · 实测 **7.40**，差 **0.03** → 折扣整档 −38% → −53%，L3 确认。
  **三档实测汇总（同一座城，咸阳）**：
  | 人口 | 实测 | 反推无折扣 | 折扣 |
  |---|---|---|---|
  | 1 | 1.89 | 2.30（城邦基准） | −18% |
  | 9 | 11.23 | 13.695 | −18% |
  | 10 | 8.68 | 14.000 | −38% |
  | 15 | 9.61 | 15.500 | −38% |
  | 16 | 7.40 | — | **−53%** |
  **顺带排除一个易误判现象**：pop 14 → 15 时科研从 10.95 掉到 9.61（−12.2%）。
  这两级都在 −38% 档，人口 +1 本应 +0.305（+2.8%），反推还有约 **−14%** 的额外全局惩罚
  —— **宜居度掉档**（人口增长吃宜居度），Civ6 固有机制，与本 mod 无关。
  以后看到「人口涨了科研反降」，先查宜居度，别怀疑本层。已写进 `nhs_18` 验收节第 ⑤ 条。
  **`NHS_SCRIPT` 不删**（原计划是三档通了就删，改主意了，理由要记）：
  机制已验收，但**平衡目标未定**——t82 人类 3 城 20.35 对最强 AI 6 城 33.80（60%），
  前期偏弱；中期（t150 之后）是否会反超过头，只能靠这个脚本观测。
  平衡定稿后再删。`nhs_18` 验收节第 5 条已同步改口。
  **要区分两件事，别混**：
  · 机制是否生效 = **已证**（三档全部实测命中，误差 0.03）
  · 平衡目标是否达成 = **未证**（要 t150 之后看总量倍数）
  version 44→45（仍只动注释与文档，SQL 数值一行未改）。
  `run_mod_sql` 202 ✓、`verify` 243 条 0 错 2 ⚠、`lua_check` 6/6、23 文件逐字节一致。

- **v7.46（t150 平衡实测：1.03 倍，目标达成但暴露趋势问题，2026-11-22）**：用户打到 t150。
  日志实测（10 城 / 1 个 major AI + 12 城邦）：
  · 人类 **91.92**（逐城合计 83.93 + 贸易/城邦等 7.99）
  · 最强 AI 吉尔伽美什 **89.49**（9 城）
  · **实际倍数 1.03**；若完全不吃折扣 `140.20 / 89.49 = 1.57 倍`
  · 规模层削减量 **48.28**，占城市科研 **36.5%**
  → 从老存档 t300 的 **6.6 倍** 压到 **1.03 倍**，「不超越 AI 太多」这一目标达成。
  **但必须记下这个趋势问题（这是本层设计上的固有代价）**：
  折扣在 16 人口封顶 −53%，此后人类每新增一个人口/建筑只拿 **47%** 收益，AI 拿 100%。
  两者扩张速度相当时，人类**持续相对走弱**。当前 1.03 倍是"刚好持平"，
  按这个斜率 t250 之后有**被反超**的风险。
  **换算好的档位表（按本次 t150 数据）**：
  | L1/L2/L3 | 累计 | 人类总 | 对 AI 倍数 |
  |---|---|---|---|
  | −18/−20/−15（现状） | −53% | 91.9 | **1.03** |
  | −12/−15/−10 | −37% | 106.7 | **1.19** |
  | −10/−12/−8 | −30% | 112.9 | **1.26** |
  | −8/−10/−6 | −24% | 118.3 | **1.32** |
  （已写进 README 旋钮表，改档时照这个推，不要再心算）
  **本轮未改任何数值**，等用户定"持平"还是"明显领先"再动。README 已记平衡实测一节。
  **另一个观察**：本局只有 1 个 major AI（首局 t1-4 时有 8 个），是用户重开时换的配置，
  所以"最强 AI"样本单一；对"人类 vs 最强 AI"这个判据够用，但看不到多 AI 的相对格局。

- **v7.46a（按用户决定执行调档：−18/−20/−15 → −10/−12/−8，2026-11-22）**：
  用户在三个方案里选了「放松到 −10/−12/−8（1.26 倍）」。
  **改动范围（SQL 数值 + 三层校验器 + 两处文案，缺一处就"改了等于没改"）**：
  ① `nhs_18` 三条 `Amount`：−18 / −20 / −15 → **−10 / −12 / −8**（累计 −53% → **−30%**）；
     同时重写「数值验算」节（原先是 t300 估算，现在换成 t150 实测倒推 + 为什么 1.26 而不是 1.0）；
     旋钮表同步改为 温和 −6/−8/−5(~1.4x) / **推荐 −10/−12/−8(~1.26x)** / 激进 −18/−20/−15(~1.03x)。
  ② `run_mod_sql.py`：`_tiers` 三条、`_CUM` 53 → **30**；
  ③ `verify_mod.py`：`_TIERS` 三条、累计断言 53 → **30**（报错文案改成"v46 从 −53% 调轻，目标倍数 1.26"）；
  ④ `nhs_text.xml`：注释段 + 中英文长描述三处全部换成 −10%/−22%/−30%；
  ⑤ `modinfo`：version 45→46、描述文案、动作注释（并写明调轻理由）。
  **反向测试 8/8 全抓**（锚点已跟着换）：
  负号写丢（−10→+10）→ `✗ Amount 不符（实际, 应为）：{'NHS_TECH_SCALE_L1': (10.0, -10)}`；
  退回 v40 加算类 → `✗ 修饰器类型不对`；L3 门槛挂错 → `✗ L3 的 Subject 门槛为 NHS_REQS_CITY_POP_10`；
  累计漂移（−12→−4）→ `✗ 三档累计折扣为 −22%；设计值 −30%`；YieldType 写文化 → `✗ YieldType 为 YIELD_CULTURE`；
  Owner 写 NULL → `✗ Owner 门槛不是 PLAYER_IS_HUMAN`；挂载删 → `✗ 只挂到 2 条`；类型名拼错 → `✗ L1 的修饰器为 …_MODIFER`。
  `run_mod_sql` 202 ✓、`verify` 243 条 0 错 2 ⚠、`lua_check` 6/6、23 文件逐字节一致、`version="46"`，
  安装目录实测 `'-10' '-12' '-8'` 三行已落地。
  **⚠ 必须新开一局才生效**（改的是 SQL 数值，老存档不追溯——这是本项目最贵的教训，v37~v41 就栽在这）。
  **新局的预期**：前 3 回合人类首城 / 城邦基准 ≈ **0.90**（−10%）；
  人口 10 时 ≈ **0.78**（−22%）；人口 16 时 ≈ **0.70**（−30%）。

- **v7.47a（远古时代豁免：三档统一加「玩家已进入古典时代」门槛，2026-11-23）**：
  用户诉求原文：「回到平衡性角度，我希望前期（远古时代）不要削弱人类玩家」。
  **动机（设计修正，不是补偿）**：远古是人类最弱的阶段——神级 AI 自带约 +40%~+50% 科研加成，
  实测 t82 人类只有最强 AI 的 60%；此时再补 −10% 等于在玩家最弱时加税。
  量级也够看：远古总科研 2~5/回合，−10% 的绝对差 0.2~0.5，但远古科技只要 25~50 点，
  累计 100 回合是 1~2 个关键远古科技（畜牧、陶器）的进度差。
  规模税的本意是「帝国成型后的承载力成本」，而远古还不算帝国。

  **机制（查库 + 原版先例，不是猜的）**：
  · `REQUIREMENT_PLAYER_ERA_AT_LEAST` + `EraType=ERA_CLASSICAL`。
    原版同类型用例：`REQUIRES_PLAYER_IS_INDUSTRIAL_ERA`（Industrial），
    被城邦奥克兰的 `MINOR_CIV_AUCKLAND_SHALLOW_WATER_PRODUCTION_BONUS_INDUSTRIAL` 使用
    → 证明该 RequirementType 在引擎里确实会被评估。
  · 组合 Set 的原版先例（与本次完全同构）：
    `PLAYER_HAS_GOLDEN_AGE_ATOMIC` = TEST_ALL{`REQUIRES_ERA_IS_ATOMIC`,
    `REQUIRES_PLAYER_HAS_GOLDEN_AGE`}，挂在 3 个 Modifier 的 **OwnerRequirementSetId** 上
    （`COMMEMORATION_AERONAUTICAL_GA_*` → `MODIFIER_PLAYER_GRANT_SPECIFIC_TECH_BOOST`）
    → 证明「时代判定 + 另一条玩家维度判定」可组成 TEST_ALL Set 并挂 Owner 阶段。
  · **用 PlayerEra 不用 GameEra**：GameEra 是全场最先进的时代，任一 AI 先进古典就会开始
    对仍处远古的人类征税，与诉求相反。库里 GAME_ERA 系列用例更多，但语义不对。

  **改动范围（6 处，缺一处就「改了等于没改」）**：
  ① `nhs_18` 新增 1b 节：`NHS_REQ_PLAYER_POST_ANCIENT`（REQUIREMENT_PLAYER_ERA_AT_LEAST
     + ERA_CLASSICAL）+ `NHS_REQS_HUMAN_POST_ANCIENT`（TEST_ALL，两个成员）；
     三条 Modifier 的 `OwnerRequirementSetId`：`PLAYER_IS_HUMAN` → **`NHS_REQS_HUMAN_POST_ANCIENT`**；
     **Amount 一个都没动**（仍 −10/−12/−8，累计 −30%）；文件头加「为什么远古要豁免」一节；
     末尾验收节加第 6 条（远古 1.00 + 古典 0.90 两个读数都要取）。
  ② `run_mod_sql.py`：`[规模]` 节把「三条 Owner 必须是 PLAYER_IS_HUMAN」换成钉死新 Set 名，
     并追加两条断言（Set 成员集合、时代门槛类型与 EraType）；
  ③ `verify_mod.py`：`_TIERS` 循环的 Owner 断言同步；新增 v47 时代门控静态块（3 条）；
     库核对追加 `REQUIREMENT_PLAYER_ERA_AT_LEAST` 与 `ERA_CLASSICAL` 两条存在性；
  ④ `nhs_text.xml`：注释段 + 中英文长描述（「自古典时代始…远古不征此税」）；
  ⑤ `modinfo`：version 46→47、标题、描述、动作注释；
  ⑥ `install.py`：收尾提示的版本号改为**从 modinfo 现读**（原本硬编码 v46，必然过期）。

  **反向测试 5/5 全抓**（`reverse_test_v47.py`，跑完自动还原并校验 sha256）：
  EraType 改 ERA_ANCIENT → `✗ 豁免边界会漂移` + `✗ 时代门槛不对`；
  删 Set 的时代成员 → `✗ 缺成员 NHS_REQ_PLAYER_POST_ANCIENT` + `✗ Owner Set 成员不对`；
  删 Set 的人类成员 → `✗ 缺成员 REQUIRES_PLAYER_IS_HUMAN`；
  L1 改回 PLAYER_IS_HUMAN → `✗ 的 Owner 门槛为 PLAYER_IS_HUMAN`；
  类型名少一个下划线 → `✗ 类型不是 REQUIREMENT_PLAYER_ERA_AT_LEAST` + `✗ 游戏库里找不到`。

  `run_mod_sql` **204 ✓**、`verify` **248 项 0 错 3 ⚠**、`lua_check` 通过、23 文件逐字节一致、
  `version="47"`，安装目录四个改动文件 sha256 一致。
  **⚠ 必须「完全退出进程 → 重启 → 新开一局」**（既改 SQL 又改挂载口径）。
  **验收判据（两个读数都要）**：远古期 人类首城 / 城邦均值 ≈ **1.00**；进入古典后 ≈ **0.90**。
  只有前一个读数无法区分「门控生效」与「整层没挂上」。三种失败形态：
    远古 0.90 → 时代 Requirement 没起作用（换成 `REQUIREMENT_GAME_ERA_ATLEAST_EXPANSION` 再试）；
    远古 1.00 且古典 1.00 → 整层没挂上（没重启进程 / 不是新局）。



1. **直接拷整个工作目录** → 14 MB 里一半是 `db/*.sqlite` 中间产物。用 zip，别用 U 盘整目录拖。
2. **`build_game_db.py` 的游戏路径** → v24 起改为 `CIV6_DIR` 环境变量优先、默认 `D:\SteamLibrary\steamapps\common\Sid Meier's Civilization VI`（旧值 `D:\Program Files (x86)\...` 已失效）。只要 `db/gameplay_verify.sqlite` 还在，平时根本不用重建；重建时会扫全部 `DLC/*/Data`，约 960 个 XML。
3. **新 AI 不知道 v7 是刻意的** → 它可能"好心"把 `CivilizationTraits` 加回来让所有文明都能用。第 5 节的开场白就是防这个。
