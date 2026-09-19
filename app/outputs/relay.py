"""Bariyer/kapi kontrol uniteleri gibi dis I/O kartlarina acik/kapali sinyali
gondermek icin degistirilebilir role suruculeri. Marka/model bagimsiz
calisabilmesi icin en yaygin uc protokol desteklenir: duz HTTP cagrisi,
ham TCP komutu ve Modbus TCP (tek bobin/coil yazma, fonksiyon kodu 0x05).
Gercek donanim olmadan da `NoneRelay` ile arayuz test edilebilir."""

import socket
import struct
import time
from abc import ABC, abstractmethod

import requests

from app.models import Camera, RelayType


class RelayDriver(ABC):
    @abstractmethod
    def trigger_open(self, pulse_seconds: float) -> tuple[bool, str]:
        raise NotImplementedError


class NoneRelay(RelayDriver):
    def trigger_open(self, pulse_seconds: float) -> tuple[bool, str]:
        return False, "Bu kamera icin role yapilandirilmamis (relay_type=none)"


class HttpRelay(RelayDriver):
    """relay_target: tam URL (orn. http://192.168.1.50/api/relay1/open).
    Cogu ag tabanli bariyer/role kartinin HTTP tetikleme uc noktasi vardir."""

    def __init__(self, url: str, timeout: float = 5.0):
        self._url = url
        self._timeout = timeout

    def trigger_open(self, pulse_seconds: float) -> tuple[bool, str]:
        try:
            response = requests.get(self._url, timeout=self._timeout)
            ok = response.status_code < 400
            return ok, f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            return False, f"HTTP istegi basarisiz: {exc}"


class TcpRelay(RelayDriver):
    """relay_target: 'ip:port'. relay_command: acilis icin gonderilecek ham
    metin komutu (kart uretucusunun dokumantasyonuna gore, orn. 'REL1ON\\r\\n')."""

    def __init__(self, host: str, port: int, command: str, timeout: float = 5.0):
        self._host = host
        self._port = port
        self._command = command
        self._timeout = timeout

    def trigger_open(self, pulse_seconds: float) -> tuple[bool, str]:
        try:
            with socket.create_connection((self._host, self._port), timeout=self._timeout) as sock:
                sock.sendall(self._command.encode())
            return True, f"TCP komutu gonderildi: {self._host}:{self._port}"
        except OSError as exc:
            return False, f"TCP baglantisi basarisiz: {exc}"


def _modbus_write_coil(host: str, port: int, coil_address: int, value_on: bool, unit_id: int = 1, timeout: float = 5.0) -> bytes:
    transaction_id = 1
    protocol_id = 0
    function_code = 0x05
    output_value = 0xFF00 if value_on else 0x0000
    pdu = struct.pack(">BHH", function_code, coil_address, output_value)
    length = len(pdu) + 1
    mbap = struct.pack(">HHHB", transaction_id, protocol_id, length, unit_id)
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(mbap + pdu)
        return sock.recv(256)


class ModbusTcpRelay(RelayDriver):
    """relay_target: 'ip:port' (varsayilan Modbus TCP portu 502).
    relay_command: yazilacak coil (bobin) adresi, orn. '0'."""

    def __init__(self, host: str, port: int, coil_address: int, timeout: float = 5.0):
        self._host = host
        self._port = port
        self._coil_address = coil_address
        self._timeout = timeout

    def trigger_open(self, pulse_seconds: float) -> tuple[bool, str]:
        try:
            _modbus_write_coil(self._host, self._port, self._coil_address, True, timeout=self._timeout)
            time.sleep(min(pulse_seconds, 30))
            _modbus_write_coil(self._host, self._port, self._coil_address, False, timeout=self._timeout)
            return True, f"Modbus TCP coil {self._coil_address} tetiklendi ({pulse_seconds}s)"
        except OSError as exc:
            return False, f"Modbus TCP baglantisi basarisiz: {exc}"


def _split_host_port(target: str, default_port: int) -> tuple[str, int]:
    if ":" in target:
        host, port_str = target.rsplit(":", 1)
        return host, int(port_str)
    return target, default_port


def build_relay_driver(camera: Camera) -> RelayDriver:
    if camera.relay_type == RelayType.HTTP:
        return HttpRelay(camera.relay_target)
    if camera.relay_type == RelayType.TCP:
        host, port = _split_host_port(camera.relay_target, 9000)
        return TcpRelay(host, port, camera.relay_command)
    if camera.relay_type == RelayType.MODBUS_TCP:
        host, port = _split_host_port(camera.relay_target, 502)
        coil_address = int(camera.relay_command or 0)
        return ModbusTcpRelay(host, port, coil_address)
    return NoneRelay()
