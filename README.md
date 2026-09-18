# Lil Mute - GTA Online warehouse glitch helper

<img src="assets/icon.png" width="104" align="right" alt="Lil Mute icon">

Press a hotkey, the game's network connection is cut for a moment, then restored
automatically. That is the whole idea. Pure OS-level — no injection, no memory
access, no packet editing. The interface ships in **English and Chinese** and you
can switch it in-app.

📄 **Step-by-step guide (PDF, Chinese):** [`docs/lil-mute-guide-zh.pdf`](docs/lil-mute-guide-zh.pdf)

![platform](https://img.shields.io/badge/platform-Windows-blue)
![python](https://img.shields.io/badge/python-3.8%2B-informational)
![deps](https://img.shields.io/badge/dependencies-none-success)
![lang](https://img.shields.io/badge/UI-English%20%2F%20%E4%B8%AD%E6%96%87-orange)

---

## What it does

| Feature | Description |
| --- | --- |
| **Auto pickup** | Automated warehouse-staff pickup loop: listens to the game audio, cuts the network at the right moment, drives the menus with a virtual gamepad |
| Cut (F8) | Blocks **outbound traffic of the GTA5 process only**, using a Windows Firewall rule |
| Auto restore | Removes the rule again after the configured number of seconds |
| Global hotkeys | `F8` to cut, `F9` to restore — both work while the game is fullscreen |
| Block the accelerator too | Point it at the accelerator's install folder (or list process names) and those processes are cut in the same press |
| Suspend | Freezes the game process briefly; a no-injection way to get a solo session |
| Kill process | One-click `taskkill`, commonly used to save progress in challenge runs |
| Workflow tab | The restock → sell flow, the in-game prerequisites and the required GTA display settings, built into the app |
| Configurable hotkeys | Any two of F1–F12, for when F8 / F9 are already taken |
| Bilingual UI | English / Chinese, switchable at the top; the choice is remembered |
| Log | Every action is timestamped, so failures are easy to trace |

The firewall rule is removed again when you close the tool, so you will not be
left offline by accident.

## What it does not do

No DLL injection, no reading or writing game memory, no packet editing — nothing
inside BattlEye's scope. Under the hood it just flips a built-in firewall rule for
you. **It is still a game glitch, though: farming currency this way can get your
account flagged. Use your own judgement.**

## Requirements

- Windows 10 / 11
- Python 3.8+ (tkinter ships with the official Windows installer) — or build a
  standalone exe, see below
- Administrator rights when you actually use it (changing firewall rules needs them)

## Quick start

```bat
python lil_mute.py            REM add --en or --zh to force a UI language
```

Or simply double-click `run.bat` — it requests administrator rights for you.

Build a single-file exe:

```bat
build_exe.bat
```

The result is `dist\LilMute.exe`.

## Usage

1. Start the tool **as administrator** (there is a *Restart as admin* button in the
   Network tab if you forgot).
2. Start the game. Hit **Refresh** and make sure the status line shows
   `Game process: GTA5_Enhanced.exe (PID …)`. If it says *not running*, the tool
   cannot see the game and F8 will refuse to fire.
3. Press **F8** at the moment you want the connection cut. The tool blocks the game's
   outbound traffic, then restores it automatically after *Cut duration* seconds
   (default 1.5 s).
4. Press **F9** at any time to restore the network immediately.

Parameters:

| Field | Meaning |
| --- | --- |
| Delay before cut | Wait this long after the hotkey before actually cutting (default 0 s). Use it to line up with the in-game moment |
| Cut duration | How long the game stays cut (default 1.5 s). Raise it to 2–3 s on an unstable connection |

> The *Block now* button in the Network tab blocks **indefinitely** — it will not
> restore by itself. Use *Unblock* or F9 afterwards.

## If you run a game accelerator

Game accelerators (the ones popular in China, e.g. UU / Xunyou) take over the game's
traffic at **driver level** with their own WFP filters and virtual adapters. The
Windows Firewall rule can lose the race against those filters, which means the tool
reports *blocked* while the game is actually still online. That is not a bug in the
tool — it is how accelerators work: they sit between the game and the network.

Order that works:

1. Tool first (as administrator)
2. Then the accelerator, wait until it reports the game is accelerated
3. Then GTA Online, then hit **Refresh** in the tool

Then verify once: press F8 and watch the game. If it disconnects (or the accelerator
panel shows a broken connection), you are fine. **If nothing happens, use Process tab
→ Suspend game instead** — freezing the process does not depend on the network path,
so an accelerator cannot route around it.

The tool will not crash your accelerator: it only adds and deletes one firewall rule.
It never touches the accelerator process, the network adapters or any driver.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| "Administrator rights are required" | Not elevated | *Restart as admin*, or right-click `run.bat` → Run as administrator |
| F8 does nothing | Hotkey already taken | Close screen recorders / macro tools / IME helpers and restart the tool; the log names the step that failed |
| "Cannot read the game path" | Not enough rights to query the process path | Run as administrator |
| "Game process not found" | Game not started | Start GTA Online first, then hit Refresh |
| Cut reported, game unaffected | A game accelerator is tunnelling the traffic | See the section above — use *Suspend game* |
| Antivirus flags the exe | Unsigned small tool, common false positive | The whole program is `lil_mute.py`; read it, or run it from source |

## Cleanup

Closing the window removes the rule automatically. If the tool was killed from Task
Manager, remove the leftover rule manually:

```bat
netsh advfirewall firewall delete rule name="LilMute-BlockOut"
```

Or check the Network tab: `Rule:` should read *absent (normal)*.

## Self-test

No GUI, no system changes — it only reports what it can see:

```bat
python lil_mute.py --selftest
```

## Relationship to other tools

What people call a "warehouse script" is really two layers, and this project only
does the first one:

1. **OS level (this project)** — network cut, session isolation, killing/suspending the
   process. It never touches the inside of the game.
2. **Menu level** — for example the Stand menu's `MusinessBanager` Lua (instant special
   cargo sales, price tuning) or projects such as
   [QuellGTA](https://github.com/mageangela/QuellGTA) and
   [GTA5-Stand-LuaAIO](https://github.com/xhcherry/GTA5-Stand-LuaAIO). Those belong to
   the third-party menu ecosystem: **this repository neither contains nor ships them.**

---

## 中文说明

一个跑在自己电脑上的 Windows 小工具，把「出货时卡一下」需要的手动操作收进一个带界面的窗口：
**一键断网 → 定时自动恢复 → 全局热键**。纯系统层实现，不注入游戏。界面支持 **中文 / English** 一键切换。

📄 **一步一步的图文教程（PDF）：** [`docs/lil-mute-guide-zh.pdf`](docs/lil-mute-guide-zh.pdf)

### 功能

| 功能 | 说明 |
| --- | --- |
| **自动取货** | 员工取货自动化：听游戏声音抓时机 + 自动断网 + 手柄切模式/切战局，循环把大仓取满 |
| 一键卡（F8） | 用 Windows 防火墙**只封禁 GTA5 进程**的出站流量 |
| 自动恢复 | 到设定秒数自动解除封禁；也能 F9 或点按钮立刻恢复 |
| 全局热键 | `F8` 卡 / `F9` 恢复，游戏全屏时同样生效 |
| 同时封禁加速器 | 填加速器的安装目录（或进程名），卡的时候把它们的进程一起断 |
| 进程暂停 | 短暂冻结游戏进程（免注入的卡单方式），到点自动恢复 |
| 结束进程 | 一键 `taskkill`，任务 / 首脑里常用的保进度操作 |
| 流程页 | 前置条件、GTA 要设的东西、取货、出货脚本步骤全内置，游戏里不用翻 PDF |
| 热键可改 | F1 ~ F12 任选两个，F8/F9 被占用时用得上 |
| 中英双语 | 顶部下拉框随时切换，选择会记住 |

退出程序时会自动解除封禁，不会把你留在断网状态。

### 它不做什么

不注入 DLL、不读写游戏内存、不改数据包、不碰 BattlEye 管辖范围内的任何东西。
本质就是帮你按了几下系统自带的防火墙开关。**但它依然是在卡 Bug，频繁刷币有封号风险，自行判断。**

### 快速开始

```bat
python lil_mute.py
```

或者直接双击 `run.bat`（会自动请求管理员权限）。想打包成单文件 exe 就跑 `build_exe.bat`，
产物在 `dist\LilMute.exe`。

### 出货流程

1. 以**管理员身份**启动工具（防火墙规则需要管理员权限）。
2. 进游戏，正常开始大仓出货。
3. 到需要卡的那一步，按 `F8`（或点「卡！」）。
4. 工具会在 `断网持续` 秒数后自动恢复网络。
5. 想手动控制就点「立即恢复」或按 `F9`。

### 挂着加速器？先看这段

UU、迅游这类加速器是**驱动级**接管游戏流量的，Windows 防火墙规则有可能被它的过滤器抢先，
结果就是工具显示「已封禁」但游戏其实没断。这不是 bug，是加速器的工作原理。

正确顺序：**先开工具（管理员）→ 再开加速器 → 进游戏 → 点「刷新状态」**。
然后实测一次：按 F8 看游戏是否掉线。**如果毫无反应，改用「进程」页的「暂停游戏」**——
冻结进程不依赖网络路径，加速器躲不掉。

工具不会让加速器崩溃：它只添加和删除一条防火墙规则，不碰加速器进程、网卡和驱动。

### 清理与自检

```bat
netsh advfirewall firewall delete rule name="LilMute-BlockOut"
python lil_mute.py --selftest
```

### 和其他工具的关系

「卡大仓脚本」其实分两层，本项目只做第一层：

1. **系统层（本项目）**：断网 / 卡单 / 结束进程，不碰游戏进程内部。
2. **菜单层**：例如 Stand 菜单的 `MusinessBanager`、[QuellGTA](https://github.com/mageangela/QuellGTA)、
   [GTA5-Stand-LuaAIO](https://github.com/xhcherry/GTA5-Stand-LuaAIO) 等。
   那些属于第三方菜单生态，**本仓库不包含也不分发**。

---

## License

MIT
