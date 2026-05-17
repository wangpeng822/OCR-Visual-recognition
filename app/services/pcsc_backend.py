from __future__ import annotations

import ctypes
from collections import deque
from ctypes import POINTER, Structure, byref, c_void_p, create_unicode_buffer
from ctypes.wintypes import DWORD, HANDLE, LONG, LPCWSTR

from app.models.nfc_models import NfcDeviceState, NfcRecord


SCARD_S_SUCCESS = 0x00000000
SCARD_SCOPE_USER = 0x00000000
SCARD_SHARE_SHARED = 0x00000002
SCARD_PROTOCOL_T0 = 0x00000001
SCARD_PROTOCOL_T1 = 0x00000002
SCARD_LEAVE_CARD = 0x00000000

GET_UID_APDU = bytes([0xFF, 0xCA, 0x00, 0x00, 0x00])


class SCARD_IO_REQUEST(Structure):
    _fields_ = [
        ("dwProtocol", DWORD),
        ("cbPciLength", DWORD),
    ]


class NfcServiceError(RuntimeError):
    def __init__(
        self,
        user_message: str,
        *,
        error_code: str | None = None,
        status_text: str | None = None,
        operation_text: str | None = None,
        severity: str = "warning",
    ) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.error_code = error_code or ""
        self.status_text = status_text or "异常"
        self.operation_text = operation_text or user_message
        self.severity = severity


class PcscBackend:
    def __init__(self) -> None:
        self.state = NfcDeviceState(operation_text="等待连接 PC/SC 读卡器")
        self.records: deque[NfcRecord] = deque(maxlen=8)
        self._context = HANDLE()
        self._card_handle = HANDLE()
        self._active_protocol = DWORD(0)
        self._connected_reader = ""
        self._winscard = ctypes.WinDLL("winscard.dll")
        self._configure_winscard()

    def connect_reader(self) -> tuple[NfcDeviceState, NfcRecord]:
        self._update_state(status_text="连接中", operation_text="正在搜索读卡器")
        self._disconnect_card()
        self._ensure_context()
        reader_name = self._pick_reader()
        self._connect_card(reader_name)
        self._update_state(
            connected=True,
            status_text="已连接",
            reader_name=reader_name,
            protocol=self._format_protocol(self._active_protocol.value),
            last_seen_text="读卡器已连接",
            operation_text="已连接，可读取 UID",
        )
        record = self._push_record("设备", f"{reader_name} 已连接")
        return self.state, record

    def read_uid(self) -> tuple[str, NfcDeviceState, NfcRecord]:
        self._require_connected()
        self._update_state(operation_text="正在读取 UID")
        response = self._transmit(GET_UID_APDU)
        uid = self._parse_uid_response(response)
        self._update_state(
            last_uid=uid,
            last_seen_text="刚刚读取 UID",
            operation_text="读卡完成",
        )
        record = self._push_record("读取", uid)
        return uid, self.state, record

    def prepare_write(self, value: str) -> tuple[NfcDeviceState, NfcRecord]:
        clean_value = value.strip()
        if not clean_value:
            raise NfcServiceError("待写入编号不能为空", status_text="参数无效", operation_text="写卡参数为空")
        self._require_connected()
        self._update_state(operation_text="写卡被阻止", last_written=clean_value)
        record = self._push_record("写入阻止", clean_value)
        return self.state, record

    def shutdown(self) -> NfcDeviceState:
        self._disconnect_card()
        if self._context.value:
            self._winscard.SCardReleaseContext(self._context)
            self._context = HANDLE()
        self._update_state(
            connected=False,
            status_text="未连接",
            reader_name="未检测到设备",
            protocol="-",
            operation_text="已断开",
        )
        return self.state

    def list_readers(self) -> list[str]:
        self._ensure_context()
        return self._list_readers()

    def _configure_winscard(self) -> None:
        self._winscard.SCardEstablishContext.argtypes = [DWORD, c_void_p, c_void_p, POINTER(HANDLE)]
        self._winscard.SCardEstablishContext.restype = LONG

        self._winscard.SCardReleaseContext.argtypes = [HANDLE]
        self._winscard.SCardReleaseContext.restype = LONG

        self._winscard.SCardListReadersW.argtypes = [HANDLE, LPCWSTR, c_void_p, POINTER(DWORD)]
        self._winscard.SCardListReadersW.restype = LONG

        self._winscard.SCardConnectW.argtypes = [
            HANDLE,
            LPCWSTR,
            DWORD,
            DWORD,
            POINTER(HANDLE),
            POINTER(DWORD),
        ]
        self._winscard.SCardConnectW.restype = LONG

        self._winscard.SCardDisconnect.argtypes = [HANDLE, DWORD]
        self._winscard.SCardDisconnect.restype = LONG

        self._winscard.SCardTransmit.argtypes = [
            HANDLE,
            POINTER(SCARD_IO_REQUEST),
            c_void_p,
            DWORD,
            c_void_p,
            c_void_p,
            POINTER(DWORD),
        ]
        self._winscard.SCardTransmit.restype = LONG

    def _ensure_context(self) -> None:
        if self._context.value:
            return
        result = self._winscard.SCardEstablishContext(
            SCARD_SCOPE_USER,
            None,
            None,
            byref(self._context),
        )
        self._check(
            result,
            "无法初始化 PC/SC 上下文",
            default_status="系统服务异常",
            default_operation="智能卡服务未就绪",
        )

    def _pick_reader(self) -> str:
        readers = self._list_readers()
        if not readers:
            raise NfcServiceError(
                "未检测到读卡器，请插入 USB 读卡器并确认驱动已安装。",
                error_code="NO_READER",
                status_text="未插读卡器",
                operation_text="等待读卡器接入",
            )
        return readers[0]

    def _list_readers(self) -> list[str]:
        size = DWORD(0)
        result = self._winscard.SCardListReadersW(self._context, None, None, byref(size))
        self._check(
            result,
            "无法枚举读卡器",
            default_status="读卡器异常",
            default_operation="读卡器列表读取失败",
        )
        if size.value <= 1:
            return []

        buffer = create_unicode_buffer(size.value)
        result = self._winscard.SCardListReadersW(self._context, None, buffer, byref(size))
        self._check(
            result,
            "无法读取读卡器列表",
            default_status="读卡器异常",
            default_operation="读卡器列表读取失败",
        )
        raw = buffer[: size.value]
        return [item for item in raw.split("\x00") if item]

    def _connect_card(self, reader_name: str) -> None:
        card_handle = HANDLE()
        active_protocol = DWORD(0)
        result = self._winscard.SCardConnectW(
            self._context,
            reader_name,
            SCARD_SHARE_SHARED,
            SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1,
            byref(card_handle),
            byref(active_protocol),
        )
        self._check(
            result,
            f"无法连接读卡器 {reader_name}",
            default_status="连接失败",
            default_operation="读卡器连接失败",
        )
        self._card_handle = card_handle
        self._active_protocol = active_protocol
        self._connected_reader = reader_name

    def _require_connected(self) -> None:
        if not self._card_handle.value:
            raise NfcServiceError(
                "NFC 设备尚未连接，请先点击“连接设备”。",
                error_code="NOT_CONNECTED",
                status_text="未连接",
                operation_text="等待连接设备",
            )

    def _transmit(self, payload: bytes) -> bytes:
        send_pci = SCARD_IO_REQUEST(self._active_protocol.value, ctypes.sizeof(SCARD_IO_REQUEST))
        send_buffer = ctypes.create_string_buffer(payload)
        recv_buffer = ctypes.create_string_buffer(258)
        recv_length = DWORD(len(recv_buffer))
        result = self._winscard.SCardTransmit(
            self._card_handle,
            byref(send_pci),
            send_buffer,
            len(payload),
            None,
            recv_buffer,
            byref(recv_length),
        )
        self._check(
            result,
            "读卡指令发送失败",
            default_status="读卡失败",
            default_operation="标签通信失败",
        )
        return recv_buffer.raw[: recv_length.value]

    def _parse_uid_response(self, response: bytes) -> str:
        if len(response) < 2:
            raise NfcServiceError(
                "读卡器返回数据异常，请重新放置卡片后重试。",
                error_code="SHORT_RESPONSE",
                status_text="读卡失败",
                operation_text="返回数据异常",
            )
        status_word = response[-2:]
        if status_word != b"\x90\x00":
            code = status_word.hex().upper()
            if status_word == b"\x63\x00":
                raise NfcServiceError(
                    "未检测到可读取的标签，请将卡片贴近读卡器。",
                    error_code=code,
                    status_text="未放卡",
                    operation_text="等待标签靠近",
                )
            raise NfcServiceError(
                f"读取 UID 失败，设备返回状态码 {code}",
                error_code=code,
                status_text="读卡失败",
                operation_text="UID 读取失败",
            )
        uid_bytes = response[:-2]
        if not uid_bytes:
            raise NfcServiceError(
                "未读取到 UID，请确认标签已贴近读卡器。",
                error_code="EMPTY_UID",
                status_text="未放卡",
                operation_text="等待标签靠近",
            )
        return uid_bytes.hex().upper()

    def _disconnect_card(self) -> None:
        if self._card_handle.value:
            self._winscard.SCardDisconnect(self._card_handle, SCARD_LEAVE_CARD)
            self._card_handle = HANDLE()
            self._active_protocol = DWORD(0)
            self._connected_reader = ""

    def _check(
        self,
        code: int,
        message: str,
        *,
        default_status: str = "异常",
        default_operation: str | None = None,
    ) -> None:
        if code == SCARD_S_SUCCESS:
            return
        normalized = code & 0xFFFFFFFF
        known = self._known_error_details(normalized)
        user_message = known["message"] if known else f"{message} ({self._format_error(normalized)})"
        raise NfcServiceError(
            user_message,
            error_code=self._format_error(normalized),
            status_text=known["status_text"] if known else default_status,
            operation_text=known["operation_text"] if known else (default_operation or message),
            severity=known["severity"] if known else "warning",
        )

    @staticmethod
    def _format_protocol(protocol: int) -> str:
        if protocol == SCARD_PROTOCOL_T0:
            return "PC/SC T=0"
        if protocol == SCARD_PROTOCOL_T1:
            return "PC/SC T=1"
        if protocol == (SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1):
            return "PC/SC T=0/T=1"
        return f"PC/SC 0x{protocol:02X}"

    @staticmethod
    def _format_error(code: int) -> str:
        known = {
            0x80100009: "SCARD_E_UNKNOWN_READER",
            0x8010000A: "SCARD_E_TIMEOUT",
            0x8010000B: "SCARD_E_SHARING_VIOLATION",
            0x8010000C: "SCARD_E_NO_SMARTCARD",
            0x8010000D: "SCARD_E_UNKNOWN_CARD",
            0x80100010: "SCARD_E_NOT_READY",
            0x8010001D: "SCARD_E_NO_SERVICE",
            0x8010001F: "SCARD_E_READER_UNAVAILABLE",
            0x8010002E: "SCARD_W_REMOVED_CARD",
        }
        return known.get(code, f"0x{code:08X}")

    @staticmethod
    def _known_error_details(code: int) -> dict[str, str] | None:
        known: dict[int, dict[str, str]] = {
            0x8010001D: {
                "message": "Windows 智能卡服务未启动，请先启动系统服务 SCardSvr。",
                "status_text": "服务未启动",
                "operation_text": "等待系统智能卡服务启动",
                "severity": "critical",
            },
            0x8010001F: {
                "message": "读卡器当前不可用，请重新插拔设备后重试。",
                "status_text": "读卡器不可用",
                "operation_text": "等待读卡器恢复",
                "severity": "warning",
            },
            0x80100009: {
                "message": "系统识别不到指定读卡器，请检查驱动是否正常。",
                "status_text": "读卡器异常",
                "operation_text": "等待驱动恢复",
                "severity": "warning",
            },
            0x8010000C: {
                "message": "未检测到卡片，请将标签贴近读卡器感应区。",
                "status_text": "未放卡",
                "operation_text": "等待标签靠近",
                "severity": "info",
            },
            0x8010002E: {
                "message": "卡片已移开，请重新将标签贴近读卡器。",
                "status_text": "卡片已移开",
                "operation_text": "等待标签重新放置",
                "severity": "info",
            },
            0x8010000B: {
                "message": "读卡器被其他程序占用，请关闭冲突程序后重试。",
                "status_text": "读卡器忙",
                "operation_text": "等待设备释放",
                "severity": "warning",
            },
            0x8010000A: {
                "message": "读卡超时，请保持标签稳定贴近读卡器后重试。",
                "status_text": "读卡超时",
                "operation_text": "等待重新读卡",
                "severity": "info",
            },
            0x80100010: {
                "message": "读卡器尚未准备好，请稍后重试。",
                "status_text": "设备未就绪",
                "operation_text": "等待设备就绪",
                "severity": "warning",
            },
        }
        return known.get(code)

    def _push_record(self, title: str, value: str) -> NfcRecord:
        record = NfcRecord(title=title, value=value)
        self.records.appendleft(record)
        return record

    def _update_state(self, **changes: object) -> None:
        for key, value in changes.items():
            setattr(self.state, key, value)
