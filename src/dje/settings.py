import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Optional

from .i18n import SUPPORTED_LOCALES

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "guild_settings.json")

_lock = asyncio.Lock()


@dataclass
class GuildSettings:
    locale: str = "tr"
    shortcuts: dict[str, str] = field(default_factory=dict)
    auto_disconnect_enabled: bool = True
    auto_disconnect_minutes: int = 60
    auto_disconnect_warn_minutes: int = 15
    shuffle_mode: str = "none"
    loop_mode: str = "none"


AUTO_DISCONNECT_DEFAULT_ENABLED = True
AUTO_DISCONNECT_DEFAULT_MINUTES = 60
AUTO_DISCONNECT_DEFAULT_WARN_MINUTES = 15
SHUFFLE_MODE_DEFAULT = "none"
LOOP_MODE_DEFAULT = "none"


def _normalize_locale(locale: str) -> str:
    if locale in SUPPORTED_LOCALES:
        return locale
    return "tr"


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _read_all() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def _atomic_write(data: dict) -> None:
    _ensure_data_dir()
    temp_path = SETTINGS_FILE + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=True, indent=2)
    os.replace(temp_path, SETTINGS_FILE)


def _get_entry(data: dict, guild_id: int) -> dict:
    entry = data.get(str(guild_id))
    if isinstance(entry, dict):
        return entry
    return {}


def _extract_shortcuts(entry: dict) -> dict[str, str]:
    shortcuts = entry.get("shortcuts")
    if isinstance(shortcuts, dict):
        return {str(k): str(v) for k, v in shortcuts.items()}
    return {}


def _extract_bool(entry: dict, key: str, default: bool) -> bool:
    value = entry.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, int):
        return bool(value)
    return default


def _extract_int(entry: dict, key: str, default: int) -> int:
    value = entry.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _find_shortcut_key(shortcuts: dict[str, str], name: str) -> Optional[str]:
    target = name.casefold()
    for key in shortcuts:
        if key.casefold() == target:
            return key
    return None


async def load_all() -> dict:
    async with _lock:
        return await asyncio.to_thread(_read_all)


async def save_all(data: dict) -> None:
    async with _lock:
        await asyncio.to_thread(_atomic_write, data)


async def get_guild_settings(guild_id: int) -> GuildSettings:
    async with _lock:
        data = await asyncio.to_thread(_read_all)
        entry = _get_entry(data, guild_id)
        locale = _normalize_locale(str(entry.get("locale", "tr")))
        shortcuts = _extract_shortcuts(entry)
        auto_disconnect_enabled = _extract_bool(
            entry, "auto_disconnect_enabled", AUTO_DISCONNECT_DEFAULT_ENABLED
        )
        auto_disconnect_minutes = _extract_int(
            entry, "auto_disconnect_minutes", AUTO_DISCONNECT_DEFAULT_MINUTES
        )
        auto_disconnect_warn_minutes = _extract_int(
            entry, "auto_disconnect_warn_minutes", AUTO_DISCONNECT_DEFAULT_WARN_MINUTES
        )
        shuffle_mode = str(entry.get("shuffle_mode", SHUFFLE_MODE_DEFAULT))
        if shuffle_mode not in ("none", "full", "smart"):
            shuffle_mode = SHUFFLE_MODE_DEFAULT
        loop_mode = str(entry.get("loop_mode", LOOP_MODE_DEFAULT))
        if loop_mode not in ("none", "queue", "single"):
            loop_mode = LOOP_MODE_DEFAULT
        return GuildSettings(
            locale=locale,
            shortcuts=shortcuts,
            auto_disconnect_enabled=auto_disconnect_enabled,
            auto_disconnect_minutes=auto_disconnect_minutes,
            auto_disconnect_warn_minutes=auto_disconnect_warn_minutes,
            shuffle_mode=shuffle_mode,
            loop_mode=loop_mode,
        )


async def set_locale(guild_id: int, locale: str) -> None:
    async with _lock:
        data = await asyncio.to_thread(_read_all)
        entry = _get_entry(data, guild_id)
        entry["locale"] = _normalize_locale(locale)
        entry["shortcuts"] = _extract_shortcuts(entry)
        data[str(guild_id)] = entry
        await asyncio.to_thread(_atomic_write, data)


async def add_shortcut(guild_id: int, name: str, url: str) -> None:
    async with _lock:
        data = await asyncio.to_thread(_read_all)
        entry = _get_entry(data, guild_id)
        shortcuts = _extract_shortcuts(entry)
        shortcuts[name] = url
        entry["locale"] = _normalize_locale(str(entry.get("locale", "tr")))
        entry["shortcuts"] = shortcuts
        data[str(guild_id)] = entry
        await asyncio.to_thread(_atomic_write, data)


async def remove_shortcut(guild_id: int, name: str) -> None:
    async with _lock:
        data = await asyncio.to_thread(_read_all)
        entry = _get_entry(data, guild_id)
        shortcuts = _extract_shortcuts(entry)
        key = _find_shortcut_key(shortcuts, name)
        if key:
            del shortcuts[key]
        entry["locale"] = _normalize_locale(str(entry.get("locale", "tr")))
        entry["shortcuts"] = shortcuts
        data[str(guild_id)] = entry
        await asyncio.to_thread(_atomic_write, data)


async def set_auto_disconnect_enabled(guild_id: int, enabled: bool) -> None:
    async with _lock:
        data = await asyncio.to_thread(_read_all)
        entry = _get_entry(data, guild_id)
        entry["auto_disconnect_enabled"] = bool(enabled)
        entry["locale"] = _normalize_locale(str(entry.get("locale", "tr")))
        entry["shortcuts"] = _extract_shortcuts(entry)
        data[str(guild_id)] = entry
        await asyncio.to_thread(_atomic_write, data)


async def set_auto_disconnect_minutes(guild_id: int, minutes: int) -> None:
    async with _lock:
        data = await asyncio.to_thread(_read_all)
        entry = _get_entry(data, guild_id)
        entry["auto_disconnect_minutes"] = int(minutes)
        entry["auto_disconnect_warn_minutes"] = _extract_int(
            entry, "auto_disconnect_warn_minutes", AUTO_DISCONNECT_DEFAULT_WARN_MINUTES
        )
        entry["auto_disconnect_enabled"] = _extract_bool(
            entry, "auto_disconnect_enabled", AUTO_DISCONNECT_DEFAULT_ENABLED
        )
        entry["locale"] = _normalize_locale(str(entry.get("locale", "tr")))
        entry["shortcuts"] = _extract_shortcuts(entry)
        data[str(guild_id)] = entry
        await asyncio.to_thread(_atomic_write, data)


async def list_shortcuts(guild_id: int) -> list[tuple[str, str]]:
    settings = await get_guild_settings(guild_id)
    items = list(settings.shortcuts.items())
    items.sort(key=lambda item: item[0].casefold())
    return items


async def get_shortcut_url(guild_id: int, name: str) -> Optional[str]:
    settings = await get_guild_settings(guild_id)
    key = _find_shortcut_key(settings.shortcuts, name)
    if key is None:
        return None
    return settings.shortcuts.get(key)


async def set_shuffle_mode(guild_id: int, mode: str) -> None:
    async with _lock:
        data = await asyncio.to_thread(_read_all)
        entry = _get_entry(data, guild_id)

        # Validate new value
        if mode not in ("none", "full", "smart"):
            mode = SHUFFLE_MODE_DEFAULT

        # Set new field
        entry["shuffle_mode"] = mode

        # CRITICAL: Preserve ALL existing fields
        entry["locale"] = _normalize_locale(str(entry.get("locale", "tr")))
        entry["shortcuts"] = _extract_shortcuts(entry)
        entry["auto_disconnect_enabled"] = _extract_bool(
            entry, "auto_disconnect_enabled", AUTO_DISCONNECT_DEFAULT_ENABLED
        )
        entry["auto_disconnect_minutes"] = _extract_int(
            entry, "auto_disconnect_minutes", AUTO_DISCONNECT_DEFAULT_MINUTES
        )
        entry["auto_disconnect_warn_minutes"] = _extract_int(
            entry, "auto_disconnect_warn_minutes", AUTO_DISCONNECT_DEFAULT_WARN_MINUTES
        )
        entry["loop_mode"] = str(entry.get("loop_mode", LOOP_MODE_DEFAULT))

        data[str(guild_id)] = entry
        await asyncio.to_thread(_atomic_write, data)


async def set_loop_mode(guild_id: int, mode: str) -> None:
    async with _lock:
        data = await asyncio.to_thread(_read_all)
        entry = _get_entry(data, guild_id)

        # Validate new value
        if mode not in ("none", "queue", "single"):
            mode = LOOP_MODE_DEFAULT

        # Set new field
        entry["loop_mode"] = mode

        # CRITICAL: Preserve ALL existing fields
        entry["locale"] = _normalize_locale(str(entry.get("locale", "tr")))
        entry["shortcuts"] = _extract_shortcuts(entry)
        entry["auto_disconnect_enabled"] = _extract_bool(
            entry, "auto_disconnect_enabled", AUTO_DISCONNECT_DEFAULT_ENABLED
        )
        entry["auto_disconnect_minutes"] = _extract_int(
            entry, "auto_disconnect_minutes", AUTO_DISCONNECT_DEFAULT_MINUTES
        )
        entry["auto_disconnect_warn_minutes"] = _extract_int(
            entry, "auto_disconnect_warn_minutes", AUTO_DISCONNECT_DEFAULT_WARN_MINUTES
        )
        entry["shuffle_mode"] = str(entry.get("shuffle_mode", SHUFFLE_MODE_DEFAULT))

        data[str(guild_id)] = entry
        await asyncio.to_thread(_atomic_write, data)
