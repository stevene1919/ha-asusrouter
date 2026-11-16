"""AsusRouter WAN module."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from asusrouter.modules.common.connection import (
    ARConnectionMethod,
    ARConnectionStatus,
)
from asusrouter.modules.service.action import ARServiceAction
from asusrouter.modules.wan import (
    ARDualWanMode,
    ARWan,
    ARWanAddress,
    ARWanSourceUniversal,
    ARWanUnit,
)
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import EntityCategory

from ..entity import (
    ARBinarySensorDescription,
    ARSensorDescription,
    ARSwitchDescription,
)
from ..helpers import to_str

UPDATE_INTERVAL = timedelta(seconds=30)

# Index of the unit, its key and its unique_id label
_UNITS = ((0, "", ""), (1, "_secondary", " (Secondary)"))


def _get_wan(data: Any) -> ARWan | None:
    """Get the WAN state, None when nothing was read."""

    return data if isinstance(data, ARWan) else None


# The device reports its WAN, not keyed by its MAC
_WAN: dict[str, Any] = {
    "source": ARWanSourceUniversal,
    "update_interval": UPDATE_INTERVAL,
    "data_fn": _get_wan,
    "entity_category": EntityCategory.DIAGNOSTIC,
}


def _has_aggregation(wan: ARWan) -> bool:
    """Get whether the device reports WAN aggregation."""

    return wan.aggregation is not None


def _has_dual_wan(wan: ARWan) -> bool:
    """Get whether the device reports dual WAN."""

    return wan.dualwan is not None


def _get_internet_attributes(wan: ARWan) -> dict[str, Any]:
    """Get the attributes of the internet connection."""

    unit = None if wan.active_unit is None else wan.units.get(wan.active_unit)

    return {
        "ip_address": None if unit is None else to_str(unit.main.ip),
        "wan_unit": wan.active_unit,
    }


def _get_unit_attributes(unit: ARWanUnit) -> dict[str, Any]:
    """Get the attributes of a WAN unit."""

    protocol = unit.protocol

    return {
        "link": unit.link,
        "primary": unit.primary,
        "protocol": (
            None if protocol is ARConnectionMethod.UNKNOWN else protocol.value
        ),
    }


def _get_address_attributes(address: ARWanAddress) -> dict[str, Any]:
    """Get the attributes of a WAN address."""

    return {
        "dns": [str(dns) for dns in address.dns],
        "expires": address.expires,
        "gateway": to_str(address.gateway),
        "lease": address.lease,
        "mask": to_str(address.mask),
    }


def _get_unit_sensor(
    index: int, key: str, label: str
) -> ARBinarySensorDescription:
    """Get the description of the binary sensor of a WAN unit."""

    return ARBinarySensorDescription(
        key=f"wan{key}",
        translation_key=f"wan{key}",
        unique_id_name=f"WAN{label}",
        value_fn=lambda wan: (
            wan.units[index].status is ARConnectionStatus.CONNECTED
        ),
        attributes_fn=lambda wan: _get_unit_attributes(wan.units[index]),
        available_fn=lambda wan: (
            index in wan.units
            and wan.units[index].status is not ARConnectionStatus.UNKNOWN
        ),
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_registry_enabled_default=False,
        **_WAN,
    )


def _get_address_sensor(
    index: int, key: str, label: str, *, extra: bool
) -> ARSensorDescription:
    """Get the description of the sensor of a WAN unit address."""

    def _get_address(wan: ARWan) -> ARWanAddress:
        """Get the address of the unit."""

        unit = wan.units[index]
        return unit.extra if extra else unit.main

    suffix = "_extra" if extra else ""

    return ARSensorDescription(
        key=f"wan_ip{key}{suffix}",
        translation_key=f"wan_ip{key}{suffix}",
        unique_id_name=f"WAN IP{label}{' (Extra)' if extra else ''}",
        value_fn=lambda wan: to_str(_get_address(wan).ip),
        attributes_fn=lambda wan: _get_address_attributes(_get_address(wan)),
        available_fn=lambda wan: index in wan.units,
        entity_registry_enabled_default=False,
        **_WAN,
    )


BINARY_SENSORS: tuple[ARBinarySensorDescription, ...] = (
    ARBinarySensorDescription(
        key="dual_wan",
        translation_key="dual_wan",
        unique_id_name="Dual WAN",
        value_fn=lambda wan: wan.dualwan.state,
        attributes_fn=lambda wan: {
            "mode": (
                None
                if wan.dualwan.mode is ARDualWanMode.UNKNOWN
                else wan.dualwan.mode.name.lower()
            ),
            "priority": wan.dualwan.priority,
        },
        available_fn=_has_dual_wan,
        exists_fn=_has_dual_wan,
        entity_registry_enabled_default=False,
        **_WAN,
    ),
    ARBinarySensorDescription(
        key="internet",
        translation_key="internet",
        unique_id_name="Internet",
        value_fn=lambda wan: (
            wan.internet_status is ARConnectionStatus.CONNECTED
        ),
        attributes_fn=_get_internet_attributes,
        available_fn=lambda wan: (
            wan.internet_status is not ARConnectionStatus.UNKNOWN
        ),
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        **_WAN,
    ),
    *(_get_unit_sensor(*unit) for unit in _UNITS),
    ARBinarySensorDescription(
        key="wan_aggregation",
        translation_key="wan_aggregation",
        unique_id_name="WAN Aggregation",
        value_fn=lambda wan: wan.aggregation.state,
        attributes_fn=lambda wan: {"ports": wan.aggregation.ports},
        available_fn=_has_aggregation,
        exists_fn=_has_aggregation,
        entity_registry_enabled_default=False,
        **_WAN,
    ),
)

SENSORS: tuple[ARSensorDescription, ...] = tuple(
    _get_address_sensor(*unit, extra=extra)
    for extra in (False, True)
    for unit in _UNITS
)


def _wan_action(
    state: bool,
    data: Any,
    bridge: Any | None = None,
) -> ARServiceAction:
    """Build the action to connect or disconnect WAN."""

    is_dsl = False
    if bridge and hasattr(bridge, "identity") and bridge.identity.model:
        is_dsl = "dsl" in bridge.identity.model.lower()
    elif (
        isinstance(data, ARWan)
        and data.dualwan
        and "dsl" in data.dualwan.capability
    ):
        is_dsl = True

    service = (
        ("start_dslwan_if 0" if state else "stop_dslwan_if 0")
        if is_dsl
        else ("start_wan" if state else "stop_wan")
    )
    val = "1" if state else "0"
    args = {
        "action_script": service,
        "wan_enable": val,
        "wan0_enable": val,
        "freeze_duck": "0",
    }
    if is_dsl:
        args["dslx_link_enable"] = val

    return ARServiceAction(service, arguments=args)


SWITCHES: tuple[ARSwitchDescription, ...] = (
    ARSwitchDescription(
        key="internet",
        translation_key="internet",
        unique_id_name="Internet",
        source=ARWanSourceUniversal,
        update_interval=UPDATE_INTERVAL,
        data_fn=_get_wan,
        value_fn=lambda wan: (
            wan.internet_status is ARConnectionStatus.CONNECTED
            if isinstance(wan, ARWan)
            else None
        ),
        available_fn=lambda wan: (
            isinstance(wan, ARWan)
            and wan.internet_status is not ARConnectionStatus.UNKNOWN
        ),
        action_fn=_wan_action,
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
    ),
)
