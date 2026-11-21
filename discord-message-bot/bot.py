import logging

import discord
from discord.ext import commands

from config import Config
from utils.security import OwnerCommandTree

log = logging.getLogger("message_bot")


class MessageBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            help_command=None,
            intents=discord.Intents(guilds=True),
            allowed_mentions=discord.AllowedMentions.none(),
            owner_id=config.owner_id,
            tree_cls=OwnerCommandTree,
        )
        id_ = config.guild_id
        self.command_guild = discord.Object(id_) if id_ else None

    async def setup_hook(self) -> None:
        for extension in ("cogs.panel", "cogs.messages", "cogs.embeds"):
            await self.load_extension(extension)
        if self.command_guild:
            self.tree.copy_global_to(guild=self.command_guild)
        commands_ = await self.tree.sync(guild=self.command_guild)
        scope = f"guild {self.command_guild.id}" if self.command_guild else "global"
        log.info("Synced %s slash commands (%s)", len(commands_), scope)

    async def on_ready(self) -> None:
        log.info("Connected as bot ID %s in %s server(s)", self.user.id, len(self.guilds))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Network exception text can include Discord webhook URLs. Log safe codes instead.
    logging.getLogger("discord").setLevel(logging.CRITICAL)
    logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
    try:
        config = Config.load()
    except ValueError as error:
        log.error("%s", error)
        raise SystemExit(1) from None
    try:
        MessageBot(config).run(config.token, log_handler=None)
    except discord.LoginFailure:
        log.error("Discord rejected DISCORD_TOKEN. Use the token from the application's Bot page.")
        raise SystemExit(1) from None
    except discord.HTTPException as error:
        log.error("Discord startup failed (HTTP %s, code %s).", error.status, error.code)
        raise SystemExit(1) from None
    except Exception as error:
        log.error("Startup failed (%s).", type(error).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
