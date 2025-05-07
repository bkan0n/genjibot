from __future__ import annotations

import typing

import discord
import msgspec
from discord import app_commands
from discord.ext import commands

from utils import constants, formatter, maps, ranks, transformers, utils

if typing.TYPE_CHECKING:
    import core
    import database


class Playlist(commands.Cog):
    def __init__(self, bot: core.Genji) -> None:
        self.bot = bot

    @app_commands.command(name="submit-playlist")
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

        data = MapModel(
            code=map_code,
            name=map_name,
            checkpoints=checkpoint_count,
            description=description,
            guide_url=guide_url,
            gold=gold,
            silver=silver,
            bronze=bronze,
        )

        view = await PlaylistSubmissionView.async_init(self.bot, self.bot.database, itx.user.id, data)
        await itx.response.send_message(
            "Is this information correct?",
            ephemeral=True,
            embed=data.build_embed(),
            view=view,
        )
        await view.wait()

class PlaylistSubmissionView(discord.ui.View):
    _initialized: bool = False

    def __init__(self, bot: core.Genji, db: database.Database, user_id: int, data: MapModel) -> None:
        if not self._initialized:
            raise ValueError("View not initialized. Call async_init() first.")
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.data = data
        self.user_id = user_id
        self.value = None

    def convert_values_to_select(self, values: list[str]) -> list[discord.SelectOption]:
        """Convert values to select options."""
        return [
            discord.SelectOption(label=value, value=value) for value in values
        ]

    @classmethod
    async def async_init(cls, bot: core.Genji, db: database.Database, user_id: int, data: MapModel) -> PlaylistSubmissionView:
        """Initialize the view."""
        cls._initialized = True
        inst = cls(bot, db, user_id, data)

        categories = await inst.db.fetch_map_restrictions()
        category_options = inst.convert_values_to_select(categories)
        category_dropdown = PlaytestSubmissionDropdown(
            options=category_options,
            placeholder="Select map category",
            dropdown_type="category",
        )
        inst.add_item(category_dropdown)
        restrictions = await inst.db.fetch_map_categories()
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
        )
        inst.add_item(difficulty_dropdown)
        return inst

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.success, row=4)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = True

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=4)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()


class PlaytestSubmissionDropdown(discord.ui.Select["PlaylistSubmissionView"]):
    def __init__(self, options: list[discord.SelectOption], placeholder: str, dropdown_type: str) -> None:
        self.dropdown_type = dropdown_type
        super().__init__(
            placeholder=placeholder,
            options=options,
            min_values=1,
            max_values=len(options),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self._default_selected_values()
        assert self.view
        if self.dropdown_type == "difficulty":
            self.view.data.difficulty = self.values[0]
        else:
            setattr(self.view.data, self.dropdown_type, self.values)
            embed =self.view.data.build_embed()
        await interaction.response.edit_message(view=self.view, embed=embed)

    def _default_selected_values(self) -> None:
        for option in self.options:
            option.default = option.value in self.values

class MapModel(msgspec.Struct):
    code: str
    name: str
    checkpoints: int
    description: str = ""
    guide_url: str = ""
    gold: float = 0
    silver: float = 0
    bronze: float = 0
    category: list[str] = []
    difficulty: str = ""
    mechanics: list[str] = []
    restrictions: list[str] = []

    def build_embed(self) -> discord.Embed:
        content = formatter.Formatter(self.to_dict()).format_map()
        embed = discord.Embed(
            title=f"Map Submission: {self.name}",
            description=content,
            color=maps.MAP_DATA[self.name].COLOR,
        )
        embed.set_image(url=maps.MAP_DATA[self.name].IMAGE_URL)
        return embed

    def to_dict(self) -> dict[str, str | None]:
        return {
            "Code": self.code,
            "Map": self.name,
            "Category": self.categories_str,
            "Checkpoints": str(self.checkpoints),
            "Difficulty": self.difficulty,
            "Mechanics": self.mechanics_str,
            "Restrictions": self.restrictions_str,
            "Guide": self.guide_str,
            "Medals": self.medals_str,
            "Desc": self.description,
        }

    @staticmethod
    def _remove_nulls(sequence: list[str] | None) -> list[str]:
        if sequence is None:
            return []
        return [x for x in sequence if x is not None]

    @property
    def mechanics_str(self) -> str | None:
        self.mechanics = self._remove_nulls(self.mechanics)
        if self.mechanics:
            return ", ".join(self.mechanics)
        return None

    @property
    def restrictions_str(self) -> str | None:
        self.restrictions = self._remove_nulls(self.restrictions)
        if self.restrictions:
            return ", ".join(self.restrictions)
        return None

    @property
    def categories_str(self) -> str | None:
        self.category = self._remove_nulls(self.category)
        if self.category:
            return ", ".join(self.category)
        return None

    @property
    def guide_str(self) -> str | None:
        all_guides = []
        for count, link in enumerate(self.guide_url, start=1):
            if link:
                all_guides.append(f"[Link {count}]({link})")
        return ", ".join(all_guides)

    @property
    def medals_str(self) -> str:
        formatted_medals = []

        if self.gold:
            formatted_medals.append(f"{constants.FULLY_VERIFIED_GOLD} {self.gold}")

        if self.silver:
            formatted_medals.append(f"{constants.FULLY_VERIFIED_SILVER} {self.silver}")

        if self.bronze:
            formatted_medals.append(f"{constants.FULLY_VERIFIED_BRONZE} {self.bronze}")

        if not formatted_medals:
            return ""
        return " | ".join(formatted_medals)

async def setup(bot: core.Genji) -> None:
    """Load the cog."""
    await bot.add_cog(Playlist(bot))
