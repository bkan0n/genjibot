from __future__ import annotations

import functools
import typing

import discord
from discord import app_commands
from discord.ext import commands

import utils
import views

if typing.TYPE_CHECKING:
    import core


class Test(commands.Cog):
    @commands.command()
    @commands.guild_only()
    @commands.is_owner()
    async def sync(
        self,
        ctx: commands.Context,
        guilds: commands.Greedy[discord.Object],
        spec: typing.Literal["~", "*", "^"] | None = None,
    ) -> None:
        """
        ?sync -> global sync
        ?sync ~ -> sync current guild
        ?sync * -> copies all global app commands to current guild and syncs
        ?sync ^ -> clears all commands from the current
                        guild target and syncs (removes guild commands)
        ?sync id_1 id_2 -> syncs guilds with id 1 and 2
        >sync $ -> Clears global commands
        """
        if not guilds:
            if spec == "~":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "^":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                synced = []
            elif spec == "$":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync()
                synced = []
            else:
                synced = await ctx.bot.tree.sync()

            await ctx.send(
                f"Synced {len(synced)} commands "
                f"{'globally' if spec is None else 'to the current guild.'}"
            )
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

    @commands.command()
    @commands.is_owner()
    async def xx(self, ctx: commands.Context[core.Genji]):
        members = [(member.id, member.name[:25]) for member in ctx.guild.members]
        await ctx.bot.database.set_many(
            "INSERT INTO users (user_id, nickname, alertable) VALUES ($1, $2, true)",
            list(members),
        )
        await ctx.send("done")

    @commands.command()
    @commands.is_owner()
    async def xxx(self, ctx: commands.Context[core.Genji]):
        members = [(member.id, member.name[:25]) for member in ctx.guild.members]
        await ctx.bot.database.set_many(
            "INSERT INTO users (user_id, nickname, alertable) VALUES ($1, $2, true)",
            list(members),
        )
        await ctx.send("done")

    @commands.command()
    @commands.is_owner()
    async def placeholder(self, ctx: commands.Context[core.Genji]):
        await ctx.send("placeholder")

    @commands.command()
    @commands.is_owner()
    async def log(
        self,
        ctx: commands.Context[core.Genji],
        level: typing.Literal["debug", "info", "DEBUG", "INFO"],
    ):
        ctx.bot.logger.setLevel(level.upper())
        await ctx.message.delete()

    # @app_commands.command(name="test")
    # @app_commands.guilds(discord.Object(id=utils.GUILD_ID))
    # async def testing_slash(self, itx: discord.Interaction[core.Genji]) -> None:
    #     command = itx.client.tree.get_app_command("submit-record", guild=utils.GUILD_ID)
    #
    #     embed = utils.GenjiEmbed(
    #         title="Test Help", description=f"Use this comman {command.mention}"
    #     )
    #
    #     await itx.response.send_message(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def close(
        self,
        ctx: commands.Context[core.Genji],
    ):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.channel.send("Bot will be down for a few minutes!")
        await ctx.message.delete()

    @commands.command()
    @commands.is_owner()
    async def open(
        self,
        ctx: commands.Context[core.Genji],
    ):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.channel.send("Back online!")
        await ctx.message.delete()

    @commands.command()
    @commands.is_owner()
    async def enlarge(
        self, ctx: commands.Context[core.Genji], emoji: discord.PartialEmoji | str
    ):
        if isinstance(emoji, discord.PartialEmoji):
            await ctx.send(emoji.url)
        else:
            await ctx.send()

    @app_commands.command(name="oogabooga")
    @app_commands.guilds(discord.Object(id=868981788968640554))
    async def _test_server_test_command(
        self, itx: discord.Interaction[core.Genji], attachment: discord.Attachment
    ):
        partial = functools.partial(self._poop)
        view = views.ConfirmBaseView(itx, partial)
        file = await attachment.to_file(filename="image.png")
        embed = utils.GenjiEmbed(
            title="eskjfnsdkf",
            description="lkdfjgd\nksjdf\ndklfjg",
            image="attachment://image.png",
        )
        await view.start(embed=embed, attachment=file)

    async def _poop(self):
        print("WOW")


async def setup(bot: core.Genji):
    await bot.add_cog(Test(bot))
