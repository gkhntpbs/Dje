import discord

from .i18n import t

EMBED_COLOR = None


def make_embed(title_key: str, desc_key: str | None = None, locale: str = "tr", **fmt: object) -> discord.Embed:
    title = t(title_key, locale, **fmt)
    description = t(desc_key, locale, **fmt) if desc_key else None
    if EMBED_COLOR is None:
        return discord.Embed(title=title, description=description)
    return discord.Embed(title=title, description=description, color=EMBED_COLOR)
