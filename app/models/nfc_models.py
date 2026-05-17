from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NfcRecord:
    title: str
    value: str
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def display_text(self) -> str:
        return f"{self.timestamp:%H:%M:%S}  {self.title}: {self.value}"


@dataclass
class NfcDeviceState:
    connected: bool = False
    status_text: str = "未连接"
    reader_name: str = "未检测到设备"
    protocol: str = "-"
    last_uid: str = "-"
    last_written: str = "-"
    last_seen_text: str = "等待连接"
    operation_text: str = "空闲"
