from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

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

        thread, _ = await forum.create_thread(
            name=f"Playtest: {data.code} {data.name} by {data.creator_names[0]}",
            reason="Playtest test created",
            view=PlaytestComponentsV2View(data),
            file=file,
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


class ModCommandsSelect(discord.ui.Select):
    """Select mod commands."""

    def __init__(self):
        super().__init__()


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
            discord.ui.TextDisplay(content=data.build_content()),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem("attachment://vote_hist.png"),
            ),
            discord.ui.ActionRow(DifficultyRatingSelect()),
        )
        self.add_item(data_section)

