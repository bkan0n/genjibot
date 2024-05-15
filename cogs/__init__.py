from __future__ import annotations

import copy
import functools
import pkgutil
import typing
from datetime import timedelta

import discord
from discord import app_commands

import utils
import views
from utils import MaxMapsInPlaytest, MaxWeeklyMapsInPlaytest, new_map_newsfeed

if typing.TYPE_CHECKING:
    import core

EXTENSIONS = [
    module.name for module in pkgutil.iter_modules(__path__, f"{__package__}.")
]


def case_ignore_compare(string1: str | None, string2: str | None) -> bool:
    """
    Compare two strings, case-insensitive.
    Args:
        string1 (str): String 1 to compare
        string2 (str): String 2 to compare
    Returns:
        True if string2 is in string1
    """
    if string1 is None or string2 is None:
        return False
    return string2.casefold() in string1.casefold()


async def _autocomplete(
    current: str,
    choices: list[app_commands.Choice[str]],
) -> list[app_commands.Choice[str]]:
    if not choices:  # Quietly ignore empty choices
        return []
    if current == "":
        response = choices[:25]
    else:
        response = [x for x in choices if case_ignore_compare(x.name, current)][:25]
    return response


async def creator_autocomplete(
    itx: discord.Interaction[core.Genji], current: str
) -> list[app_commands.Choice[str]]:
    return await _autocomplete(current, itx.client.cache.users.creator_choices)


async def map_codes_autocomplete(
    itx: discord.Interaction[core.Genji], current: str
) -> list[app_commands.Choice[str]]:
    current = current.replace("O", "0").replace("o", "0")
    return await _autocomplete(current, itx.client.cache.maps.choices)


async def map_name_autocomplete(
    itx: discord.Interaction[core.Genji], current: str
) -> list[app_commands.Choice[str]]:
    return await _autocomplete(current, itx.client.cache.map_names.choices)


async def map_type_autocomplete(
    itx: discord.Interaction[core.Genji], current: str
) -> list[app_commands.Choice[str]]:
    return await _autocomplete(current, itx.client.cache.map_types.choices)


async def map_mechanics_autocomplete(
    itx: discord.Interaction[core.Genji], current: str
) -> list[app_commands.Choice[str]]:
    return await _autocomplete(current, itx.client.cache.map_mechanics.choices)


async def map_restrictions_autocomplete(
    itx: discord.Interaction[core.Genji], current: str
) -> list[app_commands.Choice[str]]:
    return await _autocomplete(current, itx.client.cache.map_restrictions.choices)


async def tags_autocomplete(
    itx: discord.Interaction[core.Genji], current: str
) -> list[app_commands.Choice[str]]:
    return await _autocomplete(current, itx.client.cache.tags.choices)


async def users_autocomplete(
    itx: discord.Interaction[core.Genji], current: str
) -> list[app_commands.Choice[str]]:
    return await _autocomplete(current, itx.client.cache.users.choices)


async def submit_map_(
    itx: discord.Interaction[core.Genji],
    data: utils.MapSubmission,
    mod: bool = False,
) -> None:
    """
    Submit your map to the database.

    Args:
        itx: Interaction
        data: MapSubmission obj
        mod: Mod command
    """

    await itx.response.defer(ephemeral=True)

    if data.medals:
        if not 0 < data.gold < data.silver < data.bronze:
            raise utils.InvalidMedals

    if await _check_max_limit(itx) >= 5:
        raise MaxMapsInPlaytest()
    count, date = await _check_weekly_limit(itx)
    if count >= 2:
        date = date + timedelta(weeks=1)
        raise MaxWeeklyMapsInPlaytest(
            "You will be able to submit again "
            f"{discord.utils.format_dt(date, 'R')}"
            f"| {discord.utils.format_dt(date, 'F')}"
        )

    initial_message = (
        f"{data.creator.mention}, "
        f"fill in additional details to complete map submission!"
    )
    view = views.ConfirmMapSubmission(
        itx,
        partial_callback=None,
        initial_message=initial_message,
    )
    callback = functools.partial(map_submission_first_step, data, itx, mod, view)
    view.partial_callback = callback
    await view.start()


async def _check_weekly_limit(itx: discord.Interaction[core.Genji]):
    query = """
        SELECT count(*), min(date) as date
          FROM map_submission_dates
         WHERE
           user_id = $1 AND date BETWEEN now() - INTERVAL '1 weeks' AND now();
    """
    row = await itx.client.database.get_row(query, itx.user.id)
    return row.get("count", 0), row.get("date", None)


async def _check_max_limit(itx: discord.Interaction[core.Genji]):
    query = """
        SELECT count(*) FROM playtest WHERE is_author = TRUE AND user_id = $1;
    """
    row = await itx.client.database.get_row(query, itx.user.id)
    return row.get("count", 0)


async def map_submission_first_step(
    data: utils.MapSubmission,
    itx: discord.Interaction[core.Genji],
    mod: bool,
    view: views.ConfirmMapSubmission,
):
    data.set_extras(
        map_types=view.map_type.values,
        mechanics=view.mechanics.values,
        restrictions=view.restrictions.values,
        difficulty=view.difficulty.values[0],
    )
    embed = utils.GenjiEmbed(
        title="Map Submission",
        description=str(data),
    )
    embed.set_author(
        name=itx.client.cache.users[data.creator.id].nickname,
        icon_url=data.creator.display_avatar.url,
    )
    embed = utils.set_embed_thumbnail_maps(data.map_name, embed)
    view_final_confirmation = views.ConfirmBaseView(
        view.itx,
        partial_callback=None,
        initial_message=f"{itx.user.mention}, is this correct?",
    )
    callback = functools.partial(map_submission_second_step, data, embed, itx, mod)
    view_final_confirmation.partial_callback = callback
    await view_final_confirmation.start(embed=embed)


async def map_submission_second_step(
    data: utils.MapSubmission,
    embed: discord.Embed,
    itx: discord.Interaction[core.Genji],
    mod: bool,
):
    if not mod:
        embed.title = "Calling all Playtesters!"
        view = views.PlaytestVoting(
            data,
            itx.client,
        )
        playtest_message = await itx.guild.get_channel(utils.PLAYTEST).send(
            content=f"Total Votes: 0 / {view.required_votes}", embed=embed
        )
        embed = utils.GenjiEmbed(
            title="Difficulty Ratings",
            description="You can change your vote, but you cannot cast multiple!\n\n",
        )
        thread = await playtest_message.create_thread(
            name=(
                f"{data.map_code} | {data.difficulty} | {data.map_name} "
                f"{data.checkpoint_count} CPs"
            )
        )

        thread_msg = await thread.send(
            f"Discuss, play, rate, etc.",
            view=view,
            embed=embed,
        )
        itx.client.playtest_views[thread_msg.id] = view
        await thread.send(
            f"{itx.user.mention}, you can receive feedback on your map here. "
            f"I'm pinging you so you are able to join this thread automatically!"
        )

        await data.insert_playtest(itx, thread.id, thread_msg.id, playtest_message.id)
    await data.insert_all(itx, mod)
    itx.client.cache.maps.add_one(
        utils.MapData(
            map_code=data.map_code,
            user_ids=[data.creator.id],
            archived=False,
        )
    )
    if not mod:
        map_maker = itx.guild.get_role(utils.Roles.MAP_MAKER)
        if map_maker not in itx.user.roles:
            await itx.user.add_roles(map_maker, reason="Submitted a map.")
    else:
        await new_map_newsfeed(itx.client, data.creator.id, data)
        # itx.client.dispatch("newsfeed_new_map", data.creator, data)
    if not itx.client.cache.users.find(data.creator.id).is_creator:
        itx.client.cache.users.find(data.creator.id).update_is_creator(True)


async def add_creator_(
    creator: int,
    itx: discord.Interaction[core.Genji],
    map_code: str,
):
    await itx.response.defer(ephemeral=True)
    if creator in itx.client.cache.maps[map_code].user_ids:
        raise utils.CreatorAlreadyExists
    await itx.client.database.set(
        "INSERT INTO map_creators (map_code, user_id) VALUES ($1, $2)",
        map_code,
        creator,
    )
    itx.client.cache.maps[map_code].add_creator(creator)
    itx.client.cache.users[creator].is_creator = True
    await itx.edit_original_response(
        content=(
            f"Adding **{itx.client.cache.users[creator].nickname}** "
            f"to list of creators for map code **{map_code}**."
        )
    )


async def remove_creator_(creator, itx, map_code, checks: bool = False):
    await itx.response.defer(ephemeral=True)
    if creator not in itx.client.cache.maps[map_code].user_ids:
        raise utils.CreatorDoesntExist
    await itx.client.database.set(
        "DELETE FROM map_creators WHERE map_code = $1 AND user_id = $2;",
        map_code,
        creator,
    )
    itx.client.cache.maps[map_code].remove_creator(creator)
    await itx.edit_original_response(
        content=(
            f"Removing **{itx.client.cache.users[creator].nickname}** "
            f"from list of creators for map code **{map_code}**."
        )
    )
