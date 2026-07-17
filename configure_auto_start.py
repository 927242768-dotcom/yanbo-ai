"""注册或移除彦博公网服务的 Windows 自动启动与自愈机制。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import winreg
from pathlib import Path

from console_utils import configure_utf8_console


ROOT = Path(__file__).resolve().parent
DAEMON = ROOT / "remote_service_daemon.pyw"
STARTUP_DIR = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_SCRIPT = STARTUP_DIR / "YanboAI-Remote-Service.vbs"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "YanboAI Remote Service"
LOGON_TASK = "YanboAI Remote Service"
WATCHDOG_TASK = "YanboAI Remote Service Watchdog"


def _unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def _pythonw_candidates() -> list[Path]:
    """优先使用当前解释器对应入口，避免绑定不可直接执行的WindowsApps内部路径。"""
    executable = Path(sys.executable)
    versioned_name = f"pythonw{sys.version_info.major}.{sys.version_info.minor}.exe"
    candidates = [
        executable.with_name("pythonw.exe"),
        executable.with_name(versioned_name),
    ]

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        local_root = Path(local_app_data)
        candidates.extend(
            [
                local_root / "Microsoft" / "WindowsApps" / "pythonw.exe",
                local_root
                / "Programs"
                / "Python"
                / f"Python{sys.version_info.major}{sys.version_info.minor}"
                / "pythonw.exe",
            ]
        )

    found = shutil.which("pythonw.exe") or shutil.which("pythonw")
    if found:
        candidates.append(Path(found))

    base_candidate = Path(sys.base_prefix) / "pythonw.exe"
    if "program files\\windowsapps" not in str(base_candidate).lower():
        candidates.append(base_candidate)
    return _unique_paths(candidates)


def _probe_pythonw(candidate: Path) -> tuple[bool, str]:
    if not candidate.exists():
        return False, "文件不存在"
    console = candidate.with_name("python.exe")
    if not console.exists():
        return False, "缺少对应的python.exe"
    try:
        completed = subprocess.run(
            [str(console), "-c", "import remote_service_daemon"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        return False, detail or f"退出码{completed.returncode}"
    return True, ""


def find_pythonw() -> Path:
    failures: list[str] = []
    for candidate in _pythonw_candidates():
        ok, detail = _probe_pythonw(candidate)
        if ok:
            return candidate
        failures.append(f"{candidate}：{detail}")
    raise FileNotFoundError("没有找到可运行彦博服务的pythonw.exe。\n" + "\n".join(failures))


def vbs_quote(value: str) -> str:
    return value.replace('"', '""')


def _wscript_path() -> Path:
    return Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "wscript.exe"


def _launcher_command() -> str:
    return subprocess.list2cmdline([str(_wscript_path()), str(STARTUP_SCRIPT)])


def write_startup_script(pythonw: Path) -> None:
    command = f'"{pythonw}" "{DAEMON}"'
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    STARTUP_SCRIPT.write_text(
        'Set shell = CreateObject("WScript.Shell")\r\n'
        f'shell.CurrentDirectory = "{vbs_quote(str(ROOT))}"\r\n'
        f'shell.Run "{vbs_quote(command)}", 0, False\r\n',
        encoding="ascii",
    )


def register_run_key() -> None:
    """增加第二条当前用户登录启动入口，与启动文件夹互为备用。"""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
        winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, _launcher_command())


def remove_run_key() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
    except FileNotFoundError:
        pass


def _run_schtasks(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["schtasks.exe", *arguments],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def try_register_watchdog_tasks() -> bool:
    """系统允许时增加任务计划；受限电脑上失败也不影响双重登录启动。"""
    command = _launcher_command()
    logon = _run_schtasks(
        [
            "/Create",
            "/TN",
            LOGON_TASK,
            "/TR",
            command,
            "/SC",
            "ONLOGON",
            "/DELAY",
            "0000:20",
            "/F",
        ]
    )
    if logon.returncode != 0:
        return False
    watchdog = _run_schtasks(
        [
            "/Create",
            "/TN",
            WATCHDOG_TASK,
            "/TR",
            command,
            "/SC",
            "MINUTE",
            "/MO",
            "5",
            "/ST",
            "00:00",
            "/F",
        ]
    )
    if watchdog.returncode != 0:
        _run_schtasks(["/Delete", "/TN", LOGON_TASK, "/F"])
        return False
    return True


def remove_tasks() -> None:
    _run_schtasks(["/Delete", "/TN", LOGON_TASK, "/F"])
    _run_schtasks(["/Delete", "/TN", WATCHDOG_TASK, "/F"])


def start_now() -> None:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen(
        [str(_wscript_path()), str(STARTUP_SCRIPT)],
        cwd=ROOT,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def enable() -> None:
    pythonw = find_pythonw()
    write_startup_script(pythonw)
    register_run_key()
    tasks_enabled = try_register_watchdog_tasks()
    start_now()
    print("彦博公网服务已启用双重登录自启动和后台自动恢复，并已立即启动。")
    print(f"运行解释器：{pythonw}")
    print(f"启动文件：{STARTUP_SCRIPT}")
    print(f"注册表启动项：{RUN_VALUE_NAME}")
    if tasks_enabled:
        print("任务计划自愈：已启用，每5分钟检查一次守护程序。")
    else:
        print("任务计划自愈：当前Windows权限不允许创建；双重登录启动与常驻守护仍已启用。")


def disable() -> None:
    STARTUP_SCRIPT.unlink(missing_ok=True)
    remove_run_key()
    remove_tasks()
    print("彦博公网服务自动启动与自愈入口已移除。")


def main() -> None:
    configure_utf8_console()
    disable() if "--disable" in sys.argv[1:] else enable()


if __name__ == "__main__":
    main()
