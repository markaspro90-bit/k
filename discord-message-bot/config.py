import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def snowflake(value: str) -> int:
    if not re.fullmatch(r"[0-9]{17,20}", value) or not 0 < int(value) < 2**64:
        raise ValueError("Enter a valid Discord ID.")
    return int(value)


@dataclass(frozen=True)
class Config:
    token: str = field(repr=False)
    owner_id: int
    guild_id: int | None

    @classmethod
    def load(cls) -> "Config":
        load_dotenv(Path(__file__).with_name(".env"))
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise ValueError("Set DISCORD_TOKEN in .env or in your hosting variables.")
        ids = {}
        for name in ("OWNER_ID", "GUILD_ID"):
            value = os.getenv(name, "").strip()
            if name == "GUILD_ID" and not value:
                ids[name] = None
                continue
            try:
                ids[name] = snowflake(value)
            except ValueError:
                raise ValueError(f"Set {name} to a valid Discord ID.") from None
        return cls(token, ids["OWNER_ID"], ids["GUILD_ID"])
