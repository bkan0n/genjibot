from __future__ import annotations

import os
import re  # noqa: TC003
from typing import TYPE_CHECKING, Any, NamedTuple

import discord
import msgspec
from discord import Interaction

from playtest.playtest_graph import VoteHistogram
from utils import constants, maps, ranks

if TYPE_CHECKING:
    import core
    from utils.maps import MapModel


PLAYTEST_FORUM_ID = 1369672124352040970
GENJI_GUILD_ID = 842778964673953812
GENJI_API_KEY: str = os.getenv("GENJI_API_KEY", "")


class PlaytestMetadata(msgspec.Struct):
    thread_id: int
    map_id: int
    initial_difficulty: str

class PlaytestManager:
    def __init__(self, bot: core.Genji) -> None:
        self._db = bot.database
        self._bot = bot

    def get_difficulty_forum_tag(self, difficulty: str) -> discord.ForumTag:
        tags = self._bot.get_guild(GENJI_GUILD_ID).get_channel(PLAYTEST_FORUM_ID).available_tags
        for tag in tags:
            if tag.name == difficulty:
                return tag
        return None

    async def add_playtest(self, data: MapModel) -> None:
        """Add playtest forum."""
        try:
            forum = self._bot.get_guild(GENJI_GUILD_ID).get_channel(PLAYTEST_FORUM_ID)
            assert isinstance(forum, discord.ForumChannel)
        except AttributeError as e:
            e.add_note(f"Adding playtest failed, guild not found ({GENJI_GUILD_ID}): {data=}")
            raise

        difficulty_value = ranks.ALL_DIFFICULTY_RANGES_MIDPOINT[data.difficulty]
        hist = VoteHistogram([difficulty_value])
        png_buffer = await hist.export_png_bytes_async()
        file = discord.File(fp=png_buffer, filename="vote_hist.png")

        tag = self.get_difficulty_forum_tag(data.difficulty.replace(" +", "").replace(" -", ""))

        thread, message = await forum.create_thread(
            name=f"{data.code} | {data.difficulty} {data.name} by {data.creator_names[0]}"[:100],
            reason="Playtest test created",
            file=file,
            applied_tags=[tag]
        )
        view = PlaytestComponentsV2View(data)
        await message.edit(view=view)
        total_children = sum(1 for _ in view.walk_children())
        await thread.send(f"{total_children}")

        playtest_data = PlaytestMetadata(
            thread_id=thread.id,
            map_id=data.map_id,
            initial_difficulty=data.difficulty,
        )
        #await self._insert_playtest_data(playtest_data)

    async def _insert_playtest_data(self, playtest_metadata: PlaytestMetadata) -> None:
        """Insert playtest data into the database."""
        await self._bot.session.post(
            "https://apitest.genji.pk/v2/maps/playtests/metadata",
            json=msgspec.json.encode(playtest_metadata),
            headers={
                "X-API-KEY": GENJI_API_KEY,
                "Content-Type": "application/json",
            },

        )


class DifficultyRatingSelect(discord.ui.Select["PlaytestComponentsV2View"]):
    """Select difficulty rating."""

    def __init__(self) -> None:
        options = [
            discord.SelectOption(value=x, label=x) for x in ranks.DIFFICULTIES_EXT
        ]
        super().__init__(options=options, placeholder="What difficulty would you rate this map?")

    async def callback(self, interaction: Interaction) -> Any:
        ...


class SelectOptionsTuple(NamedTuple):
    label: str
    description: str


mod_only_options_data = [
    SelectOptionsTuple("Force Accept", "Force submission through, overwriting difficulty votes."),
    SelectOptionsTuple("Force Deny", "Deny submission, deleting it and any associated completions/votes."),
    SelectOptionsTuple("Approve Submission", "Approve map submission, signing off on all difficulty votes."),
    SelectOptionsTuple("Start Process Over", "Remove all completions and votes for a map without deleting the submission."),  # noqa: E501
    SelectOptionsTuple("Remove Completions", "Remove all completions for a map without deleting the submission."),
    SelectOptionsTuple("Remove Votes", "Remove all votes for a map without deleting the submission."),
    SelectOptionsTuple("Toggle Finalize Button", "Enable/Disable the Finalize button for the creator to use."),
]

mod_only_options = [
    discord.SelectOption(label=x.label, value=x.label, description=x.description) for x in mod_only_options_data
]

creator_only_options_data = [
    SelectOptionsTuple("Request Map Change", "Request a change such as code, category, or mechanics."),
    SelectOptionsTuple("Request Map Deletion", "Request to delete the map from the database."),
]

creator_only_options = [
    discord.SelectOption(label=x.label, value=x.label, description=x.description) for x in creator_only_options_data
]


class ModOnlySelectMenu(discord.ui.Select["PlaytestComponentsV2View"]):
    """Select mod commands."""

    def __init__(self) -> None:
        super().__init__(options=mod_only_options, placeholder="Mod Only Options")

    async def callback(self, interaction: Interaction) -> None:
        is_sensei = interaction.user.get_role(constants.STAFF)
        is_mod = interaction.user.get_role(constants.MOD)

        if not (is_mod or is_sensei):
            await interaction.response.send_message("You are not a mod or a sensei!", ephemeral=True)
            return

        match self.values[0]:
            case "Force Accept":
                ...
            case "Force Deny":
                ...
            case "Approve Submission":
                ...
            case "Start Process Over":
                ...
            case "Remove Completions":
                ...
            case "Remove Votes":
                ...
            case "Toggle Finalize Button":
                ...

class CreatorOnlySelectMenu(
    discord.ui.DynamicItem[discord.ui.Select["PlaytestComponentsV2View"]],
    template=r'playtest:creatoroptions:thread:(?P<id>[0-9]+)'
):
    """Select creator commands."""

    view: PlaytestComponentsV2View

    def __init__(self, *, data: MapModel, thread_id: int) -> None:
        super().__init__(
            discord.ui.Select(
                options=creator_only_options,
                placeholder="Creator Only Options",
                custom_id=f"playtest:creatoroptions:thread:{thread_id}",
            )
        )
        self.thread_id: int = thread_id
        self.data = data

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction[core.Genji],
        item: discord.ui.Select,
        match: re.Match[str],
    ) -> CreatorOnlySelectMenu:
        thread_id = int(match["id"])
        data = await cls._get_map_data(interaction.client, thread_id)
        return cls(thread_id=thread_id, data=data)

    @classmethod
    async def _get_map_data(cls, bot: core.Genji, thread_id: int) -> MapModel:
        resp = await bot.session.get(
            f"https://apitest.genji.pk/v2/maps/playtests/{thread_id}",
            headers={
                "X-API-KEY": GENJI_API_KEY,
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        return msgspec.json.decode(await resp.json(), type=maps.MapModel)

    async def callback(self, interaction: Interaction) -> None:
        if interaction.user.id not in self.view.data.creator_ids:
            await interaction.response.send_message("You are not the creator of this map!", ephemeral=True)
            return

        match self.item.values[0]:
            case "Request Map Change":
                ...
            case "Request Map Deletion":
                ...

class PlaytestLayoutViewGallery(discord.ui.MediaGallery):
    def __init__(self, url: str) -> None:
        super().__init__()
        self.media_item = discord.MediaGalleryItem(url)
        self.add_item(self.media_item)


class PlaytestComponentsV2View(discord.ui.LayoutView):

    def __init__(self, *, thread_id: int, data: MapModel) -> None:
        super().__init__(timeout=None)
        self.thread_id = thread_id
        self.data = data
        self.rebuild_components()

    def rebuild_components(self) -> None:
        self.clear_items()
        data_section = discord.ui.Container(
            PlaytestLayoutViewGallery(self.data.map_banner()),
            discord.ui.Separator(),
            discord.ui.TextDisplay(content=self.data.build_content()),
            discord.ui.Separator(),
            discord.ui.TextDisplay(content="## Mod Only Commands"),
            discord.ui.ActionRow(ModOnlySelectMenu()),
            discord.ui.TextDisplay(content="## Creator Only Commands"),
            discord.ui.ActionRow(CreatorOnlySelectMenu(thread_id=self.thread_id, data=self.data)),
            discord.ui.Separator(),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem("attachment://vote_hist.png"),
            ),
            discord.ui.ActionRow(DifficultyRatingSelect()),
        )

        self.add_item(data_section)

