import discord
from discord import app_commands
from discord.ext import commands

from utils.messages import Draft, find_owned_message
from views.base import Session
from views.main_panel import Composer, DeleteConfirmation, open_panel


class MessageCommands(commands.Cog):
    @app_commands.command(name="send", description="Open the private normal message composer.")
    @app_commands.guild_only()
    @app_commands.describe(channel="Optional text or announcement channel")
    async def send(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None) -> None:
        await open_panel(interaction, mode="text", channel=channel)

    @app_commands.command(name="edit", description="Edit a message previously sent by this bot.")
    @app_commands.guild_only()
    @app_commands.describe(
        message="A Discord message link or message ID",
        channel="Channel for a message ID. Defaults to this channel.",
    )
    async def edit(
        self, interaction: discord.Interaction, message: str, channel: discord.TextChannel | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        target = await find_owned_message(interaction, channel.id if channel else interaction.channel_id, message)
        session = Session(interaction, channel=target.channel, draft=Draft.from_message(target), target=target)
        await session.show(interaction, Composer(session))

    @app_commands.command(name="delete", description="Delete a message previously sent by this bot.")
    @app_commands.guild_only()
    @app_commands.describe(
        message="A Discord message link or message ID",
        channel="Channel for a message ID. Defaults to this channel.",
    )
    async def delete(
        self, interaction: discord.Interaction, message: str, channel: discord.TextChannel | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        target = await find_owned_message(interaction, channel.id if channel else interaction.channel_id, message)
        session = Session(interaction, channel=target.channel)
        await session.show(interaction, DeleteConfirmation(session, target))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MessageCommands())
