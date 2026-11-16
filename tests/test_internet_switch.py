"""Tests for AsusRouter Internet switch."""

from unittest.mock import AsyncMock, MagicMock

from asusrouter.connection import RequestType
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import EntityCategory
import pytest

from custom_components.asusrouter.switch import ARInternetSwitch


@pytest.fixture
def mock_router():
    """Create a mock ARDevice."""
    router = MagicMock()
    router._conf_name = "DSL-AX82U"
    router.mac = "AA:BB:CC:DD:EE:FF"
    router.device_info = {"identifiers": {("asusrouter", "AA:BB:CC:DD:EE:FF")}}
    router.bridge = MagicMock()
    router.bridge.api = MagicMock()
    router.bridge.api._connection = MagicMock()
    router.bridge.api._connection.async_query = AsyncMock(
        return_value=(200, {}, "OK")
    )
    router.bridge.api.async_run_service = AsyncMock(return_value=True)
    return router


@pytest.fixture
def mock_coordinator():
    """Create a mock DataUpdateCoordinator."""
    coordinator = MagicMock()
    coordinator.data = {"internet_link": True, "0_state": True}
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


def test_internet_switch_init(mock_coordinator, mock_router):
    """Test switch initialization and properties."""
    switch = ARInternetSwitch(mock_coordinator, mock_router)

    assert switch.name == "DSL-AX82U Internet"
    assert switch.unique_id == "aa:_bb:_cc:_dd:_ee:_ff_internet"
    assert switch.entity_description.device_class == SwitchDeviceClass.SWITCH
    assert switch.entity_description.entity_category == EntityCategory.CONFIG
    assert switch.is_on is True
    assert switch.icon == "mdi:web"


def test_internet_switch_is_on_false(mock_coordinator, mock_router):
    """Test switch is_on when disconnected."""
    mock_coordinator.data = {"internet_link": False}
    switch = ARInternetSwitch(mock_coordinator, mock_router)

    assert switch.is_on is False
    assert switch.icon == "mdi:web-off"


def test_internet_switch_is_on_fallback(mock_coordinator, mock_router):
    """Test switch is_on fallback to 0_state."""
    mock_coordinator.data = {"0_state": True}
    switch = ARInternetSwitch(mock_coordinator, mock_router)

    assert switch.is_on is True


@pytest.mark.asyncio
async def test_internet_switch_turn_on(mock_coordinator, mock_router):
    """Test turning on the internet switch."""
    mock_coordinator.data = {"internet_link": False}
    switch = ARInternetSwitch(mock_coordinator, mock_router)
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_on()

    assert switch.is_on is True
    mock_router.bridge.api._connection.async_query.assert_awaited_once()
    call_args = mock_router.bridge.api._connection.async_query.call_args
    assert call_args.kwargs["payload"] == "wanaction=Connect"
    assert call_args.kwargs["request_type"] == RequestType.GET
    mock_coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_internet_switch_turn_off(mock_coordinator, mock_router):
    """Test turning off the internet switch."""
    mock_coordinator.data = {"internet_link": True}
    switch = ARInternetSwitch(mock_coordinator, mock_router)
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_off()

    assert switch.is_on is False
    mock_router.bridge.api._connection.async_query.assert_awaited_once()
    call_args = mock_router.bridge.api._connection.async_query.call_args
    assert call_args.kwargs["payload"] == "wanaction=Disconnect"
    assert call_args.kwargs["request_type"] == RequestType.GET
    mock_coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_internet_switch_fallback_on_error(
    mock_coordinator, mock_router
):
    """Test fallback to async_run_service when wan_action.asp fails."""
    mock_router.bridge.api._connection.async_query.side_effect = Exception(
        "Connection refused"
    )
    switch = ARInternetSwitch(mock_coordinator, mock_router)
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_on()

    mock_router.bridge.api.async_run_service.assert_awaited_once_with(
        service="start_wan", apply=True
    )
    mock_coordinator.async_request_refresh.assert_awaited_once()
