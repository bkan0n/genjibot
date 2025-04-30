from __future__ import annotations

import re
from typing import TYPE_CHECKING

from discord import app_commands

from . import constants, errors, utils
from .records import CODE_VERIFICATION

if TYPE_CHECKING:
    import discord

    import core


async def transform_user(client: core.Genji, value: str) -> utils.FakeUser | discord.Member:
    """Transform user."""
    guild = client.get_guild(constants.GUILD_ID)
    assert guild
    try:
        _value = int(value)
        member = guild.get_member(_value)
        if member:
            return member
        nickname = await client.database.fetch_nickname(_value)
        return utils.FakeUser(_value, nickname)
    except ValueError:
        raise errors.UserNotFoundError


class MapNameTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        query = "SELECT name FROM all_map_names ORDER BY similarity(name, $1::text) DESC LIMIT 1;"
        return await itx.client.database.fetchval(query, value)

    async def autocomplete(
        self,
        itx: discord.Interaction[core.Genji],
        current: str,
    ) -> list[app_commands.Choice[str]]:
        query = "SELECT name FROM all_map_names ORDER BY similarity(name, $1::text) DESC LIMIT 10;"
        names = await itx.client.database.fetch(query, current)
        return [app_commands.Choice(name=x, value=x) for (x,) in names]


class MapTypesTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        query = "SELECT name FROM all_map_types ORDER BY similarity(name, $1::text) DESC LIMIT 1;"
        return await itx.client.database.fetchval(query, value)

    async def autocomplete(
        self,
        itx: discord.Interaction[core.Genji],
        current: str,
    ) -> list[app_commands.Choice[str]]:
        query = "SELECT name FROM all_map_types ORDER BY similarity(name, $1::text) DESC LIMIT 10;"
        types = await itx.client.database.fetch(query, current)
        return [app_commands.Choice(name=x, value=x) for (x,) in types]


class MapMechanicsTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        query = "SELECT name FROM all_map_mechanics ORDER BY similarity(name, $1::text) DESC LIMIT 1;"
        return await itx.client.database.fetchval(query, value)

    async def autocomplete(
        self,
        itx: discord.Interaction[core.Genji],
        current: str,
    ) -> list[app_commands.Choice[str]]:
        query = "SELECT name FROM all_map_mechanics ORDER BY similarity(name, $1::text) DESC LIMIT 10;"
        mechanics = await itx.client.database.fetch(query, current)
        return [app_commands.Choice(name=x, value=x) for (x,) in mechanics]


class MapRestrictionsTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        query = "SELECT name FROM all_map_restrictions ORDER BY similarity(name, $1::text) DESC LIMIT 1;"
        return await itx.client.database.fetchval(query, value)

    async def autocomplete(
        self,
        itx: discord.Interaction[core.Genji],
        current: str,
    ) -> list[app_commands.Choice[str]]:
        query = "SELECT name FROM all_map_restrictions ORDER BY similarity(name, $1::text) DESC LIMIT 10;"
        restrictions = await itx.client.database.fetch(query, current)
        return [app_commands.Choice(name=x, value=x) for (x,) in restrictions]


class _MapCodeBaseTransformer(app_commands.Transformer):
    @staticmethod
    def _clean_code(map_code: str) -> str:
        return map_code.upper().replace("O", "0").lstrip().rstrip()


class MapCodeSubmitTransformer(_MapCodeBaseTransformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        value = self._clean_code(value)
        if not re.match(CODE_VERIFICATION, value):
            raise errors.IncorrectCodeFormatError
        if await itx.client.database.is_existing_map_code(value):
            raise errors.MapExistsError
        return value


class _MapCodeAutocompleteBaseTransformer(_MapCodeBaseTransformer):
    async def autocomplete(self, itx: discord.Interaction[core.Genji], current: str) -> list[app_commands.Choice[str]]:
        query = "SELECT map_code FROM maps WHERE archived = FALSE ORDER BY similarity(map_code, $1) DESC LIMIT 5;"
        results = await itx.client.database.fetch(query, current)
        return [app_commands.Choice(name=a, value=a) for (a,) in results]


class MapCodeTransformer(_MapCodeAutocompleteBaseTransformer):
    @staticmethod
    def _clean_code(map_code: str) -> str:
        return map_code.upper().replace("O", "0").lstrip().rstrip()

    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        value = self._clean_code(value)
        if not re.match(CODE_VERIFICATION, value):
            raise errors.IncorrectCodeFormatError
        query = "SELECT map_code FROM maps WHERE archived = FALSE ORDER BY similarity(map_code, $1) DESC LIMIT 1;"
        res = await itx.client.database.fetch(query, value)
        if not res or res[0]["map_code"] != value:
            raise errors.NoMapsFoundError
        return value


class MapCodeRecordsTransformer(_MapCodeAutocompleteBaseTransformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        value = self._clean_code(value)

        if not await itx.client.database.is_existing_map_code(value):
            raise errors.InvalidMapCodeError

        if not re.match(CODE_VERIFICATION, value):
            raise errors.IncorrectCodeFormatError

        return value


class CreatorTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> int:
        user = await transform_user(itx.client, value)
        if not user:
            raise errors.UserNotFoundError
        else:
            return user.id

    async def autocomplete(self, itx: discord.Interaction[core.Genji], current: str) -> list[app_commands.Choice[str]]:
        query = """
            WITH creator_ids AS (
                SELECT DISTINCT user_id FROM map_creators
            ),
            matched_names AS (
                SELECT u.user_id, name
                FROM users u
                JOIN creator_ids c ON u.user_id = c.user_id
                CROSS JOIN LATERAL (
                    VALUES (u.nickname), (u.global_name)
                ) AS name_list(name)
                WHERE name % $1
            
                UNION
            
                SELECT o.user_id, o.username AS name
                FROM user_overwatch_usernames o
                JOIN creator_ids c ON o.user_id = c.user_id
                WHERE o.username % $1
            ),
            ranked_creators AS (
                SELECT user_id, MAX(similarity(name, $1)) AS sim
                FROM matched_names
                GROUP BY user_id
                ORDER BY sim DESC
                LIMIT 6
            ),
            creator_names AS (
                SELECT
                    u.user_id,
                    ARRAY_REMOVE(
                        ARRAY[
                            u.nickname,
                            u.global_name
                        ] || ARRAY_AGG(DISTINCT own_all.username),
                        NULL
                    ) AS all_usernames
                FROM ranked_creators rc
                JOIN users u ON u.user_id = rc.user_id
                LEFT JOIN user_overwatch_usernames own_all ON u.user_id = own_all.user_id
                GROUP BY u.user_id, u.nickname, u.global_name, sim
                ORDER BY sim DESC
            )
            SELECT user_id, ARRAY(SELECT DISTINCT * FROM unnest(all_usernames)) FROM creator_names;
        """
        results = await itx.client.database.fetch(query, current)
        return [
            app_commands.Choice(name=f"{', '.join(row['all_usernames'])} ({row['user_id']})"[:100], value=str(row["user_id"]))
            for row in results
        ]


class AllUserTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> utils.FakeUser | discord.Member:
        return await transform_user(itx.client, value)

    async def autocomplete(self, itx: discord.Interaction[core.Genji], current: str) -> list[app_commands.Choice[str]]:
        query = """
        WITH matches AS (
            SELECT u.user_id, name
            FROM users u
            CROSS JOIN LATERAL (
                VALUES (u.nickname), (u.global_name)
            ) AS name_list(name)
            WHERE name % $1
        
            UNION
        
            SELECT o.user_id, o.username AS name
            FROM user_overwatch_usernames o
            WHERE o.username % $1
        ),
        ranked_users AS (
            SELECT user_id, MAX(similarity(name, $1)) AS sim
            FROM matches
            GROUP BY user_id
            ORDER BY sim DESC
            LIMIT 10
        ),
        user_names AS (
            SELECT
                u.user_id,
                ARRAY_REMOVE(
                    ARRAY[
                        u.nickname,
                        u.global_name
                    ] || ARRAY_AGG(DISTINCT own_all.username),
                    NULL
                ) AS all_usernames
            FROM ranked_users ru
            JOIN users u ON u.user_id = ru.user_id
            LEFT JOIN user_overwatch_usernames own_all ON u.user_id = own_all.user_id
            GROUP BY u.user_id, u.nickname, u.global_name, sim
            ORDER BY sim DESC
        )
        SELECT user_id, ARRAY(SELECT DISTINCT * FROM unnest(all_usernames)) FROM user_names;

        """
        results = await itx.client.database.fetch(query, current)
        return [
            app_commands.Choice(name=f"{', '.join(row['all_usernames'])} ({row['user_id']})"[:100], value=str(row["user_id"]))
            for row in results
        ]


class FakeUserTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> utils.FakeUser | discord.Member:
        user = await transform_user(itx.client, value)
        if isinstance(user, utils.FakeUser):
            return user
        raise errors.FakeUserNotFoundError

    async def autocomplete(self, itx: discord.Interaction[core.Genji], current: str) -> list[app_commands.Choice[str]]:
        query = """
            SELECT user_id, nickname
            FROM USERS
            WHERE user_id < 10000000
            ORDER BY similarity(nickname, $1) DESC
            LIMIT 10;
        """
        results = await itx.client.database.fetch(query, current)
        return [app_commands.Choice(name=f"{nick} ({id_})", value=nick) for id_, nick in results]


class RecordTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> float:
        try:
            return time_convert(value)
        except ValueError:
            raise errors.IncorrectRecordFormatError


class URLTransformer(app_commands.Transformer):
    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        value = value.strip()
        if not value.startswith("https://") and not value.startswith("http://"):
            value = "https://" + value
        try:
            async with itx.client.session.get(value) as resp:
                if resp.status != 200:  # noqa: PLR2004
                    raise errors.IncorrectURLFormatError
                return str(resp.url)
        except Exception:
            raise errors.IncorrectURLFormatError


def time_convert(string: str) -> float:
    """Convert HH:MM:SS.ss string into seconds (float)."""
    negative = -1 if string[0] == "-" else 1
    time = string.split(":")
    match len(time):
        case 1:
            res = float(time[0])
        case 2:
            res = float((int(time[0]) * 60) + (negative * float(time[1])))
        case 3:
            res = float((int(time[0]) * 3600) + (negative * (int(time[1]) * 60)) + (negative * float(time[2])))
        case _:
            raise ValueError("Failed to match any cases.")
    return round(res, 2)


class KeyTypeTransformer(app_commands.Transformer):
    """Transform key type."""

    async def autocomplete(self, itx: discord.Interaction[core.Genji], current: str) -> list[app_commands.Choice[str]]:
        query = "SELECT name FROM lootbox_key_types ORDER BY similarity(name, $1) DESC LIMIT 5;"
        results = await itx.client.database.fetch(query, current)
        return [app_commands.Choice(name=a, value=a) for (a,) in results]

    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        query = "SELECT name FROM lootbox_key_types ORDER BY similarity(name, $1) DESC LIMIT 1;"
        res = await itx.client.database.fetch(query, value)
        if not res or res[0]["name"] != value:
            raise errors.NoMapsFoundError
        return value


class CommandNameTransformer(app_commands.Transformer):
    """Transform command names."""

    async def autocomplete(self, itx: discord.Interaction[core.Genji], current: str) -> list[app_commands.Choice[str]]:
        query = """
            SELECT DISTINCT event, similarity(event, $1) as similarity_score
            FROM analytics ORDER BY similarity_score DESC LIMIT 5;
        """
        results = await itx.client.database.fetch(query, current)
        return [app_commands.Choice(name=row["event"], value=row["event"]) for row in results]

    async def transform(self, itx: discord.Interaction[core.Genji], value: str) -> str:
        query = """
            SELECT DISTINCT event, similarity(event, $1) as similarity_score
            FROM analytics ORDER BY similarity_score DESC LIMIT 1;
        """
        res = await itx.client.database.fetch(query, value)
        if not res or res[0]["event"] != value:
            raise errors.NoMapsFoundError
        return value
