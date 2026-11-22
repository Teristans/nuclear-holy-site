# -*- coding: utf-8 -*-
"""
build_game_db.py —— 用游戏自带的 schema + XML 数据，构造一个"真实结构"的 SQLite 库

目的：让 mod 的 SQL 不是"静态看起来对"，而是**真的在游戏表结构上执行过**。

数据来源（本机安装目录）：
  Base/Assets/Gameplay/Data/Schema/01_GameplaySchema.sql   ← 真实的建表语句
  Base/Assets/Gameplay/Data/*.xml                          ← 基础游戏数据
  DLC/Indonesia_Khmer/Data/*.xml                           ← 高棉（国王的修道院）
  DLC/Expansion1/Data/*.xml, DLC/Expansion2/Data/*.xml     ← 两个资料片（支持 Update/Delete）

用法：python build_game_db.py
产出：db/gameplay_verify.sqlite
"""
import os
import re
import sqlite3
import glob
import sys
import zlib
import xml.etree.ElementTree as ET

GAME = os.environ.get("CIV6_DIR") or \
    r"D:\SteamLibrary\steamapps\common\Sid Meier's Civilization VI"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
DB_PATH = os.path.join(OUT_DIR, "gameplay_verify.sqlite")

SCHEMA = os.path.join(GAME, r"Base\Assets\Gameplay\Data\Schema\01_GameplaySchema.sql")
TRIGGERS = os.path.join(GAME, r"Base\Assets\Gameplay\Data\Schema\02_AddTriggers.sql")


def _build_load_order():
    """Base → 全部 DLC → Expansion1 → Expansion2。

    【v24 修正】原来只列了 Base / Indonesia_Khmer / Expansion1 / Expansion2，
    漏掉 Byzantium_Gaul 等 30 多个 DLC，导致 MODIFIER_PLAYER_CITIES_IMPROVEMENT_ADJACENCY
    这类「某 DLC 才引入」的原版 ModifierType 在验证库里查无此人，
    而实机库里明明存在（它由 DLC/Byzantium_Gaul/Data/Byzantium_Gaul_Modifiers.xml 引入）。
    现在改为扫全部 DLC/*/Data，资料片固定排最后（覆盖前面同名的旧定义，
    例如职业道德在资料片里被重做过）。
    """
    order = [os.path.join(GAME, r"Base\Assets\Gameplay\Data")]
    dlc_root = os.path.join(GAME, "DLC")
    plain, exp1, exp2 = [], [], []
    if os.path.isdir(dlc_root):
        for name in sorted(os.listdir(dlc_root)):
            d = os.path.join(dlc_root, name, "Data")
            if not os.path.isdir(d):
                continue
            if name == "Expansion1":
                exp1.append(d)
            elif name == "Expansion2":
                exp2.append(d)
            else:
                plain.append(d)
    return order + plain + exp1 + exp2


LOAD_ORDER = _build_load_order()

BOOL_MAP = {"true": 1, "false": 0, "TRUE": 1, "FALSE": 0}


def norm_table(tag):
    """XML 元素名可能带命名空间，取最后一段"""
    return tag.rsplit("}", 1)[-1]


def row_values(elem):
    """<Row Attr="v"> 与 <Row><Col>v</Col></Row> 两种写法都支持"""
    vals = dict(elem.attrib)
    for child in elem:
        tag = norm_table(child.tag)
        if tag in ("Row", "Where", "Set", "Update", "Delete"):
            continue
        vals[tag] = (child.text or "").strip()
    out = {}
    for k, v in vals.items():
        out[norm_table(k)] = BOOL_MAP.get(v, v)
    return out


def apply_file(conn, path, stats):
    try:
        tree = ET.parse(path)
    except Exception as e:
        stats["file_err"].append((os.path.basename(path), str(e)))
        return
    root = tree.getroot()
    cur = conn.cursor()
    for sect in root:
        tag = norm_table(sect.tag)
        if tag == "Update":
            table = sect.attrib.get("Table")
            where = {}
            sets = {}
            for sub in sect:
                st = norm_table(sub.tag)
                if st == "Where":
                    where.update(row_values(sub))
                elif st == "Set":
                    sets.update(row_values(sub))
            if not table or not sets or not where:
                continue
            # 列名一律加引号：Index / Domain / Type 之类是 SQLite 关键字，
            # 裸写会报 "near \"Index\": syntax error"（v24 前 IconDefinitions 全表因此没入库）
            cond = " AND ".join('"%s"=?' % k for k in where)
            sql = "UPDATE %s SET %s WHERE %s" % (
                table, ", ".join('"%s"=?' % k for k in sets), cond)
            try:
                cur.execute(sql, list(sets.values()) + list(where.values()))
                stats["updated"] += cur.rowcount if cur.rowcount > 0 else 0
            except Exception as e:
                stats["row_err"].append((table, "UPDATE: %s" % e))
        elif tag == "Delete":
            table = sect.attrib.get("Table")
            where = {}
            for sub in sect:
                if norm_table(sub.tag) == "Where":
                    where.update(row_values(sub))
            if not table or not where:
                continue
            cond = " AND ".join('"%s"=?' % k for k in where)
            try:
                cur.execute("DELETE FROM %s WHERE %s" % (table, cond), list(where.values()))
            except Exception as e:
                stats["row_err"].append((table, "DELETE: %s" % e))
        elif tag in ("Insert", "Replace", "Row"):
            continue
        else:
            table = tag
            for r in sect:
                if norm_table(r.tag) != "Row":
                    continue
                vals = row_values(r)
                if not vals:
                    continue
                cols = list(vals.keys())
                sql = "INSERT OR IGNORE INTO %s (%s) VALUES (%s)" % (
                    table, ", ".join('"%s"' % c for c in cols), ", ".join("?" * len(cols)))
                try:
                    cur.execute(sql, [vals[c] for c in cols])
                    stats["inserted"] += 1
                except Exception as e:
                    msg = str(e)
                    if "no such table" in msg:
                        stats["missing_tables"].add(table)
                    else:
                        stats["row_err"].append((table, msg))
    conn.commit()


def main():
    if not os.path.exists(SCHEMA):
        print("找不到 schema：%s" % SCHEMA)
        sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    # 游戏引擎自带的 Make_Hash：这里用 crc32 代替，只为让 Types/Kinds 的 Hash 唯一
    conn.create_function("Make_Hash", 1,
                         lambda x: zlib.crc32(str(x).encode("utf-8")) & 0x7FFFFFFF)
    with open(SCHEMA, encoding="utf-8-sig") as f:
        conn.executescript(f.read())
    if os.path.exists(TRIGGERS):
        with open(TRIGGERS, encoding="utf-8-sig") as f:
            conn.executescript(f.read())
    print("[1] schema 建库完成：%d 张表（含触发器）" % conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0])

    # LocalizedText 由本地化系统建表，玩法 schema 里没有；验证库里补建同构表
    conn.execute("""CREATE TABLE IF NOT EXISTS LocalizedText (
                      Tag TEXT NOT NULL, Language TEXT NOT NULL, Text TEXT,
                      PRIMARY KEY(Tag, Language))""")
    conn.commit()

    stats = {"inserted": 0, "updated": 0, "row_err": [], "file_err": [], "missing_tables": set()}
    n_files = 0
    for d in LOAD_ORDER:
        for p in sorted(glob.glob(os.path.join(d, "*.xml"))):
            apply_file(conn, p, stats)
            n_files += 1
    print("[2] 载入 %d 个 XML：插入 %d 行，更新 %d 行"
          % (n_files, stats["inserted"], stats["updated"]))
    if stats["missing_tables"]:
        print("    跳过（schema 无此表）：%s"
              % ", ".join(sorted(stats["missing_tables"])[:10]))
    if stats["row_err"]:
        print("    行级错误 %d 条，前 5 条：" % len(stats["row_err"]))
        for t, m in stats["row_err"][:5]:
            print("      [%s] %s" % (t, m[:120]))

    # 关键表体检
    key_tables = ["Modifiers", "ModifierArguments", "TraitModifiers", "Traits", "Types",
                  "CivilizationTraits", "Civilizations", "RequirementSets",
                  "RequirementSetRequirements", "Requirements", "RequirementArguments",
                  "DynamicModifiers", "UnitCommands", "BeliefModifiers", "PolicyModifiers",
                  "LocalizedText", "Units", "Eras", "Policies", "Beliefs"]
    print("[3] 关键表行数：")
    for t in key_tables:
        try:
            n = conn.execute("SELECT count(*) FROM %s" % t).fetchone()[0]
            print("    %-28s %6d" % (t, n))
        except Exception as e:
            print("    %-28s 读取失败: %s" % (t, e))

    conn.close()
    print("[4] 输出：%s" % DB_PATH)


if __name__ == "__main__":
    main()
