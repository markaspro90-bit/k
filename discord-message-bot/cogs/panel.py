import discord
from discord import app_commands
from discord.ext import commands

from views.main_panel import open_panel, status_embed


class PanelCommands(commands.Cog):
    @app_commands.command(name="panel", description="Open the private message control panel.")
    @app_commands.guild_only()
    async def panel(self, interaction: discord.Interaction) -> None:
        await open_panel(interaction)

    @app_commands.command(name="status", description="Check the bot's connection and latency.")
    @app_commands.guild_only()
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=status_embed(interaction), ephemeral=True)

    @app_commands.command(name="help", description="Show the private bot command reference.")
    @app_commands.guild_only()
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Message Bot Help", colour=discord.Colour.blurple(),
            description=(
                "**/panel** · Select a channel, compose, preview, and confirm.\n"
                "**/send** · Open the text and file composer.\n"
                "**/embed** · Open the custom embed builder.\n"
                "**/edit** · Edit a bot message by link or ID.\n"
                "**/delete** · Delete a bot message by link or ID.\n"
                "**/status** · Check connection and latency.\n"
                "**/help** · Show this reference."
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PanelCommands())
