"""
微信版本检测器 — 识别安装的微信版本，推荐最佳适配器
"""
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WeChatVersion:
    major: int
    minor: int
    patch: int
    build: str = ""
    install_path: str = ""
    exe_name: str = ""

    @property
    def version_str(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def is_v4(self) -> bool:
        return self.major >= 4

    @property
    def is_v3(self) -> bool:
        return self.major == 3


class VersionDetector:
    """检测微信安装版本"""

    # 可能的安装路径
    SEARCH_PATHS = [
        r"C:\Program Files\Tencent\WeChat",
        r"C:\Program Files (x86)\Tencent\WeChat",
        r"C:\Program Files\Tencent\Weixin",
        r"C:\Program Files (x86)\Tencent\Weixin",
    ]

    # 可能的 exe 名称
    EXE_NAMES = ["WeChat.exe", "weixin.exe", "Weixin.exe"]

    @classmethod
    def detect(cls) -> WeChatVersion | None:
        """检测已安装的微信版本"""
        # 方法1: 从注册表读取
        version = cls._from_registry()
        if version:
            return version

        # 方法2: 从安装目录查找
        version = cls._from_install_dir()
        if version:
            return version

        # 方法3: 从运行中进程检测
        version = cls._from_running_process()
        if version:
            return version

        return None

    @classmethod
    def _from_registry(cls) -> WeChatVersion | None:
        """从 Windows 注册表读取"""
        try:
            import winreg
            keys = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\WeChat"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Tencent\WeChat"),
            ]
            for root, subkey in keys:
                try:
                    with winreg.OpenKey(root, subkey) as key:
                        try:
                            display_version = winreg.QueryValueEx(key, "DisplayVersion")[0]
                        except:
                            display_version = ""
                        try:
                            install_path = winreg.QueryValueEx(key, "InstallLocation")[0]
                        except:
                            install_path = ""
                        if display_version:
                            return cls._parse_version(display_version, install_path)
                except OSError:
                    continue
        except ImportError:
            pass
        return None

    @classmethod
    def _from_install_dir(cls) -> WeChatVersion | None:
        """扫描安装目录"""
        for base in cls.SEARCH_PATHS:
            base_path = Path(base)
            if not base_path.exists():
                continue
            for exe in cls.EXE_NAMES:
                exe_path = base_path / exe
                if exe_path.exists():
                    # 尝试从 exe 属性读取版本
                    version = cls._read_exe_version(str(exe_path))
                    if version:
                        version.install_path = str(base_path)
                        version.exe_name = exe
                        return version
        return None

    @classmethod
    def _from_running_process(cls) -> WeChatVersion | None:
        """检查正在运行的微信进程"""
        try:
            import win32process
            import win32api
            import win32gui
            exe_names_lower = {n.lower() for n in cls.EXE_NAMES}

            def callback(hwnd, _):
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    handle = win32api.OpenProcess(0x0400 | 0x0010, False, pid)
                    path = win32process.GetModuleFileNameEx(handle, 0)
                    exe = os.path.basename(path)
                    if exe.lower() in exe_names_lower:
                        return False  # found
                except:
                    pass
                return True

            win32gui.EnumWindows(callback, None)
        except ImportError:
            pass
        return None

    @classmethod
    def _read_exe_version(cls, exe_path: str) -> WeChatVersion | None:
        """读取 exe 文件版本信息"""
        try:
            import win32api
            info = win32api.GetFileVersionInfo(exe_path, "\\")
            ms = info['FileVersionMS']
            ls = info['FileVersionLS']
            major = (ms >> 16) & 0xFFFF
            minor = ms & 0xFFFF
            patch = (ls >> 16) & 0xFFFF
            build = ls & 0xFFFF
            return WeChatVersion(major, minor, patch, str(build))
        except Exception:
            pass
        return None

    @classmethod
    def _parse_version(cls, version_str: str, install_path: str = "") -> WeChatVersion:
        """解析版本字符串 '4.1.10.51' 或 '4.1.10'"""
        parts = version_str.replace(" ", "").split(".")
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        build = parts[3] if len(parts) > 3 else ""
        return WeChatVersion(major, minor, patch, build, install_path)

    @classmethod
    def recommend_adapter(cls, version: WeChatVersion) -> str:
        """根据版本推荐适配器"""
        if version.is_v4:
            return "wx4py"
        elif version.is_v3:
            return "uia"  # wxauto 4.x 只支持 v4
        return "uia"


# 全局单例
detector = VersionDetector()
