"""Site registry: resolve a target URL to the right adapter."""

from typing import Tuple

from .base import (
    ChapterEntry,
    OPEN_CHALLENGE,
    OPEN_ERROR,
    OPEN_NO_CONTENT,
    OPEN_OK,
    SiteAdapter,
    StoryRef,
)
from .sangtacviet import SangTacVietAdapter
from .twkan import TwkanAdapter

ADAPTERS = (SangTacVietAdapter, TwkanAdapter)


def resolve_site(url: str) -> Tuple[SiteAdapter, StoryRef]:
    """Return (adapter, parsed StoryRef) for ``url``.

    Raises ValueError when no adapter recognises the URL.
    """
    for adapter_cls in ADAPTERS:
        if adapter_cls.matches(url):
            adapter = adapter_cls()
            return adapter, adapter.parse(url)

    supported = ", ".join(
        f"{cls.display_name} ({cls.name})" for cls in ADAPTERS
    )
    raise ValueError(
        f"Không hỗ trợ URL này: {url}\nCác nguồn hiện hỗ trợ: {supported}"
    )


__all__ = [
    "ADAPTERS",
    "ChapterEntry",
    "OPEN_CHALLENGE",
    "OPEN_ERROR",
    "OPEN_NO_CONTENT",
    "OPEN_OK",
    "SiteAdapter",
    "StoryRef",
    "SangTacVietAdapter",
    "TwkanAdapter",
    "resolve_site",
]
