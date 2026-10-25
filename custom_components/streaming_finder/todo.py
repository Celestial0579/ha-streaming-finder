"""Merkliste als (nur lesbare) Liste."""

from __future__ import annotations

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity, TodoListEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .merkliste import MerklisteKoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    koordinator = entry.runtime_data.merkliste
    if koordinator is not None:
        async_add_entities([MerklisteListe(koordinator)])


class MerklisteListe(CoordinatorEntity[MerklisteKoordinator], TodoListEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "merkliste"
    _attr_icon = "mdi:playlist-star"
    _attr_attribution = ATTRIBUTION
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, koordinator: MerklisteKoordinator) -> None:
        super().__init__(koordinator)
        eintrag = koordinator.config_entry
        self._attr_unique_id = f"{eintrag.entry_id}_merkliste"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, eintrag.entry_id)}, name="Streaming-Finder", entry_type=DeviceEntryType.SERVICE
        )

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=e["id"],
                summary=e["titel"],
                description=" · ".join(str(x) for x in (e["art"], e.get("jahr"), e["wo"]) if x),
                status=TodoItemStatus.NEEDS_ACTION,
            )
            for e in self.coordinator.data or []
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Titel suchen und auf die TMDB-Merkliste setzen."""
        await self.coordinator.async_hinzufuegen(str(item.summary or ""))

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Abhaken = gesehen: von der TMDB-Merkliste nehmen."""
        if item.status == TodoItemStatus.COMPLETED and item.uid:
            await self.coordinator.async_entfernen(item.uid)

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self.coordinator.async_entfernen(uid)
