# -*- coding: utf-8 -*-
"""自动取货引擎：音频监听 + 手柄模拟 + 防火墙断网循环。

思路参考 Hansimov/gtaz（MIT）的自动取货模块，按本程序的结构重写：
  · 音频：WASAPI 回环采集（soundcard）——不需要装 VBCABLE
  · 手柄：vgamepad 模拟 X360 手柄——需要 ViGEmBus（已装）
  · 断网：复用主程序的防火墙规则（netsh）
"""
from __future__ import annotations

import threading
import time

# 模块级导入：PyInstaller 靠这里把依赖打进 exe
try:
    import numpy  # noqa: F401
    import soundcard  # noqa: F401

    HAS_AUDIO = True
except Exception:  # 缺依赖时功能降级，不影响主程序
    HAS_AUDIO = False

try:
    import vgamepad  # noqa: F401

    HAS_PAD = True
except Exception:
    HAS_PAD = False

BUTTON_NAMES = {
    "a": "XUSB_GAMEPAD_A",
    "b": "XUSB_GAMEPAD_B",
    "x": "XUSB_GAMEPAD_X",
    "y": "XUSB_GAMEPAD_Y",
    "start": "XUSB_GAMEPAD_START",
    "back": "XUSB_GAMEPAD_BACK",
    "up": "XUSB_GAMEPAD_DPAD_UP",
    "down": "XUSB_GAMEPAD_DPAD_DOWN",
    "left": "XUSB_GAMEPAD_DPAD_LEFT",
    "right": "XUSB_GAMEPAD_DPAD_RIGHT",
    "lb": "XUSB_GAMEPAD_LEFT_SHOULDER",
    "rb": "XUSB_GAMEPAD_RIGHT_SHOULDER",
}

# 默认序列：菜单层级会随版本/语言变化，第一次用请按教程校准
DEFAULT_SEQUENCES = {
    "to_invite": (
        "start, wait 2, rb 1, wait 0.5, a, wait 1.5, "
        "down 1, wait 0.3, a, wait 1.5, a, wait 20"
    ),
    "to_story": (
        "start, wait 2, rb 1, wait 0.5, down 1, wait 0.3, a, wait 1, a, wait 12"
    ),
    "confirm": "a, wait 0.8, a, wait 0.8, a",
}


class AudioMonitor:
    """WASAPI 回环音量监控（不需要虚拟声卡）。"""

    def __init__(self, samplerate: int = 48000, block_ms: int = 100):
        self.samplerate = samplerate
        self.block = max(1, int(samplerate * block_ms / 1000))
        self.avg = 0.0
        self.peak = 0.0
        self.device_name = ""
        self._stop = threading.Event()
        self._thread = None

    @staticmethod
    def list_devices() -> list:
        import soundcard as sc

        return [m.name for m in sc.all_microphones(include_loopback=True) if m.isloopback]

    @staticmethod
    def default_device() -> str:
        import soundcard as sc

        try:
            return sc.default_speaker().name
        except Exception:
            return ""

    @staticmethod
    def _levels(chunk) -> tuple:
        import numpy as np

        return float(np.mean(np.abs(chunk))) * 100, float(np.max(np.abs(chunk))) * 100

    def start(self, device_name: str, on_level=None) -> None:
        self.stop()
        self.device_name = device_name
        self._stop = threading.Event()

        def worker():
            import soundcard as sc

            try:
                mic = sc.get_microphone(id=device_name, include_loopback=True)
                with mic.recorder(samplerate=self.samplerate, channels=1) as recorder:
                    while not self._stop.is_set():
                        chunk = recorder.record(numframes=self.block)
                        self.avg, self.peak = self._levels(chunk)
                        if on_level:
                            on_level(self.avg, self.peak)
            except Exception:
                self.avg = self.peak = 0.0

        self._thread = threading.Thread(target=worker, daemon=True, name="audio")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def wait_for_signal(self, avg_th: float, peak_th: float, timeout: float = 120.0) -> bool:
        """等音量超过阈值；调用前先 start()。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._stop.is_set():
                return False
            if self.avg >= avg_th and self.peak >= peak_th:
                return True
            time.sleep(0.05)
        return False


class PadController:
    """vgamepad 封装：按键、序列执行。"""

    def __init__(self):
        self.pad = None

    def ensure(self):
        if self.pad is None:
            import vgamepad as vg

            self.pad = vg.VX360Gamepad()
            self.pad.reset()
            self.pad.update()
        return self.pad

    def click(self, name: str, duration_ms: int = 120) -> None:
        import vgamepad as vg

        pad = self.ensure()
        button = getattr(vg.XUSB_BUTTON, BUTTON_NAMES[name])
        pad.press_button(button)
        pad.update()
        time.sleep(duration_ms / 1000)
        pad.release_button(button)
        pad.update()

    def run(self, text: str, log=print, stop: threading.Event = None, gap_ms: int = 200) -> bool:
        """执行一行序列，例如 "start, wait 2, rb 1, a"。

        wait N  = 等 N 秒；<按键> [N] = 点 N 次。
        """
        for raw in text.replace("\n", ",").split(","):
            token = raw.strip().lower()
            if not token or token.startswith("#"):
                continue
            if stop is not None and stop.is_set():
                return False
            parts = token.split()
            action = parts[0]
            try:
                number = float(parts[1]) if len(parts) > 1 else 1
            except ValueError:
                log(f"✗ 序列写错了：{token}")
                return False
            if action == "wait":
                log(f"   … 等 {number:g} 秒")
                if stop is not None:
                    stop.wait(number)
                else:
                    time.sleep(number)
            elif action in BUTTON_NAMES:
                for _ in range(max(1, int(number))):
                    self.click(action)
                    time.sleep(gap_ms / 1000)
                log(f"   · 按键 {action} ×{max(1, int(number))}")
            else:
                log(f"✗ 不认识的按键：{action}")
                return False
        return True


class PickupEngine:
    """自动取货循环：切模式 → 切战局 → 听声音 → 断网 → 确认 → 恢复。"""

    DEFAULTS = {
        "quiet_wait": 8.0,        # 切完战局后等音频稳定
        "detect_timeout": 180.0,  # 等信号最长时间
        "after_detect": 1.0,      # 命中后稍等再断网
        "warn_wait": 12.0,        # 等「保存失败」提示
        "goods_wait": 10.0,       # 等货物到达
        "confirm_gap": 1.0,       # 确认键间隔
    }

    def __init__(self, block, unblock, log):
        self.block = block
        self.unblock = unblock
        self.log = log
        self.pad = PadController()
        self.audio = AudioMonitor()

    def stop_audio(self) -> None:
        self.audio.stop()

    def run(
        self,
        rounds: int,
        wait_minutes: float,
        avg_th: float,
        peak_th: float,
        device: str,
        sequences: dict,
        params: dict,
        stop: threading.Event,
    ) -> None:
        cfg = dict(self.DEFAULTS)
        cfg.update(params or {})
        log = self.log

        if wait_minutes and wait_minutes > 0:
            log(f"⏳ 先等 {wait_minutes:g} 分钟（让员工把货取回来）……")
            if stop.wait(wait_minutes * 60):
                log("· 已取消等待")
                return

        for index in range(rounds):
            if stop.is_set():
                break
            log("=" * 46)
            log(f"第 {index + 1} / {rounds} 轮")
            log("=" * 46)

            self.unblock()
            log("· 切回故事模式……")
            self.pad.run(sequences.get("to_story", ""), log, stop)
            if stop.is_set():
                break

            log("· 切到新的邀请战局（员工会把货交进仓库）……")
            self.pad.run(sequences.get("to_invite", ""), log, stop)
            if stop.is_set():
                break

            log(f"· 等 {cfg['quiet_wait']:g} 秒让音频稳定……")
            if stop.wait(cfg["quiet_wait"]):
                break

            log(f"· 开始监听（阈值 平均≥{avg_th:g} / 峰值≥{peak_th:g}）……")
            self.audio.start(device)
            hit = self.audio.wait_for_signal(avg_th, peak_th, cfg["detect_timeout"])
            self.audio.stop()
            if stop.is_set():
                break
            if not hit:
                log("⚠ 没等到信号，跳过这一轮（阈值可能要调低）")
                continue

            log(f"✔ 听到信号（平均 {self.audio.avg:.0f} / 峰值 {self.audio.peak:.0f}）")
            if stop.wait(cfg["after_detect"]):
                break
            self.block()
            log("✔ 已断网")

            log(f"· 等 {cfg['warn_wait']:g} 秒出现「保存失败」提示……")
            if stop.wait(cfg["warn_wait"]):
                break
            self.pad.run(sequences.get("confirm", ""), log, stop)

            log(f"· 再等 {cfg['goods_wait']:g} 秒确保货物到达……")
            if stop.wait(cfg["goods_wait"]):
                break
            self.pad.run(sequences.get("confirm", ""), log, stop)

            self.unblock()
            log("✔ 已恢复网络，本轮结束")

        self.unblock()
        self.audio.stop()
        log("· 循环结束，网络已恢复")
        log("· 请回游戏确认左下角出现「保存成功」，并手动同步一次存档")
