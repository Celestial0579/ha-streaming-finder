"""Termine der Merkliste: neue Folgen und Starttermine."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, DOMAIN
from .merkliste import MerklisteKoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    koordinator = entry.runtime_data.merkliste
    if koordinator is not None:
        async_add_entities([MerklisteKalender(koordinator)])


def _ereignis(termin: dict) -> CalendarEvent:
    return CalendarEvent(
        start=termin["datum"],
        end=termin["datum"] + timedelta(days=1),
        summary=termin["titel"],
        description=termin["beschreibung"],
        uid=termin["uid"],
    )


class MerklisteKalender(CoordinatorEntity[MerklisteKoordinator], CalendarEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "termine"
    _attr_icon = "mdi:calendar-star"
    _attr_attribution = ATTRIBUTION

    def __init__(self, koordinator: MerklisteKoordinator) -> None:
        super().__init__(koordinator)
        eintrag = koordinator.config_entry
        self._attr_unique_id = f"{eintrag.entry_id}_termine"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, eintrag.entry_id)}, name="Streaming-Finder", entry_type=DeviceEntryType.SERVICE
        )

    @property
    def event(self) -> CalendarEvent | None:
        heute = dt_util.now().date()
        kommend = [t for t in self.coordinator.termine if t["datum"] >= heute]
        return _ereignis(kommend[0]) if kommend else None

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        von, bis = dt_util.as_local(start_date).date(), dt_util.as_local(end_date).date()
        return [_ereignis(t) for t in self.coordinator.termine if von <= t["datum"] < bis or t["datum"] == von]
