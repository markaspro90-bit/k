from collections.abc import Callable
from copy import deepcopy

import discord

from utils.security import PanelError
from utils.validators import boolean, color, url, validate_embeds
from views.base import Form, Interaction, PanelView, Session, Text
from views.main_panel import Composer, DANGER, PRIMARY, open_channels, show_preview

Edit = Callable[[discord.Embed, list[str]], None]


class EmbedBuilder(PanelView):
    def __init__(self, session: Session) -> None:
        draft = session.draft
        self.index = session.embed_index
        self.embed = draft.embeds[self.index] if draft.embeds else discord.Embed()
        footer = f"**Destination**  {session.destination}"
        if session.target:
            footer += f" · [Original message]({session.target.jump_url})"
        timestamp = "On" if self.embed.timestamp else "Off"
        super().__init__(
            session, "Custom Embed",
            f"{footer}\n\n**Embeds**  {len(draft.embeds)}/10 · "
            f"**Text**  {sum(map(len, draft.embeds)):,}/6,000 characters\n"
            f"**Fields in this embed**  {len(self.embed.fields)}/25 · **Timestamp**  {timestamp}",
        )
        if draft.embeds:
            options = [
                discord.SelectOption(
                    label=f"{index + 1}. {embed.title or 'Untitled embed'}"[:100],
                    value=str(index), default=index == self.index,
                )
                for index, embed in enumerate(draft.embeds)
            ]
            picker = discord.ui.Select(placeholder="Choose an embed to edit", options=options, row=0)

            async def pick(interaction: Interaction) -> None:
                session.embed_index = int(picker.values[0])
                await session.show(interaction, EmbedBuilder(session))

            self.select(picker, pick)
        self.button("Edit Title", self.title, row=1)
        self.button("Edit Description", self.description, row=1)
        self.button("Change Color", self.color, row=1)
        self.button("Edit Author", self.author, row=1)
        self.button("Edit Footer", self.footer, row=1)
        self.button("Set Image", self.image, row=2)
        self.button("Set Thumbnail", self.thumbnail, row=2)
        self.button("Add Field", self.add_field, row=2, disabled=len(self.embed.fields) >= 25)
        self.button("Manage Fields", self.manage_fields, row=2, disabled=not self.embed.fields)
        self.button("Toggle Timestamp", self.timestamp, row=2)
        self.button("Add Embed", self.add_embed, row=3, disabled=len(draft.embeds) >= 10)
        self.button("Remove Embed", self.remove_embed, row=3, style=DANGER, disabled=not draft.embeds)
        self.button("Select Channel", self.channels, row=3, disabled=session.target is not None)
        self.button("Preview Message", self.preview, row=3, style=PRIMARY)
        self.button("Back to Draft", self.back, row=4)

    def with_embed(self, embed: discord.Embed) -> None:
        proposed = self.session.draft.embeds.copy()
        if proposed:
            proposed[self.index] = embed
        else:
            proposed.append(embed)
        validate_embeds(proposed)
        self.session.draft.embeds = proposed

    async def form(self, interaction: Interaction, title: str, fields: list[Text], edit: Edit) -> None:
        async def save(
            confirmed: Interaction, values: list[str], files: list[discord.Attachment],
        ) -> None:
            embed = deepcopy(self.embed)
            edit(embed, values)
            self.with_embed(embed)
            await self.session.show(confirmed, EmbedBuilder(self.session))

        await interaction.response.send_modal(Form(self, title, fields, save))

    async def title(self, interaction: Interaction) -> None:
        def edit(embed: discord.Embed, values: list[str]) -> None:
            embed.title = values[0].strip() or None
            embed.url = url(values[1])

        await self.form(interaction, "Edit Title", [
            Text("Title", 256, self.embed.title or ""),
            Text("Title URL", 2048, self.embed.url or ""),
        ], edit)

    async def description(self, interaction: Interaction) -> None:
        def edit(embed: discord.Embed, values: list[str]) -> None:
            embed.description = values[0].strip() or None

        await self.form(interaction, "Edit Description", [
            Text("Description", 4096, self.embed.description or "", paragraph=True),
        ], edit)

    async def color(self, interaction: Interaction) -> None:
        def edit(embed: discord.Embed, values: list[str]) -> None:
            embed.colour = color(values[0])

        current = self.embed.colour
        await self.form(interaction, "Change Color", [
            Text("HEX color", 7, str(current) if current is not None else "", placeholder="#5865F2"),
        ], edit)

    async def author(self, interaction: Interaction) -> None:
        def edit(embed: discord.Embed, values: list[str]) -> None:
            name = values[0].strip()
            icon = url(values[1])
            link = url(values[2])
            if name:
                embed.set_author(name=name, icon_url=icon, url=link)
            elif icon or link:
                raise PanelError("Add an author name to use an author icon or URL.")
            else:
                embed.remove_author()

        author = self.embed.author
        await self.form(interaction, "Edit Author", [
            Text("Author name", 256, author.name or ""),
            Text("Author icon URL", 2048, author.icon_url or ""),
            Text("Author URL", 2048, author.url or ""),
        ], edit)

    async def footer(self, interaction: Interaction) -> None:
        def edit(embed: discord.Embed, values: list[str]) -> None:
            text = values[0].strip()
            icon = url(values[1])
            if text:
                embed.set_footer(text=text, icon_url=icon)
            elif icon:
                raise PanelError("Add footer text to use a footer icon.")
            else:
                embed.remove_footer()

        footer = self.embed.footer
        await self.form(interaction, "Edit Footer", [
            Text("Footer text", 2048, footer.text or "", paragraph=True),
            Text("Footer icon URL", 2048, footer.icon_url or ""),
        ], edit)

    async def image(self, interaction: Interaction) -> None:
        def edit(embed: discord.Embed, values: list[str]) -> None:
            embed.set_image(url=url(values[0]))

        await self.form(interaction, "Set Image", [
            Text("Image URL", 2048, self.embed.image.url or "", placeholder="https://example.com/image.png"),
        ], edit)

    async def thumbnail(self, interaction: Interaction) -> None:
        def edit(embed: discord.Embed, values: list[str]) -> None:
            embed.set_thumbnail(url=url(values[0]))

        await self.form(interaction, "Set Thumbnail", [
            Text("Thumbnail URL", 2048, self.embed.thumbnail.url or ""),
        ], edit)

    async def timestamp(self, interaction: Interaction) -> None:
        embed = deepcopy(self.embed)
        embed.timestamp = None if embed.timestamp else discord.utils.utcnow()
        self.with_embed(embed)
        await self.session.show(interaction, EmbedBuilder(self.session))

    async def add_field(self, interaction: Interaction) -> None:
        def edit(embed: discord.Embed, values: list[str]) -> None:
            embed.add_field(name=values[0].strip(), value=values[1].strip(), inline=boolean(values[2]))

        await self.form(interaction, "Add Field", field_inputs(), edit)

    async def manage_fields(self, interaction: Interaction) -> None:
        await self.session.show(interaction, FieldManager(self.session))

    async def add_embed(self, interaction: Interaction) -> None:
        embeds = [*self.session.draft.embeds, discord.Embed()]
        validate_embeds(embeds)
        self.session.draft.embeds = embeds
        self.session.embed_index = len(embeds) - 1
        await self.session.show(interaction, EmbedBuilder(self.session))

    async def remove_embed(self, interaction: Interaction) -> None:
        self.session.draft.embeds.pop(self.index)
        self.session.embed_index = max(0, min(self.index, len(self.session.draft.embeds) - 1))
        await self.session.show(interaction, EmbedBuilder(self.session))

    async def channels(self, interaction: Interaction) -> None:
        await open_channels(interaction, self.session, EmbedBuilder)

    async def preview(self, interaction: Interaction) -> None:
        await show_preview(interaction, self.session)

    async def back(self, interaction: Interaction) -> None:
        await self.session.show(interaction, Composer(self.session))


def field_inputs(name: str = "", value: str = "", inline: bool = False) -> list[Text]:
    return [
        Text("Field name", 256, name, required=True),
        Text("Field value", 1024, value, required=True, paragraph=True),
        Text("Show inline? Enter yes or no", 5, "yes" if inline else "no"),
    ]


class FieldManager(PanelView):
    def __init__(self, session: Session, index: int = 0) -> None:
        self.index = index
        self.embed = session.draft.embeds[session.embed_index]
        item = self.embed.fields[index]
        super().__init__(
            session, "Manage Embed Fields",
            f"**Field {index + 1} of {len(self.embed.fields)}** · {'Inline' if item.inline else 'Full width'}",
        )
        self.embeds[0].add_field(name=item.name, value=item.value, inline=False)
        picker = discord.ui.Select(
            placeholder="Choose a field",
            options=[
                discord.SelectOption(label=f"{position + 1}. {field.name}"[:100], value=str(position),
                                     default=position == index)
                for position, field in enumerate(self.embed.fields)
            ],
        )

        async def pick(interaction: Interaction) -> None:
            await session.show(interaction, FieldManager(session, int(picker.values[0])))

        self.select(picker, pick)
        self.button("Edit Field", self.edit, style=PRIMARY, row=1)
        self.button("Remove Field", self.remove, style=DANGER, row=1)
        self.button("Back to Embed", self.back, row=1)

    def replace(self, embed: discord.Embed) -> None:
        proposed = self.session.draft.embeds.copy()
        proposed[self.session.embed_index] = embed
        validate_embeds(proposed)
        self.session.draft.embeds = proposed

    async def edit(self, interaction: Interaction) -> None:
        field = self.embed.fields[self.index]

        async def save(
            confirmed: Interaction, values: list[str], files: list[discord.Attachment],
        ) -> None:
            embed = deepcopy(self.embed)
            embed.set_field_at(
                self.index, name=values[0].strip(), value=values[1].strip(), inline=boolean(values[2]),
            )
            self.replace(embed)
            await self.session.show(confirmed, FieldManager(self.session, self.index))

        await interaction.response.send_modal(Form(
            self, "Edit Field", field_inputs(field.name, field.value, field.inline), save,
        ))

    async def remove(self, interaction: Interaction) -> None:
        embed = deepcopy(self.embed)
        embed.remove_field(self.index)
        self.replace(embed)
        if embed.fields:
            page = FieldManager(self.session, min(self.index, len(embed.fields) - 1))
        else:
            page = EmbedBuilder(self.session)
        await self.session.show(interaction, page)

    async def back(self, interaction: Interaction) -> None:
        await self.session.show(interaction, EmbedBuilder(self.session))
