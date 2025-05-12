from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, NamedTuple

import discord
import msgspec
from discord import Interaction
from discord._types import ClientT

import database
from playtest.playtest_graph import VoteHistogram
from utils import maps, ranks

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
        thread, _ = await forum.create_thread(
            name=f"{data.code} | {data.difficulty} {data.name} by {data.creator_names[0]}"[:100],
            reason="Playtest test created",
            view=PlaytestComponentsV2View(data),
            file=file,
            applied_tags=[tag]
        )

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


class DifficultyRatingSelect(discord.ui.Select):
    """Select difficulty rating."""

    def __init__(self):
        options = [
            discord.SelectOption(value=x, label=x) for x in ranks.DIFFICULTIES_EXT
        ]
        super().__init__(options=options, placeholder="What difficulty would you rate this map?")

    async def callback(self, interaction: Interaction) -> Any:
        ...


class ModCommandsTuple(NamedTuple):
    label: str
    description: str


mod_only_options_data = {
    ModCommandsTuple("Force Accept", "Force submission through, overwriting difficulty votes."),
    ModCommandsTuple("Force Deny", "Deny submission, deleting it and any associated completions/votes."),
    ModCommandsTuple("Approve Submission", "Approve map submission, signing off on all difficulty votes."),
    ModCommandsTuple("Start Process Over", "Remove all completions and votes for a map without deleting the submission."),  # noqa: E501
    ModCommandsTuple("Remove Completions", "Remove all completions for a map without deleting the submission."),
    ModCommandsTuple("Remove Votes", "Remove all votes for a map without deleting the submission."),
    ModCommandsTuple("Toggle Finalize Button", "Enable/Disable the Finalize button for the creator to use."),
}

mod_only_options = [
    discord.SelectOption(label=x.label, value=x.label, description=x.description) for x in mod_only_options_data
]



class ModOnlySelectMenu(discord.ui.Select):
    """Select mod commands."""

    def __init__(self) -> None:
        super().__init__(options=mod_only_options, placeholder="Mod Only Options")

    async def callback(self, interaction: Interaction) -> None:
        # TODO: Mod only check
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


class PlaytestVotingView(discord.ui.View):
    """View for playtest voting."""

    def __init__(
        self,
        # bot: core.Genji, db: database.Database, data: maps.MapModel
    ) -> None:
        super().__init__(timeout=300)
        # self.bot = bot
        # self.db = db
        # self.data = data
        self.add_item(DifficultyRatingSelect())
        # self.add_item(ModCommandsSelect())


class PlaytestLayoutViewGallery(discord.ui.MediaGallery):
    def __init__(self, url: str) -> None:
        super().__init__()
        self.media_item = discord.MediaGalleryItem(url)
        self.add_item(self.media_item)


class PlaytestComponentsV2View(discord.ui.LayoutView):

    def __init__(self, data: MapModel) -> None:
        super().__init__(timeout=None)
        self.data = data

        data_section = discord.ui.Container(
            PlaytestLayoutViewGallery(data.map_banner()),
            discord.ui.Separator(),
            discord.ui.TextDisplay(content=data.build_content()),
            discord.ui.Separator(),
            discord.ui.TextDisplay(content="## Mod Only Commands"),
            discord.ui.ActionRow(ModOnlySelectMenu()),
            discord.ui.Separator(),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem("attachment://vote_hist.png"),
            ),
            discord.ui.ActionRow(DifficultyRatingSelect()),
        )

        self.add_item(data_section)


