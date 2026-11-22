#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""lua_check.py — 用 Civ6 自带的 Havok Script 编译器做 Lua 语法校验。

为什么不用标准 Lua 解释器：
    Civ6 用的是 Havok Script（Firaxis 的 Lua 5.1 分支），不是 stock Lua。
    实测它不支持 `goto` / `//`，与 5.1 一致，但若用 Lua 5.4 校验会放过
    5.1 不合法的写法。本脚本直接加载游戏目录下的
        Base/Binaries/Win64Steam/HavokScript_FinalRelease.dll
    调用导出的 C API `luaL_newstate` / `luaL_loadbuffer` / `lua_tolstring`，
    校验结果与游戏内加载时的判定**完全同源**，且零安装。

    导出名是 MSVC 修饰名，故下方用常量硬编码；若游戏大版本更新导致
    导出表变化，脚本会明确报错而不是静默通过。

用法：
    python lua_check.py                # 校验本 mod + AgriculturalDistrict
    python lua_check.py -p 某个目录     # 指定目录（可多次 -p）
    python lua_check.py --all-mods      # 校验全部已启用 mod 的 Lua
    python lua_check.py --selftest      # 反向测试：确认校验器真能抓错
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys

# ---- MSVC 修饰名（x64） ----
SYM_NEWSTATE = r"?luaL_newstate@@YAPEAUlua_State@@XZ"
SYM_LOADBUF = r"?luaL_loadbuffer@@YAHPEAUlua_State@@PEBD_K1@Z"
SYM_TOLSTRING = r"?lua_tolstring@@YAPEBDPEAUlua_State@@HPEA_K@Z"
SYM_SETTOP = r"?lua_settop@@YAXPEAUlua_State@@H@Z"
SYM_CLOSE = r"?lua_close@@YAXPEAUlua_State@@@Z"

GAME_BIN = (os.path.join(os.environ["CIV6_DIR"], "Base", "Binaries", "Win64Steam")
            if os.environ.get("CIV6_DIR")
            else r"D:\SteamLibrary\steamapps\common\Sid Meier's Civilization VI\Base\Binaries\Win64Steam")
DLL_NAME = "HavokScript_FinalRelease.dll"

PROJECT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TARGETS = [
    os.path.join(PROJECT, "mod", "lua"),
    r"D:\My Documents\My Games\Sid Meier's Civilization VI\Mods\AgriculturalDistrict",
]


class LuaCompiler:
    """对 Havok Script DLL 的薄封装。"""

    def __init__(self, game_bin: str = GAME_BIN):
        dll = os.path.join(game_bin, DLL_NAME)
        if not os.path.isfile(dll):
            raise SystemExit(
                f"[FATAL] 找不到 {DLL_NAME}\n  期望路径: {dll}\n"
                "  请确认游戏安装位置，或用 --game-bin 指定 Binaries/Win64Steam 目录。"
            )
        os.add_dll_directory(game_bin)
        self.lib = ctypes.WinDLL(dll)

        try:
            self._newstate = self.lib[SYM_NEWSTATE]
            self._loadbuf = self.lib[SYM_LOADBUF]
            self._tolstr = self.lib[SYM_TOLSTRING]
            self._settop = self.lib[SYM_SETTOP]
            self._close = self.lib[SYM_CLOSE]
        except AttributeError as exc:              # 导出表变了
            raise SystemExit(
                f"[FATAL] {DLL_NAME} 缺少预期导出符号：{exc}\n"
                "  可能游戏版本更新改变了 Lua 运行时；本脚本需要重新适配，"
                "不要当作『校验通过』处理。"
            ) from exc

        self._newstate.restype = ctypes.c_void_p
        self._loadbuf.restype = ctypes.c_int
        self._loadbuf.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                  ctypes.c_size_t, ctypes.c_char_p]
        self._tolstr.restype = ctypes.c_char_p
        self._tolstr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self._settop.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._close.argtypes = [ctypes.c_void_p]

        self.state = self._newstate()
        if not self.state:
            raise SystemExit("[FATAL] luaL_newstate() 返回空指针，无法建立编译上下文。")

    def compile(self, source: bytes, chunkname: str) -> tuple[bool, str]:
        """编译但不执行。返回 (是否通过, 错误信息)。

        每个 chunk 编译后必须 `lua_settop(L, 0)` 清栈：成功时编译产物
        （一个 function）被压栈，`lua_tolstring` **不会** 弹栈，不清就会
        随文件数线性累积，几百个文件后触发栈上限而崩溃或被误判。
        """
        name = chunkname.encode("utf-8", "replace")
        rc = self._loadbuf(self.state, source, len(source), name)
        if rc == 0:
            self._settop(self.state, 0)          # 丢弃编译产物，防止栈累积
            return True, ""
        err = self._tolstr(self.state, -1, None)
        msg = (err or b"<no error message>").decode("utf-8", "replace")
        self._settop(self.state, 0)
        return False, msg

    def close(self) -> None:
        if self.state:
            self._close(self.state)
            self.state = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def read_source(path: str) -> bytes:
    """按字节读取。Lua 只关心字节序列，转换编码没有意义且可能引入差异。"""
    with open(path, "rb") as fh:
        return fh.read()


def collect_lua(paths: list[str]) -> list[str]:
    out: list[str] = []
    for p in paths:
        if os.path.isfile(p) and p.lower().endswith(".lua"):
            out.append(p)
        elif os.path.isdir(p):
            for root, _, files in os.walk(p):
                for fn in files:
                    if fn.lower().endswith(".lua"):
                        out.append(os.path.join(root, fn))
    return sorted(set(out))


def enabled_mods_lua() -> list[str]:
    """从 Mods.sqlite 取已启用 mod 的 Lua 文件路径。"""
    import sqlite3

    db = os.path.join(os.environ["LOCALAPPDATA"], "Firaxis Games",
                      "Sid Meier's Civilization VI", "Mods.sqlite")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT s.Path FROM Mods m
           JOIN ScannedFiles s ON s.ScannedFileRowId = m.ScannedFileRowId
           JOIN ModGroupItems gi ON gi.ModRowId = m.ModRowId
                AND gi.ModGroupRowId = 1 AND gi.Disabled = 0"""
    ).fetchall()
    roots = []
    for r in rows:
        mi = os.path.abspath(r["Path"])
        if os.path.isfile(mi):
            roots.append(os.path.dirname(mi))
    return collect_lua(roots)


def selftest(cc: LuaCompiler) -> int:
    """反向测试：故意喂错误代码，确认校验器不是永远返回 True。"""
    cases = [
        (b"local a = 1\n", True, "最小合法代码"),
        (b"function f()\n  return 1\n", False, "缺 end"),
        (b"local x = (1 + 2\n", False, "括号未闭合"),
        (b"if true then\n", False, "缺 end 的 if"),
        (b"local s = 'abc\n", False, "字符串未闭合"),
        (b"end\n", False, "多余的 end"),
        (b"goto done\n::done::\n", False, "goto（Lua 5.1 不支持）"),
        (b"local a = 7 // 2\n", False, "整除 //（Lua 5.1 不支持）"),
    ]
    bad = 0
    for src, expect_ok, desc in cases:
        ok, err = cc.compile(src, "selftest")
        mark = "✓" if ok == expect_ok else "✗"
        if ok != expect_ok:
            bad += 1
        detail = "" if ok else "  → " + err.splitlines()[0][:70]
        print(f"  {mark} {desc:<24} 期望{'通过' if expect_ok else '报错'}，实际{'通过' if ok else '报错'}{detail}")
    print()
    if bad:
        print(f"反向测试失败 {bad} 项：校验器行为不可信，禁止据其结论放行代码。")
        return 1
    print("反向测试全部符合预期，校验器可信。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="用 Civ6 的 Havok Script 校验 Lua 语法")
    ap.add_argument("-p", "--path", action="append", default=None,
                    help="要校验的目录或 .lua 文件，可重复")
    ap.add_argument("--all-mods", action="store_true", help="校验全部已启用 mod 的 Lua")
    ap.add_argument("--selftest", action="store_true", help="只跑反向测试")
    ap.add_argument("--game-bin", default=GAME_BIN, help="Binaries/Win64Steam 目录")
    args = ap.parse_args()

    with LuaCompiler(args.game_bin) as cc:
        if args.selftest:
            return selftest(cc)

        targets = args.path if args.path else list(DEFAULT_TARGETS)
        files = collect_lua(targets)
        if args.all_mods:
            files = sorted(set(files) | set(enabled_mods_lua()))
        if not files:
            print("没有找到任何 .lua 文件。检查路径是否正确。")
            return 2

        fails = []
        for fp in files:
            try:
                src = read_source(fp)
            except OSError as exc:
                fails.append((fp, f"读取失败: {exc}"))
                continue
            rel = fp.replace("\\", "/")
            ok, err = cc.compile(src, os.path.basename(fp))
            if not ok:
                fails.append((fp, err))

        head = "Lua 语法校验（Havok Script / Lua 5.1）"
        print(head)
        print("=" * len(head))
        print(f"文件数: {len(files)}   通过: {len(files) - len(fails)}   失败: {len(fails)}")
        for fp in files:
            rel = os.path.relpath(fp, PROJECT) if fp.startswith(PROJECT) else fp
            bad = next((e for p, e in fails if p == fp), None)
            if bad:
                print(f"  [FAIL] {rel}")
            else:
                print(f"  [ OK ] {rel}")
        if fails:
            print("\n错误明细:")
            for fp, err in fails:
                rel = os.path.relpath(fp, PROJECT) if fp.startswith(PROJECT) else fp
                print(f"\n  {rel}")
                for line in err.splitlines():
                    print(f"      {line}")
            return 1
        print("\n全部通过。")
        return 0


if __name__ == "__main__":
    sys.exit(main())
