@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [!] Python not found. Install Python 3.8+ and enable "Add to PATH".
    pause
    exit /b 1
)

echo [*] Installing PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo [!] pip install failed.
    pause
    exit /b 1
)

echo [*] Building single-file exe...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name LilMute lil_mute.py
if errorlevel 1 (
    echo [!] Build failed.
    pause
    exit /b 1
)

echo [OK] Output: dist\LilMute.exe
pause
