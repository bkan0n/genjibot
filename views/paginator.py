from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import TYPE_CHECKING

import discord

from utils import embeds, errors

if TYPE_CHECKING:
    import core


class Paginator(discord.ui.View):
    """A view for paginating multiple embeds."""

    def __init__(
        self,
        _embeds: list[discord.Embed | embeds.GenjiEmbed | str],
        author: discord.Member | discord.User,
        timeout: int = 600,
    ) -> None:
        """Init paginator."""
        super().__init__(timeout=timeout)
        self.pages = _embeds
        self.author = author
        self._curr_page = 0
        self.page_number.label = f"1/{len(self.pages)}"
        if len(self.pages) == 1:
            self.first.disabled = True
            self.back.disabled = True
            self.next.disabled = True
            self.last.disabled = True
        self.end_time = ""
        self.original_itx = None
        self._timeout = timeout
        if timeout is not None:
            self._update_end_time()

    def _update_end_time(self) -> None:
        time = discord.utils.format_dt(discord.utils.utcnow() + timedelta(seconds=self._timeout), "R")
        self.timeout = self._timeout
        self.end_time = "This search will time out " + time

    async def start(self, itx: discord.Interaction[core.Genji]) -> None:
        """Start the pagination view."""
        if isinstance(self.pages[0], str):
            await itx.edit_original_response(
                content=self.end_time + "\n" + self.pages[0],
                view=self,
            )
        else:
            await itx.edit_original_response(
                content=self.end_time,
                embed=self.pages[0],
                view=self,
            )
        self.original_itx = itx
        await self.wait()

    async def interaction_check(self, itx: discord.Interaction[core.Genji]) -> bool:
        """Check if the itx user is the original users who started the itx."""
        return itx.user == self.author

    async def on_timeout(self) -> None:
        """Stop view on timeout."""
        self.clear_items()
        with contextlib.suppress(discord.HTTPException):
            if isinstance(self.pages[self._curr_page], str):
                await self.original_itx.edit_original_response(
                    content=self.pages[self._curr_page],
                    view=self,
                )
            else:
                await self.original_itx.edit_original_response(
                    content=None,
                    embed=self.pages[self._curr_page],
                    view=self,
                )

        return await super().on_timeout()

    @discord.ui.button(label="First", emoji="⏮")
    async def first(self, itx: discord.Interaction[core.Genji], button: discord.ui.Button) -> None:
        """Button component to return to the first pagination page."""
        if len(self.pages) == 1:
            button.disabled = True
        self._curr_page = 0
        return await self.change_page(itx)

    @discord.ui.button(label="Back", emoji="◀")
    async def back(self, itx: discord.Interaction[core.Genji], button: discord.ui.Button) -> None:
        """Button component to go back to the last pagination page."""
        if len(self.pages) == 1:
            button.disabled = True
        if self._curr_page == 0:
            self._curr_page = len(self.pages) - 1
        else:
            self._curr_page -= 1

        return await self.change_page(itx)

    async def change_page(self, itx: discord.Interaction[core.Genji]) -> None:
        """Change the current page in paginator."""
        self.page_number.label = f"{self._curr_page + 1}/{len(self.pages)}"
        try:
            if isinstance(self.pages[self._curr_page], str):
                await itx.response.edit_message(
                    content=self.end_time + "\n" + self.pages[self._curr_page],
                    view=self,
                )
            else:
                await itx.response.edit_message(content=self.end_time, embed=self.pages[self._curr_page], view=self)
        except discord.errors.InteractionResponded:
            if isinstance(self.pages[self._curr_page], str):
                await itx.edit_original_response(
                    content=self.end_time + "\n" + self.pages[self._curr_page],
                    view=self,
                )
            else:
                await itx.edit_original_response(content=self.end_time, embed=self.pages[self._curr_page], view=self)

    @discord.ui.button(label="...")
    async def page_number(
        self,
        itx: discord.Interaction[core.Genji],
        button: discord.ui.Button,
    ) -> None:
        """Button component to open page number selection modal."""
        modal = PageNumberModal(len(self.pages))
        await itx.response.send_modal(modal)
        await modal.wait()
        number = int(modal.number.value)
        self._curr_page = number - 1
        await self.change_page(itx)

    @discord.ui.button(label="Next", emoji="▶")
    async def next(self, itx: discord.Interaction[core.Genji], button: discord.ui.Button) -> None:
        """Button component to go to the next pagination page."""
        if len(self.pages) == 1:
            button.disabled = True
        if self._curr_page == len(self.pages) - 1:
            self._curr_page = 0
        else:
            self._curr_page += 1

        return await self.change_page(itx)

    @discord.ui.button(label="Last", emoji="⏭")
    async def last(self, itx: discord.Interaction[core.Genji], button: discord.ui.Button) -> None:
        """Button component to go to the last pagination page."""
        if len(self.pages) == 1:
            button.disabled = True
        self._curr_page = len(self.pages) - 1

        return await self.change_page(itx)


class PageNumberModal(discord.ui.Modal):
    """Page number selector modal."""

    number = discord.ui.TextInput(label="Number")
    value = None

    def __init__(self, limit: int) -> None:
        super().__init__(title="Choose a page...")
        self.limit = limit
        self.number.placeholder = f"Must be an integer in range 1 - {self.limit}"

    async def on_submit(self, itx: discord.Interaction[core.Genji]) -> None:
        """Page number selection modal callback."""
        await itx.response.defer(ephemeral=True, thinking=True)

        try:
            self.value = int(self.number.value)
            if not 1 <= self.value <= self.limit:
                raise errors.OutOfRangeError
        except ValueError:
            raise errors.InvalidInteger

        if self.value:
            await itx.delete_original_response()

    async def on_error(self, itx: discord.Interaction[core.Genji], error: Exception) -> None:
        """Error handler for Page number selection modal."""
        await errors.on_app_command_error(itx, error)
