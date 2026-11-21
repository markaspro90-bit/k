import logging

import discord
from discord import app_commands

log = logging.getLogger(__name__)


class PanelError(Exception):
    """An error whose message can be shown to the owner."""


async def private_reply(interaction: discord.Interaction, text: str) -> None:
    kwargs = dict(ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    if interaction.response.is_done():
        await interaction.followup.send(text, **kwargs)
    else:
        await interaction.response.send_message(text, **kwargs)


async def require_owner(interaction: discord.Interaction) -> bool:
    if interaction.user.id != interaction.client.owner_id:
        await private_reply(interaction, "Access Denied")
        return False
    if interaction.guild is None:
        await private_reply(interaction, "Open the panel from a server channel.")
        return False
    return True


async def show_error(interaction: discord.Interaction, error: Exception) -> None:
    if isinstance(error, app_commands.CommandInvokeError):
        error = error.original
    if isinstance(error, PanelError):
        message = str(error)
    elif isinstance(error, discord.Forbidden):
        message = "Discord denied access. Check the bot’s permissions in the selected channel."
    elif isinstance(error, discord.NotFound):
        if error.code in (10062, 10015):
            log.info("Discord interaction expired (code %s)", error.code)
            return
        message = "Discord could not find that channel or message. It may have been removed."
    elif isinstance(error, discord.HTTPException):
        log.warning("Discord request failed (HTTP %s, code %s)", error.status, error.code)
        message = f"Discord rejected the request (code {error.code or error.status})."
    else:
        log.error("Interaction failed (%s)", type(error).__name__)
        message = "The operation failed. Reopen /panel if the controls are out of date."
    try:
        await private_reply(interaction, message)
    except discord.HTTPException as reply_error:
        log.info("Could not deliver private response (Discord code %s)", reply_error.code)
    except Exception as reply_error:
        log.info("Could not deliver private response (%s)", type(reply_error).__name__)


class OwnerCommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await require_owner(interaction)

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        await show_error(interaction, error)
