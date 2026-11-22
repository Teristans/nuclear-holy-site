# 验证报告 / Verification Report

> 核动力圣地 Mod · **v7（秦始皇专属）** · 2026-11-20
> 验证对象：本机安装的 **Sid Meier's Civilization VI**（含《迭起兴衰》《风云变幻》）
> 安装路径：`D:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization VI`
>
> **v7 变更**：发放方式从 `CivilizationTraits`（所有文明）改为 `LeaderTraits`（只挂 `LEADER_QIN`）。本报告新增 2.8 节记录这次改造的验证依据。

之前所有结论只能靠社区资料 + 静态推理，标注为"⚠️ 未验证"。装了游戏本体后，这些项已逐条核对到**游戏自己的数据文件**。下面是可追溯的记录。

---

## 1. 用游戏真实结构执行 mod SQL

| 项 | 结果 |
|---|---|
| 建库依据 | 游戏自带 `Base/Assets/Gameplay/Data/Schema/01_GameplaySchema.sql`（310 张表）+ `02_AddTriggers.sql` |
| 灌入数据 | 328 个游戏 XML，42020 行（Base + 高棉 DLC + 两个资料片） |
| 执行对象 | `mod/sql/nhs_01~09.sql`，共 **65 条语句** |
| 执行结果 | **65/65 通过，0 报错** |
| 结构断言 | **33 项全过**（引用完整性、人类门槛、克隆产出、数值锚点、移动力、奇观加速、文案、**秦始皇专属挂载**、幂等） |
| 复现命令 | `python build_game_db.py && python run_mod_sql.py` |

脚本：`build_game_db.py`（建库）、`run_mod_sql.py`（执行 + 断言）。

**这个验证的边界**：它证明了"SQL 在游戏真实表结构上不会报错、引用都存在、克隆确实取到行、trait 确实只挂在 `LEADER_QIN` 上"。它**不能**证明引擎的 C++ 行为（例如 AI 是否真用奇观加速、加速按钮的显示条件）、UI 显示、以及手感。

---

## 2. 逐条核对结论（带出处）

### 2.1 `PLAYER_IS_HUMAN`（整个 mod 的地基）

| 事实 | 文件:行号 |
|---|---|
| 定义为 `REQUIREMENTSET_TEST_ALL` | `Leaders.xml:5444` |
| 由 `REQUIRES_PLAYER_IS_HUMAN` 构成 | `Leaders.xml:5934` |
| 需求类型 `REQUIREMENT_PLAYER_IS_HUMAN` 存在 | `Leaders.xml:6437` |
| **原版就在用它做 `OwnerRequirementSetId`**（野蛮人营地金币 `BARBARIAN_CAMP_GOLD_SCALING`） | `Leaders.xml:1460` |

→ 结论升级：不只是"社区 mod 用过"，而是**原版官方自己就这么用**。

### 2.2 奇观加速的时代限制

| 事实 | 文件:行号 |
|---|---|
| `UNITCOMMAND_WONDER_PRODUCTION` 行 `MaxEra="2"` | `UnitCommands.xml:49` |
| 表结构 `MaxEra INTEGER NOT NULL DEFAULT -1` | `01_GameplaySchema.sql` |
| `ERA_ANCIENT ChronologyIndex=1` / `ERA_CLASSICAL=2` → 2 = 上限古典 | `Eras.xml:16,17` |
| 同表 `UNITCOMMAND_HARVEST_WONDER` 的 `MaxEra=-1`（即"不限"的约定值） | 实测查询结果 |

→ 因此 `nhs_09` 把 `MaxEra` 从 2 改为 **9**（原版 8 个时代 + GS 未来时代），在 `era <= MaxEra` 判定下等于全开。

### 2.3 移动力

| 事实 | 文件:行号 |
|---|---|
| `MODIFIER_PLAYER_UNITS_ADJUST_MOVEMENT` | `Modifiers.xml:312`（Types）、`:2025`（DynamicModifiers） |
| 其 `CollectionType=COLLECTION_PLAYER_UNITS`、`EffectType=EFFECT_ADJUST_UNIT_MOVEMENT` | `Modifiers.xml:2026,2027` |
| `REQUIREMENT_UNIT_TYPE_MATCHES` 存在（原版用于审判官/商人） | `Leaders.xml:6511,6515`；`Policies.xml:5392` |
| 侦察兵 `BaseMoves="3"` | `Units.xml:771` |
| 移民 `BaseMoves="2"` | `Units.xml:751` |

→ +3 / +2 正好等于翻倍，已由上表基础值确认。

### 2.4 工人加速百分比

| 事实 | 文件:行号 |
|---|---|
| `MODIFIER_PLAYER_ADJUST_UNIT_WONDER_PERCENT` | `Modifiers.xml:79`（Types）、`:1180`（DynamicModifiers） |
| 其 `CollectionType=COLLECTION_OWNER`、`EffectType=EFFECT_ADJUST_PLAYER_UNIT_WONDER_PERCENT` | `Modifiers.xml:1181,1182` |
| 秦始皇的 `TRAIT_BUILDER_WONDER_PERCENT` 用的就是这个类型 | `Leaders.xml:1531,1532` |

→ 因为 CollectionType 是 `COLLECTION_OWNER`（主体即玩家），只挂 `OwnerRequirementSetId=PLAYER_IS_HUMAN` 是正确写法，不需要 Subject 门槛。

### 2.5 信条与政策

| 事实 | 文件:行号 |
|---|---|
| `BELIEF_WORK_ETHIC` / `BELIEF_DANCE_OF_THE_AURORA` / `BELIEF_JESUIT_EDUCATION` 均存在 | `Beliefs.xml:42,8,39` |
| 极光之舞的两个 modifier 挂在 `BeliefModifiers` 上 | `Beliefs.xml:1812-1817` |
| `POLICY_SCRIPTURE` = **神学解锁、经济政策位** | `Policies.xml:153` |
| 经文的 modifier `SCRIPTURE_DISTRICTFAITH`：`YieldType=YIELD_FAITH`、`Amount=100`、`SubjectRequirementSetId=DISTRICT_IS_HOLY_SITE` | `Policies.xml:1044-1046`、`:3493-3500` |
| GS 版职业道德 = `WORK_ETHIC_ADJACENCY_PRODUCTION_2`，需求集含 **`REQUIRES_CITY_FOLLOWS_RELIGION`** + `REQUIRES_WORK_ETHIC_DISTRICT_IS_HOLY_SITE` | `Expansion2_Beliefs.xml:388-390`、`:1397-1402` |
| 游戏内文案：经文"+100%圣地相邻加成"；GS 职业道德"圣地区域的信仰值相邻加成也提供生产力" | `Vanilla_zh_Hans_CN.xml:27102`、`Expansion2_Translations_Text.xml:202601` |

→ 一个重要确认：**宗教门槛是写在 modifier 上的**，不是引擎隐式加的。所以克隆时保留 `SubjectRequirementSetId` 就真的保住了"必须创教信教"这个前提（执行验证里检出 4 个克隆体带 `REQUIREMENT_CITY_FOLLOWS_RELIGION`）。

### 2.6 俄罗斯母亲 / 国王的修道院

| 事实 | 文件:行号 |
|---|---|
| `TRAIT_CIVILIZATION_MOTHER_RUSSIA` 存在 | `Civilizations.xml:86,2188` |
| 其 TraitModifiers 共 5 条（基础版）：苔原信仰/产能、丘陵信仰/产能、额外领土 | `Civilizations.xml:2461-2479` |
| `TRAIT_INCREASED_TILES` 的 `Amount = 5` → **建城额外 5 格领土** | `Civilizations.xml:1462-1464` |
| 这些 modifier 只有 `ModifierId`/`ModifierType`/`SubjectRequirementSetId` 三个字段，**没有** `RunOnce`/`Permanent` 等标志 | `Civilizations.xml:480-502` |
| `TRAIT_LEADER_MONASTERIES_KING` 存在（高棉 DLC），载入后 TraitModifiers 有 6 条 | `DLC/Indonesia_Khmer` |

→ 由此确认两件事：
1. 我之前把"建城 8 格"更正为"5 格"是对的，**用游戏数据验证了**；
2. 我的克隆只复制 4 列是**忠实**的，因为这些 modifier 本来就没有用别的标志列（否则会丢语义）。

### 2.7 modinfo 格式

| 事实 | 依据 |
|---|---|
| 游戏自带 43 个 modinfo，**0 个**使用 `<Modules>` 或 `<Handles>` | 全目录扫描 |
| 36 个用 `<InGameActions>`，7 个用 `<Components>` | 同上 |
| 原生写法示例 | `DLC/Expansion2/Expansion2.modinfo` |

→ v6 已把 modinfo 从旧式 `<Modules><Module>` 改写为 `<Mod><Properties><InGameActions>`，与原生一致。

### 2.8 秦始皇专属挂载（v7 新增）

| 事实 | 依据 |
|---|---|
| 全游戏只有 **`LEADER_QIN`** 一个秦始皇 ID（不存在 `LEADER_QIN_SHI_HUANG` 之类的变体） | `Leaders.xml:145`；数据库 `SELECT LeaderType FROM Leaders WHERE LeaderType LIKE '%QIN%'` → 仅 1 行 |
| `LEADER_QIN` 的文明是 `CIVILIZATION_CHINA` | `CivilizationLeaders` 表联查 |
| `LEADER_QIN` 的原版 trait 是 `FIRST_EMPEROR_TRAIT` | `Leaders.xml:856` |
| `FIRST_EMPEROR_TRAIT` 挂的 modifier：`TRAIT_ADJUST_BUILDER_CHARGES`、`TRAIT_BUILDER_WONDER_PERCENT` | `Leaders.xml:1086-1087` |
| `TRAIT_BUILDER_WONDER_PERCENT` 的 `Amount = 15` | `Leaders.xml:3652-3654` |
| **全游戏只有 1 个领袖拥有 `TRAIT_BUILDER_WONDER_PERCENT`，就是 `LEADER_QIN`** | 数据库联查 `LeaderTraits × TraitModifiers` |
| `LeaderTraits` 表结构：`(LeaderType, TraitType)` 双主键，外键指向 `Leaders` / `Traits` | `01_GameplaySchema.sql` |

→ **这是 v7 方案成立的核心证据**：在数据层，"拥有工人加速能力"与"是秦始皇"完全等价。所以把 mod 的 trait 也只挂到 `LEADER_QIN`，就把"谁能用"收窄到了同一个集合。人类选秦始皇时 AI 不可能同时是秦始皇，于是 AI 自然拿不到这份效果。

⚠️ **仍未证明的一环**：引擎 C++ 是否真的以"玩家拥有该 modifier"作为显示加速按钮的判据。上面只能证明"原版数据里两者一一对应"，配合社区一致表述（秦始皇是唯一能加速奇观的领袖），构成极强推断但非机制证明。

---

## 3. 执行验证的 33 项断言（摘要）

```
[执行]  nhs_01 19/19 · nhs_02 4/4 · nhs_03 5/5 · nhs_04 6/6 · nhs_05 6/6
        nhs_06 8/8 · nhs_07 10/10 · nhs_08 6/6 · nhs_09 1/1

[引用] ModifierType / RequirementSet / Trait / 领袖 全部有对应记录
[门槛] 27 个 NHS Modifier 全部挂 PLAYER_IS_HUMAN
[克隆] 俄罗斯母亲 5 个（原版 9 个，已排除暴风雪相关）
[克隆] 国王的修道院 6 个（原版 6 个）
[克隆] 极光之舞 6 个 · 经文政策 1 个
[克隆] 4 个信条克隆保留 REQUIRES_CITY_FOLLOWS_RELIGION
[数值] 产能0 / 食物1 / 信仰2 / 文化1 / 住房2
[移动] 侦察兵 3+3=6 · 移民 2+2=4（均为精确翻倍，已对基础值）
[奇观] 加速：本层15 + 原版秦始皇15 = 30% · MaxEra 2→9
[文案] 24 条 zh_CN + en_US
[专属] 6 层 trait 全部挂 LEADER_QIN（逐层断言）
[专属] CivilizationTraits 中 NHS trait 为 0 行（没有发给任何文明）
[专属] 除 LEADER_QIN 外无其他领袖获得
[专属] LEADER_QIN 在 Leaders 表中存在（防拼写错误静默失效）
[幂等] 重复加载两次，Modifier 数量 27 → 27
```

---

## 4. 仍然无法验证的部分（不粉饰）

| 项 | 为什么无法验证 | 怎么验 |
|---|---|---|
| AI 是否真的吃不到加成 | 需要跑一局看 AI 城市产出 | 开一局，观察 AI 城市圣地 |
| **加速按钮的显示是否真的取决于该 modifier** | 引擎 C++ 行为；数据层只能证明"两者在数据上一一对应" | 玩秦始皇时看你有按钮、AI 没有；再换非秦始皇开局对比 |
| 移民（民用车）是否受 `COLLECTION_PLAYER_UNITS` 覆盖 | 同上，C++ 行为 | 开局看移民移动力是否 4 |
| 信条克隆后是否语义等价 | 依赖引擎对"宗教归属"的运行时判定 | 创教后看产能是否跳升 |
| `MaxEra=9` 是否真的解锁后续时代 | 需在游戏中跑到中古以后 | 中古后开奇观，看有没有加速按钮 |
| 奇观加速是否真按 30% 推进 | 引擎行为 | 试一次看进度条 |
| 手感 / 是否过强 | 数值模拟不能替代试玩 | 打一局神级 |

---

## 5. 复现方式

```bash
python build_game_db.py    # 用游戏 schema + XML 造真实结构库（约 42000 行）
python run_mod_sql.py      # 在库副本上执行 mod SQL 并断言（33 项）
python verify_mod.py       # 离线结构校验（不依赖游戏，给别人用时也能跑）
python civ6_nhs_balance_v5.py   # 产出曲线
python civ6_nhs_balance_v6.py   # 移动/奇观冲击
```

依赖：仅 Python 3 标准库（sqlite3 / xml.etree / zlib）。
