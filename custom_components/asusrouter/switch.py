"""AsusRouter switch module."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
)

from . import ARConfigEntry
from .entity import ARSwitchDescription, ARToggleEntity, async_setup_entities
from .modules import SWITCHES


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ARConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AsusRouter switches."""

    async_setup_entities(config_entry, SWITCHES, ARSwitch, async_add_entities)


class ARSwitch(ARToggleEntity, SwitchEntity):
    """AsusRouter switch."""

    entity_description: ARSwitchDescription

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize switch."""

        super().__init__(*args, **kwargs)
        self._attr_is_on: bool | None = None

    @property
    def is_on(self) -> bool | None:
        """Return the entity state."""

        if self._attr_is_on is not None:
            return self._attr_is_on
        return super().is_on

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""

        if self._attr_is_on is not None:
            native = super().is_on
            if native is not None and native == self._attr_is_on:
                self._attr_is_on = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""

        self._attr_is_on = True
        self.async_write_ha_state()
        try:
            await super().async_turn_on(**kwargs)
        except Exception:
            self._attr_is_on = None
            self.async_write_ha_state()
            raise

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""

        self._attr_is_on = False
        self.async_write_ha_state()
        try:
            await super().async_turn_off(**kwargs)
        except Exception:
            self._attr_is_on = None
            self.async_write_ha_state()
            raise
