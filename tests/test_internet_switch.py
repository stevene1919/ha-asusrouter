"""Tests for AsusRouter Internet switch."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import EntityCategory
import pytest

from custom_components.asusrouter.switch import ARInternetSwitch


@pytest.fixture
def mock_router():
    """Create a mock ARDevice for a DSL router."""
    router = MagicMock()
    router._conf_name = "DSL-AX82U"
    router.mac = "AA:BB:CC:DD:EE:FF"
    router.device_info = {"identifiers": {("asusrouter", "AA:BB:CC:DD:EE:FF")}}
    router.bridge = MagicMock()
    router.bridge.model = "DSL-AX82U"
    router.bridge.api = MagicMock()
    router.bridge.api.async_api_command = AsyncMock(return_value=True)
    router.bridge.api.async_run_service = AsyncMock(return_value=True)
    return router


@pytest.fixture
def mock_non_dsl_router():
    """Create a mock ARDevice for a non-DSL router."""
    router = MagicMock()
    router._conf_name = "RT-AX88U"
    router.mac = "11:22:33:44:55:66"
    router.device_info = {"identifiers": {("asusrouter", "11:22:33:44:55:66")}}
    router.bridge = MagicMock()
    router.bridge.model = "RT-AX88U"
    router.bridge.api = MagicMock()
    router.bridge.api.async_api_command = AsyncMock(return_value=True)
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
async def test_internet_switch_turn_on_dsl(mock_coordinator, mock_router):
    """Test turning on internet on a DSL router."""
    mock_coordinator.data = {"internet_link": False}
    switch = ARInternetSwitch(mock_coordinator, mock_router)
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_on()

    assert switch.is_on is True
    mock_router.bridge.api.async_api_command.assert_awaited_once_with(
        {
            "action_mode": "apply",
            "rc_service": "start_dslwan_if 0",
            "action_script": "start_dslwan_if 0",
            "wan_enable": "1",
            "wan0_enable": "1",
            "dslx_link_enable": "1",
            "freeze_duck": "0",
        }
    )


@pytest.mark.asyncio
async def test_internet_switch_turn_off_dsl(mock_coordinator, mock_router):
    """Test turning off internet on a DSL router."""
    mock_coordinator.data = {"internet_link": True}
    switch = ARInternetSwitch(mock_coordinator, mock_router)
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_off()

    assert switch.is_on is False
    mock_router.bridge.api.async_api_command.assert_awaited_once_with(
        {
            "action_mode": "apply",
            "rc_service": "stop_dslwan_if 0",
            "action_script": "stop_dslwan_if 0",
            "wan_enable": "0",
            "wan0_enable": "0",
            "dslx_link_enable": "0",
            "freeze_duck": "0",
        }
    )


@pytest.mark.asyncio
async def test_internet_switch_turn_on_non_dsl(
    mock_coordinator, mock_non_dsl_router
):
    """Test turning on internet on a standard Ethernet router."""
    mock_coordinator.data = {"internet_link": False}
    switch = ARInternetSwitch(mock_coordinator, mock_non_dsl_router)
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_on()

    assert switch.is_on is True
    mock_non_dsl_router.bridge.api.async_api_command.assert_awaited_once_with(
        {
            "action_mode": "apply",
            "rc_service": "start_wan",
            "action_script": "start_wan",
            "wan_enable": "1",
            "wan0_enable": "1",
            "freeze_duck": "0",
        }
    )


@pytest.mark.asyncio
async def test_internet_switch_optimistic_state_holding(
    mock_coordinator, mock_router
):
    """Test that optimistic state is preserved until coordinator agrees."""
    mock_coordinator.data = {"internet_link": True}
    switch = ARInternetSwitch(mock_coordinator, mock_router)
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_off()
    assert switch.is_on is False

    # Intermediate update where coordinator still reports True
    # (WAN tearing down)
    mock_coordinator.data = {"internet_link": True}
    switch._handle_coordinator_update()
    # Switch should STILL be False (not bouncing back to True)
    assert switch.is_on is False
    assert switch._attr_is_on is False

    # Eventual update where coordinator reports False (WAN fully stopped)
    mock_coordinator.data = {"internet_link": False}
    switch._handle_coordinator_update()
    # Switch matches, optimistic attribute cleared, native state is False
    assert switch.is_on is False
    assert switch._attr_is_on is None


@pytest.mark.asyncio
async def test_internet_switch_fallback_on_error(
    mock_coordinator, mock_router
):
    """Test fallback to async_run_service when async_api_command fails."""
    mock_router.bridge.api.async_api_command.side_effect = Exception(
        "API command error"
    )
    switch = ARInternetSwitch(mock_coordinator, mock_router)
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_on()

    mock_router.bridge.api.async_run_service.assert_awaited_once_with(
        service="start_dslwan_if 0",
        arguments={
            "wan_enable": "1",
            "wan0_enable": "1",
            "dslx_link_enable": "1",
            "freeze_duck": "0",
        },
        apply=True,
        expect_modify=False,
    )
    assert switch.is_on is True


@pytest.mark.asyncio
async def test_internet_switch_revert_on_total_failure(
    mock_coordinator, mock_router
):
    """Test state reverts when both primary and fallback methods fail."""
    mock_coordinator.data = {"internet_link": True}
    mock_router.bridge.api.async_api_command.side_effect = Exception("fail")
    mock_router.bridge.api.async_run_service.side_effect = Exception("fail")
    switch = ARInternetSwitch(mock_coordinator, mock_router)
    switch.async_write_ha_state = MagicMock()

    await switch.async_turn_off()

    # Reverted back to True
    assert switch.is_on is True
