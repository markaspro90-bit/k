import logging
from dataclasses import replace

import aiohttp
import discord

from utils.messages import (
    CHANNEL_TYPES, Draft, Upload, bot_member, ensure_post_permissions, find_owned_message,
    get_channel, message_lock, sendable,
)
from utils.security import PanelError, private_reply
from views.base import Form, Interaction, PanelView, Session, Text, require_channel

log = logging.getLogger(__name__)
PRIMARY = discord.ButtonStyle.primary
SUCCESS = discord.ButtonStyle.success
DANGER = discord.ButtonStyle.danger
PAGE_SIZE = 25


async def open_panel(
    interaction: Interaction, *, mode: str = "home", channel: discord.TextChannel | None = None,
) -> None:
    if channel and not sendable(channel, bot_member(interaction)):
        raise PanelError("The bot cannot send to that channel. Choose another channel.")
    session = Session(interaction, channel=channel)
    if mode == "embed":
        from views.embed_builder import EmbedBuilder
        page = EmbedBuilder(session)
    elif mode == "text":
        page = Composer(session)
    else:
        page = MainPanel(session)
    await session.show(interaction, page, initial=True)


def status_embed(interaction: Interaction) -> discord.Embed:
    client = interaction.client
    latency = client.latency
    embed = discord.Embed(title="Bot Status", colour=discord.Colour.green())
    embed.add_field(name="Gateway", value="Connected" if client.is_ready() else "Connecting")
    embed.add_field(name="Latency", value=f"{latency * 1000:.0f} ms" if latency == latency else "Pending")
    embed.add_field(name="Servers", value=str(len(client.guilds)))
    return embed


class MainPanel(PanelView):
    def __init__(self, session: Session) -> None:
        super().__init__(
            session, "Message Control Panel",
            f"**Destination**  {session.destination}\nChoose a channel, then write or manage a message.",
        )
        self.button("Select Channel", self.channels, style=PRIMARY, emoji="📍", row=0)
        self.button("Normal Message", self.compose, emoji="✏️", row=0)
        self.button("Create Embed", self.embeds_page, emoji="🧩", row=0)
        self.button("Preview Message", self.preview, row=0)
        self.button("Edit Message", self.edit, row=1)
        self.button("Delete Message", self.delete, style=DANGER, row=1)
        self.button("Bot Status", self.status, row=1)

    async def channels(self, interaction: Interaction) -> None:
        await open_channels(interaction, self.session, MainPanel)

    async def compose(self, interaction: Interaction) -> None:
        await self.session.show(interaction, Composer(self.session))

    async def embeds_page(self, interaction: Interaction) -> None:
        from views.embed_builder import EmbedBuilder
        await self.session.show(interaction, EmbedBuilder(self.session))

    async def preview(self, interaction: Interaction) -> None:
        await show_preview(interaction, self.session)

    async def edit(self, interaction: Interaction) -> None:
        await prompt_target(self, interaction, "edit")

    async def delete(self, interaction: Interaction) -> None:
        await prompt_target(self, interaction, "delete")

    async def status(self, interaction: Interaction) -> None:
        await interaction.response.send_message(embed=status_embed(interaction), ephemeral=True)


async def open_channels(interaction: Interaction, session: Session, back: type[PanelView]) -> None:
    if session.target is not None:
        raise PanelError("A published message cannot be moved to another channel from its edit screen.")
    await interaction.response.defer()
    member = bot_member(interaction)
    channels = sorted(
        (channel for channel in await interaction.guild.fetch_channels() if sendable(channel, member)),
        key=lambda channel: (channel.name.casefold(), channel.id),
    )
    await session.show(interaction, ChannelPicker(session, channels, back))


class ChannelPicker(PanelView):
    def __init__(
        self, session: Session, channels: list[discord.TextChannel], back: type[PanelView],
        index: int = 0,
    ) -> None:
        self.channels = channels
        self.back = back
        self.index = index
        pages = max(1, (len(channels) + PAGE_SIZE - 1) // PAGE_SIZE)
        description = (
            f"**Current destination**  {session.destination}\n"
            f"Channels where the bot can post: **{len(channels)}**."
        )
        if channels:
            description += (
                "\nUse the first list for sendable channels or search with Discord’s channel picker."
            )
        else:
            description += "\nGive the bot View Channel and Send Messages in a text or announcement channel."
        super().__init__(session, "Select Channel", description)
        start = index * PAGE_SIZE
        if channels:
            options = [
                discord.SelectOption(
                    label=f"#{channel.name}"[:100], value=str(channel.id),
                    description=("Announcement" if channel.is_news() else "Text")
                    + (f" · {channel.category.name}"[:83] if channel.category else ""),
                    default=session.channel is not None and session.channel.id == channel.id,
                )
                for channel in channels[start:start + PAGE_SIZE]
            ]
            filtered = discord.ui.Select(
                placeholder=f"Sendable channels · {index + 1}/{pages}", options=options, row=0,
            )

            async def select_filtered(interaction: Interaction) -> None:
                await self.choose(interaction, int(filtered.values[0]))

            self.select(filtered, select_filtered)
        native = discord.ui.ChannelSelect(
            channel_types=list(CHANNEL_TYPES), placeholder="Search channels with Discord",
            row=1,
        )

        async def select_native(interaction: Interaction) -> None:
            await self.choose(interaction, native.values[0].id)

        self.select(native, select_native)
        self.button("Previous", self.previous, row=2, disabled=index == 0)
        self.button("Next", self.next, row=2, disabled=index + 1 >= pages)
        self.button("Back", self.go_back, row=2)

    async def choose(self, interaction: Interaction, channel_id: int) -> None:
        await interaction.response.defer()
        channel = await get_channel(interaction, channel_id)
        if not sendable(channel, bot_member(interaction)):
            raise PanelError("The bot cannot send in that channel. Choose one in the sendable list.")
        self.session.channel = channel
        await self.session.show(interaction, self.back(self.session))

    async def previous(self, interaction: Interaction) -> None:
        await self.turn(interaction, self.index - 1)

    async def next(self, interaction: Interaction) -> None:
        await self.turn(interaction, self.index + 1)

    async def turn(self, interaction: Interaction, index: int) -> None:
        await self.session.show(interaction, ChannelPicker(self.session, self.channels, self.back, index))

    async def go_back(self, interaction: Interaction) -> None:
        await self.session.show(interaction, self.back(self.session))


class Composer(PanelView):
    def __init__(self, session: Session) -> None:
        draft = session.draft
        destination = f"**Destination**  {session.destination}"
        if session.target:
            destination += f" · [Original message]({session.target.jump_url})"
        super().__init__(
            session, "Edit Message" if session.target else "Compose Message",
            f"{destination}\n\n"
            f"**Draft**  {len(draft.content):,} text characters · "
            f"{len(draft.attachments)} files · {len(draft.embeds)} embeds\n"
            f"**User and role mentions**  {'On' if draft.mentions else 'Off'}",
        )
        self.button("Write Text & Attach Files", self.write, style=PRIMARY, emoji="✏️", row=0)
        self.button("Custom Embed", self.embeds_page, emoji="🧩", row=0)
        self.button("Clear Files", self.clear_files, disabled=not draft.attachments, row=0)
        self.button(
            "Disable Mentions" if draft.mentions else "Enable Mentions",
            self.toggle_mentions, row=1, disabled=session.target is not None,
        )
        self.button("Select Channel", self.channels, row=1, disabled=session.target is not None)
        self.button("Preview Message", self.preview, style=PRIMARY, row=1)
        self.button("Discard Edit" if session.target else "Main Panel", self.back, row=2)

    async def write(self, interaction: Interaction) -> None:
        draft = self.session.draft

        async def save(
            confirmed: Interaction, values: list[str], files: list[discord.Attachment],
        ) -> None:
            proposed = replace(draft, content=values[0], attachments=[*draft.attachments, *files])
            if files:
                limit = min(confirmed.filesize_limit, confirmed.guild.filesize_limit)
                proposed.check_uploads(limit)
                await confirmed.response.defer()
                uploads = [Upload(part.filename, await part.read(), part.description) for part in files]
                proposed.attachments = [*draft.attachments, *uploads]
            self.session.draft = proposed
            await self.session.show(confirmed, Composer(self.session))

        await interaction.response.send_modal(Form(
            self, "Write Message",
            [Text("Message text", 2000, draft.content, paragraph=True, placeholder="Type Markdown, emojis, or text")],
            save, upload=True,
        ))

    async def clear_files(self, interaction: Interaction) -> None:
        self.session.draft.attachments = []
        await self.session.show(interaction, Composer(self.session))

    async def toggle_mentions(self, interaction: Interaction) -> None:
        self.session.draft.mentions = not self.session.draft.mentions
        await self.session.show(interaction, Composer(self.session))

    async def channels(self, interaction: Interaction) -> None:
        await open_channels(interaction, self.session, Composer)

    async def embeds_page(self, interaction: Interaction) -> None:
        from views.embed_builder import EmbedBuilder
        await self.session.show(interaction, EmbedBuilder(self.session))

    async def preview(self, interaction: Interaction) -> None:
        await show_preview(interaction, self.session)

    async def back(self, interaction: Interaction) -> None:
        if self.session.target:
            self.session.target = None
            self.session.draft = Draft()
            self.session.embed_index = 0
        await self.session.show(interaction, MainPanel(self.session))


async def show_preview(interaction: Interaction, session: Session) -> None:
    destination = require_channel(session)
    draft = session.draft
    draft.validate()
    draft.check_uploads(min(interaction.filesize_limit, interaction.guild.filesize_limit))
    await interaction.response.defer()
    channel = await get_channel(interaction, destination.id)
    ensure_post_permissions(interaction, channel, draft, editing=session.target is not None)
    session.channel = channel
    uploads = await draft.copy_attachments()
    await session.show(interaction, Preview(session, uploads, nonce=interaction.id))


class Preview(PanelView):
    def __init__(self, session: Session, uploads: list[Upload], *, nonce: int) -> None:
        super().__init__(session)
        self.draft = session.draft
        self.uploads = uploads
        self.target = session.target
        self.channel = session.channel
        self.nonce = nonce
        self.used = False
        self.content = self.draft.content or None
        self.embeds = self.draft.embeds
        self.files = [upload.file() for upload in uploads]
        self.button(
            f"Destination · #{self.channel.name}"[:80], style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/{session.guild_id}/{self.channel.id}", row=0,
        )
        self.button(
            "🚨 User and role mentions enabled" if self.draft.mentions else "Mentions off",
            disabled=True, row=0,
        )
        self.button("Confirm Edit" if self.target else "Confirm Send", self.confirm, style=SUCCESS, row=1)
        self.button("Cancel", self.cancel, row=1)
        self.button("Select Channel", self.channels, disabled=self.target is not None, row=1)

    async def cancel(self, interaction: Interaction) -> None:
        await self.session.show(interaction, Composer(self.session))

    async def channels(self, interaction: Interaction) -> None:
        await open_channels(interaction, self.session, Composer)

    async def confirm(self, interaction: Interaction) -> None:
        if self.used:
            raise PanelError("This confirmation has already been used.")
        await interaction.response.defer()
        channel = await get_channel(interaction, self.channel.id)
        self.draft.validate()
        self.draft.check_uploads(
            interaction.guild.filesize_limit, retain_existing=self.target is not None,
        )
        ensure_post_permissions(interaction, channel, self.draft, editing=self.target is not None)
        options = dict(
            content=self.draft.content or None, embeds=self.draft.embeds,
            allowed_mentions=self.draft.allowed_mentions(),
        )
        try:
            if self.target:
                async with message_lock(self.target.id):
                    current = await find_owned_message(interaction, channel.id, str(self.target.id))
                    if current.edited_at != self.target.edited_at:
                        raise PanelError("The message changed after you opened it. Reopen it with /edit.")
                    self.used = True
                    message = await current.edit(**options, attachments=self.draft.edit_attachments())
            else:
                self.used = True
                message = await channel.send(
                    **options, files=[upload.file() for upload in self.uploads],
                    nonce=str(self.nonce),
                )
        except (discord.HTTPException, aiohttp.ClientError, TimeoutError, OSError) as error:
            if not self.used:
                raise
            if isinstance(error, discord.HTTPException) and error.status < 500:
                await self.session.show(
                    interaction, Composer(self.session),
                )
                raise
            log.warning("Uncertain Discord write outcome (%s)", type(error).__name__)
            await self.session.show(interaction, PanelView(
                self.session, "Check the destination",
                f"Discord did not confirm the request. Check {channel.mention} before trying again.",
            ))
            return
        self.session.target = None
        try:
            await self.session.show(interaction, Receipt(self.session, message, self.target is not None))
        except discord.HTTPException:
            await private_reply(interaction, f"Saved in {channel.mention}. {message.jump_url}")


class Receipt(PanelView):
    def __init__(self, session: Session, message: discord.Message, edited: bool) -> None:
        self.message = message
        super().__init__(
            session, "Message Updated" if edited else "Message Sent",
            f"{'Updated' if edited else 'Published'} in {message.channel.mention}. "
            f"[Open published message]({message.jump_url})",
        )
        self.embeds[0].colour = discord.Colour.green()
        self.button("Send Again", self.again, style=PRIMARY, row=0)
        self.button("Edit Message", self.edit, row=0)
        self.button("Delete Message", self.delete, style=DANGER, row=0)
        self.button("Main Panel", self.home, row=1)

    async def again(self, interaction: Interaction) -> None:
        self.session.channel = None
        self.session.draft.mentions = False
        await open_channels(interaction, self.session, Composer)

    async def edit(self, interaction: Interaction) -> None:
        await interaction.response.defer()
        message = await find_owned_message(interaction, self.message.channel.id, str(self.message.id))
        await load_edit(interaction, self.session, message)

    async def delete(self, interaction: Interaction) -> None:
        await interaction.response.defer()
        message = await find_owned_message(interaction, self.message.channel.id, str(self.message.id))
        await self.session.show(interaction, DeleteConfirmation(self.session, message))

    async def home(self, interaction: Interaction) -> None:
        self.session.draft = Draft()
        self.session.embed_index = 0
        await self.session.show(interaction, MainPanel(self.session))


async def load_edit(interaction: Interaction, session: Session, message: discord.Message) -> None:
    session.channel = message.channel
    session.target = message
    session.draft = Draft.from_message(message)
    session.embed_index = 0
    await session.show(interaction, Composer(session))


async def prompt_target(page: PanelView, interaction: Interaction, mode: str) -> None:
    async def find(
        confirmed: Interaction, values: list[str], files: list[discord.Attachment],
    ) -> None:
        await confirmed.response.defer()
        channel = page.session.channel
        message = await find_owned_message(confirmed, channel.id if channel else confirmed.channel_id, values[0])
        if mode == "edit":
            await load_edit(confirmed, page.session, message)
        else:
            await page.session.show(confirmed, DeleteConfirmation(page.session, message))

    await interaction.response.send_modal(Form(
        page, f"{mode.title()} a Bot Message",
        [Text("Message link or ID", 200, required=True, placeholder="Paste the message link or ID")],
        find,
    ))


class DeleteConfirmation(PanelView):
    def __init__(self, session: Session, message: discord.Message) -> None:
        self.message = message
        self.used = False
        super().__init__(
            session, "Delete Message",
            f"Permanently delete [this bot message]({message.jump_url}) "
            f"from {message.channel.mention}? This action cannot be undone.",
        )
        self.button("Confirm Delete", self.confirm, style=DANGER)
        self.button("Cancel", self.cancel)

    async def confirm(self, interaction: Interaction) -> None:
        if self.used:
            raise PanelError("This confirmation has already been used.")
        await interaction.response.defer()
        async with message_lock(self.message.id):
            message = await find_owned_message(interaction, self.message.channel.id, str(self.message.id))
            self.used = True
            try:
                await message.delete()
            except discord.HTTPException:
                await self.session.show(interaction, MainPanel(self.session))
                raise
        page = MainPanel(self.session)
        page.content = f"Message deleted from {message.channel.mention}."
        await self.session.show(interaction, page)

    async def cancel(self, interaction: Interaction) -> None:
        await self.session.show(interaction, MainPanel(self.session))
