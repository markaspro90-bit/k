import discord
from discord import app_commands
from discord.ext import commands

from views.main_panel import open_panel


class EmbedCommands(commands.Cog):
    @app_commands.command(name="embed", description="Open the private custom embed builder.")
    @app_commands.guild_only()
    @app_commands.describe(channel="Optional text or announcement channel")
    async def embed(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        await open_panel(interaction, mode="embed", channel=channel)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EmbedCommands())
