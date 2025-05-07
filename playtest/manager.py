from __future__ import annotations

import os
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    import core
    from utils.maps import MapModel


PLAYTEST_FORUM_ID = 1369672124352040970
GENJI_GUILD_ID = 842778964673953812
GENJI_API_KEY: str = os.getenv("GENJI_API_KEY", "")

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

        await forum.create_thread(
            name=f"Playtest: {data.code} {data.name} by {data.creator_ids[0]}",
            content="testing",
            reason="Playtest () created",
        )

    async def _insert_playtest_data(self, rabbit_data: dict) -> None:
        """Insert playtest data into the database."""
        await self._bot.session.post(
            "https://api.genji.pk/v2/maps/playtests/",
            json={
                "playtest_id": rabbit_data["playtest_id"],
                "name": rabbit_data["name"],
                "message": rabbit_data["message"],
                "date": rabbit_data["date"],
            },
            headers={
                "X-API-KEY": GENJI_API_KEY,
                "Content-Type": "application/json",
            },

        )