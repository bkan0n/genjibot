from __future__ import annotations

import contextlib
import json
import logging
from typing import TYPE_CHECKING

import discord
from discord import Interaction, InteractionType
from discord.ext import commands, tasks

if TYPE_CHECKING:
    import datetime

    from core import Genji

log = logging.getLogger(__name__)


class AnalyticsTasks(commands.Cog):
    def __init__(self, bot: Genji) -> None:
        super().__init__()
        self.bot = bot
        self.send_info_to_db.start()

    async def cog_unload(self) -> None:
        self.send_info_to_db.cancel()

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context[Genji]) -> None:
        self.bot.log_analytics(
            ctx.command.qualified_name,
            ctx.author.id,
            ctx.message.created_at,
            ctx.kwargs,
        )

    @commands.Cog.listener()
    async def on_interaction(self, itx: discord.Interaction[Genji]) -> None:
        if itx.command and itx.type == InteractionType.application_command:
            _namespace = {}
            for k, v in itx.namespace.__dict__.items():
                if isinstance(v, (str, int, float)):
                    _namespace[k] = v
                elif isinstance(v, (discord.Member, discord.User, discord.Role, discord.Guild)):
                    _namespace[k] = f"{v.name} {v.id}"
            log.info(
                "On Interaction Logging the following info\n\n %s %s %s %s",
                itx.command.name,
                itx.user.id,
                itx.created_at,
                _namespace,
            )
            self.bot.log_analytics(itx.command.name, itx.user.id, itx.created_at, _namespace)

    @tasks.loop(seconds=60)
    async def send_info_to_db(self) -> None:
        query = """
            INSERT INTO analytics (event, user_id,  date_collected, args)
            VALUES($1, $2, $3, $4);
        """
        rows: list[tuple[str, int, datetime.datetime, str]] = []
        for raw_event, user_id, timestamp, args in self.bot.analytics_buffer:
            log.debug(raw_event, user_id, timestamp, args)
            with contextlib.suppress(KeyError):
                args.pop("screenshot")
            rows.append((raw_event, user_id, timestamp, json.dumps(args)))
        if rows:
            await self.bot.database.set_many(query, rows)
            self.bot.analytics_buffer = []


async def setup(bot: Genji) -> None:
    """Add bot cog via extension."""
    bot.analytics_buffer = []
    await bot.add_cog(AnalyticsTasks(bot))
