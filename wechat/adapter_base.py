"""
微信适配器抽象基类 — 定义统一接口
所有微信自动化后端必须实现此接口
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ChatMonitor:
    """聊天监控器 — 一个联系人/群对应一个实例"""
    name: str
    chat_type: str  # 'contact' | 'group'
    adapter: "WeChatAdapter"
    running: bool = False
    on_message: Optional[Callable] = None
    # Signature: (monitor, sender, content, is_image=False, msg_control=None,
    #             is_group=False, is_at=False, hwnd=0) -> None

    @abstractmethod
    def start(self) -> bool:
        """启动监控"""
        ...

    @abstractmethod
    def stop(self):
        """停止监控"""
        ...


class WeChatAdapter(ABC):
    """微信适配器抽象基类"""

    name: str = "base"
    description: str = "Abstract adapter"
    supported_versions: list[str] = []

    @abstractmethod
    def connect(self) -> bool:
        """连接到微信"""
        ...

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """是否已连接"""
        ...

    @abstractmethod
    def send_message(self, target: str, text: str) -> bool:
        """发送文字消息"""
        ...

    def send_file(self, target: str, filepath: str) -> bool:
        """发送文件/图片"""
        return False

    @abstractmethod
    def open_chat_monitor(self, name: str, chat_type: str = "contact") -> Optional[ChatMonitor]:
        """为指定联系人/群聊打开独立窗口监控器"""
        ...

    def get_version_info(self) -> str:
        """获取微信版本信息"""
        return "unknown"

    def __repr__(self):
        return f"<{self.name}>"
