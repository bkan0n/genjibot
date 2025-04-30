from __future__ import annotations

import typing

import discord.ui

from utils import utils

if typing.TYPE_CHECKING:
    import core


def bool_string(value: bool) -> str:
    """Return ON or OFF depending on the boolean value given."""
    if value:
        return "ON"
    else:
        return "OFF"


ENABLED_EMOJI = "🔔"
DISABLED_EMOJI = "🔕"


class SettingsView(discord.ui.View):
    """User settings view."""

    def __init__(self, original_itx: discord.Interaction[core.Genji], flags: int) -> None:
        super().__init__(timeout=3600)
        self.itx = original_itx
        self.flags = utils.SettingFlags(flags)
        self.verification = NotificationButton("Verification", utils.SettingFlags.VERIFICATION in self.flags)
        self.add_item(self.verification)
        self.promotion = NotificationButton("Promotion", utils.SettingFlags.PROMOTION in self.flags)
        self.add_item(self.promotion)

    @discord.ui.button(label="Change Name", style=discord.ButtonStyle.blurple, row=1)
    async def name_change(self, itx: discord.Interaction[core.Genji], button: discord.ui.Button) -> None:
        """Change name button callback."""
        await itx.response.send_modal(NameChangeModal())


class NotificationButton(discord.ui.Button):
    """Notification settings button."""

    view: SettingsView

    def __init__(self, name: str, value: bool) -> None:
        self.name = name
        super().__init__()
        self.edit_button(name, value)

    async def callback(self, itx: discord.Interaction[core.Genji]) -> None:
        """Notification button callback."""
        await itx.response.defer(ephemeral=True)
        self.view.flags ^= getattr(utils.SettingFlags, self.name.upper())
        self.edit_button(self.name, getattr(utils.SettingFlags, self.name.upper()) in self.view.flags)
        await self.view.itx.edit_original_response(view=self.view)
        await itx.client.database.execute(
            "UPDATE users SET flags = $1 WHERE user_id = $2;",
            self.view.flags,
            itx.user.id,
        )

    def edit_button(self, name: str, value: bool) -> None:
        """Edit button."""
        self.label = f"{name} Notifications are {bool_string(value)}"
        self.emoji = ENABLED_EMOJI if value else DISABLED_EMOJI
        self.style = discord.ButtonStyle.green if value else discord.ButtonStyle.red


class NameChangeModal(discord.ui.Modal, title="Change Name"):
    """Name change modal."""

    name = discord.ui.TextInput(
        label="Nickname",
        style=discord.TextStyle.short,
        placeholder="Write your most commonly known nickname/alias.",
    )

    async def on_submit(self, itx: discord.Interaction[core.Genji]) -> None:
        """Name change modal callback."""
        await itx.response.send_message(f"You have changed your display name to {self.name}!", ephemeral=True)

        await itx.client.database.execute(
            "UPDATE users SET nickname = $1 WHERE user_id = $2;",
            self.name.value[:25],
            itx.user.id,
        )


class OverwatchUsernamesView(discord.ui.View):
    """Overwatch usernames view."""

    message: discord.Message

    @discord.ui.button(label="Add Overwatch Username", style=discord.ButtonStyle.green, row=1)
    async def _add_overwatch_username(self, itx: discord.Interaction[core.Genji], button: discord.ui.Button) -> None:
        """Add Overwatch username button callback."""
        await itx.response.send_modal(OverwatchUsernameModal())

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

        await self.message.edit(view=self)


class OverwatchUsernameModal(discord.ui.Modal, title="Add Overwatch Username"):
    """Overwatch username modal."""

    username = discord.ui.TextInput(
        label="Overwatch Username",
        style=discord.TextStyle.short,
        placeholder=(
            "Enter your Overwatch username. "
            "You can ignore the discriminator (the trailing numbers including the # sign)"),
        max_length=25,
        required=True,
    )

    async def on_submit(self, itx: discord.Interaction[core.Genji]) -> None:
        """Username modal callback."""
        await itx.response.send_message(f"Added Overwatch username: {self.username.value}", ephemeral=True)
        query = "INSERT INTO user_overwatch_usernames (user_id, username, is_primary) VALUES ($1, $2, $3);"
        await itx.client.database.execute(query, itx.user.id, self.username.value, True)


