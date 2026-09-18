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
import hashlib
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
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    import pickup as pickup_mod

    HAS_PICKUP = pickup_mod.HAS_AUDIO and pickup_mod.HAS_KEYS
except Exception:
    pickup_mod = None
    HAS_PICKUP = False

APP_VER = "2.1.1"
APP_NAME = {"zh": "小哑巴 · 卡大仓", "en": "Lil Mute · Warehouse Glitch"}
APP_SHORT = {"zh": "小哑巴", "en": "Lil Mute"}
RULE_NAME = "LilMute-BlockOut"
RULE_PREFIX = "LilMute-"
GAME_EXE_NAMES = ("GTA5.exe", "GTA5_Enhanced.exe")


def app_dir() -> str:
    """程序所在目录。打包成 exe 后 __file__ 指向临时解压目录，必须用 sys.executable。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(app_dir(), "config.json")

DEFAULT_CONFIG = {
    "lang": "",
    "delay": 0.0,
    "hold": 1.5,
    "suspend_seconds": 10,
    "hotkey_cut": "F8",
    "hotkey_restore": "F9",
    "accel_block": False,
    "accel_dir": "",
    "accel_names": (
        "uu.exe,UUGameAssistant.exe,uu_booster.exe,"
        "XunyouClient.exe,XunyouAcc.exe,QiyouBox.exe,qiyou.exe,LeiShen.exe"
    ),
    "pickup_device": "",
    "pickup_avg": 25.0,
    "pickup_peak": 45.0,
    "pickup_rounds": 85,
    "pickup_wait_min": 48.0,
    "seq_to_story": "",
    "seq_to_invite": "",
    "seq_confirm": "",
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

COLOR_OK = "#1A7F37"
COLOR_BAD = "#CF222E"
COLOR_MUTED = "#57606A"

# --------------------------------------------------------------------------
# 文案 / Strings
# --------------------------------------------------------------------------
STRINGS = {
    "zh": {
        "tab_main": "  手动工具（备用）  ",
        "tab_manual": "  ② 手动工具（备用）  ",
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
            "· 只断游戏（和加速器）进程，浏览器 / 微信不受影响\n"
            "· F8 卡 / F9 恢复；关窗口会自动解除封禁\n"
            "· 不注入、不读内存；频繁刷币有封号风险"
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
        "chk_advanced": "显示高级选项（加速器封禁 —— 只有手动断网时才需要）",
        "lbl_accel_names": "加速器进程名（逗号分隔）：",
        "btn_accel_scan": "检测进程",
        "lbl_accel_dir": "加速器目录：",
        "btn_browse": "浏览",
        "note_accel": (
            "填加速器安装目录最省事：该目录下在跑的进程会一起封掉"
        ),
        "log_accel_found": "检测到 {n} 个加速器进程：{list}",
        "log_accel_none": "没检测到配置里的加速器进程（不影响游戏封禁）",
        "log_accel_blocked": "✔ 同时封禁了 {n} 个加速器进程",
        "log_accel_skipped": "· 未检测到加速器进程，只封了游戏",
        "log_accel_fail": "⚠ 加速器进程封禁失败：{name}",
        "note_net": "规则名 {rule}；清理命令可在「流程」页一键复制",
        "st_accel_on": "加速器：已启用封禁",
        "st_accel_off": "加速器：未启用",
        "accel_scan_none": "未匹配到进程（加速器没启动时就是这个结果）",
        "accel_scan_hit": "已匹配 {n} 个进程",
        "lbl_accel_names_adv": "进程名：",
        "sec_proc": "进程操作（免注入）",
        "lbl_suspend": "暂停时长(秒)：",
        "btn_suspend": "暂停游戏",
        "btn_resume": "恢复运行",
        "btn_kill": "结束游戏进程",
        "note_proc": (
            "· 暂停 = 短暂冻结游戏，用来卡单；到点自动恢复\n"
            "· 结束进程不会上传结算，任务里常用来保进度"
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
        "tab_flow": "  说明  ",
        "tab_pickup": "  ① 自动取货（主功能）  ",
        "banner": "主功能是「① 自动取货」：挂机把大仓取满。其余页签是手动 / 辅助操作，用不到可以不管。",
        "sec_audio": "音频（WASAPI 回环，不需要虚拟声卡）",
        "lbl_device": "设备：",
        "btn_refresh_devices": "刷新设备",
        "lbl_level": "实时音量：平均 {avg:.0f} / 峰值 {peak:.0f}",
        "btn_test_listen": "测试监听 30 秒",
        "btn_test_pad": "测试按键",
        "log_test_pad_ok": "✔ 按键模拟可用（已发送一次 Shift）",
        "log_test_pad_fail": "✗ 按键模拟不可用：{err}",
        "lbl_thresholds": "触发阈值：",
        "lbl_avg_th": "平均 ≥",
        "lbl_peak_th": "峰值 ≥",
        "sec_loop": "循环参数",
        "lbl_wait_min": "先等（分钟）：",
        "lbl_rounds": "循环次数：",
        "sec_seq": "按键序列（第一次用必须在游戏里校准）",
        "lbl_seq_story": "切故事：",
        "lbl_seq_invite": "切邀请战局：",
        "lbl_seq_confirm": "确认弹窗：",
        "btn_seq_default": "恢复默认序列",
        "btn_start_pickup": "开始自动取货",
        "btn_stop_pickup": "停止",
        "st_pickup_idle": "就绪",
        "st_pickup_running": "运行中：第 {i}/{n} 轮",
        "log_pickup_nodep": "✗ 缺少依赖（soundcard / numpy / vgamepad），自动取货不可用",
        "log_test_listen": "· 测试监听 30 秒，请让游戏发出那个声音……",
        "log_test_done": "· 测试结束，峰值 {peak:.0f}（阈值 {peak_th:.0f}）",
        "log_seq_help": (
            "序列写法：wait 秒数 等待；esc / enter / up / down / left / right / q / e / space / tab 等按键，"
            "后面可跟次数。例如：esc, wait 2, e, down 1, enter。运行时游戏窗口要保持在前台。"
        ),
        "log_pickup_started": "▶ 自动取货开始：等 {wait:g} 分钟，循环 {rounds} 轮",
        "log_pickup_stopped": "■ 自动取货已停止",
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
            "【这个插件帮你做什么 / 你要手动做什么】\n"
            "■ 插件负责（全自动）：\n"
            "   · 听游戏声音，抓「该断网的那一瞬间」\n"
            "   · 到时自动断网 → 自动确认「保存失败」弹窗 → 自动恢复网络\n"
            "   · 用模拟键盘切故事模式、切邀请战局\n"
            "   · 每一轮写日志；出错会告诉你哪一步不对\n"
            "■ 你要手动做（只有这些，做完一次就够）：\n"
            "   1. 关掉游戏加速器（必须）2. 游戏改窗口模式（建议 1024×768）\n"
            "   3. 声音里关掉「游戏失去焦点时静音」4. 在大仓派员工取货，看到 -$7,500\n"
            "   5. 出生点设室内（推荐游戏厅）6. 先做一次音频校准 + 按键校准\n"
            "   7. 启动后别切窗口——GTA 要保持在前台\n"
            "■ 时间与等待（心里有数，就不会以为卡住了）：\n"
            "   ·「先等 48 分钟」是给员工取货的时间，这期间工具什么都不做，正常\n"
            "   · 每轮约 1.5~2 分钟：切故事 12 秒 → 切战局 20 秒 → 音频稳定 8 秒 →\n"
            "     等信号（最多 3 分钟，没等到就跳过这一轮）→ 断网 → 等 12 秒 → 确认 → 等 10 秒 → 再确认\n"
            "   · 85 轮大约 2~3 小时，中途不用管；想停就点「停止」，它会先恢复网络\n"
            "────────────────────────────────────────\n"
            "【第 1 步 · 前置条件（游戏里先弄好）】\n"
            "1. 关掉游戏加速器 —— 防火墙要能真断，加速器会干扰（和手动断网场景相反）\n"
            "2. 设置 → 图像：屏幕类型改「窗口模式」，分辨率建议 1024×768（更稳）\n"
            "3. 设置 → 声音：把「游戏失去焦点时静音」改成关闭（要在后台听声音）\n"
            "4. 大仓里派员工出去取货：一定要看到 -$7,500，并且员工已离开仓库\n"
            "   派了哪几个仓，就只给这几个仓取货\n"
            "5. 出生点设室内（推荐游戏厅，能在大屏看大仓库存）；别选机库、别选带浴室的地点\n"
            "6. 本工具用管理员身份运行（改防火墙需要）\n"
        ),
        "flow_gta": (
            "【这个「卡」到底卡的是什么】\n"
            "正常玩法：花 $7,500 派员工取货 → 等 48 分钟 → 带回 1~3 箱。大仓满仓 111 箱，\n"
            "正常要跑几十趟、几十小时。\n"
            "卡法：员工取货回来、游戏要写存档的那一刻切断网络（游戏会提示「保存失败」），\n"
            "货物已经进仓，这次却不算数 → 马上再切一次战局重复，大仓很快就满了。\n"
            "工具干的事只有三件：模拟手柄按键（切模式/切战局/确认）+ 听声音抓时机 + 开关防火墙。\n"
            "不注入、不读内存、不改数据包。\n"
        ),
        "flow_buy": (
            "【第 2 步 · 校准音频】（自动取货页上半部分）\n"
            "1. 设备：选游戏声音输出的那个设备（列出来的都是可回环录制的）\n"
            "2. 点「测试监听 30 秒」→ 让游戏发出那个声音（进入战局/员工交货的音效）\n"
            "   看「实时音量」的峰值跳到多少；不跳就换一个设备再试\n"
            "3. 把阈值定在「峰值跳起来时的一半左右」，例如峰值 60 → 阈值 平均 25 / 峰值 45\n"
            "4. 嫌麻烦就先用默认 25 / 45，跑一轮看日志再调\n"
        ),
        "flow_sell": (
            "【第 3 步 · 校准按键序列】（自动取货页下半部分）\n"
            "序列写法：wait 秒数 = 等待；a / b / y / start / back / up / down / left / right / lb / rb = 按键，\n"
            "后面可以跟次数。例：start, wait 2, rb 1, a, wait 1, down 1, a\n"
            "· 切故事 / 切邀请战局 / 确认弹窗 三条都要在你的游戏里试一次\n"
            "· 试法：先手动把游戏切到对应界面，点「开始自动取货」看它按得对不对，不对就改序列再试\n"
            "· 默认序列是按中文版菜单写的起点，不同版本/语言可能要改「按几次、往哪走」\n"
        ),
        "flow_refs": (
            "【第 4 步 · 正式跑】\n"
            "1. 先把员工派出去取货（-$7,500），人待在大仓里\n"
            "2. 「先等（分钟）」填 48：给员工足够时间把货取回来\n"
            "3. 「循环次数」填 85：大致能把大仓取满（一次 1~3 箱）\n"
            "4. 点「开始自动取货」→ 然后别再碰键鼠，它会自己切模式、断网、确认\n"
            "5. 看日志：出现「✔ 听到信号」「✔ 已断网」就是对的；连着几轮「没等到信号」就要调低阈值\n"
            "6. 循环结束后回游戏确认左下角「保存成功」，手动同步一次存档\n"
            "【风险】断网卡存档属于卡 Bug，收益异常仍可能被风控；别一次刷太满，别贪。\n"
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
        "tab_main": "  Manual tools (fallback)  ",
        "tab_manual": "  2. Manual tools (fallback)  ",
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
            "· Only the game (and accelerator) processes are cut — browser / chat apps stay online\n"
            "· F8 to cut, F9 to restore; closing the window clears the rules\n"
            "· No injection, no memory access; farming glitches can still get you flagged"
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
        "chk_advanced": "Show advanced options (accelerator blocking - only needed for a manual cut)",
        "lbl_accel_names": "Accelerator process names (comma separated):",
        "btn_accel_scan": "Detect",
        "lbl_accel_dir": "Accelerator folder:",
        "btn_browse": "Browse",
        "note_accel": (
            "Point it at the accelerator's install folder: every process running from there is cut too"
        ),
        "log_accel_found": "Found {n} accelerator process(es): {list}",
        "log_accel_none": "None of the configured accelerator processes are running (game blocking still works)",
        "log_accel_blocked": "✔ Also blocked {n} accelerator process(es)",
        "log_accel_skipped": "· No accelerator process found, blocked the game only",
        "log_accel_fail": "⚠ Failed to block accelerator process: {name}",
        "note_net": "Rule name: {rule}. Copy the cleanup command from the Workflow tab.",
        "st_accel_on": "Accelerator: blocked too",
        "st_accel_off": "Accelerator: off",
        "accel_scan_none": "No processes matched (expected while the accelerator is off)",
        "accel_scan_hit": "Matched {n} process(es)",
        "lbl_accel_names_adv": "Process names:",
        "sec_proc": "Process actions (no injection)",
        "lbl_suspend": "Suspend for (s):",
        "btn_suspend": "Suspend game",
        "btn_resume": "Resume",
        "btn_kill": "Kill game process",
        "note_proc": (
            "· Suspend freezes the game briefly (a common way to get a solo session); it auto-resumes\n"
            "· Killing the process skips the save, useful to protect progress in challenges"
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
        "tab_flow": "  Guide  ",
        "tab_pickup": "  1. Auto pickup (main)  ",
        "banner": (
            "The main feature is 1. Auto pickup (fills a warehouse while you AFK). "
            "The other tabs are manual / fallback helpers."
        ),
        "sec_audio": "Audio (WASAPI loopback - no virtual cable needed)",
        "lbl_device": "Device:",
        "btn_refresh_devices": "Refresh",
        "lbl_level": "Live level: avg {avg:.0f} / peak {peak:.0f}",
        "btn_test_listen": "Test 30 s",
        "btn_test_pad": "Test gamepad",
        "log_test_pad_ok": "✔ Keyboard simulation works (sent one Shift)",
        "log_test_pad_fail": "✗ Keyboard simulation unavailable: {err}",
        "lbl_thresholds": "Trigger:",
        "lbl_avg_th": "avg ≥",
        "lbl_peak_th": "peak ≥",
        "sec_loop": "Loop",
        "lbl_wait_min": "Wait (min):",
        "lbl_rounds": "Rounds:",
        "sec_seq": "Key sequences (calibrate once in game)",
        "lbl_seq_story": "To story:",
        "lbl_seq_invite": "To invite:",
        "lbl_seq_confirm": "Confirm:",
        "btn_seq_default": "Restore defaults",
        "btn_start_pickup": "Start auto pickup",
        "btn_stop_pickup": "Stop",
        "st_pickup_idle": "Ready",
        "st_pickup_running": "Running: round {i}/{n}",
        "log_pickup_nodep": "✗ Missing dependencies (soundcard / numpy / vgamepad)",
        "log_test_listen": "· Listening for 30 s - let the game play the cue sound…",
        "log_test_done": "· Test finished, peak {peak:.0f} (threshold {peak_th:.0f})",
        "log_seq_help": (
            "Sequence syntax: 'wait N' to pause; esc / enter / up / down / left / right / q / e / "
            "space / tab to press, with an optional repeat count. Keep the game window focused."
        ),
        "log_pickup_started": "▶ Auto pickup started: wait {wait:g} min, {rounds} rounds",
        "log_pickup_stopped": "■ Auto pickup stopped",
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
            "[What the plugin does / what you do by hand]\n"
            "* The plugin handles (fully automatic):\n"
            "  - listens to the game audio to catch the exact moment\n"
            "  - cuts the network, confirms the 'save failed' dialog, restores the network\n"
            "  - switches story mode / invite session with simulated keyboard input\n"
            "  - logs every round, and tells you which step failed\n"
            "* You do by hand (once):\n"
            "  1. accelerator OFF  2. windowed mode (1024x768)  3. 'mute when not in focus' OFF\n"
            "  4. send warehouse staff out (-$7,500)  5. spawn indoors (arcade)\n"
            "  6. calibrate audio + keys once  7. keep the game window focused while it runs\n"
            "* Waiting, so you do not think it froze:\n"
            "  - 'wait 48 min' is for the staff to come back; the tool idles during it\n"
            "  - each round ~1.5-2 min: story 12s -> invite 20s -> audio settle 8s ->\n"
            "    wait for the cue (max 3 min, skipped if missed) -> cut -> 12s -> confirm -> 10s -> confirm\n"
            "  - 85 rounds take roughly 2-3 hours; press Stop any time to abort safely\n"
            "----------------------------------------\n"
            "[Step 1 - in-game prerequisites]\n"
            "1. Turn the game accelerator OFF - the firewall must really cut, accelerators interfere\n"
            "2. Settings -> Graphics: screen type 'Windowed', 1024x768 is the most stable\n"
            "3. Settings -> Audio: turn 'Mute game when not in focus' OFF (audio is read in background)\n"
            "4. Send warehouse staff out to collect: you must see -$7,500 and the staff leaving\n"
            "5. Spawn indoors (arcade recommended); avoid hangars and properties with a bathroom\n"
            "6. Run this tool as administrator (firewall rules)\n"
        ),
        "flow_gta": (
            "[What is actually being glitched]\n"
            "Normal: pay $7,500 to send staff out, wait 48 minutes, they bring back 1-3 crates.\n"
            "A large warehouse holds 111 crates, so it takes dozens of hours by hand.\n"
            "The trick: cut the network at the moment the game tries to save -> 'save failed', the\n"
            "crates are already in the warehouse but this round does not count -> repeat.\n"
            "The tool does three things: gamepad keys, listening for the cue, toggling the firewall.\n"
            "No injection, no memory access, no packet editing.\n"
        ),
        "flow_buy": (
            "[Step 2 - calibrate audio] (top half of the Auto pickup tab)\n"
            "1. Pick the device your game plays through\n"
            "2. Hit 'Test 30 s', let the game play the cue, watch the live peak\n"
            "3. Set the thresholds to roughly half of that peak (peak 60 -> avg 25 / peak 45)\n"
            "4. Or keep the defaults and read the log after one round\n"
        ),
        "flow_sell": (
            "[Step 3 - calibrate the key sequences] (bottom half)\n"
            "Syntax: 'wait N' pauses; a / b / y / start / back / up / down / left / right / lb / rb press,\n"
            "optionally followed by a repeat count.\n"
            "- Test all three sequences in your own game; edit them if a step lands wrong\n"
            "- The defaults are a starting point for the Chinese UI; versions differ\n"
        ),
        "flow_refs": (
            "[Step 4 - the real run]\n"
            "1. Send the staff out (-$7,500) and stay inside the warehouse\n"
            "2. 'Wait (min)' = 48, 'Rounds' = 85 (fills a large warehouse)\n"
            "3. Hit 'Start auto pickup' and then keep your hands off keyboard and mouse\n"
            "4. Watch the log: 'heard the signal' + 'cut' means it works; several missed rounds means\n"
            "   your thresholds are too high\n"
            "5. When it finishes, confirm 'save successful' in game and sync the save manually\n"
            "[Risk] This is a save-blocking glitch. Abnormal income can still be flagged - do not be greedy.\n"
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


def accel_rule_name(program_path: str) -> str:
    """按完整路径生成规则名：同名但不同路径的进程不会互相顶掉。"""
    digest = hashlib.md5(program_path.lower().encode("utf-8")).hexdigest()[:8]
    return RULE_PREFIX + "Accel-" + digest


def find_processes_by_dir(folder: str) -> list:
    """找可执行文件位于该目录（含子目录）下的所有运行中进程。"""
    folder = (folder or "").strip().strip('"').rstrip("\\/")
    if not folder:
        return []
    root = os.path.normcase(os.path.normpath(folder))
    found = []
    for pid, name in iter_processes():
        path = process_path(pid)
        if not path:
            continue
        full = os.path.normcase(os.path.normpath(path))
        if full == root or full.startswith(root + os.sep):
            found.append((pid, name, path))
    return found


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
        self.pickup_thread = None
        self.pickup_stop = None
        self.audio_test_running = False

        self.geometry("780x800")
        self.minsize(700, 660)
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

        tk.Label(
            self, text=t("banner"), anchor="w", justify="left", wraplength=700,
            fg="#0B5FFF", font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(fill="x", padx=10, pady=(8, 0))

        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=(4, 0))
        ttk.Label(top, text=f"{t('lbl_lang')}:").pack(side="left")
        self.lang_box = ttk.Combobox(
            top, values=["中文", "English"], state="readonly", width=10
        )
        self.lang_box.set("中文" if _LANG == "zh" else "English")
        self.lang_box.pack(side="left", padx=6)
        self.lang_box.bind("<<ComboboxSelected>>", self._on_lang_change)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        self.tab_pickup = ttk.Frame(nb)
        # "手动断网 / 进程 / 网络" 合并成一页：它们都是手动操作和它的配置，
        # 分成三页只会让用户分不清和主功能的关系
        self.tab_manual = ttk.Frame(nb)
        self.tab_main = self.tab_manual
        self.tab_net = self.tab_manual
        self.tab_proc = self.tab_manual
        self.tab_flow = ttk.Frame(nb)
        self.tab_log = ttk.Frame(nb)
        nb.add(self.tab_pickup, text=t("tab_pickup"))
        nb.add(self.tab_manual, text=t("tab_manual"))
        nb.add(self.tab_flow, text=t("tab_flow"))
        nb.add(self.tab_log, text=t("tab_log"))

        self._build_main_tab()
        self._build_proc_tab()
        self._build_net_tab()
        self._build_pickup_tab()
        self._build_flow_tab()
        self._build_log_tab()

        self.status = tk.StringVar(value=t("ready"))
        bar = ttk.Label(self, textvariable=self.status, anchor="w", relief="sunken", padding=(8, 4))
        bar.pack(fill="x", side="bottom")

    def _build_main_tab(self) -> None:
        f = self.tab_main
        box = ttk.LabelFrame(f, text=t("sec_status"), padding=10)
        box.pack(fill="x", padx=10, pady=8)
        self.game_label = tk.Label(
            box, text=t("game_none"), anchor="w", fg=COLOR_MUTED,
            font=("Microsoft YaHei UI", 10),
        )
        self.game_label.pack(fill="x")
        self.net_label = tk.Label(
            box, text=t("st_detecting"), anchor="w", fg=COLOR_MUTED,
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        self.net_label.pack(fill="x", pady=(4, 0))
        self.accel_label = tk.Label(
            box, text="", anchor="w", fg=COLOR_MUTED, font=("Microsoft YaHei UI", 9)
        )
        self.accel_label.pack(fill="x", pady=(2, 0))
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

        act = ttk.Frame(f)
        act.pack(fill="x", padx=10, pady=14)
        ttk.Button(act, text=t("btn_ka"), style="Big.TButton", command=self.action_ka).pack(
            side="left", expand=True, fill="x", padx=(0, 6)
        )
        ttk.Button(act, text=t("btn_restore"), style="Big.TButton", command=self.action_restore).pack(
            side="left", expand=True, fill="x", padx=(6, 0)
        )


    def _build_pickup_tab(self) -> None:
        f = self.tab_pickup
        audio = ttk.LabelFrame(f, text=t("sec_audio"), padding=10)
        audio.pack(fill="x", padx=10, pady=8)

        row = ttk.Frame(audio)
        row.pack(fill="x")
        ttk.Label(row, text=t("lbl_device")).pack(side="left")
        self.device_var = tk.StringVar(value=self.cfg.get("pickup_device", ""))
        self.device_box = ttk.Combobox(row, textvariable=self.device_var, values=[], state="readonly")
        self.device_box.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text=t("btn_refresh_devices"), command=self.action_refresh_devices).pack(side="left")

        row2 = ttk.Frame(audio)
        row2.pack(fill="x", pady=(6, 0))
        self.level_var = tk.StringVar(value=t("lbl_level", avg=0, peak=0))
        self.level_label = tk.Label(
            row2, textvariable=self.level_var, anchor="w",
            fg=COLOR_MUTED, font=("Consolas", 11),
        )
        self.level_label.pack(side="left")
        ttk.Button(row2, text=t("btn_test_listen"), command=self.action_test_listen).pack(side="right")
        ttk.Button(row2, text=t("btn_test_pad"), command=self.action_test_pad).pack(side="right", padx=6)

        row3 = ttk.Frame(audio)
        row3.pack(fill="x", pady=(6, 0))
        ttk.Label(row3, text=t("lbl_thresholds")).pack(side="left")
        ttk.Label(row3, text=t("lbl_avg_th")).pack(side="left")
        self.avg_th_var = tk.StringVar(value=str(self.cfg.get("pickup_avg", 25)))
        ttk.Entry(row3, textvariable=self.avg_th_var, width=5).pack(side="left", padx=(2, 12))
        ttk.Label(row3, text=t("lbl_peak_th")).pack(side="left")
        self.peak_th_var = tk.StringVar(value=str(self.cfg.get("pickup_peak", 45)))
        ttk.Entry(row3, textvariable=self.peak_th_var, width=5).pack(side="left", padx=2)

        loop = ttk.LabelFrame(f, text=t("sec_loop"), padding=10)
        loop.pack(fill="x", padx=10, pady=(0, 8))
        row4 = ttk.Frame(loop)
        row4.pack(anchor="w")
        ttk.Label(row4, text=t("lbl_wait_min")).pack(side="left")
        self.wait_min_var = tk.StringVar(value=str(self.cfg.get("pickup_wait_min", 48)))
        ttk.Entry(row4, textvariable=self.wait_min_var, width=6).pack(side="left", padx=(2, 18))
        ttk.Label(row4, text=t("lbl_rounds")).pack(side="left")
        self.rounds_var = tk.StringVar(value=str(self.cfg.get("pickup_rounds", 85)))
        ttk.Entry(row4, textvariable=self.rounds_var, width=6).pack(side="left", padx=2)

        seq = ttk.LabelFrame(f, text=t("sec_seq"), padding=10)
        seq.pack(fill="x", padx=10, pady=(0, 8))
        defaults = {
            "seq_to_story": "to_story",
            "seq_to_invite": "to_invite",
            "seq_confirm": "confirm",
        }
        for cfg_key, label_key in (
            ("seq_to_story", "lbl_seq_story"),
            ("seq_to_invite", "lbl_seq_invite"),
            ("seq_confirm", "lbl_seq_confirm"),
        ):
            line = ttk.Frame(seq)
            line.pack(fill="x", pady=2)
            ttk.Label(line, text=t(label_key), width=12, anchor="w").pack(side="left")
            default_value = ""
            if pickup_mod is not None:
                default_value = pickup_mod.DEFAULT_SEQUENCES.get(defaults[cfg_key], "")
            var = tk.StringVar(value=self.cfg.get(cfg_key) or default_value)
            ttk.Entry(line, textvariable=var).pack(side="left", fill="x", expand=True, padx=6)
            setattr(self, cfg_key + "_var", var)
        ttk.Button(seq, text=t("btn_seq_default"), command=self.action_restore_sequences).pack(
            anchor="e", pady=(4, 0)
        )

        act = ttk.Frame(f)
        act.pack(fill="x", padx=10, pady=(0, 10))
        self.pickup_btn = ttk.Button(
            act, text=t("btn_start_pickup"), style="Big.TButton", command=self.action_start_pickup
        )
        self.pickup_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.pickup_stop_btn = ttk.Button(
            act, text=t("btn_stop_pickup"), style="Big.TButton",
            command=self.action_stop_pickup, state="disabled",
        )
        self.pickup_stop_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))
        if not HAS_PICKUP:
            self.pickup_btn.state(["disabled"])

        self.action_refresh_devices(quiet=True)

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

        # 加速器封禁与自动取货是矛盾的（自动取货要求关加速器），默认收进"高级选项"
        self.adv_var = tk.BooleanVar(value=False)
        self.adv_chk = ttk.Checkbutton(
            f, text=t("chk_advanced"), variable=self.adv_var, command=self._toggle_advanced
        )
        self.adv_chk.pack(anchor="w", padx=10, pady=(0, 6))

        accel = ttk.LabelFrame(f, text=t("sec_accel"), padding=10)
        self.accel_frame = accel
        self.accel_chk_var = tk.BooleanVar(value=bool(self.cfg.get("accel_block")))
        ttk.Checkbutton(
            accel, text=t("chk_accel"), variable=self.accel_chk_var, command=self._save_accel
        ).pack(anchor="w")

        # 主选：加速器目录（整目录进程一起封）
        row_dir = ttk.Frame(accel)
        row_dir.pack(fill="x", pady=(6, 0))
        ttk.Label(row_dir, text=t("lbl_accel_dir"), width=16, anchor="w").pack(side="left")
        self.accel_dir_var = tk.StringVar(value=self.cfg.get("accel_dir", ""))
        ttk.Entry(row_dir, textvariable=self.accel_dir_var).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(row_dir, text=t("btn_browse"), command=self.action_pick_accel_dir).pack(side="left")

        # 备选：进程名
        row_name = ttk.Frame(accel)
        row_name.pack(fill="x", pady=(4, 0))
        ttk.Label(row_name, text=t("lbl_accel_names_adv"), width=16, anchor="w").pack(side="left")
        self.accel_names_var = tk.StringVar(value=self.cfg.get("accel_names", ""))
        ttk.Entry(row_name, textvariable=self.accel_names_var).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(row_name, text=t("btn_accel_scan"), command=self.action_scan_accel).pack(side="left")

        self.accel_hint = tk.Label(
            accel, text=t("note_accel"), anchor="w", justify="left",
            fg=COLOR_MUTED, font=("Microsoft YaHei UI", 9),
        )
        self.accel_hint.pack(fill="x", pady=(6, 0))
        self.accel_result = tk.Label(
            accel, text="", anchor="w", justify="left",
            fg=COLOR_MUTED, font=("Microsoft YaHei UI", 9),
        )
        self.accel_result.pack(fill="x")

        tip = ttk.LabelFrame(f, text=t("sec_notes"), padding=10)
        tip.pack(fill="x", padx=10, pady=(0, 10))
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
        self.cfg["accel_dir"] = self.accel_dir_var.get().strip()
        save_config(self.cfg)
        try:
            self.refresh_state()
        except Exception:
            pass

    def _toggle_advanced(self) -> None:
        """高级选项：加速器封禁默认收起来，勾上才显示。"""
        try:
            if self.adv_var.get():
                self.accel_frame.pack(
                    fill="x", padx=10, pady=(0, 8), after=self.adv_chk
                )
            else:
                self.accel_frame.pack_forget()
        except Exception:
            pass

    def _accel_names(self) -> list:
        return [n.strip() for n in str(self.accel_names_var.get()).split(",") if n.strip()]

    def action_scan_accel(self) -> None:
        self._save_accel()
        targets = {}
        for pid, name, path in find_processes_by_names(self._accel_names()):
            targets[path.lower()] = (name, pid)
        for pid, name, path in find_processes_by_dir(self.cfg.get("accel_dir", "")):
            targets[path.lower()] = (name, pid)
        if targets:
            detail = ", ".join(f"{name} (PID {pid})" for name, pid in targets.values())
            self.accel_result.configure(text=t("accel_scan_hit", n=len(targets)) + "：" + detail,
                                        fg=COLOR_OK)
            self.log(t("log_accel_found", n=len(targets), list=detail))
        else:
            self.accel_result.configure(text=t("accel_scan_none"), fg=COLOR_MUTED)
            self.log(t("log_accel_none"))

    def action_pick_accel_dir(self) -> None:
        folder = filedialog.askdirectory(title=t("lbl_accel_dir"))
        if folder:
            self.accel_dir_var.set(folder.replace("/", "\\"))
            self._save_accel()
            self.action_scan_accel()

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

    def action_open_guide(self) -> None:
        base = app_dir()
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

    # ---------------- 自动取货 ----------------
    def _save_pickup_cfg(self) -> None:
        self.cfg.update({
            "pickup_device": self.device_var.get().strip(),
            "pickup_avg": self._read_float(self.avg_th_var, 25.0),
            "pickup_peak": self._read_float(self.peak_th_var, 45.0),
            "pickup_rounds": int(self._read_float(self.rounds_var, 85)),
            "pickup_wait_min": self._read_float(self.wait_min_var, 48.0),
            "seq_to_story": self.seq_to_story_var.get().strip(),
            "seq_to_invite": self.seq_to_invite_var.get().strip(),
            "seq_confirm": self.seq_confirm_var.get().strip(),
        })
        save_config(self.cfg)

    def action_refresh_devices(self, quiet: bool = False) -> None:
        if pickup_mod is None:
            self.log(t("log_pickup_nodep"))
            return
        try:
            devices = pickup_mod.AudioMonitor.list_devices()
        except Exception as exc:
            self.log(f"✗ 读取音频设备失败：{exc}")
            return
        self.device_box.configure(values=devices)
        if self.device_var.get() not in devices:
            default = pickup_mod.AudioMonitor.default_device()
            self.device_var.set(default if default in devices else (devices[0] if devices else ""))
        if not quiet:
            self.log(f"· 找到 {len(devices)} 个可回环设备")

    def action_restore_sequences(self) -> None:
        if pickup_mod is None:
            return
        for cfg_key, default_key in (
            ("seq_to_story", "to_story"),
            ("seq_to_invite", "to_invite"),
            ("seq_confirm", "confirm"),
        ):
            getattr(self, cfg_key + "_var").set(pickup_mod.DEFAULT_SEQUENCES[default_key])
        self.log("· 已恢复默认序列（记得在游戏里校准）")

    def _on_level(self, avg, peak) -> None:
        self.hotkey_queue.put(("level", (avg, peak)))

    def action_test_listen(self) -> None:
        if pickup_mod is None:
            self.log(t("log_pickup_nodep"))
            return
        if self.audio_test_running:
            return
        self.audio_test_running = True
        self.log(t("log_test_listen"))
        peak_th = self._read_float(self.peak_th_var, 45.0)
        device = self.device_var.get()

        def worker():
            monitor = pickup_mod.AudioMonitor()
            monitor.start(device, self._on_level)
            best = 0.0
            end = time.time() + 30
            while time.time() < end:
                best = max(best, monitor.peak)
                time.sleep(0.2)
            monitor.stop()
            self.hotkey_queue.put(("log", t("log_test_done", peak=best, peak_th=peak_th)))
            self.hotkey_queue.put(("call", self._finish_test))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_test(self) -> None:
        self.audio_test_running = False

    def action_test_pad(self) -> None:
        if pickup_mod is None:
            self.log(t("log_pickup_nodep"))
            return
        try:
            pickup_mod.KeyController().click("shift")
            self.log(t("log_test_pad_ok"))
        except Exception as exc:
            self.log(t("log_test_pad_fail", err=exc))

    def _pickup_block(self) -> None:
        game = find_game()
        if not game:
            self.log_async("✗ 找不到游戏进程，跳过断网")
            return
        ok, out = fw_block(game[2])
        if not ok:
            self.log_async(t("log_block_fail", out=out))

    def _pickup_unblock(self) -> None:
        fw_unblock()

    def action_start_pickup(self) -> None:
        if pickup_mod is None:
            self.log(t("log_pickup_nodep"))
            return
        if self.pickup_thread and self.pickup_thread.is_alive():
            self.log("… 已经在跑了")
            return
        if not find_game():
            self.log("✗ 没检测到游戏进程，先开 GTA 再启动")
            return
        if not is_admin():
            self.log(t("log_need_admin"))
            return
        self._save_pickup_cfg()
        stop = threading.Event()
        self.pickup_stop = stop
        engine = pickup_mod.PickupEngine(self._pickup_block, self._pickup_unblock, self.log_async)
        args = {
            "rounds": int(self._read_float(self.rounds_var, 85)),
            "wait_minutes": self._read_float(self.wait_min_var, 48.0),
            "avg_th": self._read_float(self.avg_th_var, 25.0),
            "peak_th": self._read_float(self.peak_th_var, 45.0),
            "device": self.device_var.get(),
            "sequences": {
                "to_story": self.seq_to_story_var.get(),
                "to_invite": self.seq_to_invite_var.get(),
                "confirm": self.seq_confirm_var.get(),
            },
            "params": {},
            "stop": stop,
        }
        self.log(t("log_pickup_started", wait=args["wait_minutes"], rounds=args["rounds"]))
        self.log(t("log_seq_help"))

        def worker():
            try:
                engine.run(**args)
            except Exception as exc:
                self.log_async(f"✗ 自动取货出错：{exc}")
            finally:
                self.hotkey_queue.put(("call", self._pickup_finished))

        self.pickup_thread = threading.Thread(target=worker, daemon=True, name="pickup")
        self.pickup_btn.state(["disabled"])
        self.pickup_stop_btn.state(["!disabled"])
        self.set_status(t("st_pickup_running", i=0, n=args["rounds"]))
        self.pickup_thread.start()

    def action_stop_pickup(self) -> None:
        if self.pickup_stop:
            self.pickup_stop.set()
        self.log(t("log_pickup_stopped"))

    def _pickup_finished(self) -> None:
        self.pickup_btn.state(["!disabled"])
        self.pickup_stop_btn.state(["disabled"])
        self.set_status(t("st_pickup_idle"))

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
            self.game_label.configure(text=t("game_running", name=name, pid=pid), fg=COLOR_OK)
            self.path_var.set(path or t("st_read_fail"))
        else:
            self.game_label.configure(text=t("game_none"), fg=COLOR_MUTED)
            self.path_var.set(t("path_none"))
        blocked = fw_is_blocked()
        self.net_label.configure(
            text=t("net_blocked") if blocked else t("net_ok"),
            fg=COLOR_BAD if blocked else COLOR_OK,
        )
        accel_dir = str(self.cfg.get("accel_dir", "")).strip()
        if self.cfg.get("accel_block"):
            suffix = f"（{accel_dir}）" if accel_dir else ""
            self.accel_label.configure(text=t("st_accel_on") + suffix, fg=COLOR_OK)
        else:
            self.accel_label.configure(text=t("st_accel_off"), fg=COLOR_MUTED)
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
                elif kind == "level":
                    avg, peak = payload
                    self.level_var.set(t("lbl_level", avg=avg, peak=peak))
                    try:
                        hot = peak >= self._read_float(self.peak_th_var, 45.0)
                    except Exception:
                        hot = False
                    self.level_label.configure(fg=COLOR_BAD if hot else COLOR_MUTED)
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
            targets = {}
            for _pid, aname, apath in find_processes_by_names(self._accel_names()):
                targets[apath.lower()] = (aname, apath)
            for _pid, aname, apath in find_processes_by_dir(self.cfg.get("accel_dir", "")):
                targets[apath.lower()] = (aname, apath)
            blocked = 0
            for aname, apath in targets.values():
                ok_accel, _ = fw_block(apath, accel_rule_name(apath))
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
    if "--touch-config" in sys.argv:
        # 诊断用：确认配置文件到底落在哪，然后立刻退出（不开界面）
        save_config(load_config())
        return 0
    if "--pickup-selftest" in sys.argv:
        # 诊断用：把音频/手柄自检结果写到 exe 旁边，用于验证打包是否完整
        lines = []
        try:
            import pickup as pm

            lines.append(f"HAS_AUDIO={pm.HAS_AUDIO} HAS_KEYS={pm.HAS_KEYS}")
            lines.append("devices=" + " | ".join(pm.AudioMonitor.list_devices()))
            pm.KeyController().click("shift")
            lines.append("keyboard=OK")
        except Exception as exc:
            lines.append(f"ERROR: {exc!r}")
        with open(os.path.join(app_dir(), "pickup-selftest.txt"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        return 0
    if "--selftest" in sys.argv:
        return selftest()
    app = LilMute()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
