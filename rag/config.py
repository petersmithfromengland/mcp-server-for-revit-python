# -*- coding: utf-8 -*-
"""
Configuration loader for the RAG pipeline.

Reads ``config.xml`` from the repository root and exposes the duHast
library path and RAG-specific settings.  Uses the stdlib
``xml.etree.ElementTree`` parser — no third-party dependencies required.
"""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

_EXTENSION_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_EXTENSION_DIR, "config.xml")


@dataclass
class LibraryConfig:
    """Configuration for a single external library to index."""

    name: str
    path: str
    enabled: bool = True


@dataclass
class RAGConfig:
    """RAG pipeline settings."""

    chunk_size: int = 500
    chunk_overlap: int = 50
    max_results: int = 8
    vector_store_dir: str = ""  # resolved at load time


@dataclass
class ServerConfig:
    """Top-level server configuration."""

    libraries: List[LibraryConfig] = field(default_factory=list)
    rag: RAGConfig = field(default_factory=RAGConfig)
    allow_implicit_code_execution: bool = False


def _text(element: Optional[ET.Element], default: str = "") -> str:
    """Return stripped text content of an element, or ``default`` if None."""
    if element is None or element.text is None:
        return default
    return element.text.strip()


def _bool(element: Optional[ET.Element], default: bool = False) -> bool:
    """Parse a ``<tag>true</tag>`` / ``<tag>false</tag>`` element."""
    return _text(element, str(default)).lower() == "true"


def _int(element: Optional[ET.Element], default: int = 0) -> int:
    """Parse an integer text element."""
    try:
        return int(_text(element, str(default)))
    except ValueError:
        return default


def load_config(config_path: str = _CONFIG_PATH) -> ServerConfig:
    """Load and return the server configuration from ``config.xml``."""
    logger.debug("Loading config from %s", config_path)
    try:
        tree = ET.parse(config_path)
    except FileNotFoundError:
        raise FileNotFoundError(
            "config.xml not found at: {}\n"
            "Ensure the file exists in the repository root.".format(config_path)
        )
    except ET.ParseError as exc:
        raise ValueError("Failed to parse config.xml: {}".format(exc))

    root = tree.getroot()

    # ---- allow_implicit_code_execution ----
    allow_implicit = _bool(root.find("allow_implicit_code_execution"), default=False)

    # ---- external_stems / libraries ----
    libs: List[LibraryConfig] = []
    ext_stems = root.find("external_stems")
    if ext_stems is not None:
        libraries_el = ext_stems.find("libraries")
        if libraries_el is not None:
            for lib_el in libraries_el.findall("library"):
                libs.append(
                    LibraryConfig(
                        name=_text(lib_el.find("name")),
                        path=_text(lib_el.find("path")),
                        enabled=_bool(lib_el.find("enabled"), default=True),
                    )
                )

    # ---- rag settings ----
    default_store_dir = os.path.join(_EXTENSION_DIR, "rag", "duhast")
    rag_el = root.find("rag")
    if rag_el is not None:
        store_dir_el = rag_el.find("vector_store_dir")
        rag = RAGConfig(
            chunk_size=_int(rag_el.find("chunk_size"), 500),
            chunk_overlap=_int(rag_el.find("chunk_overlap"), 50),
            max_results=_int(rag_el.find("max_results"), 8),
            vector_store_dir=_text(store_dir_el, default_store_dir),
        )
    else:
        rag = RAGConfig(vector_store_dir=default_store_dir)

    return ServerConfig(
        libraries=libs,
        rag=rag,
        allow_implicit_code_execution=allow_implicit,
    )
