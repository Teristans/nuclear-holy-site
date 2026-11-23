# -*- coding: utf-8 -*-
"""install.py —— 把 mod/ 安装到文明6 的 Mods 目录，并逐字节复核。

用法：
    python install.py                       # 自动探测 Mods 目录
    python install.py --mods "D:/My Documents/My Games/Sid Meier's Civilization VI/Mods"
    python install.py --dry-run             # 只打印将要做什么，不写盘

为什么需要这个脚本：
  1) Civ6 的 Mods 目录经常不在 C 盘（文档目录被重定向到 D 盘是常见情况），
     注册表里读 Personal 才是真实位置，硬编码 %USERPROFILE%\\Documents 会装错地方。
  2) 装完必须复核「装进去的每个字节 == 仓库里的每个字节」。这在 v37~v41 那几轮
     吃过亏：游戏读的还是旧文件，却以为改动没生效。
  3) Civ6 只在**进程启动**时解析一次 modinfo，装完不重启等于没装。
     脚本会先检查 CivilizationVI.exe 是否在跑，在跑就直接拒绝。

退出码：0 成功 / 1 失败（找不到目录、游戏在跑、文件不一致）
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "mod")
TARGET_NAME = "NuclearHolySite"
GAME_EXE = "CivilizationVI.exe"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def walk_files(base):
    """返回 [(相对路径, 绝对路径)]，跳过 __pycache__ 之类。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        for fn in filenames:
            if fn.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(dirpath, fn)
            out.append((os.path.relpath(full, base), full))
    return sorted(out)


def candidate_mods_dirs():
    """按可信度排序的候选 Mods 目录。注册表 > 默认文档目录。"""
    docs = []
    # ① 注册表里的「文档」真实路径（文档被重定向到 D 盘时只有这里是对的）
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as k:
            v, _ = winreg.QueryValueEx(k, "Personal")
            if v:
                docs.append(v)
    except Exception:
        pass
    # ② 兜底：默认文档目录
    docs.append(os.path.join(os.path.expanduser("~"), "Documents"))

    seen, out = set(), []
    for d in docs:
        p = os.path.join(d, "My Games", "Sid Meier's Civilization VI", "Mods")
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def game_running():
    try:
        # tasklist 的输出是系统 ANSI 代码页（中文 Windows 是 cp936），
        # 用 text=True 会让 Python 按 UTF-8 解码并在 reader 线程里抛
        # UnicodeDecodeError —— 所以这里收 bytes 自己解。
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq " + GAME_EXE, "/NH"],
            capture_output=True, timeout=15,
        )
        out = (r.stdout or b"").decode("gbk", "ignore")
        return GAME_EXE.lower() in out.lower()
    except Exception:
        return False  # 查不到就不拦，只提示


def main():
    ap = argparse.ArgumentParser(description="安装 Nuclear Holy Site 到文明6 Mods 目录")
    ap.add_argument("--mods", help="Mods 目录的绝对路径（不填则自动探测）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写盘")
    args = ap.parse_args()

    if not os.path.isdir(SRC):
        print("[✗] 找不到源目录：%s" % SRC)
        return 1

    src_files = walk_files(SRC)
    if not src_files:
        print("[✗] mod/ 是空的")
        return 1
    if not any(f.endswith(".modinfo") for _, f in src_files):
        print("[✗] mod/ 里没有 .modinfo，不是合法的 mod 目录")
        return 1

    # 目标目录
    if args.mods:
        mods_dir, how = args.mods, "命令行指定"
    else:
        mods_dir, how = None, ""
        for cand in candidate_mods_dirs():
            if os.path.isdir(cand):
                mods_dir, how = cand, "自动探测"
                break
        if mods_dir is None:
            print("[✗] 找不到文明6 的 Mods 目录。请用 --mods 指定，例如：")
            print(r'    python install.py --mods "D:/My Documents/My Games/Sid Meier\'s Civilization VI/Mods"')
            return 1

    dest = os.path.join(mods_dir, TARGET_NAME)

    print("源目录   : %s（%d 个文件）" % (SRC, len(src_files)))
    print("目标目录 : %s（%s）" % (dest, how))

    if game_running():
        print()
        print("[✗] 检测到 %s 正在运行。" % GAME_EXE)
        print("    Civ6 只在进程启动时解析一次 modinfo，边跑边装等于没装。")
        print("    请**完全退出游戏进程**（不是回主菜单）后重新运行本脚本。")
        return 1

    # 计划
    plan_new, plan_upd, plan_same = [], [], []
    for rel, full in src_files:
        tgt = os.path.join(dest, rel)
        if not os.path.exists(tgt):
            plan_new.append(rel)
        elif sha256(full) != sha256(tgt):
            plan_upd.append(rel)
        else:
            plan_same.append(rel)

    print("待新增 %d / 待更新 %d / 已一致 %d" % (len(plan_new), len(plan_upd), len(plan_same)))
    for rel in plan_new:
        print("   + %s" % rel)
    for rel in plan_upd:
        print("   ~ %s" % rel)

    if args.dry_run:
        print("\n[--dry-run] 未写盘。")
        return 0

    # 复制
    os.makedirs(dest, exist_ok=True)
    for rel, full in src_files:
        tgt = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        shutil.copy2(full, tgt)

    # 逐字节复核
    bad = []
    for rel, full in src_files:
        tgt = os.path.join(dest, rel)
        if not os.path.exists(tgt) or sha256(full) != sha256(tgt):
            bad.append(rel)

    if bad:
        print("\n[✗] 有 %d 个文件复制后校验不一致：" % len(bad))
        for rel in bad:
            print("   %s" % rel)
        return 1

    # 目标目录里多出来的文件（旧版遗留）只警告，不删
    srcset = {rel for rel, _ in src_files}
    extra = [rel for rel, _ in walk_files(dest) if rel not in srcset]
    if extra:
        print("\n[!] 目标目录里有 %d 个源目录不存在的文件（多半是旧版遗留，本脚本不删）：" % len(extra))
        for rel in extra[:10]:
            print("   - %s" % rel)

    print("\n[✓] 已安装 %d 个文件到：\n    %s" % (len(src_files), dest))
    print("[✓] 逐字节校验通过（sha256 全一致）")
    print()
    # 版本号从源 modinfo 现读，避免提示文本与 modinfo 脱节（v46 时就是硬编码导致的过期提示）
    _ver = "?"
    try:
        import re as _re
        _mi = open(os.path.join(SRC, "NuclearHolySite.modinfo"), encoding="utf-8").read(2000)
        _m = _re.search(r'version="(\d+)"', _mi)
        if _m:
            _ver = "v" + _m.group(1)
    except Exception:
        pass
    print("下一步：启动游戏 → 额外内容 → 确认「皇帝之威 …（%s）」为启用状态 → 新开一局。" % _ver)
    print("注意：改的是 SQL 层时，老存档不会追溯生效（Civ6 在建局那一刻固化 modifier 集合）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
