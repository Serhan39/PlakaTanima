from unittest.mock import MagicMock, patch

from app.models import Camera, RelayType
from app.outputs.relay import HttpRelay, ModbusTcpRelay, NoneRelay, TcpRelay, build_relay_driver


def _camera(**kwargs) -> Camera:
    defaults = dict(
        id=1,
        name="Test Kamera",
        rtsp_url="rtsp://demo",
        relay_type=RelayType.NONE,
        relay_target="",
        relay_command="",
        relay_pulse_seconds=1.0,
        open_categories="allowed,staff",
    )
    defaults.update(kwargs)
    return Camera(**defaults)


def test_build_relay_driver_none():
    driver = build_relay_driver(_camera())
    assert isinstance(driver, NoneRelay)
    success, message = driver.trigger_open(1.0)
    assert success is False


def test_build_relay_driver_http():
    driver = build_relay_driver(_camera(relay_type=RelayType.HTTP, relay_target="http://192.168.1.1/open"))
    assert isinstance(driver, HttpRelay)


def test_build_relay_driver_tcp_splits_host_port():
    driver = build_relay_driver(
        _camera(relay_type=RelayType.TCP, relay_target="192.168.1.1:9000", relay_command="OPEN\r\n")
    )
    assert isinstance(driver, TcpRelay)
    assert driver._host == "192.168.1.1"
    assert driver._port == 9000


def test_build_relay_driver_modbus_default_port():
    driver = build_relay_driver(_camera(relay_type=RelayType.MODBUS_TCP, relay_target="192.168.1.1", relay_command="0"))
    assert isinstance(driver, ModbusTcpRelay)
    assert driver._port == 502
    assert driver._coil_address == 0


def test_http_relay_success():
    with patch("app.outputs.relay.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        driver = HttpRelay("http://example.local/open")
        success, message = driver.trigger_open(1.0)
        assert success is True


def test_http_relay_failure_status():
    with patch("app.outputs.relay.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=500)
        driver = HttpRelay("http://example.local/open")
        success, _ = driver.trigger_open(1.0)
        assert success is False


def test_modbus_relay_sends_write_coil_frames():
    with patch("app.outputs.relay.socket.create_connection") as mock_conn:
        sock = MagicMock()
        mock_conn.return_value.__enter__.return_value = sock
        sock.recv.return_value = b"\x00\x01\x00\x00\x00\x06\x01\x05\x00\x00\xff\x00"

        driver = ModbusTcpRelay("192.168.1.1", 502, coil_address=0)
        success, message = driver.trigger_open(0)

        assert success is True
        assert sock.sendall.call_count == 2
        first_frame = sock.sendall.call_args_list[0][0][0]
        assert first_frame[-4:] == b"\x00\x00\xff\x00"  # function 05, coil 0, ON
