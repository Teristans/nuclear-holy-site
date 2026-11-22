# DEVELOPMENT.md —— 换一台机器继续开发

> 这份文件解决一件事：**把仓库 clone 到一台新电脑上，从零到能改代码、能自证改对了**。
> 设计理念与数值依据看 [README.md](README.md)；逐版本变更史与踩过的坑看 [HANDOFF.md](HANDOFF.md)（46 个版本，很长但值）。

---

## 0. 三十秒版本

```bash
git clone https://github.com/<账号>/nuclear-holy-site.git
cd nuclear-holy-site
set CIV6_DIR=D:\SteamLibrary\steamapps\common\Sid Meier's Civilization VI
python build_game_db.py      # 重建 30MB 验证库（不入库，必须自己生成）
python run_mod_sql.py        # 期望：202 条 ✓ / 0 错
python verify_mod.py         # 期望：246 项 / 0 错 / 1 WARN
python lua_check.py          # 期望：2/2 OK
python install.py            # 装进游戏
```

四道全绿 = 这台机器可以开工了。

---

## 1. 当前状态（2026-11-22，mod `version="46"`）

| 层 | 状态 | 证据 / 缺口 |
|---|---|---|
| 八威仪（圣地、克隆层、移动、奇观、道路、政策、宜居、城市名） | ✅ 已实机运行 | 见 `VERIFICATION.md` 逐条对账 |
| 科技规模三档（`nhs_18`） | ✅ 机制已逐档实测命中 | 跨门槛整档跳变，−18/−38/−53 三个状态都读到过（v42 口径） |
| **科技规模三档（v46 数值 −10/−12/−8）** | ⚠️ **未实测** | 需新开一局，预期读到 −10 / −22 / −30 |
| **平衡目标（人类 ≈ 最强 AI 的 1.25~1.45 倍）** | ⚠️ **未实测** | t150 是唯一判据，见 README 4.2 第 8 条 |
| 产能 / 金币 / 文化三轴 | ⏸ **刻意不动** | t300 实测产能 4.38 倍（但每人口 0.79 倍），属"规模的自然结果"，压它会让"人多"变纯负收益 |
| `nhs_info.lua` 诊断脚本 | 🔧 临时挂载 | 平衡定稿后要从 `.modinfo` 删掉 `NHS_SCRIPT` 动作块并删文件 |

---

## 2. 环境要求

| 项 | 要求 | 说明 |
|---|---|---|
| 操作系统 | **Windows** | 三个脚本分别用了 `winreg`（读文档真实路径）、`tasklist`（查游戏进程）、`ctypes.WinDLL`（加载游戏自带 Lua 编译器）。macOS / Linux 跑不了，也不要试图改 |
| 文明6 | 含 **Gathering Storm** | 克隆层引用的 modifier 来自 GS / 各 DLC；缺资料片会在建库阶段报「类型不存在」 |
| Python | 3.8+（本机 3.13.14） | **零第三方依赖**，不要 `pip install` 任何东西 |
| 磁盘 | 约 50MB | 验证库 30MB + 临时库 |

不需要：Steam Workshop 上传工具、ModBuddy、Visual Studio、任何 Civ6 SDK。

---

## 3. 首次配置：三个路径

### 3.1 `CIV6_DIR`（游戏安装目录）

`build_game_db.py`、`verify_mod.py`、`lua_check.py` 都优先读这个环境变量，读不到才退回硬编码的
`D:\SteamLibrary\...`。

```bat
set CIV6_DIR=D:\SteamLibrary\steamapps\common\Sid Meier's Civilization VI
```

（想永久生效：`setx CIV6_DIR "..."`，然后重开终端。）

### 3.2 Mods 目录

**不要硬编码 `%USERPROFILE%\Documents`。** 很多人的「文档」被 OneDrive 或手动重定向到 D 盘，
真实路径只在注册表里：

```
HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders → Personal
```

`install.py` 就是按这个顺序探测的，装错地方它也会告诉你实际写到了哪。
非要手动指定：`python install.py --mods "D:/.../Civilization VI/Mods"`。

### 3.3 实机取证路径（Lua 日志与引擎真实库）

```
%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VI\Cache\DebugGameplay.sqlite   ← 引擎真正建出来的库
%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VI\Logs\Lua.log                ← 诊断脚本输出
%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VI\Logs\Database.log            ← SQL 报错
```

**`db/gameplay_verify.sqlite` 不是它。** 前者是我们用游戏 schema + XML 离线拼的，后者是引擎自己建的。
判断"克隆层有没有真的取到原版 modifier"必须查后者 —— 离线库里全 DLC 是合并后再跑我们，
顺序问题在它上面永远不出现。

---

## 4. 三道校验（每次改完必跑）

| 命令 | 抓什么 | 当前基线 |
|---|---|---|
| `python run_mod_sql.py` | 17 个 SQL 在**真实表结构**上逐条执行 + 数值锚点 + 幂等 + 原版数值未被误改 | **202 ✓ / 0 错** |
| `python verify_mod.py` | 离线静态：ModifierType / RequirementSet / Trait / 领袖引用存在性、文案同步、GUID、modinfo 结构 | **246 项 / 0 错 / 1 WARN**（WARN 是刻意保留的 `UnitCommands` 泄漏说明） |
| `python lua_check.py` | 用游戏自带 Havok 编译器做 Lua 语法校验（**不执行**，只编译） | **2/2 OK**（会连带扫其他已启用 mod） |

判定口径只有一条：**看有没有 `✗` 行 / `ERROR` 计数是否 > 0**。不要看"✓ 很多所以没问题" ——
v35 那次就是因为断言写成"是否出现 ✓ 通过行"，命中的全是本来就该通过的，等于没测。

反向测试（确认校验器真的能抓错）——每加一条断言就该做一次：

```bash
python tools/_revtest18.py     # nhs_18 的 8 组反向用例：负号丢失/退回加算类/门槛挂错/累计漂移/
                               # YieldType 写错/Owner 写 NULL/挂载被删/类型名拼错
```

---

## 5. 改一处数值的标准流程

以"把 L1 从 −10 调到 −8"为例，**一次改五个地方**，少一处就是文档与实现分叉：

1. `mod/sql/nhs_18_tech_scaling.sql` —— 三处：文件头【三档设计】表、第 2 节的 `Amount`、【旋钮】表
2. `run_mod_sql.py` —— `_tiers` 与 `_CUM`（累计值）
3. `verify_mod.py` —— `_TIERS` 与累计断言
4. `mod/text/nhs_text.xml` —— 中文长描述、英文长描述（两处都写死了百分比）
5. `mod/NuclearHolySite.modinfo` —— `<Mod version>` 自增、`<Name>` 里的（vNN）、`<Description>` 首段

然后：

```bash
python run_mod_sql.py && python verify_mod.py && python lua_check.py
python tools/_revtest18.py
python install.py                    # 装进 Mods，自动 sha256 复核
```

最后**完全退出游戏进程**（不是回菜单）→ 重启 → **新开一局** → 打几回合看 `Lua.log`。

---

## 6. 硬规则（这几条会咬人，都是真金白银换来的）

1. **Civ6 在建局那一刻就把玩家已挂载的 trait modifier 集合写进存档。** 之后往 mod 里新增的
   modifier 只进游戏库（`GameInfo` 查得到），**不追溯挂到已经在跑的存档上**。
   → 改 SQL 层**只能在新开的局里验证**，老存档永远 0% 效果。v37 / v38 / v40 三轮"零效果"
   结论全是因为违反这条而作废的，代价是三个版本的开发时间。
2. **`SQL_FILES` 在 `run_mod_sql.py`（裸文件名）和 `verify_mod.py`（带 `sql/` 前缀）各有一份硬编码列表。**
   新增 SQL 文件必须两处都加，否则该文件永不参与校验，且不会有任何报错。
3. **每个 `UpdateDatabase` 组件必须写 `<Properties><LoadOrder>500</LoadOrder></Properties>`。**
   不写就是 0，会在官方资料片（100 / -100）之前建库，克隆层取不到源头。
4. **百分比按加法叠加，不是乘法。** 14.000 × (1−0.18−0.20) = 8.68 实测命中；×0.82×0.80 = 9.18 不命中。
   累计值 = 三个 `Amount` 直接相加。
5. **加断言必须做反向测试，判据指向失败信号（`✗` 行）。** 只确认"出现了通过行"等于没测。
6. **克隆层必须回查 `Cache/DebugGameplay.sqlite`。** 离线库证明不了加载顺序。
7. **不为了读写 Office / 解析文件而装东西。** 本机 Python 标准库 + 已有工具足够。
8. **改完一定重启游戏进程。** modinfo 只在进程启动时解析一次，改完不重启，标题栏还显示旧版本号。

（完整版见 `HANDOFF.md` 开头的约束清单。）

---

## 7. 常见故障

| 现象 | 原因 | 处置 |
|---|---|---|
| 游戏里数字一点没变 | 在**老存档**上测 | 退出进程 → 重启 → 新开一局。没有例外 |
| 标题栏版本号还是旧的 | mod 没装到正确位置，或游戏没重启 | `python install.py`（会检查进程 + sha256），再重启 |
| `额外内容` 里出现两个同名 mod | 同一份 `.modinfo` 存在两处（典型来源：`backups/` 被放进 Mods 目录） | 删掉多余那份。本仓库已把 `backups/` 排除在 git 之外 |
| `run_mod_sql.py` 报找不到表 | `db/gameplay_verify.sqlite` 不存在或过期 | `python build_game_db.py` 重建 |
| `lua_check.py` 报找不到 DLL | `CIV6_DIR` 未设 / 指错 | 设 `CIV6_DIR`，或 `python lua_check.py --game-bin "<...>\Base\Binaries\Win64Steam"` |
| 新增 SQL 文件后校验条数没涨 | `SQL_FILES` 两处硬编码漏加 | 见 §6 第 2 条 |
| 人口涨了科研反而掉了 | 宜居度掉档（Civ6 固有机制），不是本层 bug | 查宜居度，不要动 `nhs_18` |

---

## 8. 待办（按优先级）

1. **v46 数值验证**：新开一局，确认三档读到 −10 / −22 / −30，再打到 **t150** 看人类/AI 科研总量比
   是否落在 **1.25~1.45**（判据见 README 4.2 第 8 条）。`nhs_info.lua` 会直接打印比值。
2. **平衡定稿后清理**：`.modinfo` 删 `NHS_SCRIPT` 动作块 → 删 `mod/lua/nhs_info.lua` → version 自增。
3. **若整体仍偏强**：下一个该动的是**产能**，不是科技。科技已经 1.3 倍，再压就掉进 1.2 以下的慢性失血区。
   建议只压 ≥16 人口的大城产能，门槛复用现成的 `NHS_REQS_CITY_POP_16`，不需要新建 requirement set。
4. **样本单一**：t150 那局只有 1 个 major AI。"最快的 AI"在标准 7 AI 局里通常更强，实际倍数可能比
   单 AI 局低 0.1 左右。要更准就开一局多 AI 的。
5. **老存档（t303 那局）救不回来** —— 存档里没有这条 modifier，Lua 强扣科研只是绕过问题，不建议做。

---

## 9. 目录约定

| 目录 | 入库 | 原因 |
|---|---|---|
| `mod/` | ✅ | mod 本体，23 个文件，292KB |
| 根目录脚本 / 文档 | ✅ | 校验链与设计依据 |
| `db/` | ❌ | 30MB，含 Firaxis 版权数据（游戏原始库副本 + 存档），DMCA 风险。跑 `build_game_db.py` 重建 |
| `backups/` | ❌ | 旧版全量备份，改用 git tag 保存历史；且同 GUID 的两份 modinfo 会造成游戏识别冲突 |
| `*.sqlite` / `*.Civ6Save` | ❌ | 同上 |

历史版本用 tag 而不是文件夹：

```bash
git tag -l                 # 看所有版本
git checkout v45 -- mod/   # 临时取回某个版本的 mod 文件做对照
```
