import re
from urllib.parse import urlsplit

import discord

from utils.security import PanelError


def url(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    try:
        parts = urlsplit(value)
        valid_host = parts.hostname and not parts.username and not parts.password
        port = parts.port
    except ValueError:
        valid_host = False
        port = None
    if (
        len(value) > 2048
        or not re.match(r"(?i)^https?://", value)
        or not valid_host
        or port == 0
        or re.search(r"[\s\x00-\x1f\x7f\\]", value)
    ):
        raise PanelError("Enter a public HTTP or HTTPS URL, or leave the field blank.")
    return value


def color(value: str) -> discord.Colour | None:
    value = value.strip()
    if not value:
        return None
    if not re.fullmatch(r"#?[A-Fa-f0-9]{6}", value):
        raise PanelError("Enter a six-digit HEX color such as #5865F2.")
    return discord.Colour(int(value.removeprefix("#"), 16))


def boolean(value: str) -> bool:
    match value.strip().lower():
        case "yes" | "y" | "true" | "on":
            return True
        case "" | "no" | "n" | "false" | "off":
            return False
        case _:
            raise PanelError("Enter yes or no.")


def validate_embeds(embeds: list[discord.Embed], *, complete: bool = False) -> None:
    if len(embeds) > 10 or sum(map(len, embeds)) > 6000:
        raise PanelError("Discord allows up to 10 embeds and 6,000 characters across all embeds.")
    for embed in embeds:
        parts = (
            (embed.title, 256, "Title"),
            (embed.description, 4096, "Description"),
            (embed.author.name, 256, "Author"),
            (embed.footer.text, 2048, "Footer"),
        )
        for value, maximum, label in parts:
            if value and len(value) > maximum:
                raise PanelError(f"{label} must be {maximum:,} characters or fewer.")
        if len(embed.fields) > 25:
            raise PanelError("Each embed can have up to 25 fields.")
        for field in embed.fields:
            if not (0 < len(field.name.strip()) and len(field.name) <= 256):
                raise PanelError("Field names must contain 1–256 characters.")
            if not (0 < len(field.value.strip()) and len(field.value) <= 1024):
                raise PanelError("Field values must contain 1–1,024 characters.")
        if complete and not (
            embed.title or embed.description or embed.author.name or embed.footer.text
            or embed.fields or embed.image.url or embed.thumbnail.url
        ):
            raise PanelError("Every embed needs visible content. Fill in or remove any empty embeds.")
        if complete and embed.url and not embed.title:
            raise PanelError("Add a title to use a title URL.")
