import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

from utils.messages import Draft
from utils.security import PanelError, private_reply, require_owner, show_error

Interaction = discord.Interaction
Action = Callable[[Interaction], Awaitable[None]]
BLUE = discord.Colour.blurple()
TIMEOUT = 600


class Session:
    def __init__(
        self, interaction: Interaction, *, channel: discord.TextChannel | None = None,
        draft: Draft | None = None, target: discord.Message | None = None,
    ) -> None:
        self.owner_id = interaction.user.id
        self.guild_id = interaction.guild_id
        self.channel = channel
        self.draft = draft if draft is not None else Draft()
        self.target = target
        self.embed_index = 0
        self.current: PanelView | None = None
        self.lock = asyncio.Lock()

    async def show(
        self, interaction: Interaction, page: "PanelView", *, initial: bool = False,
    ) -> None:
        options = dict(
            content=page.content, embeds=page.embeds, view=page,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        try:
            if initial:
                await interaction.response.send_message(**options, ephemeral=True)
            elif interaction.response.is_done():
                await interaction.edit_original_response(**options, attachments=page.files)
            else:
                await interaction.response.edit_message(**options, attachments=page.files)
        finally:
            for file in page.files:
                file.close()
            page.files.clear()
        if self.current is not None:
            self.current.stop()
        self.current = page
        page.last_interaction = interaction

    @property
    def destination(self) -> str:
        return self.channel.mention if self.channel else "Choose a channel"


class PanelView(discord.ui.View):
    def __init__(self, session: Session, title: str = "", description: str = "") -> None:
        super().__init__(timeout=TIMEOUT)
        self.session = session
        self.content: str | None = None
        self.embeds = [discord.Embed(title=title, description=description, colour=BLUE)] if title else []
        self.files: list[discord.File] = []
        self.last_interaction: Interaction | None = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        if not await require_owner(interaction):
            return False
        if interaction.user.id != self.session.owner_id or interaction.guild_id != self.session.guild_id:
            await private_reply(interaction, "Access Denied")
            return False
        return True

    async def run(self, interaction: Interaction, action: Action) -> None:
        if self.session.lock.locked():
            await private_reply(interaction, "An action is already in progress.")
            return
        async with self.session.lock:
            if self.session.current is not self or self.is_finished():
                await private_reply(interaction, "These controls have expired. Open /panel to start again.")
                return
            try:
                await action(interaction)
            except Exception as error:
                await show_error(interaction, error)

    def button(
        self, label: str, action: Action | None = None, *,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        row: int | None = None, disabled: bool = False, emoji: str | None = None,
        url: str | None = None,
    ) -> None:
        item = discord.ui.Button(
            label=label, style=style, row=row, disabled=disabled, emoji=emoji, url=url,
        )
        if action:
            async def callback(interaction: Interaction) -> None:
                await self.run(interaction, action)
            item.callback = callback
        self.add_item(item)

    def select(self, item: discord.ui.Select | discord.ui.ChannelSelect, action: Action) -> None:
        async def callback(interaction: Interaction) -> None:
            await self.run(interaction, action)
        item.callback = callback
        self.add_item(item)

    async def on_error(self, interaction: Interaction, error: Exception, item: discord.ui.Item) -> None:
        await show_error(interaction, error)

    async def on_timeout(self) -> None:
        interaction = self.last_interaction
        if self.session.current is not self or not interaction or interaction.is_expired():
            return
        if self.session.lock.locked():
            return
        async with self.session.lock:
            try:
                await interaction.edit_original_response(
                    content="This panel expired. Use /panel to open a new one.",
                    embeds=[], attachments=[], view=None,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                pass


@dataclass(frozen=True)
class Text:
    label: str
    limit: int
    value: str = ""
    required: bool = False
    paragraph: bool = False
    placeholder: str | None = None


FormAction = Callable[[Interaction, list[str], list[discord.Attachment]], Awaitable[None]]


class Form(discord.ui.Modal):
    def __init__(
        self, page: PanelView, title: str, fields: list[Text], action: FormAction,
        *, upload: bool = False,
    ) -> None:
        super().__init__(title=title, timeout=TIMEOUT)
        self.page = page
        self.action = action
        self.inputs = []
        for field in fields:
            item = discord.ui.TextInput(
                max_length=field.limit, default=field.value or None, required=field.required,
                style=discord.TextStyle.paragraph if field.paragraph else discord.TextStyle.short,
                placeholder=field.placeholder,
            )
            self.inputs.append(item)
            self.add_item(discord.ui.Label(text=field.label, component=item))
        self.upload = discord.ui.FileUpload(max_values=10, required=False) if upload else None
        if self.upload:
            self.add_item(discord.ui.Label(
                text="Images or other files", component=self.upload,
                description="New uploads are added to the draft. Leave blank to keep existing files.",
            ))

    async def interaction_check(self, interaction: Interaction) -> bool:
        return await self.page.interaction_check(interaction)

    async def on_submit(self, interaction: Interaction) -> None:
        async def submit(confirmed: Interaction) -> None:
            values = [item.value for item in self.inputs]
            files = list(self.upload.values) if self.upload else []
            await self.action(confirmed, values, files)
        await self.page.run(interaction, submit)

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        await show_error(interaction, error)


def require_channel(session: Session) -> discord.TextChannel:
    if session.channel is None:
        raise PanelError("Select a destination channel first.")
    return session.channel
