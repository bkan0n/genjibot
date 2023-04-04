import math

import discord

# GUILD_ID = 968951072599187476  # Test
GUILD_ID = 842778964673953812
# GUILD_ID = 868981788968640554

# STAFF = 1021889200242573322  # Test
STAFF = 842790097312153610

# PLAYTESTER = 1054779896305569792 # Test
ANCIENT_GOD = 868225134257897502

# TAG_MAKER = 1002267404816093244 # Test
TAG_MAKER = 1072935381357576334

#
CONFIRM = "<:_:1052666519487795261>"
# HALF_VERIFIED = "<:_:1042541868723998871>"

ROLE_REACT = 1072897860544241804


UNVERIFIED = "<:_:1042541865821556746>"

FULLY_VERIFIED = "<a:_:1053038647978512535>"
FULLY_VERIFIED_GOLD = "<a:_:1053038660553027707>"
FULLY_VERIFIED_SILVER = "<a:_:1053038666114666669>"
FULLY_VERIFIED_BRONZE = "<a:_:1053038654274162718>"

PARTIAL_VERIFIED = "<:_:1053038667935002727>"
# PARTIAL_VERIFIED_GOLD = "<:_:1053038670527074434>"
# PARTIAL_VERIFIED_SILVER = "<:_:1053038671688900629>"
# PARTIAL_VERIFIED_BRONZE = "<:_:1053038669168136302>"

TIME = "⌛"

CONFIRM_EMOJI = discord.PartialEmoji.from_str(CONFIRM)
# HALF_VERIFIED_EMOJI = discord.PartialEmoji.from_str(HALF_VERIFIED)
UNVERIFIED_EMOJI = discord.PartialEmoji.from_str(UNVERIFIED)

_FIRST = "<:_:1043226244575142018>"
_SECOND = "<:_:1043226243463659540>"
_THIRD = "<:_:1043226242335391794>"

PLACEMENTS = {
    1: _FIRST,
    2: _SECOND,
    3: _THIRD,
}


COMPLETION_PLACEHOLDER = 99_999_999.99

STAR = "★"
EMPTY_STAR = "☆"


def create_stars(rating: int | float | None) -> str:
    if not rating:
        return "Unrated"
    filled = math.ceil(rating) * STAR
    return filled + ((6 - len(filled)) * EMPTY_STAR)


def _generate_all_stars() -> list[str]:
    return [create_stars(x) for x in range(1, 7)]


ALL_STARS = _generate_all_stars()
ALL_STARS_CHOICES = [
    discord.app_commands.Choice(name=x, value=i)
    for i, x in enumerate(ALL_STARS, start=1)
]

# NEW_MAPS = 1060045563883700255  # Test
NEW_MAPS = 1072898028811341874
# PLAYTEST = 988812516551438426  # Test
PLAYTEST = 1072898429149249676
# VERIFICATION_QUEUE = 992134125253316699   # Test
VERIFICATION_QUEUE = 1072898747551469658
# NEWSFEED = 1055501059352698930  # Test
NEWSFEED = 1072897578762506260
# RECORDS = 979491570237730817   # Test
RECORDS = 1072898844339224627


class Roles:
    # NINJA = 989188787106119690  # TEST
    # JUMPER = 989184572224843877  # TEST
    # JUMPER_PLUS = 1034572630184968313  # TEST
    # SKILLED = 989184754840657920  # TEST
    # SKILLED_PLUS = 1034572662271389726  # TEST
    # PRO = 989184805843378226  # TEST
    # PRO_PLUS = 1034572705393016954  # TEST
    # MASTER = 989184828832370688  # TEST
    # MASTER_PLUS = 1034572740994269335  # TEST
    # GRANDMASTER = 989188737718169642  # TEST
    # GRANDMASTER_PLUS = 1034572780148117524  # TEST
    # GOD = 989184852639223838  # TEST
    # GOD_PLUS = 1034572827807985674  # TEST

    NINJA = 842786707417858079
    JUMPER = 1072932235084300308
    JUMPER_PLUS = 1072932216449015878
    SKILLED = 1072932198493204490
    SKILLED_PLUS = 1072932174128496710
    PRO = 1072932159993688095
    PRO_PLUS = 1072932137617076334
    MASTER = 1072932123952021524
    MASTER_PLUS = 1072932102913404998
    GRANDMASTER = 1072932080691974155
    GRANDMASTER_PLUS = 1072932057522634792
    GOD = 1072931972663476276
    GOD_PLUS = 1072932017018249300

    # MAP_MAKER = 1001927190935515188 # Test
    MAP_MAKER = 1001688523067371582

    @classmethod
    def roles_per_rank(cls, rank_num: int) -> list[int]:
        return cls.ranks[:rank_num + 1]

    @classmethod
    def ranks(cls) -> list[int]:
        return [
            cls.NINJA,
            cls.JUMPER,
            cls.SKILLED,
            cls.PRO,
            cls.MASTER,
            cls.GRANDMASTER,
            cls.GOD,
        ]

    @classmethod
    def ranks_plus(cls) -> list[int]:
        return [
            0,
            cls.JUMPER_PLUS,
            cls.SKILLED_PLUS,
            cls.PRO_PLUS,
            cls.MASTER_PLUS,
            cls.GRANDMASTER_PLUS,
            cls.GOD_PLUS,
        ]

    @classmethod
    async def find_highest_rank(cls, user: discord.Member) -> int:
        """Find the highest rank a user has.

        Args:
            user (discord.Member): User to check

        Returns:
            int: index for highest rank
        """
        ids = [r.id for r in user.roles]
        return sum(role in ids for role in cls.ranks())
