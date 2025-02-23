from __future__ import annotations

import logging
import traceback
import typing

import discord
import msgspec
from discord.app_commands import Transform, command, guilds
from discord.ext import commands

from utils import constants, transformers
from utils.embeds import GenjiEmbed
from utils.maps import MapEmbedData

if typing.TYPE_CHECKING:
    import datetime

    import asyncpg

    from core import Genji
    from database import Database

    GenjiItx: typing.TypeAlias = discord.Interaction[Genji]


log = logging.getLogger(__name__)


class ChangeRequest(msgspec.Struct):
    content: str
    created_at: datetime.datetime
    thread_id: int
    resolved: bool

    @property
    def jump_url(self) -> str:
        return f"https://discord.com/channels/1342953312000934069/{self.thread_id}"

    @classmethod
    def build_embed(cls, map_code: str, change_requests: list[ChangeRequest]) -> discord.Embed:
        embed = GenjiEmbed()
        embed.title = f"Open Change Requests for {map_code}"
        embed_len_limit = 5000  # Kept lower than actual limit (6000)
        for i, cr in enumerate(change_requests):
            name = f"Resolved Change Request {i + 1}" if cr.resolved else f"Unresolved Change Request {i + 1}"
            embed.add_field(
                name=name,
                value=f">>> `Request:` {cr.content}\n{cr.jump_url}",
                inline=False,
            )
            if len(embed) >= embed_len_limit:
                break
        return embed


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

    async def on_error(self, itx: GenjiItx, error: Exception) -> None:
        await itx.response.send_message("Oops! Something went wrong.", ephemeral=True)
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
        channel = guild.get_channel(1342953312000934069)
        assert isinstance(channel, discord.ForumChannel)
        tags = [channel.get_tag(int(tag)) for tag in self.forum_tags_select.values]
        return [tag for tag in tags if tag]

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.green, row=2, disabled=True)
    async def submit_button(self, itx: GenjiItx, button: discord.ui.Button) -> None:
        assert itx.guild
        channel = itx.guild.get_channel(1342953312000934069)
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
        # view = ChangeRequestConfirmationView(user_ids, self.map_code)
        map_data = await self._fetch_map_data(itx.client.database, self.map_code)
        embed = self._build_embed(map_data)
        await channel.create_thread(
            name=f"CR-{self.map_code} Discussion",
            content=content,
            embed=embed,
            applied_tags=self._construct_forum_tags(itx.guild),
            #    view=view,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, row=2)
    async def cancel_button(self, itx: GenjiItx, button: discord.ui.Button) -> None: ...


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

    async def _fetch_change_requests(self, map_code: str) -> list[ChangeRequest]:
        query = """
            SELECT content, created_at, thread_id, resolved
            FROM change_requests
            WHERE map_code = $1
                AND resolved IS FALSE
            ORDER BY created_at DESC, resolved DESC;
        """
        rows = await self.db.fetch(query, map_code)
        return [ChangeRequest(*row) for row in rows]

    @command(name="change-request-test")
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
            )
            await view.wait()
            if not view.value:
                return

        resp = itx.edit_original_response if itx.response.is_done() else itx.response.send_message
        assert itx.guild
        forum = itx.guild.get_channel(1342953312000934069)
        assert isinstance(forum, discord.ForumChannel)
        forum_tags_select = ForumTagsSelect([tag for tag in forum.available_tags if tag.name != "Resolved"])
        view = ChangeRequestConfirmationView(map_code, forum_tags_select)

        await resp(content="Please provide the details of your change request.", view=view, embeds=[])


async def setup(bot: Genji) -> None:
    """Add Cog to Discord bot."""
    await bot.add_cog(ChangeRequestsCog(bot))
