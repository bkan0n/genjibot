from __future__ import annotations

import re
import typing

import discord

from . import ranks
from .constants import COMPLETION_PLACEHOLDER


class GenjiEmbed(discord.Embed):
    def __init__(
        self,
        *,
        color: int | discord.Color | None = None,
        title: str | None = None,
        url: str | None = None,
        description: str | None = None,
        thumbnail: str | None = None,
        image: str | None = None,
    ) -> None:
        if not color:
            color = discord.Color.from_rgb(1, 1, 1)

        super().__init__(color=color, title=title, url=url, description=description)

        if not thumbnail:
            self.set_thumbnail(url="https://i.imgur.com/qhcwGOY.png")
        else:
            self.set_thumbnail(url=thumbnail)

        if not image:
            self.set_image(url="https://i.imgur.com/YhJokJW.png")
        else:
            self.set_image(url=image)

    def add_description_field(self, name: str, value: str) -> None:
        if not self.description:
            self.description = ""
        self.description += f"```{name}```{value}\n"  # \u001b[{format};{color}m


class ErrorEmbed(GenjiEmbed):
    def __init__(
        self,
        *,
        description: str,
        unknown: bool = False,
    ) -> None:
        if unknown:
            super().__init__(
                title="Uh oh! Something went wrong.",
                description=description,
                color=discord.Color.red(),
                thumbnail="http://bkan0n.com/assets/images/icons/error.png",
            )
        else:
            super().__init__(
                title="What happened?",
                description=description,
                color=discord.Color.yellow(),
            )

            self.set_footer(text="If you have any questions, message nebula#6662")


def set_embed_thumbnail_maps(map_name: str, embed: discord.Embed) -> discord.Embed | GenjiEmbed:
    """Set embed thumbnail.

    The embed_thumbnail_setter function takes a map name
    and an embed object as parameters.
    It then uses the map name to search for a thumbnail image
    and sets that image as the embed's thumbnail.

    Args:
        map_name (str): Set the map name to be used in the embed
        embed (discord.Embed): Set the thumbnail of the embed
    Returns:
        The embed object with the thumbnail set to a map's image

    """
    map_name = re.sub(r"[:'\s]", "", map_name).lower()
    embed.set_thumbnail(url=f"http://bkan0n.com/assets/images/map_banners/{map_name}.png")
    return embed


def record_embed(data: dict[str, typing.Any]) -> discord.Embed:
    """Create record embed."""
    if data.get("record") and data["record"] == COMPLETION_PLACEHOLDER:
        data["record"] = "Completion"

    if not data.get("video"):
        description = (
            f"┣ `   Code ` {data['map_code']}\n"
            f"┣ `   Diff ` {ranks.convert_num_to_difficulty(data['difficulty'])}\n"
            f"┗ ` Record ` {data['record']}\n"
        )
    else:
        description = (
            f"┣ `   Code ` {data['map_code']}\n"
            f"┣ `   Diff ` {ranks.convert_num_to_difficulty(data['difficulty'])}\n"
            f"┣ ` Record ` {data['record']}\n"
            f"┗ `  Video ` [Link]({data['video']})\n"
        )

    embed = GenjiEmbed(
        title="New Submission!",
        description=description,
    )
    embed.set_author(name=data["user_name"], icon_url=data["user_url"])
    embed.set_image(url="attachment://image.png")
    return embed
