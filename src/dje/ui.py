import discord

from .i18n import t

EMBED_COLOR = None


def make_embed(title_key: str, desc_key: str | None = None, locale: str = "tr", **fmt: object) -> discord.Embed:
    title = t(title_key, locale, **fmt)
    description = t(desc_key, locale, **fmt) if desc_key else None
    if EMBED_COLOR is None:
        return discord.Embed(title=title, description=description)
    return discord.Embed(title=title, description=description, color=EMBED_COLOR)


class NowPlayingView(discord.ui.View):
    """View with Pause/Resume, Skip, and Lyrics buttons for now playing track."""

    def __init__(self, guild_id: int, locale: str = "tr", is_paused: bool = False, timeout: float = 300.0) -> None:
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.locale = locale
        self.message: discord.Message | None = None

        # Create buttons dynamically with localized labels
        pause_label = t("buttons.resume" if is_paused else "buttons.pause", locale)
        pause_emoji = "▶️" if is_paused else "⏸️"
        pause_style = discord.ButtonStyle.success if is_paused else discord.ButtonStyle.primary

        self.pause_button = discord.ui.Button(
            emoji=pause_emoji,
            label=pause_label,
            style=pause_style,
            custom_id="pause_resume"
        )
        self.pause_button.callback = self._pause_resume_callback
        self.add_item(self.pause_button)

        skip_button = discord.ui.Button(
            emoji="⏭️",
            label=t("buttons.skip", locale),
            style=discord.ButtonStyle.secondary,
            custom_id="skip"
        )
        skip_button.callback = self._skip_callback
        self.add_item(skip_button)

        lyrics_button = discord.ui.Button(
            emoji="📝",
            label=t("buttons.lyrics", locale),
            style=discord.ButtonStyle.secondary,
            custom_id="lyrics"
        )
        lyrics_button.callback = self._lyrics_callback
        self.add_item(lyrics_button)

    def _update_pause_button(self, is_paused: bool) -> None:
        """Update pause button style and emoji based on state."""
        if is_paused:
            self.pause_button.emoji = "▶️"
            self.pause_button.label = t("buttons.resume", self.locale)
            self.pause_button.style = discord.ButtonStyle.success
        else:
            self.pause_button.emoji = "⏸️"
            self.pause_button.label = t("buttons.pause", self.locale)
            self.pause_button.style = discord.ButtonStyle.primary

    async def _pause_resume_callback(self, interaction: discord.Interaction) -> None:
        """Toggle pause/resume."""
        from .bot import players

        if self.guild_id not in players:
            await interaction.response.send_message("Not playing anything.", ephemeral=True)
            return

        player = players[self.guild_id]
        vc = player.voice_client

        if not vc:
            await interaction.response.send_message("Not connected to voice.", ephemeral=True)
            return

        if vc.is_playing():
            player.pause()
            self._update_pause_button(True)
            await interaction.response.edit_message(view=self)
        elif vc.is_paused():
            player.resume()
            self._update_pause_button(False)
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    async def _skip_callback(self, interaction: discord.Interaction) -> None:
        """Skip current track."""
        from .bot import players

        if self.guild_id not in players:
            await interaction.response.send_message("Not playing anything.", ephemeral=True)
            return

        player = players[self.guild_id]
        player.skip()
        await interaction.response.send_message("⏭️ Skipped.", ephemeral=True)

    async def _lyrics_callback(self, interaction: discord.Interaction) -> None:
        """Show lyrics for current track."""
        from .bot import players
        import aiohttp
        import logging

        if self.guild_id not in players:
            await interaction.response.send_message("Not playing anything.", ephemeral=True)
            return

        player = players[self.guild_id]
        if not player.current:
            await interaction.response.send_message("Not playing anything.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Extract artist and title
        title_parts = player.current.title.split(" - ", 1)
        if len(title_parts) == 2:
            artist, title = title_parts[0].strip(), title_parts[1].strip()
        else:
            artist, title = "", player.current.title.strip()

        # Fetch lyrics
        url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
        lyrics_text = None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        lyrics_text = data.get("lyrics")
        except Exception as e:
            logging.error("Lyrics fetch error: %s", e)

        if not lyrics_text:
            await interaction.followup.send(f"Lyrics not found for: {player.current.title}", ephemeral=True)
            return

        # Truncate if too long
        if len(lyrics_text) > 4000:
            lyrics_text = lyrics_text[:3997] + "..."

        embed = discord.Embed(
            title=f"📝 {player.current.title}",
            description=lyrics_text
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def on_timeout(self) -> None:
        """Disable buttons on timeout."""
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass
