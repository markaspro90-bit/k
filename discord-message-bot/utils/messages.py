import asyncio
import re
from dataclasses import dataclass, field
from io import BytesIO
from weakref import WeakValueDictionary

import discord

from config import snowflake
from utils.security import PanelError
from utils.validators import validate_embeds

CHANNEL_TYPES = (discord.ChannelType.text, discord.ChannelType.news)
ATTACHMENT_LIMIT = 10
REQUEST_FILE_LIMIT = 24 * 1024 * 1024
_message_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()


def message_lock(message_id: int) -> asyncio.Lock:
    lock = _message_locks.get(message_id)
    if lock is None:
        lock = _message_locks[message_id] = asyncio.Lock()
    return lock


@dataclass(frozen=True)
class Upload:
    filename: str
    data: bytes
    description: str | None = None

    def file(self) -> discord.File:
        return discord.File(BytesIO(self.data), filename=self.filename, description=self.description)


@dataclass
class Draft:
    content: str = ""
    embeds: list[discord.Embed] = field(default_factory=list)
    attachments: list[discord.Attachment | Upload] = field(default_factory=list)
    mentions: bool = False

    @classmethod
    def from_message(cls, message: discord.Message) -> "Draft":
        return cls(
            content=message.content,
            embeds=[embed for embed in message.embeds if embed.type == "rich"],
            attachments=list(message.attachments),
        )

    def validate(self) -> None:
        if not (self.content.strip() or self.embeds or self.attachments):
            raise PanelError("Add some text, an attachment, or an embed first.")
        if len(self.content) > 2000:
            raise PanelError("A message can have up to 2,000 characters.")
        validate_embeds(self.embeds, complete=True)

    def allowed_mentions(self) -> discord.AllowedMentions:
        return discord.AllowedMentions(
            everyone=False, users=self.mentions, roles=self.mentions, replied_user=False
        )

    def check_uploads(self, limit: int, *, retain_existing: bool = False) -> None:
        if len(self.attachments) > ATTACHMENT_LIMIT:
            raise PanelError("A message can contain up to 10 attachments.")
        sizes = [
            len(part.data) if isinstance(part, Upload) else part.size
            for part in self.attachments
            if not retain_existing or isinstance(part, Upload)
        ]
        if any(size > limit for size in sizes):
            raise PanelError("An attachment is larger than this server’s or interaction’s upload limit.")
        if sum(sizes) > REQUEST_FILE_LIMIT:
            raise PanelError("The combined files in a single upload can use up to 24 MiB.")

    async def copy_attachments(self) -> list[Upload]:
        return [
            part if isinstance(part, Upload)
            else Upload(part.filename, await part.read(), part.description)
            for part in self.attachments
        ]

    def edit_attachments(self) -> list[discord.Attachment | discord.File]:
        return [part.file() if isinstance(part, Upload) else part for part in self.attachments]


def sendable(channel: discord.abc.GuildChannel, member: discord.Member) -> bool:
    if not isinstance(channel, discord.TextChannel) or channel.type not in CHANNEL_TYPES:
        return False
    perms = channel.permissions_for(member)
    return perms.view_channel and perms.send_messages


def bot_member(interaction: discord.Interaction) -> discord.Member:
    member = interaction.guild.me
    if member is None:
        raise PanelError("The bot’s server permissions are unavailable. Try again shortly.")
    return member


async def get_channel(interaction: discord.Interaction, channel_id: int) -> discord.TextChannel:
    channel = await interaction.guild.fetch_channel(channel_id)
    if not isinstance(channel, discord.TextChannel) or channel.type not in CHANNEL_TYPES:
        raise PanelError("Choose a text or announcement channel in this server.")
    return channel


def ensure_post_permissions(
    interaction: discord.Interaction, channel: discord.TextChannel, draft: Draft, *, editing: bool
) -> None:
    perms = channel.permissions_for(bot_member(interaction))
    if not perms.view_channel or (not editing and not perms.send_messages):
        raise PanelError("The bot needs View Channel and Send Messages in this channel.")
    if draft.embeds and not perms.embed_links:
        raise PanelError("The bot needs Embed Links in this channel.")
    uploading = any(isinstance(part, Upload) or not editing for part in draft.attachments)
    if uploading and not perms.attach_files:
        raise PanelError("The bot needs Attach Files in this channel.")


async def find_owned_message(
    interaction: discord.Interaction, channel_id: int, reference: str
) -> discord.Message:
    reference = reference.strip()
    link = re.fullmatch(
        r"https://(?:(?:canary|ptb|www)\.)?discord(?:app)?\.com/channels/"
        r"([0-9]{17,20})/([0-9]{17,20})/([0-9]{17,20})/?(?:\?[^\s]*)?",
        reference,
        re.IGNORECASE,
    )
    try:
        if link:
            guild_id, channel_id, message_id = map(snowflake, link.groups())
            if guild_id != interaction.guild_id:
                raise PanelError("Use a message from this server.")
        else:
            message_id = snowflake(reference)
    except ValueError:
        raise PanelError("Enter a Discord message ID or a Discord message link.") from None
    channel = await get_channel(interaction, channel_id)
    perms = channel.permissions_for(bot_member(interaction))
    if not perms.view_channel or not perms.read_message_history:
        raise PanelError("The bot needs View Channel and Read Message History for this channel.")
    message = await channel.fetch_message(message_id)
    if message.author.id != interaction.client.user.id or message.webhook_id is not None:
        raise PanelError("You can only edit or delete messages sent by this bot.")
    return message
