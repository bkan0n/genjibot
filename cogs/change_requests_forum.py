from __future__ import annotations

import datetime
import logging
import re  # noqa: TC003
import traceback
import typing

import discord
import msgspec
from discord.app_commands import Transform, command, guilds
from discord.ext import commands, tasks

from utils import constants, transformers
from utils.embeds import GenjiEmbed
from utils.maps import MapEmbedData

if typing.TYPE_CHECKING:
    import asyncpg

    from core import Genji
    from database import Database

    GenjiItx: typing.TypeAlias = discord.Interaction[Genji]


log = logging.getLogger(__name__)

FORUM_ID = 1342953312000934069

async def _check_permission_for_change_request_button(
    db: Database, user_id: int, thread_id: int, map_code: str
) -> bool:
    query = """
        SELECT creator_mentions FROM change_requests
        WHERE thread_id = $1 AND map_code = $2;
    """
    val = await db.fetchval(query, thread_id, map_code)
    return str(user_id) in val

class ChangeRequest(msgspec.Struct):
    content: str
    thread_id: int
    created_at: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
    resolved: bool = False
    map_code: str | None = None
    user_id: int | None = None
    creator_mentions: str | None = None
    alerted: bool = False

    @property
    def jump_url(self) -> str:
        return f"https://discord.com/channels/{FORUM_ID}/{self.thread_id}"

    @classmethod
    def build_embed(cls, map_code: str, change_requests: list[ChangeRequest]) -> discord.Embed:
        embed = GenjiEmbed()
        embed.title = f"Open Change Requests for {map_code}"
        embed_len_limit = 5000  # Kept lower than actual limit (6000)
        for i, cr in enumerate(change_requests):
            name = f"Resolved Change Request {i + 1}" if cr.resolved else f"Unresolved Change Request {i + 1}"
            embed.add_field(
                name=name,
                value=f">>> `Request` {cr.content}\n{cr.jump_url}",
                inline=False,
            )
            if len(embed) >= embed_len_limit:
                break
        return embed

    async def insert_change_request(self, db: Database) -> None:
        query = """
            INSERT INTO change_requests (thread_id, map_code, user_id, content, creator_mentions)
            VALUES ($1, $2, $3, $4, $5);
        """
        await db.execute(query, self.thread_id, self.map_code, self.user_id, self.content, self.creator_mentions)

class ChangeRequestModCloseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def interaction_check(self, itx: GenjiItx, /) -> bool:
        assert itx.guild and isinstance(itx.user, discord.Member)
        sensei = itx.guild.get_role(842790097312153610)
        moderator = itx.guild.get_role(1128014001318666423)
        return sensei in itx.user.roles or moderator in itx.user.roles

    @discord.ui.button(
        label="Close (Sensei Only)",
        style=discord.ButtonStyle.red,
        custom_id="CR-ModClose",
        row=1,
        emoji="\N{HEAVY MULTIPLICATION X}",
    )
    async def callback(self, itx: GenjiItx, button: discord.ui.Button) -> None:
        await itx.response.send_message("Closing thread.")
        thread = itx.channel
        assert isinstance(thread, discord.Thread) and itx.guild
        forum = itx.guild.get_channel(FORUM_ID)
        assert isinstance(forum, discord.ForumChannel)
        resolved_tag = next(item for item in forum.available_tags if item.name == "Resolved")
        tags = thread.applied_tags
        if resolved_tag not in tags:
            tags.append(resolved_tag)
        await thread.edit(archived=True, locked=True, applied_tags=tags[:5])
        query = """
            UPDATE change_requests
            SET resolved = TRUE
            WHERE thread_id = $1;
        """
        await itx.client.database.execute(query, thread.id)


class ChangeRequestArchiveMapButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"FCRA-(?P<map_code>[A-Z0-9]{4,6})-(?P<thread_id>\d+)",
):
    def __init__(self, map_code: str, thread_id: str) -> None:
        custom_id = "-".join(["FCRA", map_code, thread_id])
        super().__init__(
            discord.ui.Button(
                label="Request Map Archive",
                style=discord.ButtonStyle.red,
                custom_id=custom_id,
                emoji="\N{CARD FILE BOX}",
            )
        )
        self.thread_id = thread_id
        self.map_code = map_code

    @classmethod
    async def from_custom_id(
        cls, itx: GenjiItx, item: discord.ui.Button, match: re.Match[str]
    ) -> ChangeRequestArchiveMapButton:
        return cls(match["map_code"], match["thread_id"])

    async def callback(self, itx: GenjiItx) -> None:
        await itx.response.defer(ephemeral=True, thinking=True)
        permitted = await _check_permission_for_change_request_button(
            itx.client.database,
            itx.user.id,
            int(self.thread_id),
            self.map_code,
        )
        if permitted:
            await itx.edit_original_response(content="Requesting map archive.")
            assert isinstance(itx.channel, discord.Thread)
            await itx.channel.send(
                f"<@&1120076555293569081>\n\n{itx.user.mention} is requesting map archive.",
                view=ChangeRequestModCloseView(),
            )
        else:
            await itx.edit_original_response(content="You do not have permission to use this.")


class ChangeRequestConfirmChangesButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"FCRC-(?P<map_code>[A-Z0-9]{4,6})-(?P<thread_id>\d+)",
):
    def __init__(self, map_code: str, thread_id: str) -> None:
        custom_id = "-".join(["FCRC", map_code, thread_id])
        super().__init__(
            discord.ui.Button(
                label="Confirm changes have been made",
                style=discord.ButtonStyle.green,
                custom_id=custom_id,
                emoji="\N{THUMBS UP SIGN}",
            )
        )
        self.thread_id = thread_id
        self.map_code = map_code

    @classmethod
    async def from_custom_id(
        cls, itx: GenjiItx, item: discord.ui.Button, match: re.Match[str]
    ) -> ChangeRequestConfirmChangesButton:
        return cls(match["map_code"], match["thread_id"])

    async def callback(self, itx: GenjiItx) -> None:
        await itx.response.defer(ephemeral=True, thinking=True)
        permitted = await _check_permission_for_change_request_button(
            itx.client.database,
            itx.user.id,
            int(self.thread_id),
            self.map_code,
        )
        if permitted:
            await itx.edit_original_response(content="Confirming changes have been made.")
            assert isinstance(itx.channel, discord.Thread)
            await itx.channel.send(
                f"<@&1120076555293569081>\n\n{itx.user.mention} has confirmed changes have been made.",
                view=ChangeRequestModCloseView(),
            )
        else:
            await itx.edit_original_response(content="You do not have permission to use this.")


class ChangeRequestDenyChangesButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"FCRD-(?P<map_code>[A-Z0-9]{4,6})-(?P<thread_id>\d+)",
):
    def __init__(self, map_code: str, thread_id: str) -> None:
        custom_id = "-".join(["FCRD", map_code, thread_id])
        super().__init__(
            discord.ui.Button(
                label="Deny changes as non applicable",
                style=discord.ButtonStyle.red,
                custom_id=custom_id,
                emoji="\N{HEAVY MULTIPLICATION X}",
            )
        )
        self.thread_id = thread_id
        self.map_code = map_code

    @classmethod
    async def from_custom_id(
        cls, itx: GenjiItx, item: discord.ui.Button, match: re.Match[str]
    ) -> ChangeRequestDenyChangesButton:
        return cls(match["map_code"], match["thread_id"])

    async def callback(self, itx: GenjiItx) -> None:
        await itx.response.defer(ephemeral=True, thinking=True)
        permitted = await _check_permission_for_change_request_button(
            itx.client.database,
            itx.user.id,
            int(self.thread_id),
            self.map_code,
        )
        if permitted:
            await itx.edit_original_response(content="Denying changes.")
            assert isinstance(itx.channel, discord.Thread)
            await itx.channel.send(
                f"<@&1120076555293569081>\n\n{itx.user.mention} is denying changes as non applicable.",
                view=ChangeRequestModCloseView(),
            )
        else:
            await itx.edit_original_response(content="You do not have permission to use this.")

class ChangeRequestView(discord.ui.View):
    def __init__(self, map_code: str, thread_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(ChangeRequestConfirmChangesButton(map_code, str(thread_id)))
        self.add_item(ChangeRequestDenyChangesButton(map_code, str(thread_id)))
        self.add_item(ChangeRequestArchiveMapButton(map_code, str(thread_id)))


class DuplicatedChangeRequestView(discord.ui.View):
    def __init__(
        self,
        map_code: str,
        change_requests: list[ChangeRequest],
    ) -> None:
        super().__init__()
        self.map_code = map_code
        self.change_requests = change_requests
        self.value: bool = False

    @discord.ui.button(label="Continue making change request", style=discord.ButtonStyle.green)
    async def continue_button(self, itx: GenjiItx, button: discord.ui.Button) -> None:
        self.value = True
        self.stop()
        await itx.response.send_message("Please continue with your change request.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, itx: GenjiItx, button: discord.ui.Button) -> None:
        self.stop()
        await itx.response.send_message("Change request cancelled.", ephemeral=True)
        await itx.delete_original_response()


class ChangeRequestConfirmationView(discord.ui.View):
    edit_details_modal: ChangeRequestModal

    def __init__(self, map_code: str, forum_tags_select: discord.ui.Select) -> None:
        super().__init__()
        self.map_code = map_code
        self.forum_tags_select = forum_tags_select
        self.add_item(forum_tags_select)

    @staticmethod
    async def _fetch_map_data(db: Database, map_code: str) -> asyncpg.Record:
        query = """
            SELECT
              am.map_name, map_type, am.map_code, am."desc", am.official,
              am.archived, guide, mechanics, restrictions, am.checkpoints,
              creators, difficulty, quality, creator_ids, am.gold, am.silver,
              am.bronze, p.thread_id, pa.count, pa.required_votes
              FROM
                all_maps am
                  LEFT JOIN playtest p ON am.map_code = p.map_code AND p.is_author IS TRUE
                  LEFT JOIN playtest_avgs pa ON pa.map_code = am.map_code
             WHERE
                 ($1::text IS NULL OR am.map_code = $1)
             GROUP BY
               am.map_name, map_type, am.map_code, am."desc", am.official, am.archived, guide, mechanics,
               restrictions, am.checkpoints, creators, difficulty, quality, creator_ids, am.gold, am.silver,
               am.bronze, p.thread_id, pa.count, pa.required_votes
            ORDER BY
                difficulty, quality DESC;
        """
        return await db.fetchrow(query, map_code)

    @staticmethod
    def _build_embed(map_data: asyncpg.Record) -> discord.Embed:
        embed = GenjiEmbed()
        m = MapEmbedData(map_data)
        embed.add_description_field(
            name=m.name,
            value=m.value,
        )
        return embed

    @staticmethod
    async def _get_map_creators(db: Database, map_code: str) -> list[int]:
        query = """
            SELECT array_agg(user_id)
            FROM map_creators
            WHERE map_code = $1
            GROUP BY map_code;
        """
        return await db.fetchval(query, map_code)

    @staticmethod
    def _convert_ids_to_mentions(ids: list[int], guild: discord.Guild) -> str:
        mentions = []
        fake_user_limit = 100000
        for id_ in ids:
            member = guild.get_member(id_) if id_ > fake_user_limit else None
            if member:
                mentions.append(member.mention)
        return " ".join(mentions)

    async def on_error(self, itx: GenjiItx, error: Exception, item: discord.ui.Item) -> None:
        traceback.print_exception(type(error), error, error.__traceback__)

    @discord.ui.button(label="Edit Details", style=discord.ButtonStyle.blurple, row=0)
    async def edit_details_button(self, itx: GenjiItx, button: discord.ui.Button) -> None:
        self.edit_details_modal = ChangeRequestModal(self.map_code)
        await itx.response.send_modal(self.edit_details_modal)
        await self.edit_details_modal.wait()
        if not self.edit_details_modal.submitted:
            return
        self.submit_button.disabled = False
        content = (
            f"Please provide the details of your change request.\n\n`Request`: {self.edit_details_modal.feedback.value}"
        )
        await itx.edit_original_response(content=content, embed=None, view=self)

    def _construct_forum_tags(self, guild: discord.Guild) -> list[discord.ForumTag]:
        channel = guild.get_channel(FORUM_ID)
        assert isinstance(channel, discord.ForumChannel)
        tags = [channel.get_tag(int(tag)) for tag in self.forum_tags_select.values]
        return [tag for tag in tags if tag]

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.green, row=2, disabled=True)
    async def submit_button(self, itx: GenjiItx, button: discord.ui.Button) -> None:
        await itx.response.defer(ephemeral=True)
        self.stop()
        assert itx.guild
        channel = itx.guild.get_channel(FORUM_ID)
        assert isinstance(channel, discord.ForumChannel)
        user_ids = await self._get_map_creators(itx.client.database, self.map_code)
        mentions = self._convert_ids_to_mentions(user_ids, itx.guild)
        if not mentions:
            mentions = "<@&1120076555293569081>\n-# The creator of this map is not in this server."
        content = (
            f"# {mentions}\n\n"
            f"## {itx.user.mention} is requesting changes for map **{self.map_code}**\n\n"
            f"{self.edit_details_modal.feedback.value}"
        )

        map_data = await self._fetch_map_data(itx.client.database, self.map_code)
        embed = self._build_embed(map_data)
        thread = await channel.create_thread(
            name=f"CR-{self.map_code} Discussion",
            content=content,
            embed=embed,
            applied_tags=self._construct_forum_tags(itx.guild),
        )
        change_request = ChangeRequest(
            content=self.edit_details_modal.feedback.value,
            thread_id=thread[0].id,
            map_code=self.map_code,
            user_id=itx.user.id,
            creator_mentions=mentions,
        )
        await change_request.insert_change_request(itx.client.database)
        view = ChangeRequestView(self.map_code, thread[0].id)
        await thread[1].edit(view=view)
        await itx.delete_original_response()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, row=2)
    async def cancel_button(self, itx: GenjiItx, button: discord.ui.Button) -> None:
        await itx.response.send_message("Change request cancelled.", ephemeral=True)
        self.stop()
        await itx.delete_original_response()


class ForumTagsSelect(discord.ui.Select):
    def __init__(self, forum_tags: typing.Sequence[discord.ForumTag]) -> None:
        options = [discord.SelectOption(label=tag.name, value=str(tag.id)) for tag in forum_tags]
        super().__init__(placeholder="Select a forum tag", options=options, max_values=len(forum_tags), row=1)

    async def callback(self, itx: GenjiItx) -> None:
        _value_names = [option.label for option in self.options if option.value in self.values]
        await itx.response.send_message(f"Selected {', '.join(_value_names)}", ephemeral=True)


class ChangeRequestModal(discord.ui.Modal):
    def __init__(self, map_code: str) -> None:
        super().__init__(title="Change Request", timeout=600)
        self.map_code = map_code
        self.submitted = False

    feedback = discord.ui.TextInput(
        label="What change are you requesting?",
        style=discord.TextStyle.long,
        placeholder="Type your feedback here and please be specific.",
    )

    async def on_submit(self, itx: GenjiItx) -> None:
        await itx.response.send_message("Details have been edited.", ephemeral=True)
        self.submitted = True


class ChangeRequestsCog(commands.Cog):
    def __init__(self, bot: Genji) -> None:
        self.bot = bot
        self.db = bot.database

    async def cog_load(self) -> None:
        self.alert_stale_change_requests.start()
        return await super().cog_load()

    async def cog_unload(self) -> None:
        self.alert_stale_change_requests.stop()
        return await super().cog_unload()

    async def _fetch_change_requests(self, map_code: str) -> list[ChangeRequest]:
        query = """
            SELECT *
            FROM change_requests
            WHERE map_code = $1
                AND resolved IS FALSE
            ORDER BY created_at DESC, resolved DESC;
        """
        rows = await self.db.fetch(query, map_code)
        return [ChangeRequest(**row) for row in rows]

    @command(name="change-request")
    @guilds(constants.GUILD_ID)
    async def change_request(
        self,
        itx: GenjiItx,
        map_code: Transform[str, transformers.MapCodeTransformer],
    ) -> None:
        change_requests = await self._fetch_change_requests(map_code)
        view = DuplicatedChangeRequestView(map_code, change_requests)
        if change_requests:
            await itx.response.send_message(
                "There are already open change requests for this map. What would you like to do?",
                view=view,
                embed=ChangeRequest.build_embed(map_code, change_requests),
                ephemeral=True,
            )
            await view.wait()
            if not view.value:
                return

        assert itx.guild
        forum = itx.guild.get_channel(FORUM_ID)
        assert isinstance(forum, discord.ForumChannel)
        forum_tags_select = ForumTagsSelect([tag for tag in forum.available_tags if tag.name != "Resolved"])
        view = ChangeRequestConfirmationView(map_code, forum_tags_select)
        content = "Please provide the details of your change request."
        if itx.response.is_done():
            await itx.edit_original_response(content=content, view=view, embeds=[])
        else:
            await itx.response.send_message(content=content, view=view, embeds=[], ephemeral=True)

    @tasks.loop(hours=1)
    async def alert_stale_change_requests(self) -> None:
        query = """
            SELECT thread_id, user_id
            FROM change_requests
            WHERE created_at < NOW() - INTERVAL '2 weeks'
                AND alerted IS FALSE AND resolved IS FALSE;
        """
        rows = await self.db.fetch(query)
        for row in rows:
            thread = self.bot.get_channel(row["thread_id"])
            if not thread:
                continue
            assert isinstance(thread, discord.Thread)
            user = self.bot.get_user(row["user_id"])
            mention = user.mention if user else ""
            await thread.send(
                f"{mention}<@&1120076555293569081>\n# This change request is now stale. "
                "If you have made the necessary changes, please click the button above to confirm.",
                view=ChangeRequestModCloseView(),
            )
            await self._set_alerted(row["thread_id"])

    async def _set_alerted(self, thread_id: int) -> None:
        query = """
            UPDATE change_request
            SET alerted = TRUE
            WHERE thread_id = $1;
        """
        await self.db.execute(query, thread_id)


async def setup(bot: Genji) -> None:
    """Add Cog to Discord bot."""
    await bot.add_cog(ChangeRequestsCog(bot))
    bot.add_dynamic_items(ChangeRequestConfirmChangesButton)
    bot.add_dynamic_items(ChangeRequestDenyChangesButton)
    bot.add_dynamic_items(ChangeRequestArchiveMapButton)
    bot.add_view(ChangeRequestModCloseView())
