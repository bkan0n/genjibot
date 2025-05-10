from __future__ import annotations

import os
import typing

import discord
from discord import app_commands
from discord.ext import commands

from utils import constants, maps, ranks, transformers, utils

if typing.TYPE_CHECKING:
    import core
    import database


class Playlist(commands.Cog):
    def __init__(self, bot: core.Genji) -> None:
        self.bot = bot

    @app_commands.command(name="submit-playtest")
    @app_commands.guilds(discord.Object(id=constants.GUILD_ID))
    async def submit_playlist(
        self,
        itx: discord.Interaction[core.Genji],
        map_code: app_commands.Transform[str, transformers.MapCodeSubmitTransformer],
        map_name: app_commands.Transform[str, transformers.MapNameTransformer],
        checkpoint_count: app_commands.Range[int, 1, 500],
        description: str = "",
        guide_url: str = "",
        gold: app_commands.Transform[float, transformers.RecordTransformer] = 0,
        silver: app_commands.Transform[float, transformers.RecordTransformer] = 0,
        bronze: app_commands.Transform[float, transformers.RecordTransformer] = 0,
    ) -> None:
        """Submit your map to get play tested.

        Args:
            itx: Interaction
            map_code: Overwatch share code
            map_name: Overwatch map
            checkpoint_count: Number of checkpoints in the map
            description: Other optional information for the map
            guide_url: Guide URL
            gold: Gold medal time (must be the fastest time)
            silver: Silver medal time (must be between gold and bronze)
            bronze: Bronze medal time (must be the slowest time)

        """
        await itx.response.defer(ephemeral=True)

        data = maps.MapModel(
            creator_ids=[itx.user.id],
            code=map_code,
            name=map_name,
            checkpoints=checkpoint_count,
            description=description,
            guide_urls=[guide_url],
            gold=gold,
            silver=silver,
            bronze=bronze,
        )

        view = await PlaylistSubmissionView.async_init(self.bot, self.bot.database, itx.user.id, data)
        await itx.edit_original_response(
            content="Is this information correct?",
            embed=data.build_embed(),
            view=view,
        )
        await view.wait()


class PlaytestSubmissionDropdown(discord.ui.Select["PlaylistSubmissionView"]):
    def __init__(
        self,
        options: list[discord.SelectOption],
        placeholder: str,
        dropdown_type: str,
        max_options: int | None = None,
    ) -> None:
        self.dropdown_type = dropdown_type
        super().__init__(
            placeholder=placeholder,
            options=options,
            min_values=1,
            max_values=max_options or len(options),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self._default_selected_values()
        assert self.view
        if self.dropdown_type == "difficulty":
            self.view.data.difficulty = self.values[0]
        else:
            setattr(self.view.data, self.dropdown_type, self.values)
        embed = self.view.data.build_embed()
        await interaction.response.edit_message(view=self.view, embed=embed)

    def _default_selected_values(self) -> None:
        for option in self.options:
            option.default = option.value in self.values

class PlaylistSubmissionView(discord.ui.View):
    _initialized: bool = False

    def __init__(self, bot: core.Genji, db: database.Database, user_id: int, data: maps.MapModel) -> None:
        if not self._initialized:
            raise ValueError("View not initialized. Call async_init() first.")
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.data = data
        self.user_id = user_id

    def convert_values_to_select(self, values: list[str]) -> list[discord.SelectOption]:
        """Convert values to select options."""
        return [discord.SelectOption(label=value, value=value) for value in values]

    @classmethod
    async def async_init(
        cls, bot: core.Genji, db: database.Database, user_id: int, data: maps.MapModel
    ) -> PlaylistSubmissionView:
        """Initialize the view."""
        cls._initialized = True
        inst = cls(bot, db, user_id, data)

        categories = await inst.db.fetch_map_categories()
        category_options = inst.convert_values_to_select(categories)
        category_dropdown = PlaytestSubmissionDropdown(
            options=category_options,
            placeholder="Select map category",
            dropdown_type="category",
        )
        inst.add_item(category_dropdown)
        restrictions = await inst.db.fetch_map_restrictions()
        restriction_options = inst.convert_values_to_select(restrictions)
        restrictions_dropdown = PlaytestSubmissionDropdown(
            options=restriction_options,
            placeholder="Select map restrictions",
            dropdown_type="restrictions",
        )
        inst.add_item(restrictions_dropdown)
        mechanics = await inst.db.fetch_map_mechanics()
        mechanics_options = inst.convert_values_to_select(mechanics)
        mechanics_dropdown = PlaytestSubmissionDropdown(
            options=mechanics_options,
            placeholder="Select map mechanics",
            dropdown_type="mechanics",
        )
        inst.add_item(mechanics_dropdown)
        difficulties = ranks.DIFFICULTIES_EXT
        difficulty_options = inst.convert_values_to_select(difficulties)
        difficulty_dropdown = PlaytestSubmissionDropdown(
            options=difficulty_options,
            placeholder="Select map difficulty",
            dropdown_type="difficulty",
            max_options=1,
        )
        inst.add_item(difficulty_dropdown)
        return inst

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.success, row=4)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content="Submitted!", view=None)
        await self.bot.session.post(
            "https://apitest.genji.pk/v2/maps/playtests/",
            json=self.data.to_api_dict(),
            headers={"X-API-KEY": os.getenv("GENJI_API_KEY", ""), "Content-Type": "application/json"},
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=4)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(content="Submission cancelled.", view=None)







async def setup(bot: core.Genji) -> None:
    """Load the cog."""
    await bot.add_cog(Playlist(bot))
