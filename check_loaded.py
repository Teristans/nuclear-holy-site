#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""check_loaded.py —— 核对「上一次游戏启动到底加载了哪几个 NHS 文件」

为什么需要它：
  Civ6 只在**进程启动**时解析 modinfo 的 <InGameActions> 并缓存动作列表。
  之后在游戏内读档 / 重开新局，都只是重放这份缓存，不会再读一次 modinfo。
  所以「改完文件 → 游戏内读档」永远不会生效，而失败时数据库和 Lua 都不报错，
  只会静默地什么都不发生（本项目已因此浪费过两轮排查：v7.28~v7.30 三个版本
  全部未加载，却不报任何错）。

  判据不是「文件是否存在」，而是 Modding.log 里有没有 `UpdateDatabase - Loading`
  这一行。本脚本把「上次启动实际加载的集合」与「modinfo 现在声明的集合」对账。

用法：
    python check_loaded.py            # 对账
    python check_loaded.py --quiet    # 只在有缺失时输出（供 verify 调用）
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
MODINFO_NAME = "NuclearHolySite.modinfo"
MODINFO = os.path.join(HERE, "mod", MODINFO_NAME)
LOG = os.path.join(
    os.environ.get("LOCALAPPDATA", r"C:\Users\Smart\AppData\Local"),
    "Firaxis Games", "Sid Meier's Civilization VI", "Logs", "Modding.log")

ACTION_TAGS = ("UpdateDatabase", "UpdateIcons", "UpdateText",
               "AddGameplayScripts", "AddUserInterfaces", "ImportFiles")


def strip_ns(tag):
    return tag.rsplit("}", 1)[-1]


def declared_files():
    """modinfo 里 <InGameActions> 声明的文件，按出现顺序，去重。"""
    root = ET.parse(MODINFO).getroot()
    out = []
    for e in root.iter():
        if strip_ns(e.tag) != "InGameActions":
            continue
        for act in e:
            if strip_ns(act.tag) not in ACTION_TAGS:
                continue
            for f in act:
                if strip_ns(f.tag) == "File" and f.text:
                    p = f.text.strip()
                    if p not in out:
                        out.append(p)
        break
    return out


def loaded_blocks():
    """最近一次游戏启动实际加载的 NHS 文件集合。

    Civ6 在**同一次启动**里分两批加载本 mod，v7.36 实测确认：
      批 1（前端阶段）: LocalizedText / GameplayScripts / UpdateIcons
                        → text/nhs_text.xml、lua/nhs_wonder_watch.lua、data/nhs_icons.xml
                        日志时间戳 12180.25x，位于 3383-3388 行
      批 2（进入游戏）: UpdateDatabase 的 17 个 SQL + data/nhs_notifications.xml
                        日志时间戳 12186.4~5，位于 4859-4891 行

    早期实现只保留「最后一个连续块」，于是整批 1 被漏掉，误报 3 个文件
    「从未被加载」——而它们其实都在。现改为：定位最后一次
    "Initializing Modding Framework."，取其后的全部 NHS 记录并集。

    脚本类动作的日志动词是 Registering，不是 Loading（踩过这个误报）。
    """
    if not os.path.exists(LOG):
        return None, []

    pat = re.compile(r"^\[([\d.]+)\] (UpdateDatabase|UpdateIcons|UpdateText|"
                     r"LocalizedText) - Loading (.+?)\s*$"
                     r"|^\[([\d.]+)\] GameplayScripts - Registering (.+?)\s*$")

    # 第一遍：最后一次启动的起始行（modinfo 解析与动作重放都在其后）
    start = 0
    with open(LOG, encoding="utf-8", errors="ignore") as fh:
        for i, line in enumerate(fh, 1):
            if "Initializing Modding Framework." in line:
                start = i

    # 第二遍：取该次启动内的全部 NHS 记录（跨批次并集）
    seen, uniq, first_ts = set(), [], None
    with open(LOG, encoding="utf-8", errors="ignore") as fh:
        for i, line in enumerate(fh, 1):
            if i <= start:
                continue
            m = pat.match(line)
            if not m:
                continue
            if m.group(3) is not None:          # Loading 类
                stamp, path = m.group(1), m.group(3)
            else:                                # Registering 类（Lua）
                stamp, path = m.group(4), m.group(5)
            if not ("/Mods/NuclearHolySite/" in path
                    or path.startswith(("sql/nhs_", "lua/nhs_", "data/nhs_", "text/nhs_"))):
                continue
            rel = path.split("/Mods/NuclearHolySite/")[-1] if "/Mods/NuclearHolySite/" in path else path
            if rel in seen:
                continue
            seen.add(rel)
            uniq.append((stamp, rel))
            if first_ts is None:
                first_ts = stamp

    if not uniq:
        return None, []
    return first_ts, uniq


def stale_files():
    """已加载、但文件内容比日志更晚改动过的文件。

    为什么需要这一层：上面的 loaded_blocks 只比对**文件名**。
    一旦某个文件以前加载过、这轮又改了内容，名字仍在列表里 → 显示 OK，
    但游戏里跑的其实是旧内容。v7.34 就撞上过：nhs_13_amenities.sql 被改到
    00:13，进程 21:54 就启动了，可对账结果仍是 [OK]，因为旧版本早就加载过。

    判据：Modding.log 只在**启动时**写入，所以「文件 mtime 晚于 log 的 mtime」
     ≈ 「改完之后没再启动过」。这是近似，不是铁证（touch 一下也会触发），
    所以只作提示，不下结论。

    特别地，modinfo 自身也必须在检查范围内。它不出现在 declared_files() 里
    （那是它声明的内容），但它才是动作列表与 LoadOrder 的源头。v7.35 就撞上过：
    只改了 modinfo 的 LoadOrder，本脚本仍报「全部已加载，且没有改动早于最后一次
    启动的文件」——而那正是最需要重启的一类改动。加载过哪些文件是旧值、顺序是旧值，
    库里就会少行，却一切显示正常。
    """
    if not os.path.exists(LOG):
        return []
    try:
        log_mtime = os.path.getmtime(LOG)
    except OSError:
        return []
    _ts, loaded = loaded_blocks()
    out = []
    for _, rel in loaded:
        p = os.path.join(HERE, "mod", rel.replace("/", os.sep))
        try:
            if os.path.exists(p) and os.path.getmtime(p) > log_mtime + 1:
                out.append(rel)
        except OSError:
            continue
    # modinfo 自身（不在 loaded 列表里，单独查）
    try:
        if (os.path.exists(MODINFO)
                and os.path.getmtime(MODINFO) > log_mtime + 1):
            out.append(MODINFO_NAME)
    except OSError:
        pass
    return out


def main():
    quiet = "--quiet" in sys.argv

    decl = declared_files()
    ts, loaded = loaded_blocks()

    if ts is None:
        print("！ Modding.log 里找不到本 mod 的任何加载记录。")
        print("  要么还没启用这个 mod，要么日志被清过。先启动一次游戏再看。")
        return 1

    loaded_set = {rel for _, rel in loaded}
    missing = [f for f in decl if f not in loaded_set]
    extra = [rel for _, rel in loaded if rel not in decl]
    stale = [f for f in stale_files() if f not in missing]

    if not quiet:
        import datetime
        print("=" * 62)
        print("modinfo 声明 %d 个文件，上次启动加载 %d 个" % (len(decl), len(loaded)))
        print("=" * 62)
        # modinfo 自身排在最前：它不参与 declared 对账，却是动作列表与 LoadOrder
        # 的源头，改了它而不重启，整个执行顺序都还是旧的。
        if os.path.exists(MODINFO):
            print("  [%s] %-34s %s" % (
                "过期" if MODINFO_NAME in stale else "OK  ",
                MODINFO_NAME,
                datetime.datetime.fromtimestamp(
                    os.path.getmtime(MODINFO)).strftime("%m-%d %H:%M")))
            print("  " + "-" * 56)
        for f in decl:
            if f not in loaded_set:
                mark = "缺失"
            elif f in stale:
                mark = "过期"
            else:
                mark = "OK  "
            mtime = ""
            p = os.path.join(HERE, "mod", f.replace("/", os.sep))
            if os.path.exists(p):
                import datetime
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M")
            print("  [%s] %-34s %s" % (mark, f, mtime))
        if extra:
            print("\n  已加载但 modinfo 现在不再声明（多为改名/删除）：")
            for e in extra:
                print("    -", e)

    if missing:
        print("\n" + "!" * 62)
        print("有 %d 个文件从未被加载：" % len(missing))
        for m in missing:
            print("    -", m)
        print("!" * 62)
        print("原因几乎总是同一个：**写完文件后没有退出并重启游戏**。")
        print("Civ6 只在进程启动时读一次 modinfo；游戏内读档不会重新解析。")

    if stale:
        print("\n" + "~" * 62)
        print("有 %d 个文件加载过、但之后又被改动了 —— 游戏里跑的是旧内容：" % len(stale))
        for s in stale:
            print("    -", s)
        print("~" * 62)
        print("这类「名字在列表里所以显示 OK」的假象，比从未加载更难发现：")
        print("对账通过、双校验全绿、游戏里却什么也没变。")
        if MODINFO_NAME in stale:
            print()
            print("其中 modinfo 这一项格外要紧：它决定动作列表与 LoadOrder。")
            print("不重启就仍是旧的建库顺序 —— 克隆源 trait/belief 尚不存在时，")
            print("INSERT...SELECT 会静默插入 0 条，不报错、不留痕。")

    if missing or stale:
        print()
        print("正确步骤（两类问题都一样）：")
        print("  1. 完全退出文明6（不是回主菜单，是退出进程）")
        print("  2. 重新启动游戏")
        print("  3. 数据库类改动（SQL）还需要**新开一局**；只重载 Lua 的改动读档即可")
        return 1

    if not quiet:
        print("\n全部已加载，且没有改动早于最后一次启动的文件。" + ("（首次加载时间戳 %s）" % ts if ts else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
