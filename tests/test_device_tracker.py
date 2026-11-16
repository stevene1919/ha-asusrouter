"""Tests for AsusRouter device tracker."""

from unittest.mock import MagicMock

from homeassistant.components.device_tracker import SourceType
from homeassistant.helpers.entity import DeviceInfo

from custom_components.asusrouter.device_tracker import ARDeviceEntity


def test_device_tracker_is_connected_boolean():
    """Test is_connected returns strict boolean."""
    router = MagicMock()
    router.mac = "AA:BB:CC:DD:EE:FF"
    router.client_device = False

    client = MagicMock()
    client.mac_address = "11:22:33:44:55:66"
    client.name = "Phone"
    client.device = False

    # Disconnected state (None) -> must return False, not None
    client.state = None
    tracker = ARDeviceEntity(router, client)
    assert tracker.is_connected is False

    # Connected state (True) -> returns True
    client.state = True
    assert tracker.is_connected is True


def test_device_tracker_empty_device_info():
    """Test empty DeviceInfo when client devices disabled."""
    router = MagicMock()
    router.mac = "AA:BB:CC:DD:EE:FF"
    router.client_device = False

    client = MagicMock()
    client.mac_address = "11:22:33:44:55:66"
    client.name = "Phone"
    client.device = False
    client.state = True

    tracker = ARDeviceEntity(router, client)
    assert isinstance(tracker.device_info, DeviceInfo)
    assert tracker.source_type == SourceType.ROUTER


def test_device_tracker_capability_attributes():
    """Test capability attributes preserves tracking type."""
    router = MagicMock()
    router.mac = "AA:BB:CC:DD:EE:FF"
    router.client_device = False

    client = MagicMock()
    client.mac_address = "11:22:33:44:55:66"
    client.name = "Phone"
    client.device = False
    client.state = True

    tracker = ARDeviceEntity(router, client)
    attrs = tracker.capability_attributes
    assert attrs["mac"] == "11:22:33:44:55:66"
    assert attrs["name"] == "Phone"
