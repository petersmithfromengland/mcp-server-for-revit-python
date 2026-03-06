# -*- coding: utf-8 -*-
"""
Configuration loader for external stems.

Reads ``config.yaml`` from the repository root and exposes the
external library paths + Revit API XML path.  If the config file
is missing, falls back to sensible defaults so the server still
starts.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import yaml  # PyYAML
except ImportError:
    yaml = None  # type: ignore[assignment]


_EXTENSION_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_EXTENSION_DIR, "config.yaml")


@dataclass
class LibraryConfig:
    """Configuration for a single external library."""

    name: str
    path: str
    enabled: bool = True


@dataclass
class ExternalStemsConfig:
    """Top-level external stems configuration."""

    libraries: List[LibraryConfig] = field(default_factory=list)
    revit_api_xml: str = ""


@dataclass
class ServerConfig:
    """Top-level server configuration (all sections)."""

    external_stems: ExternalStemsConfig = field(default_factory=ExternalStemsConfig)
    allow_implicit_code_execution: bool = False


def _parse_yaml(path: str) -> dict:
    """Read a YAML file and return the parsed dict."""
    if yaml is None:
        # Minimal fallback parser for the simple config format
        return _parse_yaml_fallback(path)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_yaml_fallback(path: str) -> dict:
    """Very simple YAML-like parser for when PyYAML is not installed.

    Only handles the flat structure used by config.yaml:
      - top-level keys
      - list items with simple key: value pairs
      - quoted string values
    """
    data: dict = {}
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    current_section = None
    current_list = None
    current_item: dict = {}

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.lstrip()

        # Skip comments and blanks
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(stripped)

        # Top-level key (indent 0)
        if indent == 0 and ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                data[key] = _unquote(val)
            else:
                data[key] = {}
            current_section = key
            current_list = None
            continue

        # Second-level key
        if indent == 2 and ":" in stripped and not stripped.startswith("-"):
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if current_section and isinstance(data.get(current_section), dict):
                if val:
                    data[current_section][key] = _unquote(val)
                else:
                    data[current_section][key] = []
                    current_list = key
            continue

        # List item start
        if stripped.startswith("- "):
            if current_item:
                _append_item(data, current_section, current_list, current_item)
            item_str = stripped[2:]
            if ":" in item_str:
                k, _, v = item_str.partition(":")
                current_item = {k.strip(): _unquote(v.strip())}
            else:
                current_item = {"value": _unquote(item_str)}
            continue

        # Continuation of a list item
        if indent >= 6 and ":" in stripped:
            k, _, v = stripped.partition(":")
            current_item[k.strip()] = _unquote(v.strip())
            continue

    # Flush last item
    if current_item:
        _append_item(data, current_section, current_list, current_item)

    return data


def _unquote(s: str) -> str:
    """Strip surrounding quotes and unescape."""
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (
        s.startswith("'") and s.endswith("'")
    ):
        s = s[1:-1]
    return s.replace("\\\\", "\\")


def _append_item(data: dict, section: str, list_key: str, item: dict) -> None:
    """Append a parsed item to the correct list in data."""
    if section and list_key and isinstance(data.get(section), dict):
        target = data[section].get(list_key)
        if isinstance(target, list):
            target.append(item)


# ── Public API ─────────────────────────────────────────────────────

_server_config: Optional[ServerConfig] = None


def _parse_bool(value) -> bool:
    """Coerce a YAML value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _load_server_config(path: str = None) -> ServerConfig:
    """Load and cache the full server configuration."""
    global _server_config
    if _server_config is not None:
        return _server_config

    config_path = path or _CONFIG_PATH
    srv = ServerConfig()

    if not os.path.exists(config_path):
        _server_config = srv
        return srv

    try:
        raw = _parse_yaml(config_path)
    except Exception:
        _server_config = srv
        return srv

    # ── allow_implicit_code_execution (top-level) ──────────────
    if "allow_implicit_code_execution" in raw:
        srv.allow_implicit_code_execution = _parse_bool(
            raw["allow_implicit_code_execution"]
        )

    # ── external_stems section ─────────────────────────────────
    cfg = srv.external_stems
    ext = raw.get("external_stems", {})
    if isinstance(ext, dict):
        # Libraries
        for lib in ext.get("libraries", []):
            if isinstance(lib, dict):
                name = lib.get("name", "")
                lib_path = lib.get("path", "")
                enabled = lib.get("enabled", True)
                if isinstance(enabled, str):
                    enabled = enabled.lower() in ("true", "1", "yes")
                if name and lib_path:
                    cfg.libraries.append(
                        LibraryConfig(name=name, path=lib_path, enabled=bool(enabled))
                    )

        # Revit API XML
        api_xml = ext.get("revit_api_xml", "")
        if api_xml:
            # Resolve relative paths against the extension directory
            if not os.path.isabs(api_xml):
                api_xml = os.path.join(_EXTENSION_DIR, api_xml)
            cfg.revit_api_xml = api_xml

    _server_config = srv
    return srv


def load_config(path: str = None) -> ExternalStemsConfig:
    """Load and cache the external stems configuration.

    Args:
        path: Optional override path to config.yaml.
              Defaults to ``config.yaml`` in the repository root.
    """
    return _load_server_config(path).external_stems


def load_server_config(path: str = None) -> ServerConfig:
    """Load and cache the full server configuration.

    Returns the top-level ``ServerConfig`` which includes
    ``allow_implicit_code_execution`` and ``external_stems``.
    """
    return _load_server_config(path)


def reload_config(path: str = None) -> ExternalStemsConfig:
    """Force-reload the configuration (clears cache)."""
    global _server_config
    _server_config = None
    return load_config(path)


def get_cache_dir() -> str:
    """Return the path to the external stems cache directory, creating it if needed."""
    cache_dir = os.path.join(_EXTENSION_DIR, "external_stems", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir
