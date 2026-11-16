"""AsusRouter switch module."""

from __future__ import annotations

import logging
from typing import Any

from asusrouter.modules.homeassistant import convert_to_ha_state_bool
from asusrouter.modules.parental_control import ParentalControlRule, PCRuleType
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ASUSROUTER,
    CONF_DEFAULT_HIDE_PASSWORDS,
    CONF_HIDE_PASSWORDS,
    COORDINATOR,
    DOMAIN,
    ICON_INTERNET_ACCESS_OFF,
    ICON_INTERNET_ACCESS_ON,
    STATIC_SWITCHES,
    WAN,
)
from .dataclass import ARSwitchDescription
from .entity import ARBinaryEntity, async_setup_ar_entry
from .helpers import to_unique_id
from .router import ARDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AsusRouter switches."""

    switches = STATIC_SWITCHES.copy()

    hide = []
    if config_entry.options.get(
        CONF_HIDE_PASSWORDS, CONF_DEFAULT_HIDE_PASSWORDS
    ):
        hide.extend(["password", "private_key", "psk"])

    await async_setup_ar_entry(
        hass, config_entry, async_add_entities, switches, ARSwitch, hide
    )

    router = hass.data[DOMAIN][config_entry.entry_id][ASUSROUTER]

    # Add Internet switch if WAN coordinator is available
    if WAN in router.sensor_coordinator:
        coordinator = router.sensor_coordinator[WAN][COORDINATOR]
        async_add_entities([ARInternetSwitch(coordinator, router)])

    tracked: set = set()

    @callback
    def update_router():
        """Update the values of the router."""

        add_entities(router, async_add_entities, tracked)

    router.async_on_close(
        async_dispatcher_connect(
            hass, router.signal_pc_rules_new, update_router
        )
    )

    update_router()


@callback
def add_entities(
    router: ARDevice,
    async_add_entities: AddEntitiesCallback,
    tracked: set[str],
) -> None:
    """Add new tracker entities from the router."""

    new_tracked = []

    for mac, rule in router.pc_rules.items():
        if mac in tracked:
            continue

        new_tracked.append(ClientInternetSwitch(router, rule))
        tracked.add(mac)

    if new_tracked:
        async_add_entities(new_tracked)


class ARSwitch(ARBinaryEntity, SwitchEntity):
    """AsusRouter switch."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        router: ARDevice,
        description: ARSwitchDescription,
    ) -> None:
        """Initialize AsusRouter switch."""

        super().__init__(coordinator, router, description)
        self.entity_description: ARSwitchDescription = description

        # State on
        self._state_on = description.state_on
        self._state_on_args = description.state_on_args
        # State off
        self._state_off = description.state_off
        self._state_off_args = description.state_off_args
        # Expect modify
        self._state_expect_modify = description.state_expect_modify

    async def async_turn_on(
        self,
        **kwargs: Any,
    ) -> None:
        """Turn on switch."""

        kwargs = self._state_on_args if self._state_on_args is not None else {}

        await self._set_state(
            state=self._state_on,
            expect_modify=self._state_expect_modify,
            **kwargs,
        )

    async def async_turn_off(
        self,
        **kwargs: Any,
    ) -> None:
        """Turn off switch."""

        kwargs = (
            self._state_off_args if self._state_off_args is not None else {}
        )

        await self._set_state(
            state=self._state_off,
            expect_modify=self._state_expect_modify,
            **kwargs,
        )


class ClientInternetSwitch(SwitchEntity):
    """Client internet switch."""

    def __init__(
        self,
        router: ARDevice,
        rule: ParentalControlRule,
    ):
        """Initialize client switch."""

        self._router = router
        self._rule = rule
        self._mac = dr.format_mac(rule.mac)
        self._attr_unique_id = to_unique_id(
            f"{router.mac}_{self._mac}_block_internet"
        )
        self._attr_name = f"{rule.name} Block Internet"

        # Assign device info if set up
        if router.create_devices is True:
            self._attr_device_info = self._compile_device_info()

    def _compile_device_info(self) -> DeviceInfo:
        """Compile device info."""

        return DeviceInfo(
            connections={(dr.CONNECTION_NETWORK_MAC, self._mac)},
            default_name=self._rule.name,
            via_device=(DOMAIN, self._router.mac),
        )

    @property
    def is_on(self) -> bool | None:
        """Get the state."""

        match self._rule.type:
            case PCRuleType.BLOCK:
                return True
            case PCRuleType.DISABLE:
                return False
            case _:
                return None

    @property
    def icon(self) -> str | None:
        """Get the icon."""

        if self.is_on:
            return ICON_INTERNET_ACCESS_OFF
        return ICON_INTERNET_ACCESS_ON

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""

        return {
            "mac": self._mac,
        }

    async def _set_state(
        self,
        state: ParentalControlRule,
        **kwargs: Any,
    ) -> None:
        """Set state."""

        try:
            _LOGGER.debug("Changing PC rule to %s", state)
            result = await self._router.bridge.api.async_set_state(
                state=state, **kwargs
            )
            self._rule = state
            if not result:
                _LOGGER.debug("State was not set!")
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error("Unable to set state with an exception: %s", ex)

    async def async_turn_on(
        self,
        **kwargs: Any,
    ) -> None:
        """Turn on block."""

        await self._set_state(
            state=ParentalControlRule(
                mac=self._rule.mac,
                name=self._rule.name,
                type=PCRuleType.BLOCK,
            ),
            **kwargs,
        )

    async def async_turn_off(
        self,
        **kwargs: Any,
    ) -> None:
        """Turn off block."""

        await self._set_state(
            state=ParentalControlRule(
                mac=self._rule.mac,
                name=self._rule.name,
                type=PCRuleType.DISABLE,
            ),
            **kwargs,
        )

    @callback
    def async_on_demand_update(self) -> None:
        """Update the state."""

        if self._rule.mac in self._router.pc_rules:
            self._rule = self._router.pc_rules[self._rule.mac]
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register state update callback."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_pc_rules_update,
                self.async_on_demand_update,
            )
        )


class ARInternetSwitch(ARBinaryEntity, SwitchEntity):
    """AsusRouter Internet connect/disconnect switch."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        router: ARDevice,
    ) -> None:
        """Initialize the Internet switch."""

        description = ARSwitchDescription(
            key="internet_link",
            key_group=WAN,
            name="Internet",
            icon_on="mdi:web",
            icon_off="mdi:web-off",
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=True,
            device_class=SwitchDeviceClass.SWITCH,
        )

        super().__init__(coordinator, router, description)
        self.entity_description: ARSwitchDescription = description
        self._attr_is_on: bool | None = None

    def _get_native_state(self) -> bool | None:
        """Get native state from coordinator data."""
        if self.coordinator.data:
            state = self.coordinator.data.get("internet_link")
            if state is not None:
                return convert_to_ha_state_bool(state)
            state_0 = self.coordinator.data.get("0_state")
            if state_0 is not None:
                return convert_to_ha_state_bool(state_0)
        return None

    @property
    def is_on(self) -> bool | None:
        """Get the switch state."""
        if self._attr_is_on is not None:
            return self._attr_is_on

        return self._get_native_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._attr_is_on is not None:
            native = self._get_native_state()
            if native is not None and native == self._attr_is_on:
                self._attr_is_on = None
        super()._handle_coordinator_update()

    def _is_dsl_router(self) -> bool:
        """Determine if router is a DSL model."""
        if hasattr(self.router, "bridge") and self.router.bridge:
            model = getattr(self.router.bridge, "model", "") or ""
            if "dsl" in model.lower():
                return True
        if hasattr(self.router, "_conf_name"):
            conf_name = self.router._conf_name or ""
            if "dsl" in conf_name.lower():
                return True
        return False

    async def _async_trigger_wan_action(self, action: str) -> bool:
        """Trigger WAN action (Connect or Disconnect)."""
        is_connect = action == "Connect"
        is_dsl = self._is_dsl_router()
        service = (
            ("start_dslwan_if 0" if is_connect else "stop_dslwan_if 0")
            if is_dsl
            else ("start_wan" if is_connect else "stop_wan")
        )
        wan_enable = "1" if is_connect else "0"

        _LOGGER.debug(
            "Triggering WAN %s: is_dsl=%s, service=%s, wan_enable=%s",
            action,
            is_dsl,
            service,
            wan_enable,
        )

        # Primary method: applyapp.cgi with rc_service, action_script,
        # wan_enable, wan0_enable, dslx_link_enable, freeze_duck=0
        try:
            commands = {
                "action_mode": "apply",
                "rc_service": service,
                "action_script": service,
                "wan_enable": wan_enable,
                "wan0_enable": wan_enable,
                "freeze_duck": "0",
            }
            if is_dsl:
                commands["dslx_link_enable"] = wan_enable

            _LOGGER.info(
                "Executing WAN %s via async_api_command: %s",
                action,
                commands,
            )
            await self.api.async_api_command(commands)
            return True
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning(
                "WAN action `%s` via async_api_command failed: %s. "
                "Attempting fallback via async_run_service",
                action,
                ex,
            )

        # Fallback method: rc_service call via applyapp.cgi
        try:
            fallback_arguments = {
                "wan_enable": wan_enable,
                "wan0_enable": wan_enable,
                "freeze_duck": "0",
            }
            if is_dsl:
                fallback_arguments["dslx_link_enable"] = wan_enable

            result = await self.api.async_run_service(
                service=service,
                arguments=fallback_arguments,
                apply=True,
                expect_modify=False,
            )
            _LOGGER.info(
                "Executed WAN fallback service `%s`: result=%s",
                service,
                result,
            )
            return bool(result)
        except Exception as ex:  # noqa: BLE001
            _LOGGER.error(
                "Failed to execute WAN fallback service for `%s`: %s",
                action,
                ex,
            )
            return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Connect to the Internet."""
        self._attr_is_on = True
        self.async_write_ha_state()

        success = await self._async_trigger_wan_action("Connect")
        if not success:
            self._attr_is_on = False
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disconnect from the Internet."""
        self._attr_is_on = False
        self.async_write_ha_state()

        success = await self._async_trigger_wan_action("Disconnect")
        if not success:
            self._attr_is_on = True
            self.async_write_ha_state()


