# -*- coding: utf-8 -*-
"""
小哑巴 · 卡大仓 / Lil Mute · Warehouse Glitch

纯系统层工具：Windows 防火墙出站封禁 + 进程暂停/结束 + 全局热键。
不注入游戏、不读写内存、不改数据包，只调用系统自带功能。
界面支持中文 / English 切换。

用法 / Usage:
    python lil_mute.py               启动界面 / launch GUI
    python lil_mute.py --selftest    自检 / self-test (no system changes)
"""
from __future__ import annotations

import ctypes
import json
import locale
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from tkinter import messagebox, scrolledtext, ttk

APP_VER = "1.3.0"
APP_NAME = {"zh": "小哑巴 · 卡大仓", "en": "Lil Mute · Warehouse Glitch"}
APP_SHORT = {"zh": "小哑巴", "en": "Lil Mute"}
RULE_NAME = "LilMute-BlockOut"
RULE_PREFIX = "LilMute-"
GAME_EXE_NAMES = ("GTA5.exe", "GTA5_Enhanced.exe")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "lang": "",
    "delay": 0.0,
    "hold": 1.5,
    "suspend_seconds": 10,
    "hotkey_cut": "F8",
    "hotkey_restore": "F9",
    "accel_block": False,
    "accel_names": (
        "uu.exe,UUGameAssistant.exe,uu_booster.exe,"
        "XunyouClient.exe,XunyouAcc.exe,QiyouBox.exe,qiyou.exe,LeiShen.exe"
    ),
}

CREATE_NO_WINDOW = 0x08000000
MAX_PATH = 260
TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SUSPEND_RESUME = 0x0800
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NOREPEAT = 0x4000
VK_F8, VK_F9 = 0x77, 0x78

# 热键表：F1~F12 够用，避免引入键盘钩子
VK_TABLE = {f"F{i}": 0x6F + i for i in range(1, 13)}

# --------------------------------------------------------------------------
# 文案 / Strings
# --------------------------------------------------------------------------
STRINGS = {
    "zh": {
        "tab_main": "  主控 · 卡仓  ",
        "tab_net": "  网络  ",
        "tab_proc": "  进程  ",
        "tab_log": "  日志  ",
        "lbl_lang": "语言",
        "sec_status": "状态",
        "sec_params": "参数",
        "sec_notes": "说明",
        "st_detecting": "检测中…",
        "lbl_refresh": "刷新状态",
        "lbl_delay": "按下后延时(秒)：",
        "lbl_hold": "    断网持续(秒)：",
        "hint_flow": "流程：正常玩 → 到点按 F8 → 到期自动恢复网络，不用手动切网卡。",
        "btn_ka": "卡！(F8)",
        "btn_restore": "立即恢复 (F9)",
        "note_main": (
            "· 断网只封禁游戏进程本身（出站），浏览器 / 微信不受影响。\n"
            "· F8 / F9 是全局热键，游戏全屏时也生效。\n"
            "· 用完点“立即恢复”；直接关窗口也会自动解除封禁。\n"
            "· 本工具不注入、不读内存、不改数据包；但频繁卡 Bug 刷币仍可能被封号。"
        ),
        "game_running": "游戏进程：{name}  (PID {pid})",
        "game_none": "游戏进程：未运行",
        "net_blocked": "网络：已封禁（游戏断线中）",
        "net_ok": "网络：正常",
        "path_none": "程序：未检测到 GTA5.exe / GTA5_Enhanced.exe",
        "sec_fw": "防火墙规则（按程序出站封禁）",
        "rule_checking": "规则：检测中…",
        "rule_exists": "规则：已存在（封禁中）",
        "rule_none": "规则：不存在（正常）",
        "btn_block": "立即封禁",
        "btn_unblock": "解除封禁",
        "btn_refresh": "刷新",
        "btn_elevate": "以管理员重启",
        "sec_accel": "加速器（可选）",
        "chk_accel": "卡的时候把加速器进程也一起封禁",
        "lbl_accel_names": "加速器进程名（逗号分隔）：",
        "btn_accel_scan": "检测进程",
        "note_accel": (
            "· 加速器是驱动级接管游戏流量，只封游戏进程有时不管用；勾上这个，F8 会把加速器进程\n"
            "   也一起封掉，断网更彻底。\n"
            "· 进程名去任务管理器里看（右键加速器 → 打开文件位置），填进来即可。\n"
            "· 名字填错没有副作用：检测不到就只封游戏。"
        ),
        "log_accel_found": "检测到 {n} 个加速器进程：{list}",
        "log_accel_none": "没检测到配置里的加速器进程（不影响游戏封禁）",
        "log_accel_blocked": "✔ 同时封禁了 {n} 个加速器进程",
        "log_accel_skipped": "· 未检测到加速器进程，只封了游戏",
        "log_accel_fail": "⚠ 加速器进程封禁失败：{name}",
        "note_net": (
            "· 需要管理员权限；规则名固定为：\n"
            "   {rule}\n"
            "· 手动清理：高级安全 Windows Defender 防火墙 → 出站规则 → 删除同名规则，或执行\n"
            '   netsh advfirewall firewall delete rule name="{rule}"'
        ),
        "sec_proc": "进程操作（免注入）",
        "lbl_suspend": "暂停时长(秒)：",
        "btn_suspend": "暂停游戏",
        "btn_resume": "恢复运行",
        "btn_kill": "结束游戏进程",
        "note_proc": (
            "· 暂停进程 = 让游戏短暂冻结，常用来卡单；到点自动恢复，不会卡死。\n"
            "· 结束进程不会上传结算，是首脑 / 任务里常见的“保进度”操作。\n"
            "· 二者都是普通系统操作，不涉及注入或内存修改。"
        ),
        "btn_clear_log": "清空日志",
        "ready": "就绪",
        "status_cut": "已断网",
        "status_restored": "网络已恢复",
        "status_nothing": "无需恢复",
        "status_paused": "已暂停",
        "status_resumed": "已恢复",
        "status_fail_admin": "失败：缺管理员权限",
        "status_fail_nogame": "失败：游戏未运行",
        "status_fail_path": "失败：读不到路径",
        "status_fail_fw": "失败：防火墙拒绝",
        "log_started": "{app} v{ver} 启动（{lang}）",
        "log_admin_ok": "✔ 已获得管理员权限",
        "log_admin_no": "⚠ 未以管理员身份运行：防火墙封禁不可用，可点“以管理员重启”",
        "log_hotkeys_ok": "✔ 热键已注册：{cut} 卡 / {restore} 恢复",
        "log_hotkeys_applied": "✔ 热键已改为：{cut} 卡 / {restore} 恢复",
        "log_hotkey_bad": "✗ 不认识这个键名：{key}（只支持 F1 ~ F12）",
        "log_hotkey_fail": "⚠ 热键注册失败：{label}（可能被其他程序占用）",
        "tab_flow": "  流程  ",
        "sec_hotkeys": "热键（F8/F9 被占用就改这里）",
        "lbl_hotkey_cut": "卡的键：",
        "lbl_hotkey_restore": "恢复的键：",
        "btn_apply_hotkeys": "应用热键",
        "btn_open_guide": "打开教程 PDF",
        "btn_copy_fix": "复制清规则命令",
        "btn_copy_refs": "复制参考链接",
        "log_copied": "✔ 已复制到剪贴板",
        "log_guide_missing": "✗ 同目录下没找到 {name}，先把它放到工具旁边",
        "flow_pre": (
            "【前置条件 · 游戏里】\n"
            "1. 身份：注册 CEO（摩托帮 MC 不行，脚本会提示 You are in an MC）\n"
            "2. 仓库：已买特种货物仓库（你有 4 大仓 + 1 小仓）\n"
            "3. 位置：人站在你要操作的那个仓库里，否则提示「您不在您当前选择的仓库里!」\n"
            "4. 货物：仓库里要有货，空仓提示「您的仓库里已经没有板条箱」\n"
            "5. 战局：先卡单（进程页 → 暂停游戏 10 秒）把其他人清出去\n"
        ),
        "flow_gta": (
            "【GTA 里要先设好的东西】\n"
            "· 设置 → 显示 → 显示模式：选「无边框窗口」或「窗口」\n"
            "   独占全屏下部分系统/叠加层会吞掉全局热键，切窗口还会黑屏\n"
            "· 设置 → 图形：分辨率与桌面一致；别装激进的性能 mod\n"
            "· 设置 → 按键：确认 F8 / F9 没被占用；占了就改本工具的键（下面）\n"
            "· 叠加层：Discord / Steam / 加速器的 overlay 建议关，它们会抢热键\n"
            "· 加速器：用「进程 / 游戏模式」，别开全局代理或 TUN；并把进程名填进网络页\n"
        ),
        "flow_buy": (
            "【取货（进货）】\n"
            "方式 A（游戏内正规）：CEO 办公室或仓库的电脑 → 购买货物（1 / 2 / 3 箱）\n"
            "方式 B（菜单脚本）：Stand → Musiness Banager → Special Cargo，面板里有购买/补货相关开关\n"
            "   （源码里对应 SpecialCargoBuy* 与 BypassBuyCooldown：买货、跳过购买冷却）\n"
            "· 想全自动循环：加装 BusinessManager Cargo Add-On（自动出售 + 自动补货，可 AFK）\n"
            "· 大仓满载 111 箱；补货本身也是游戏交易，风险与出货同源\n"
        ),
        "flow_sell": (
            "【出货（卡价卖货）】\n"
            "1. Stand 菜单（默认热键 INSERT）→ Lua Scripts → Repository → 搜 Musiness Banager 安装\n"
            "   或手动把 MusinessBanagersource.lua 放进 %appdata%\\Stand\\Lua Scripts\n"
            "2. 在 Lua Scripts 列表里点它启动 → 出现「生意管理器」面板\n"
            "3. 进 Special Cargo（特种货物）→ 面板显示各仓库库存：特种货物仓库 {1}: {2}/{3}\n"
            "4. 选中你要出的那个仓（最多 5 个槽位）\n"
            "5. 打开 Max Sell Price（最大销售价格，源码默认 6000000）—— 这一步就是「卡价」\n"
            "6. 点 Sell A Crate（出售一个特种货物板条箱），点一次卖一箱\n"
            "7. 回游戏看现金 / 银行，到账即完成\n"
            "原理：脚本改写游戏全局变量（SpecialCargoRewardPerCrate、CrateMultiplier1/2/3）后\n"
            "走游戏自己的出售流程，属于菜单的内存写入；本工具不参与这一步，也不包含菜单。\n"
        ),
        "flow_refs": (
            "【参考项目 · GitHub】\n"
            "· calamity-inc/MusinessBanager —— 生意管理器本体（出售/补货/库存监控）\n"
            "· xhcherry/GTA5-Stand-LuaAIO —— 国内整合包，含 Musiness Banager 与中文翻译\n"
            "· AnnaThorne/BusinessManager-Cargo-Add-On —— 自动出售 + 自动补货循环\n"
            "· Perryx-20/cargo-loop-for-dummies —— 极简 cargo loop\n"
            "· mageangela/QuellGTA —— 断网 / 卡单 / 差传工具\n"
            "· LBWSIR/LBW-Cheat-Wiki —— 中文菜单文档与赚钱风险说明\n"
        ),
        "log_busy": "… 上一次卡还没结束，忽略本次",
        "log_delay_wait": "⏳ {delay:g} 秒后执行卡仓",
        "log_blocked": "✔ 已封禁 {name} 的出站流量",
        "log_auto_restore": "⏱ {hold:g} 秒后自动恢复",
        "log_unblocked": "✔ 已解除封禁，网络恢复",
        "log_no_rule": "· 当前没有封禁规则",
        "log_need_admin": "✗ 需要管理员权限才能改防火墙规则",
        "log_no_game": "✗ 未检测到游戏进程，先启动 GTA5 再卡",
        "log_no_path": "✗ 读不到游戏路径，请以管理员身份运行本工具",
        "log_block_fail": "✗ 封禁失败：{out}",
        "log_paused": "⏸ 已暂停 {name}，{seconds:g} 秒后自动恢复",
        "log_resumed": "▶ 已恢复 {name} 运行",
        "log_resume_fail": "✗ 恢复失败",
        "log_suspend_fail": "✗ 暂停失败，请以管理员身份运行",
        "log_killed": "✔ 已结束：{name}",
        "log_kill_fail": "✗ 结束失败：{name}",
        "log_lang": "· 界面语言已切换为 {lang}",
        "log_exit_unblock": "退出前已解除封禁，网络恢复正常",
        "dlg_confirm_title": "确认",
        "dlg_confirm_kill": "确定结束 {name} (PID {pid})？未结算的进度会丢失。",
        "st_selftest": "自检",
        "st_python": "Python",
        "st_admin": "管理员权限",
        "st_game": "游戏进程",
        "st_game_path": "游戏路径",
        "st_rule": "防火墙规则存在",
        "st_netsh": "netsh 可用",
        "st_not_running": "未运行",
        "st_read_fail": "(读取失败)",
        "st_yes": "是",
        "st_no": "否",
        "st_selftest_done": "自检结束（未修改任何系统设置）",
    },
    "en": {
        "tab_main": "  Main · Cargo  ",
        "tab_net": "  Network  ",
        "tab_proc": "  Process  ",
        "tab_log": "  Log  ",
        "lbl_lang": "Language",
        "sec_status": "Status",
        "sec_params": "Parameters",
        "sec_notes": "Notes",
        "st_detecting": "detecting…",
        "lbl_refresh": "Refresh",
        "lbl_delay": "Delay before cut (s):",
        "lbl_hold": "    Cut duration (s):",
        "hint_flow": "Flow: play normally → press F8 on cue → network restores automatically.",
        "btn_ka": "CUT! (F8)",
        "btn_restore": "RESTORE (F9)",
        "note_main": (
            "· Only the game process is blocked (outbound). Browser / chat apps are unaffected.\n"
            "· F8 / F9 are global hotkeys, they work while the game is fullscreen.\n"
            "· Press RESTORE when done; closing the window also clears the rule.\n"
            "· No injection, no memory access, no packet editing — but abusing glitches can still get you banned."
        ),
        "game_running": "Game process: {name}  (PID {pid})",
        "game_none": "Game process: not running",
        "net_blocked": "Network: blocked (game offline)",
        "net_ok": "Network: normal",
        "path_none": "Program: GTA5.exe / GTA5_Enhanced.exe not found",
        "sec_fw": "Firewall rule (block outbound by program)",
        "rule_checking": "Rule: detecting…",
        "rule_exists": "Rule: present (blocking)",
        "rule_none": "Rule: absent (normal)",
        "btn_block": "Block now",
        "btn_unblock": "Unblock",
        "btn_refresh": "Refresh",
        "btn_elevate": "Restart as admin",
        "sec_accel": "Game accelerator (optional)",
        "chk_accel": "Block the accelerator processes as well when cutting",
        "lbl_accel_names": "Accelerator process names (comma separated):",
        "btn_accel_scan": "Detect",
        "note_accel": (
            "· Accelerators take over the game's traffic at driver level, so blocking only the game\n"
            "   process sometimes does nothing. Tick this and F8 will block the accelerator too.\n"
            "· Get the process name from Task Manager (Details tab) and paste it here.\n"
            "· A wrong name is harmless: if nothing matches, only the game is blocked."
        ),
        "log_accel_found": "Found {n} accelerator process(es): {list}",
        "log_accel_none": "None of the configured accelerator processes are running (game blocking still works)",
        "log_accel_blocked": "✔ Also blocked {n} accelerator process(es)",
        "log_accel_skipped": "· No accelerator process found, blocked the game only",
        "log_accel_fail": "⚠ Failed to block accelerator process: {name}",
        "note_net": (
            "· Requires administrator rights. Rule name is fixed:\n"
            "   {rule}\n"
            "· To clean up manually: Windows Defender Firewall with Advanced Security → Outbound Rules, or run\n"
            '   netsh advfirewall firewall delete rule name="{rule}"'
        ),
        "sec_proc": "Process actions (no injection)",
        "lbl_suspend": "Suspend for (s):",
        "btn_suspend": "Suspend game",
        "btn_resume": "Resume",
        "btn_kill": "Kill game process",
        "note_proc": (
            "· Suspending freezes the game briefly (a common way to get a solo session); it auto-resumes.\n"
            "· Killing the process skips the save, commonly used to protect progress in challenges.\n"
            "· Both are plain OS operations, no injection or memory patching."
        ),
        "btn_clear_log": "Clear log",
        "ready": "Ready",
        "status_cut": "Blocked",
        "status_restored": "Network restored",
        "status_nothing": "Nothing to restore",
        "status_paused": "Suspended",
        "status_resumed": "Resumed",
        "status_fail_admin": "Failed: admin rights required",
        "status_fail_nogame": "Failed: game not running",
        "status_fail_path": "Failed: cannot read game path",
        "status_fail_fw": "Failed: firewall rejected",
        "log_started": "{app} v{ver} started ({lang})",
        "log_admin_ok": "✔ Administrator rights granted",
        "log_admin_no": "⚠ Not running as administrator: firewall blocking is unavailable, use “Restart as admin”",
        "log_hotkeys_ok": "✔ Hotkeys registered: {cut} cut / {restore} restore",
        "log_hotkeys_applied": "✔ Hotkeys changed to: {cut} cut / {restore} restore",
        "log_hotkey_bad": "✗ Unknown key name: {key} (F1 ~ F12 only)",
        "log_hotkey_fail": "⚠ Hotkey registration failed: {label} (already in use?)",
        "tab_flow": "  Workflow  ",
        "sec_hotkeys": "Hotkeys (change them if F8 / F9 are taken)",
        "lbl_hotkey_cut": "Cut key:",
        "lbl_hotkey_restore": "Restore key:",
        "btn_apply_hotkeys": "Apply",
        "btn_open_guide": "Open guide PDF",
        "btn_copy_fix": "Copy cleanup command",
        "btn_copy_refs": "Copy reference links",
        "log_copied": "✔ Copied to clipboard",
        "log_guide_missing": "✗ {name} was not found next to this tool",
        "flow_pre": (
            "[Prerequisites - in game]\n"
            "1. Be a CEO (an MC will not work, the script answers 'You are in an MC!')\n"
            "2. Own special cargo warehouses\n"
            "3. Stand inside the warehouse you are going to work on, otherwise the script warns\n"
            "   ('You are not in your currently selected warehouse!')\n"
            "4. The warehouse must have crates, otherwise ('no more crates in your warehouse')\n"
            "5. Isolate the session first: Process tab -> Suspend game for 10 s\n"
        ),
        "flow_gta": (
            "[GTA settings to set first]\n"
            "- Settings -> Display -> Display mode: 'Borderless Window' or 'Windowed'.\n"
            "  In exclusive fullscreen some systems/overlays swallow global hotkeys.\n"
            "- Settings -> Graphics: keep the resolution equal to your desktop; avoid aggressive perf mods.\n"
            "- Settings -> Key bindings: make sure F8 / F9 are free. If not, change them below.\n"
            "- Overlays: Discord / Steam / accelerator overlays compete for hotkeys - turn them off.\n"
            "- Accelerator: use process/game mode, not global proxy or TUN; paste its process name in Network.\n"
        ),
        "flow_buy": (
            "[Restock (buy crates)]\n"
            "A) In game: the laptop in your CEO office or warehouse -> buy 1 / 2 / 3 crates.\n"
            "B) Menu script: Stand -> Musiness Banager -> Special Cargo. It also handles buying\n"
            "   (in the source: SpecialCargoBuy* and BypassBuyCooldown).\n"
            "- Fully automatic loop: add BusinessManager Cargo Add-On (auto sell + auto resupply, AFK).\n"
            "- A large warehouse holds 111 crates. Restocking is a game transaction, same risk as selling.\n"
        ),
        "flow_sell": (
            "[Sell (price glitch)]\n"
            "1. Stand menu (default key INSERT) -> Lua Scripts -> Repository, install 'Musiness Banager'\n"
            "   or drop MusinessBanagersource.lua into %appdata%\\Stand\\Lua Scripts\n"
            "2. Start it from the Lua Scripts list\n"
            "3. Open Special Cargo - the panel lists your warehouses and stock\n"
            "4. Select the warehouse you want to empty (up to 5 slots)\n"
            "5. Turn on Max Sell Price (the source defaults to 6000000) - this is the price step\n"
            "6. Press 'Sell A Crate' - one crate per press\n"
            "7. Back in game, check cash / bank. Done.\n"
            "How it works: the script rewrites game globals (SpecialCargoRewardPerCrate,\n"
            "CrateMultiplier1/2/3) and then runs the game's own sale flow. That is a menu-side memory\n"
            "write; this tool does not take part in it and ships no menu.\n"
        ),
        "flow_refs": (
            "[Reference projects on GitHub]\n"
            "- calamity-inc/MusinessBanager - the business manager itself (sell / restock / stock monitor)\n"
            "- xhcherry/GTA5-Stand-LuaAIO - Chinese all-in-one pack with Musiness Banager\n"
            "- AnnaThorne/BusinessManager-Cargo-Add-On - automated sell + resupply loop\n"
            "- Perryx-20/cargo-loop-for-dummies - minimal cargo loop\n"
            "- mageangela/QuellGTA - network cut / session isolation tool\n"
            "- LBWSIR/LBW-Cheat-Wiki - Chinese menu docs and money-making risk notes\n"
        ),
        "log_busy": "… previous cut still running, ignored",
        "log_delay_wait": "⏳ cutting in {delay:g}s",
        "log_blocked": "✔ Blocked outbound traffic of {name}",
        "log_auto_restore": "⏱ auto-restore in {hold:g}s",
        "log_unblocked": "✔ Unblocked, network restored",
        "log_no_rule": "· no blocking rule present",
        "log_need_admin": "✗ Administrator rights are required to change firewall rules",
        "log_no_game": "✗ Game process not found — start GTA5 first",
        "log_no_path": "✗ Cannot read the game path, please run this tool as administrator",
        "log_block_fail": "✗ Block failed: {out}",
        "log_paused": "⏸ {name} suspended, auto-resume in {seconds:g}s",
        "log_resumed": "▶ {name} resumed",
        "log_resume_fail": "✗ Resume failed",
        "log_suspend_fail": "✗ Suspend failed, please run as administrator",
        "log_killed": "✔ Killed: {name}",
        "log_kill_fail": "✗ Kill failed: {name}",
        "log_lang": "· UI language switched to {lang}",
        "log_exit_unblock": "Unblocked before exit, network restored",
        "dlg_confirm_title": "Confirm",
        "dlg_confirm_kill": "Kill {name} (PID {pid})? Unsaved progress will be lost.",
        "st_selftest": "Self-test",
        "st_python": "Python",
        "st_admin": "Administrator",
        "st_game": "Game process",
        "st_game_path": "Game path",
        "st_rule": "Firewall rule exists",
        "st_netsh": "netsh available",
        "st_not_running": "not running",
        "st_read_fail": "(read failed)",
        "st_yes": "yes",
        "st_no": "no",
        "st_selftest_done": "Self-test finished (no system settings were changed)",
    },
}

_LANG = "zh"
_FORCE_LANG = ""


def set_lang(lang: str) -> str:
    """切换当前语言，返回实际生效的语言代码。"""
    global _LANG
    _LANG = lang if lang in STRINGS else "zh"
    return _LANG


def t(name: str, **kwargs) -> str:
    """取文案。找不到的键回退到中文，再回退到键名本身。"""
    text = STRINGS.get(_LANG, {}).get(name) or STRINGS["zh"].get(name) or name
    return text.format(**kwargs) if kwargs else text


# --------------------------------------------------------------------------
# Win32
# --------------------------------------------------------------------------
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
ntdll.NtSuspendProcess.argtypes = [wintypes.HANDLE]
ntdll.NtSuspendProcess.restype = ctypes.c_long
ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
ntdll.NtResumeProcess.restype = ctypes.c_long
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.GetMessageW.restype = ctypes.c_int


# --------------------------------------------------------------------------
# 基础工具 / Utilities
# --------------------------------------------------------------------------
def decode_output(data: bytes) -> str:
    """netsh 在中文系统上输出 GBK，统一解码。"""
    if not data:
        return ""
    for enc in (locale.getpreferredencoding(False), "utf-8", "gbk"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def run_hidden(cmdline: str):
    """执行命令行（不弹黑窗），返回 (返回码, 输出)。"""
    try:
        proc = subprocess.run(
            cmdline,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        return proc.returncode, decode_output(proc.stdout)
    except Exception as exc:  # 环境异常时不要让界面崩掉
        return -1, str(exc)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    """以管理员身份重启自己（会弹 UAC）。"""
    if getattr(sys, "frozen", False):
        args = sys.argv[1:]
    else:
        args = [os.path.abspath(sys.argv[0])] + sys.argv[1:]
    params = subprocess.list2cmdline(args)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)


def detect_system_lang() -> str:
    """按 Windows 界面语言猜一个默认值：中文系统 → zh，其余 → en。"""
    try:
        langid = kernel32.GetUserDefaultUILanguage()
        return "zh" if (langid & 0x3FF) == 0x04 else "en"
    except Exception:
        return "zh"


# --------------------------------------------------------------------------
# 进程 / Processes
# --------------------------------------------------------------------------
def iter_processes():
    """遍历 (pid, exe 名)。"""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        return
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            yield int(entry.th32ProcessID), entry.szExeFile
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)


def process_path(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def find_game():
    """返回 (pid, 进程名, 完整路径)；找不到返回 None。"""
    for pid, name in iter_processes():
        if name in GAME_EXE_NAMES:
            return pid, name, process_path(pid)
    return None


def suspend_process(pid: int) -> bool:
    handle = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
    if not handle:
        return False
    try:
        return ntdll.NtSuspendProcess(handle) == 0
    finally:
        kernel32.CloseHandle(handle)


def resume_process(pid: int) -> bool:
    handle = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
    if not handle:
        return False
    try:
        return ntdll.NtResumeProcess(handle) == 0
    finally:
        kernel32.CloseHandle(handle)


# --------------------------------------------------------------------------
# 防火墙 / Firewall（按程序出站封禁）
# --------------------------------------------------------------------------
def list_own_rules() -> list:
    """列出本工具建的所有出站规则（含加速器那几条），用于彻底清理。"""
    code, out = run_hidden("netsh advfirewall firewall show rule name=all dir=out")
    if code != 0:
        return []
    names = []
    for line in out.splitlines():
        for label in ("Rule Name", "规则名称"):
            if line.strip().startswith(label):
                value = line.split(":", 1)[-1].strip()
                if value.startswith(RULE_PREFIX):
                    names.append(value)
    return names


def find_processes_by_names(names) -> list:
    """按进程名找进程（不区分大小写），返回 [(pid, name, path)]。"""
    wanted = {n.strip().lower() for n in names if n and n.strip()}
    if not wanted:
        return []
    found = []
    for pid, name in iter_processes():
        if name.lower() in wanted:
            path = process_path(pid)
            if path:
                found.append((pid, name, path))
    return found


def accel_rule_name(process_name: str) -> str:
    return RULE_PREFIX + "Accel-" + os.path.splitext(process_name)[0]


def fw_is_blocked() -> bool:
    code, _ = run_hidden(f'netsh advfirewall firewall show rule name="{RULE_NAME}"')
    return code == 0


def fw_block(program_path: str, rule_name: str = RULE_NAME):
    run_hidden(f'netsh advfirewall firewall delete rule name="{rule_name}"')
    code, out = run_hidden(
        f'netsh advfirewall firewall add rule name="{rule_name}" dir=out '
        f'program="{program_path}" action=block enable=yes profile=any'
    )
    return code == 0, out.strip()


def fw_unblock() -> bool:
    """删掉本工具建的所有规则（游戏那条 + 加速器那几条）。"""
    removed = False
    for name in set(list_own_rules()) | {RULE_NAME}:
        code, _ = run_hidden(f'netsh advfirewall firewall delete rule name="{name}"')
        removed = removed or code == 0
    return removed


# --------------------------------------------------------------------------
# 配置 / Config
# --------------------------------------------------------------------------
def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    except Exception:
        pass
    if _FORCE_LANG in STRINGS:
        cfg["lang"] = _FORCE_LANG
    elif cfg.get("lang") not in STRINGS:
        cfg["lang"] = detect_system_lang()
    return cfg


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


# --------------------------------------------------------------------------
# 界面 / GUI
# --------------------------------------------------------------------------
class LilMute(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = load_config()
        set_lang(self.cfg["lang"])
        self.hotkey_queue = queue.Queue()
        self.timers = []
        self.busy = threading.Lock()
        self.hotkey_thread_id = 0

        self.geometry("740x620")
        self.minsize(680, 560)
        self._build_style()
        self._build_ui()
        self._start_hotkeys()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(150, self._pump)
        self.refresh_state()

        self.log(t("log_started", app=APP_NAME[_LANG], ver=APP_VER, lang=_LANG))
        self.log(t("log_admin_ok") if is_admin() else t("log_admin_no"))

    # ---------------- 语言 ----------------
    def _on_lang_change(self, _event=None) -> None:
        chosen = "zh" if self.lang_box.get() == "中文" else "en"
        if chosen == _LANG:
            return
        set_lang(chosen)
        self.cfg["lang"] = chosen
        save_config(self.cfg)
        self._rebuild()
        self.log(t("log_lang", lang=APP_NAME[_LANG]))

    def _rebuild(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self.title(f"{APP_NAME[_LANG]} v{APP_VER}")
        self._build_ui()
        self.refresh_state()

    # ---------------- 界面搭建 ----------------
    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Big.TButton", font=("Microsoft YaHei UI", 13, "bold"), padding=10)
        style.configure("TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10))

    def _build_ui(self) -> None:
        self.title(f"{APP_NAME[_LANG]} v{APP_VER}")

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(8, 0))
        ttk.Label(top, text=f"{t('lbl_lang')}:").pack(side="left")
        self.lang_box = ttk.Combobox(
            top, values=["中文", "English"], state="readonly", width=10
        )
        self.lang_box.set("中文" if _LANG == "zh" else "English")
        self.lang_box.pack(side="left", padx=6)
        self.lang_box.bind("<<ComboboxSelected>>", self._on_lang_change)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        self.tab_main = ttk.Frame(nb)
        self.tab_net = ttk.Frame(nb)
        self.tab_proc = ttk.Frame(nb)
        self.tab_flow = ttk.Frame(nb)
        self.tab_log = ttk.Frame(nb)
        nb.add(self.tab_main, text=t("tab_main"))
        nb.add(self.tab_net, text=t("tab_net"))
        nb.add(self.tab_proc, text=t("tab_proc"))
        nb.add(self.tab_flow, text=t("tab_flow"))
        nb.add(self.tab_log, text=t("tab_log"))

        self._build_main_tab()
        self._build_net_tab()
        self._build_proc_tab()
        self._build_flow_tab()
        self._build_log_tab()

        self.status = tk.StringVar(value=t("ready"))
        bar = ttk.Label(self, textvariable=self.status, anchor="w", relief="sunken", padding=(8, 4))
        bar.pack(fill="x", side="bottom")

    def _build_main_tab(self) -> None:
        f = self.tab_main
        box = ttk.LabelFrame(f, text=t("sec_status"), padding=10)
        box.pack(fill="x", padx=10, pady=8)
        self.game_var = tk.StringVar(value=t("st_detecting"))
        ttk.Label(box, textvariable=self.game_var).pack(anchor="w")
        self.net_var = tk.StringVar(value=t("st_detecting"))
        ttk.Label(box, textvariable=self.net_var).pack(anchor="w", pady=(4, 0))
        ttk.Button(box, text=t("lbl_refresh"), command=self.refresh_state).pack(anchor="e", pady=(6, 0))

        param = ttk.LabelFrame(f, text=t("sec_params"), padding=10)
        param.pack(fill="x", padx=10, pady=4)
        self.delay_var = tk.StringVar(value=str(self.cfg["delay"]))
        self.hold_var = tk.StringVar(value=str(self.cfg["hold"]))
        row = ttk.Frame(param)
        row.pack(anchor="w")
        ttk.Label(row, text=t("lbl_delay")).pack(side="left")
        ttk.Entry(row, textvariable=self.delay_var, width=6).pack(side="left")
        ttk.Label(row, text=t("lbl_hold")).pack(side="left")
        ttk.Entry(row, textvariable=self.hold_var, width=6).pack(side="left")
        ttk.Label(param, text=t("hint_flow"), foreground="#555555").pack(anchor="w", pady=(8, 0))

        act = ttk.Frame(f)
        act.pack(fill="x", padx=10, pady=14)
        ttk.Button(act, text=t("btn_ka"), style="Big.TButton", command=self.action_ka).pack(
            side="left", expand=True, fill="x", padx=(0, 6)
        )
        ttk.Button(act, text=t("btn_restore"), style="Big.TButton", command=self.action_restore).pack(
            side="left", expand=True, fill="x", padx=(6, 0)
        )

        hint = ttk.LabelFrame(f, text=t("sec_notes"), padding=10)
        hint.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        ttk.Label(hint, text=t("note_main"), justify="left").pack(anchor="w")

    def _build_net_tab(self) -> None:
        f = self.tab_net
        box = ttk.LabelFrame(f, text=t("sec_fw"), padding=10)
        box.pack(fill="x", padx=10, pady=8)
        self.rule_var = tk.StringVar(value=t("rule_checking"))
        ttk.Label(box, textvariable=self.rule_var).pack(anchor="w")
        self.path_var = tk.StringVar(value=t("path_none"))
        ttk.Label(box, textvariable=self.path_var, wraplength=650, justify="left").pack(
            anchor="w", pady=(4, 0)
        )
        btns = ttk.Frame(box)
        btns.pack(anchor="w", pady=(8, 0))
        ttk.Button(btns, text=t("btn_block"), command=lambda: self.do_block(None)).pack(side="left")
        ttk.Button(btns, text=t("btn_unblock"), command=self.action_restore).pack(side="left", padx=6)
        ttk.Button(btns, text=t("btn_refresh"), command=self.refresh_state).pack(side="left")
        self.admin_btn = ttk.Button(btns, text=t("btn_elevate"), command=self.do_elevate)
        self.admin_btn.pack(side="left", padx=6)

        accel = ttk.LabelFrame(f, text=t("sec_accel"), padding=10)
        accel.pack(fill="x", padx=10, pady=(0, 8))
        self.accel_chk_var = tk.BooleanVar(value=bool(self.cfg.get("accel_block")))
        ttk.Checkbutton(
            accel, text=t("chk_accel"), variable=self.accel_chk_var, command=self._save_accel
        ).pack(anchor="w")
        row = ttk.Frame(accel)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text=t("lbl_accel_names")).pack(side="left")
        self.accel_names_var = tk.StringVar(value=self.cfg.get("accel_names", ""))
        ttk.Entry(row, textvariable=self.accel_names_var).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(row, text=t("btn_accel_scan"), command=self.action_scan_accel).pack(side="left")
        ttk.Label(accel, text=t("note_accel"), justify="left").pack(anchor="w", pady=(6, 0))

        tip = ttk.LabelFrame(f, text=t("sec_notes"), padding=10)
        tip.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        ttk.Label(tip, text=t("note_net", rule=RULE_NAME), justify="left").pack(anchor="w")

    def _build_proc_tab(self) -> None:
        f = self.tab_proc
        box = ttk.LabelFrame(f, text=t("sec_proc"), padding=10)
        box.pack(fill="x", padx=10, pady=8)

        row = ttk.Frame(box)
        row.pack(anchor="w")
        self.suspend_var = tk.StringVar(value=str(self.cfg["suspend_seconds"]))
        ttk.Label(row, text=t("lbl_suspend")).pack(side="left")
        ttk.Entry(row, textvariable=self.suspend_var, width=6).pack(side="left")
        ttk.Button(row, text=t("btn_suspend"), command=self.action_suspend).pack(side="left", padx=8)
        ttk.Button(row, text=t("btn_resume"), command=self.action_resume).pack(side="left")

        row2 = ttk.Frame(box)
        row2.pack(anchor="w", pady=(10, 0))
        ttk.Button(row2, text=t("btn_kill"), command=self.action_kill).pack(side="left")

        tip = ttk.LabelFrame(f, text=t("sec_notes"), padding=10)
        tip.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        ttk.Label(tip, text=t("note_proc"), justify="left").pack(anchor="w")

    def _build_log_tab(self) -> None:
        f = self.tab_log
        self.log_box = scrolledtext.ScrolledText(
            f, height=20, font=("Consolas", 9), state="disabled", wrap="word"
        )
        self.log_box.pack(fill="both", expand=True, padx=10, pady=8)
        ttk.Button(f, text=t("btn_clear_log"), command=self.clear_log).pack(
            anchor="e", padx=10, pady=(0, 10)
        )

    def _build_flow_tab(self) -> None:
        """流程页：把「取货 → 出货」的脚本菜单操作和 GTA 设置放在游戏旁边就能看。"""
        f = self.tab_flow
        body = "\n".join((
            t("flow_pre"), t("flow_gta"), t("flow_buy"), t("flow_sell"), t("flow_refs"),
        ))
        self.flow_box = scrolledtext.ScrolledText(
            f, height=18, font=("Microsoft YaHei UI", 9), wrap="word"
        )
        self.flow_box.pack(fill="both", expand=True, padx=10, pady=(8, 4))
        self.flow_box.insert("end", body)
        self.flow_box.configure(state="disabled")

        hot = ttk.LabelFrame(f, text=t("sec_hotkeys"), padding=8)
        hot.pack(fill="x", padx=10, pady=(0, 6))
        row = ttk.Frame(hot)
        row.pack(anchor="w")
        keys = [f"F{i}" for i in range(1, 13)]
        ttk.Label(row, text=t("lbl_hotkey_cut")).pack(side="left")
        self.hotkey_cut_var = tk.StringVar(value=self.cfg.get("hotkey_cut", "F8"))
        ttk.Combobox(row, textvariable=self.hotkey_cut_var, values=keys, width=5,
                     state="readonly").pack(side="left", padx=(0, 12))
        ttk.Label(row, text=t("lbl_hotkey_restore")).pack(side="left")
        self.hotkey_restore_var = tk.StringVar(value=self.cfg.get("hotkey_restore", "F9"))
        ttk.Combobox(row, textvariable=self.hotkey_restore_var, values=keys, width=5,
                     state="readonly").pack(side="left", padx=(0, 12))
        ttk.Button(row, text=t("btn_apply_hotkeys"), command=self.action_apply_hotkeys).pack(side="left")

        btns = ttk.Frame(f)
        btns.pack(anchor="w", padx=10, pady=(0, 10))
        ttk.Button(btns, text=t("btn_open_guide"), command=self.action_open_guide).pack(side="left")
        ttk.Button(btns, text=t("btn_copy_fix"), command=self.action_copy_cleanup).pack(
            side="left", padx=6
        )
        ttk.Button(btns, text=t("btn_copy_refs"), command=self.action_copy_refs).pack(side="left")

    # ---------------- 日志 / 状态 ----------------
    def log(self, text: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {text}\n"
        try:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", line)
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        except tk.TclError:
            pass

    def log_async(self, text: str) -> None:
        """从后台线程写日志：丢进队列，由主线程落笔，避免跨线程操作 Tk。"""
        self.hotkey_queue.put(("log", text))

    def _save_accel(self) -> None:
        self.cfg["accel_block"] = bool(self.accel_chk_var.get())
        self.cfg["accel_names"] = self.accel_names_var.get().strip()
        save_config(self.cfg)

    def _accel_names(self) -> list:
        return [n.strip() for n in str(self.accel_names_var.get()).split(",") if n.strip()]

    def action_scan_accel(self) -> None:
        self._save_accel()
        found = find_processes_by_names(self._accel_names())
        if found:
            self.log(t(
                "log_accel_found",
                n=len(found),
                list=", ".join(f"{name} (PID {pid})" for pid, name, _ in found),
            ))
        else:
            self.log(t("log_accel_none"))

    def action_apply_hotkeys(self) -> None:
        cut = str(self.hotkey_cut_var.get()).strip().upper()
        restore = str(self.hotkey_restore_var.get()).strip().upper()
        bad = [k for k in (cut, restore) if k not in VK_TABLE]
        if bad:
            self.log(t("log_hotkey_bad", key=", ".join(bad)))
            return
        self.cfg["hotkey_cut"], self.cfg["hotkey_restore"] = cut, restore
        save_config(self.cfg)
        self._start_hotkeys()
        self.log(t("log_hotkeys_applied", cut=cut, restore=restore))

    def _app_dir(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.abspath(__file__))

    def action_open_guide(self) -> None:
        base = self._app_dir()
        for name in ("lil-mute-guide-zh.pdf", "小哑巴-卡大仓-使用教程.pdf"):
            path = os.path.join(base, name)
            if os.path.exists(path):
                os.startfile(path)  # noqa: S606 - Windows 专用
                self.log(f"· 打开教程：{name}")
                return
        self.log(t("log_guide_missing", name="lil-mute-guide-zh.pdf"))

    def _copy(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.log(t("log_copied"))

    def action_copy_cleanup(self) -> None:
        self._copy(f'netsh advfirewall firewall delete rule name="{RULE_NAME}"')

    def action_copy_refs(self) -> None:
        self._copy("\n".join((
            "https://github.com/calamity-inc/MusinessBanager",
            "https://github.com/xhcherry/GTA5-Stand-LuaAIO",
            "https://github.com/AnnaThorne/BusinessManager-Cargo-Add-On",
            "https://github.com/Perryx-20/cargo-loop-for-dummies",
            "https://github.com/mageangela/QuellGTA",
            "https://github.com/LBWSIR/LBW-Cheat-Wiki",
        )))

    def clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def set_status(self, text: str) -> None:
        self.status.set(text)

    def refresh_state(self):
        game = find_game()
        if game:
            pid, name, path = game
            self.game_var.set(t("game_running", name=name, pid=pid))
            self.path_var.set(path or t("st_read_fail"))
        else:
            self.game_var.set(t("game_none"))
            self.path_var.set(t("path_none"))
        blocked = fw_is_blocked()
        self.net_var.set(t("net_blocked") if blocked else t("net_ok"))
        self.rule_var.set(t("rule_exists") if blocked else t("rule_none"))
        self.admin_btn.state(["disabled"] if is_admin() else ["!disabled"])
        return blocked

    # ---------------- 全局热键 ----------------
    def _start_hotkeys(self) -> None:
        # 先掐掉上一轮的热键线程：线程退出时系统会自动注销它注册的热键
        if self.hotkey_thread_id:
            user32.PostThreadMessageW(self.hotkey_thread_id, WM_QUIT, 0, 0)
            self.hotkey_thread_id = 0
            time.sleep(0.35)  # 等旧线程真正退出，避免注册冲突

        cut_key = str(self.cfg.get("hotkey_cut", "F8")).strip().upper()
        restore_key = str(self.cfg.get("hotkey_restore", "F9")).strip().upper()

        def worker():
            self.hotkey_thread_id = int(kernel32.GetCurrentThreadId())
            failed = []
            for hk_id, key in ((1, cut_key), (2, restore_key)):
                vk = VK_TABLE.get(key)
                if not vk:
                    self.hotkey_queue.put(("tlog", ("log_hotkey_bad", {"key": key})))
                    failed.append(key)
                    continue
                if not user32.RegisterHotKey(None, hk_id, MOD_NOREPEAT, vk):
                    self.hotkey_queue.put(("tlog", ("log_hotkey_fail", {"label": key})))
                    failed.append(key)
            if not failed:
                self.hotkey_queue.put(
                    ("tlog", ("log_hotkeys_ok", {"cut": cut_key, "restore": restore_key}))
                )
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    self.hotkey_queue.put(("hotkey", int(msg.wParam)))

        threading.Thread(target=worker, daemon=True, name="hotkeys").start()

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.hotkey_queue.get_nowait()
                if kind == "hotkey":
                    self.action_ka() if payload == 1 else self.action_restore()
                elif kind == "tlog":
                    key, kwargs = payload
                    self.log(t(key, **kwargs))
                elif kind == "log":
                    self.log(str(payload))
                elif kind == "call":
                    payload()
        except queue.Empty:
            pass
        except Exception as exc:  # 队列里的动作出错也不能让界面停摆
            self.log(f"✗ {exc}")
        self.after(150, self._pump)

    # ---------------- 动作 ----------------
    def _read_float(self, var, default: float) -> float:
        try:
            return max(0.0, float(str(var.get()).strip()))
        except ValueError:
            return default

    def _cancel_timers(self) -> None:
        for timer in self.timers:
            timer.cancel()
        self.timers.clear()

    def _schedule(self, seconds: float, func) -> None:
        # 定时回调统一回到主线程执行，避免后台线程直接操作 Tk
        timer = threading.Timer(seconds, lambda: self.hotkey_queue.put(("call", func)))
        timer.daemon = True
        self.timers.append(timer)
        timer.start()

    def do_block(self, hold):
        """封禁游戏出站流量；hold 秒后自动恢复（None = 一直封到手动解除）。"""
        if not is_admin():
            self.log(t("log_need_admin"))
            self.set_status(t("status_fail_admin"))
            return False
        game = find_game()
        if not game:
            self.log(t("log_no_game"))
            self.set_status(t("status_fail_nogame"))
            return False
        _pid, name, path = game
        if not path:
            self.log(t("log_no_path"))
            self.set_status(t("status_fail_path"))
            return False
        ok, out = fw_block(path)
        if not ok:
            self.log(t("log_block_fail", out=out))
            self.set_status(t("status_fail_fw"))
            return False
        self.log(t("log_blocked", name=name))
        if self.cfg.get("accel_block"):
            blocked = 0
            for _apid, aname, apath in find_processes_by_names(self._accel_names()):
                ok_accel, _ = fw_block(apath, accel_rule_name(aname))
                if ok_accel:
                    blocked += 1
                else:
                    self.log(t("log_accel_fail", name=aname))
            self.log(t("log_accel_blocked", n=blocked) if blocked else t("log_accel_skipped"))
        self.set_status(t("status_cut"))
        self.refresh_state()
        if hold is not None:
            self._schedule(hold, self.action_restore)
            self.log(t("log_auto_restore", hold=hold))
        return True

    def action_ka(self) -> None:
        if not self.busy.acquire(blocking=False):
            self.log(t("log_busy"))
            return
        delay = self._read_float(self.delay_var, 0.0)
        hold = self._read_float(self.hold_var, 1.5)
        self.cfg.update({"delay": delay, "hold": hold})
        save_config(self.cfg)

        def worker():
            try:
                if delay > 0:
                    self.log_async(t("log_delay_wait", delay=delay))
                    time.sleep(delay)
                self.hotkey_queue.put(("call", lambda: self.do_block(hold)))
            finally:
                self.busy.release()

        threading.Thread(target=worker, daemon=True).start()

    def action_restore(self) -> None:
        self._cancel_timers()
        if fw_unblock():
            self.log(t("log_unblocked"))
            self.set_status(t("status_restored"))
        else:
            self.log(t("log_no_rule"))
            self.set_status(t("status_nothing"))
        self.refresh_state()

    def action_suspend(self) -> None:
        seconds = self._read_float(self.suspend_var, 10.0)
        self.cfg["suspend_seconds"] = seconds
        save_config(self.cfg)
        game = find_game()
        if not game:
            self.log(t("log_no_game"))
            return
        pid, name, _ = game
        if suspend_process(pid):
            self.log(t("log_paused", name=name, seconds=seconds))
            self.set_status(t("status_paused"))
            self._schedule(seconds, lambda: self._resume_pid(pid, name))
        else:
            self.log(t("log_suspend_fail"))

    def _resume_pid(self, pid: int, name: str) -> None:
        if resume_process(pid):
            self.log(t("log_resumed", name=name))
            self.set_status(t("status_resumed"))
        else:
            self.log(t("log_resume_fail"))

    def action_resume(self) -> None:
        game = find_game()
        if not game:
            self.log(t("log_no_game"))
            return
        self._resume_pid(game[0], game[1])

    def action_kill(self) -> None:
        game = find_game()
        if not game:
            self.log(t("log_no_game"))
            return
        pid, name, _ = game
        if messagebox.askyesno(t("dlg_confirm_title"), t("dlg_confirm_kill", name=name, pid=pid)):
            code, _ = run_hidden(f"taskkill /PID {pid} /F")
            self.log(t("log_killed", name=name) if code == 0 else t("log_kill_fail", name=name))
            self.refresh_state()

    def do_elevate(self) -> None:
        relaunch_as_admin()
        self.destroy()

    # ---------------- 退出 ----------------
    def on_close(self) -> None:
        try:
            if fw_is_blocked():
                fw_unblock()
                self.log(t("log_exit_unblock"))
            self._cancel_timers()
            game = find_game()
            if game:
                resume_process(game[0])
        finally:
            self.destroy()


# --------------------------------------------------------------------------
# 自检 / Self-test（不开界面、不改系统设置）
# --------------------------------------------------------------------------
def _pad(label: str, width: int = 18) -> str:
    """按显示宽度对齐（中日韩字符占两格）。"""
    disp = sum(2 if ord(ch) > 0x2E80 else 1 for ch in label)
    return label + " " * max(1, width - disp)


def selftest() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    cfg = load_config()
    set_lang(cfg["lang"])
    print(f"{APP_NAME[_LANG]} v{APP_VER} — {t('st_selftest')}")
    print(f"  {_pad(t('st_python'))}: {sys.version.split()[0]}")
    print(f"  {_pad(t('st_admin'))}: {t('st_yes') if is_admin() else t('st_no')}")
    game = find_game()
    if game:
        pid, name, path = game
        print(f"  {_pad(t('st_game'))}: {name} (PID {pid})")
        print(f"  {_pad(t('st_game_path'))}: {path or t('st_read_fail')}")
    else:
        print(f"  {_pad(t('st_game'))}: {t('st_not_running')}")
    print(f"  {_pad(t('st_rule'))}: {t('st_yes') if fw_is_blocked() else t('st_no')}")
    code, _ = run_hidden("netsh advfirewall show allprofiles state")
    print(f"  {_pad(t('st_netsh'))}: {t('st_yes') if code == 0 else t('st_no')}")
    print(f"  {t('st_selftest_done')}")
    return 0


def main() -> int:
    global _FORCE_LANG
    if "--en" in sys.argv:
        _FORCE_LANG = "en"
    elif "--zh" in sys.argv:
        _FORCE_LANG = "zh"
    if "--selftest" in sys.argv:
        return selftest()
    app = LilMute()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
