import asyncio
import logging
import sys
import ssl
import discord
import aiohttp
from collections import deque
from discord import app_commands
from . import config
from .config import DISCORD_TOKEN, DISCORD_GUILD_ID
from . import voice, audio, youtube, player as player_module, spotify, settings, VERSION
from . import ui, ui_shortcuts
from .i18n import t, SUPPORTED_LOCALES
from . import network_health

# Global dictionary to hold GuildPlayer instances
# guild_id -> GuildPlayer
players: dict[int, player_module.GuildPlayer] = {}
last_shortcut_order: dict[int, list[str]] = {}

# Global network health monitor
net_health: network_health.NetworkHealth = None

def get_player(guild: discord.Guild) -> player_module.GuildPlayer:
    if guild.id not in players:
        # Default to the first text channel or system channel for updates if context unclear,
        # but commands will update the interaction_channel on use.
        # Ideally we update interaction_channel every time a command is used.
        players[guild.id] = player_module.GuildPlayer(guild.id, guild.voice_client.client if guild.voice_client else None, None) # Client is passed awkwardly here, will fix below
    return players[guild.id]

class DjeClient(discord.Client):
    def __init__(self) -> None:
        super().__init__(
            intents=discord.Intents.default()
        )
        self.tree = app_commands.CommandTree(self)
        self.cleanup_task = None

    async def setup_hook(self) -> None:
        """Called when the client is setting up. Event loop is available here."""
        # Apply WARP/VPN compatibility settings if needed
        if config.DISABLE_DISCORD_SSL_VERIFY:
            logging.warning(
                "SSL verification disabled for Discord connections. "
                "This is a workaround for WARP/VPN issues."
            )
            # The connector is already created by discord.py at this point,
            # so we'll handle SSL via the http module if needed

    async def on_ready(self) -> None:
        global net_health
        try:
            logging.info("Logged in as %s (ID: %s)", self.user, self.user.id)

            await player_module.cleanup_old_downloads()

            if net_health:
                await net_health.record_gateway_connect()
                await net_health.record_success()

            if DISCORD_GUILD_ID:
                guild = discord.Object(id=int(DISCORD_GUILD_ID))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logging.info(
                    "Synced %d command(s) to Guild ID: %s", len(synced), DISCORD_GUILD_ID
                )
            else:
                synced = await self.tree.sync()
                logging.info("Synced %d command(s) globally.", len(synced))
                logging.warning(
                    "Global sync can take up to 1 hour to appear. Add DISCORD_GUILD_ID to .env for instant updates."
                )

            # Start periodic cleanup task
            if self.cleanup_task is None:
                self.cleanup_task = asyncio.create_task(self.periodic_cleanup())
                logging.info("Periodic cleanup task started (every 5 minutes)")

        except Exception as e:
            logging.error("Failed to sync commands: %s", e)
            if net_health:
                await net_health.record_failure(e, "gateway")
    
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ) -> None:
        """Log voice state changes for the bot for debugging."""
        # Only log changes for the bot itself
        if member.id != self.user.id:
            return

        from . import audio_debug

        if before.channel != after.channel:
            if before.channel is None and after.channel is not None:
                logging.info("Voice: Connected to %s", after.channel.name)
                if audio_debug.is_debug_enabled():
                    logging.debug("Voice connection details: guild=%s, channel_id=%s",
                                  member.guild.name, after.channel.id)
            elif before.channel is not None and after.channel is None:
                logging.info("Voice: Disconnected from %s", before.channel.name)
            elif before.channel is not None and after.channel is not None:
                logging.info("Voice: Moved from %s to %s", before.channel.name, after.channel.name)

    async def periodic_cleanup(self) -> None:
        """Background task to clean up inactive downloads every 5 minutes."""
        await self.wait_until_ready()
        while not self.is_closed():
            await asyncio.sleep(5 * 60)  # Every 5 minutes
            try:
                # Check if any player is currently playing
                any_playing = any(
                    p.voice_client and p.voice_client.is_playing()
                    for p in players.values()
                )

                if any_playing:
                    logging.debug("Skipping cleanup - audio currently playing")
                    continue

                deleted = await player_module.cleanup_inactive_downloads(players)
                if deleted > 0:
                    logging.info("Periodic cleanup removed %d inactive files", deleted)

                # Also log current size
                size_mb = player_module.get_downloads_size_mb()
                if size_mb > 0:
                    logging.info("Downloads folder size: %.1f MB", size_mb)
            except Exception as e:
                logging.error("Cleanup error: %s", e)

def main() -> None:
    global net_health

    # Initialize network health monitor
    net_health = network_health.NetworkHealth(
        backoff_base_sec=config.NETWORK_BACKOFF_BASE_SEC,
        backoff_max_sec=config.NETWORK_BACKOFF_MAX_SEC,
        fail_window_sec=config.NETWORK_FAIL_WINDOW_SEC,
        fail_threshold=config.NETWORK_FAIL_THRESHOLD,
    )
    logging.info(
        "Network health monitor initialized (threshold: %d failures in %ds window)",
        config.NETWORK_FAIL_THRESHOLD,
        int(config.NETWORK_FAIL_WINDOW_SEC)
    )

    # Ensure opus is loaded before doing anything voice-related
    audio.load_opus_lib()
    logging.info("Launching Discord client")
    client = DjeClient()

    async def get_locale(interaction: discord.Interaction) -> str:
        if not interaction.guild_id:
            return "tr"
        settings_data = await settings.get_guild_settings(interaction.guild_id)
        return settings_data.locale

    async def send_message(
        interaction: discord.Interaction,
        content: str | None = None,
        *,
        ephemeral: bool = False,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
    ) -> None:
        kwargs: dict[str, object] = {"ephemeral": ephemeral}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if view is not None:
            kwargs["view"] = view

        if interaction.response.is_done():
            await interaction.followup.send(**kwargs)
        else:
            await interaction.response.send_message(**kwargs)

    def is_youtube_url(url: str) -> bool:
        return "youtube.com" in url or "youtu.be" in url

    async def handle_play(
        interaction: discord.Interaction,
        query: str,
        locale: str,
        send_info,
        send_error,
        *,
        enqueue_mode: str = "append",
    ) -> None:
        if not interaction.guild:
            await send_error(interaction, t("errors.guild_only", locale), ephemeral=True)
            return

        # 1. Ensure user is in voice
        if not interaction.user.voice or not interaction.user.voice.channel:
            await send_error(interaction, t("errors.user_not_in_voice", locale), ephemeral=True)
            return

        if not interaction.response.is_done():
            await interaction.response.defer()

        # 2. Ensure bot is connected
        target_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client
        if not voice_client:
            try:
                voice_client = await target_channel.connect()
            except Exception as e:
                await send_error(interaction, t("errors.connect_failed", locale, error=e))
                return
        elif voice_client.channel != target_channel:
            await voice_client.move_to(target_channel)

        # 3. Get or create Player
        if interaction.guild.id not in players:
            players[interaction.guild.id] = player_module.GuildPlayer(
                interaction.guild.id, client, interaction.channel
            )

        player = players[interaction.guild.id]
        player.interaction_channel = interaction.channel
        mode = enqueue_mode
        if mode == "insert_next":
            has_pending = (
                player.current is not None
                or player.override_queue
                or player.insert_next_queue
                or player.queue
            )
            if not has_pending:
                mode = "append"

        # 4. Check for Spotify
        spotify_info = spotify.parse_spotify_url(query)
        if spotify_info:
            sp_type, sp_id = spotify_info

            await send_info(interaction, t("spotify.processing", locale, type=sp_type))

            try:
                if sp_type == "track":
                    items, skipped, name = await spotify.resolve_track(sp_id)
                    origin_name = name
                elif sp_type == "playlist":
                    items, skipped, _, origin_name = await spotify.resolve_playlist(sp_id)
                elif sp_type == "album":
                    items, skipped, _, origin_name = await spotify.resolve_album(sp_id)
                else:
                    await send_error(interaction, t("errors.spotify_unsupported", locale))
                    return

                if not items:
                    await send_error(interaction, t("errors.spotify_no_playable", locale))
                    return

                await send_info(
                    interaction, t("spotify.preparing", locale, count=len(items))
                )

                # Resolve to YouTube Tracks
                resolved_tracks = []
                yt_failures = 0

                for item in items:
                    yt_query = item.to_youtube_query()
                    try:
                        # Use existing youtube resolver
                        track = await youtube.resolve(yt_query, interaction.user.display_name)
                        resolved_tracks.append(track)
                        # Small delay to be nice to YouTube
                        await asyncio.sleep(0.1)
                    except Exception:
                        yt_failures += 1

                if resolved_tracks:
                    await player.enqueue_items(resolved_tracks, mode=mode)
                queued_count = len(resolved_tracks)

                # Build summary message
                lines = []
                if mode == "insert_next":
                    lines.append(
                        t("queue.inserted_next_batch", locale, count=queued_count)
                    )
                else:
                    lines.append(
                        t("spotify.added_summary", locale, type=sp_type, name=origin_name)
                    )
                    lines.append(t("spotify.queued_count", locale, count=queued_count))

                if len(items) >= spotify.SPOTIFY_MAX_TRACKS:
                    lines[-1] += f" {t('spotify.limit', locale, limit=spotify.SPOTIFY_MAX_TRACKS)}"

                if skipped > 0:
                    lines.append(t("spotify.skipped", locale, count=skipped))
                if yt_failures > 0:
                    lines.append(t("spotify.yt_failures", locale, count=yt_failures))

                await send_info(interaction, "\n".join(lines))
                return

            except spotify.SpotifyNotConfiguredError:
                await send_error(interaction, t("errors.spotify_not_configured", locale))
                return
            except spotify.SpotifyError as e:
                if network_health.is_dns_error(e) or "network error" in str(e).lower():
                    await net_health.record_failure(e, "spotify_api")
                await send_error(interaction, t("errors.spotify_error", locale, error=e))
                return
            except Exception as e:
                await send_error(interaction, t("errors.unexpected", locale, error=e))
                return

        # 5. Check for playlist vs single track (YouTube)
        is_playlist = "list=" in query and ("youtube.com" in query or "youtu.be" in query)

        if is_playlist:
            try:
                tracks, skipped = await youtube.resolve_playlist(
                    query, interaction.user.display_name, limit=50
                )
                if not tracks:
                    await send_error(interaction, t("errors.playlist_no_tracks", locale))
                    return

                await player.enqueue_items(tracks, mode=mode)

                if mode == "insert_next":
                    lines = [t("queue.inserted_next_batch", locale, count=len(tracks))]
                else:
                    lines = [t("playlist.added", locale, count=len(tracks))]
                if len(tracks) >= 50:
                    lines[-1] += f" {t('playlist.limit', locale, limit=50)}"
                if skipped > 0:
                    lines.append(t("playlist.skipped", locale, count=skipped))

                await send_info(interaction, "\n".join(lines))
                return

            except youtube.YouTubeError as e:
                if network_health.is_dns_error(e) or "dns resolution failed" in str(e).lower():
                    await net_health.record_failure(e, "youtube_api")
                await send_error(interaction, t("errors.playlist_load_failed", locale, error=e))
                return

        try:
            track = await youtube.resolve(query, interaction.user.display_name)
        except youtube.YouTubeError as e:
            if network_health.is_dns_error(e) or "dns resolution failed" in str(e).lower():
                await net_health.record_failure(e, "youtube_api")
            await send_error(interaction, t("errors.track_not_found", locale, error=e))
            return

        # Download track BEFORE adding to queue (for seamless playback)
        try:
            await send_info(interaction, t("download.downloading", locale, title=track.title))
            filepath = await player_module.download_track(
                track.webpage_url, player_module.extract_video_id(track.webpage_url)
            )
            track.filepath = filepath
        except player_module.DurationLimitError as e:
            await send_error(
                interaction,
                t(
                    "errors.duration_limit",
                    locale,
                    minutes=e.minutes,
                    max_minutes=e.max_minutes,
                ),
            )
            return
        except Exception:
            await send_error(interaction, t("errors.download_failed_generic", locale))
            return

        # Enqueue (track has filepath)
        await player.enqueue_items([track], mode=mode)
        if mode == "insert_next":
            await send_info(
                interaction, t("queue.inserted_next", locale, title=track.title)
            )
        else:
            await send_info(interaction, t("queue.added", locale, title=track.title))

    async def play_shortcut(
        interaction: discord.Interaction,
        name_value: str,
        locale: str,
        *,
        confirm_ephemeral: bool,
        suppress_info: bool,
    ) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        shortcut_url = await settings.get_shortcut_url(interaction.guild_id, name_value)
        if not shortcut_url:
            await send_message(
                interaction, t("shortcuts.not_found", locale, name=name_value), ephemeral=True
            )
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await send_message(
                interaction, t("errors.user_not_in_voice", locale), ephemeral=True
            )
            return

        await send_message(
            interaction,
            t("shortcuts.play_started", locale, name=name_value),
            ephemeral=confirm_ephemeral,
        )

        async def send_info(interaction_obj, content: str, *, ephemeral: bool = False) -> None:
            if suppress_info:
                return
            await send_message(interaction_obj, content, ephemeral=ephemeral)

        async def send_error(interaction_obj, content: str, *, ephemeral: bool = False) -> None:
            await send_message(interaction_obj, content, ephemeral=confirm_ephemeral or ephemeral)

        await handle_play(interaction, shortcut_url, locale, send_info, send_error)

    async def play_shortcut_from_view(interaction: discord.Interaction, name_value: str) -> None:
        locale = await get_locale(interaction)
        await play_shortcut(
            interaction,
            name_value,
            locale,
            confirm_ephemeral=True,
            suppress_info=True,
        )

    async def send_shortcuts_list(interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        locale = await get_locale(interaction)
        items = await settings.list_shortcuts(interaction.guild_id)
        if not items:
            await send_message(interaction, t("shortcuts.list_empty", locale), ephemeral=True)
            return

        shown_items = items[:20]
        last_shortcut_order[interaction.guild_id] = [name for name, _ in shown_items]

        lines = [f"**{t('shortcuts.list_header', locale)}**"]
        for idx, (name, _) in enumerate(shown_items, 1):
            lines.append(f"{idx}. {name}")

        if len(items) > 20:
            lines.append(t("shortcuts.list_more", locale, count=len(items) - 20))

        content = "\n".join(lines)
        view = ui_shortcuts.ShortcutsView(shown_items, play_callback=play_shortcut_from_view)
        await send_message(interaction, content=content, view=view)
        try:
            view.message = await interaction.original_response()
        except Exception:
            pass

    class ShortcutsGroup(app_commands.Group):
        def __init__(self) -> None:
            super().__init__(name="shortcuts", description="Shortcut management")

    shortcuts_group = ShortcutsGroup()
    client.tree.add_command(shortcuts_group)

    @shortcuts_group.command(name="list", description="Show all shortcuts")
    async def shortcuts_list(interaction: discord.Interaction) -> None:
        await send_shortcuts_list(interaction)

    class SettingsGroup(app_commands.Group):
        def __init__(self) -> None:
            super().__init__(name="settings", description="Guild settings")

    settings_group = SettingsGroup()
    client.tree.add_command(settings_group)

    LOCALE_CHOICES = [
        app_commands.Choice(name="Turkce (tr)", value="tr"),
        app_commands.Choice(name="English (en)", value="en"),
    ]
    AUTODISC_CHOICES = [
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off"),
    ]

    async def set_language(interaction: discord.Interaction, locale: str) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        current_locale = await get_locale(interaction)
        locale_value = locale.strip().lower()
        if locale_value not in SUPPORTED_LOCALES:
            await send_message(
                interaction,
                t(
                    "settings.invalid_locale",
                    current_locale,
                    locales=", ".join(SUPPORTED_LOCALES),
                ),
                ephemeral=True,
            )
            return

        await settings.set_locale(interaction.guild_id, locale_value)
        await send_message(
            interaction,
            t("settings.locale_set", locale_value, new_locale=locale_value),
        )

    async def do_join(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)
        await voice.join_channel(interaction, locale)

    async def do_leave(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)
        if interaction.guild_id in players:
            player = players[interaction.guild_id]
            player.cancel_idle_disconnect()
            player.stop_warning_playback()
            await player.stop()
            del players[interaction.guild_id]
        await voice.leave_channel(interaction, locale)

    async def do_play(interaction: discord.Interaction, query: str) -> None:
        locale = await get_locale(interaction)

        async def send_info(
            interaction_obj, content: str, *, ephemeral: bool = False
        ) -> None:
            await send_message(interaction_obj, content, ephemeral=ephemeral)

        async def send_error(
            interaction_obj, content: str, *, ephemeral: bool = False
        ) -> None:
            await send_message(interaction_obj, content, ephemeral=ephemeral)

        await handle_play(interaction, query, locale, send_info, send_error)

    async def do_playnext(interaction: discord.Interaction, query: str) -> None:
        locale = await get_locale(interaction)

        async def send_info(
            interaction_obj, content: str, *, ephemeral: bool = False
        ) -> None:
            await send_message(interaction_obj, content, ephemeral=ephemeral)

        async def send_error(
            interaction_obj, content: str, *, ephemeral: bool = False
        ) -> None:
            await send_message(interaction_obj, content, ephemeral=ephemeral)

        await handle_play(
            interaction,
            query,
            locale,
            send_info,
            send_error,
            enqueue_mode="insert_next",
        )

    async def do_info(interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        locale = await get_locale(interaction)
        settings_data = await settings.get_guild_settings(interaction.guild_id)

        embed = ui.make_embed("info.embed_title", locale=locale)

        # Set bot avatar as thumbnail
        if client.user and client.user.avatar:
            embed.set_thumbnail(url=client.user.avatar.url)

        embed.description = t("info.description", locale)

        # Statistics
        embed.add_field(
            name=f"📊 {t('info.field_statistics', locale)}",
            value=(
                f"**{t('info.field_version', locale)}:** {VERSION}\n"
                f"**{t('info.field_locale', locale)}:** {settings_data.locale}\n"
                f"**{t('info.field_shortcuts', locale)}:** {len(settings_data.shortcuts)}\n"
                f"**{t('info.field_servers', locale)}:** {len(client.guilds)}"
            ),
            inline=False
        )

        # Current Settings
        autoplay = t("common.on", locale) if settings_data.autoplay_enabled else t("common.off", locale)
        shuffle = settings_data.shuffle_mode
        loop = settings_data.loop_mode

        embed.add_field(
            name=f"⚙️ {t('info.field_settings', locale)}",
            value=f"**Shuffle:** {shuffle}\n**Loop:** {loop}\n**Autoplay:** {autoplay}",
            inline=True
        )

        # Generate invite URL
        permissions = discord.Permissions(36779584)
        invite_url = discord.utils.oauth_url(client.user.id, permissions=permissions, scopes=["bot", "applications.commands"])

        # Links
        embed.add_field(
            name=f"🔗 {t('info.field_links', locale)}",
            value=(
                f"[{t('info.link_repo', locale)}](https://github.com/gkhntpbs/Dje)\n"
                f"[{t('info.link_support', locale)}](https://www.buymeacoffee.com/gkhntpbs)\n"
                f"[{t('info.link_invite', locale)}]({invite_url})"
            ),
            inline=True
        )

        embed.set_footer(text=t("info.footer_tip", locale))

        await send_message(interaction, embed=embed)

    async def do_skip(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)
        if not interaction.guild:
            await send_message(interaction, t("errors.guild_only", locale), ephemeral=True)
            return
        if interaction.guild.id in players:
            players[interaction.guild.id].skip()
            await send_message(interaction, t("playback.skipped", locale))
        else:
            await send_message(interaction, t("errors.nothing_playing", locale), ephemeral=True)

    async def do_prev(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)
        if not interaction.guild:
            await send_message(interaction, t("errors.guild_only", locale), ephemeral=True)
            return
        if interaction.guild.id not in players:
            await send_message(interaction, t("errors.not_connected", locale), ephemeral=True)
            return

        player = players[interaction.guild.id]
        prev_track = await player.play_previous()

        if prev_track:
            await send_message(
                interaction, t("playback.prev_playing", locale, title=prev_track.title)
            )
        else:
            await send_message(interaction, t("playback.no_previous", locale), ephemeral=True)

    async def do_pause(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)
        if not interaction.guild:
            await send_message(interaction, t("errors.guild_only", locale), ephemeral=True)
            return
        if interaction.guild.id not in players:
            await send_message(interaction, t("errors.not_connected", locale), ephemeral=True)
            return

        player = players[interaction.guild.id]
        if player.pause():
            await send_message(interaction, t("playback.paused", locale))
        else:
            vc = player.voice_client
            if vc and vc.is_paused():
                await send_message(
                    interaction, t("errors.already_paused", locale), ephemeral=True
                )
            elif not player.current:
                await send_message(
                    interaction, t("errors.nothing_playing", locale), ephemeral=True
                )
            else:
                await send_message(interaction, t("errors.pause_failed", locale), ephemeral=True)

    async def do_resume(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)
        if not interaction.guild:
            await send_message(interaction, t("errors.guild_only", locale), ephemeral=True)
            return
        if interaction.guild.id not in players:
            await send_message(interaction, t("errors.not_connected", locale), ephemeral=True)
            return

        player = players[interaction.guild.id]
        if player.resume():
            await send_message(interaction, t("playback.resumed", locale))
        else:
            vc = player.voice_client
            if vc and not vc.is_paused():
                await send_message(
                    interaction, t("errors.already_playing", locale), ephemeral=True
                )
            else:
                await send_message(interaction, t("errors.resume_failed", locale), ephemeral=True)

    async def do_stop(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)
        if not interaction.guild:
            await send_message(interaction, t("errors.guild_only", locale), ephemeral=True)
            return
        if interaction.guild.id in players:
            player = players[interaction.guild.id]
            await player.stop()
            deleted_count = await player_module.clear_all_downloads()
            if deleted_count > 0:
                logging.info("/stop removed %d files", deleted_count)

            voice_client = interaction.guild.voice_client
            if voice_client:
                await voice_client.disconnect()

            await send_message(interaction, t("playback.stopped", locale))
        else:
            await send_message(interaction, t("errors.nothing_playing", locale), ephemeral=True)

    async def do_queue(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)
        if not interaction.guild:
            await send_message(interaction, t("errors.guild_only", locale), ephemeral=True)
            return
        if interaction.guild.id not in players:
            await send_message(interaction, t("queue.empty", locale), ephemeral=True)
            return

        player = players[interaction.guild.id]

        if (
            not player.current
            and not player.override_queue
            and not player.insert_next_queue
            and not player.queue
            and not player.history
        ):
            await send_message(interaction, t("queue.empty", locale), ephemeral=True)
            return

        lines = []

        if player.history:
            last_prev = player.history[-1]
            lines.append(f"{t('queue.previous', locale)} {last_prev.title}")

        if player.current:
            status_key = (
                "queue.status_paused"
                if player.voice_client and player.voice_client.is_paused()
                else "queue.status_playing"
            )
            status = t(status_key, locale)
            lines.append(
                t(
                    "queue.now_playing",
                    locale,
                    status=status,
                    title=player.current.title,
                    requested_by=player.current.requested_by,
                )
            )

        q_list = (
            list(player.override_queue)
            + list(player.insert_next_queue)
            + list(player.queue)
        )
        if q_list:
            lines.append(f"\n{t('queue.up_next', locale)}")
            for i, track in enumerate(q_list[:10], 1):
                lines.append(f"{i}. {track.title}")
            if len(q_list) > 10:
                lines.append(t("queue.more", locale, count=len(q_list) - 10))
        else:
            lines.append(f"\n{t('queue.none', locale)}")

        await send_message(interaction, "\n".join(lines))

    async def do_shuffle(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)
        if not interaction.guild:
            await send_message(interaction, t("errors.guild_only", locale), ephemeral=True)
            return
        if interaction.guild.id not in players:
            await send_message(interaction, t("errors.not_connected", locale), ephemeral=True)
            return

        player = players[interaction.guild.id]
        settings_data = await settings.get_guild_settings(interaction.guild.id)

        # Apply shuffle to current queue
        if settings_data.shuffle_mode != "none":
            await player.apply_shuffle()
            count = len(player.queue)
            key = f"shuffle.enabled_{settings_data.shuffle_mode}"
            await send_message(
                interaction,
                f"{t(key, locale)}\n{t('shuffle.queue_shuffled', locale, count=count)}"
            )
        else:
            await send_message(interaction, t("shuffle.disabled", locale))

    async def do_loop(interaction: discord.Interaction, mode: str) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        locale = await get_locale(interaction)
        mode_value = mode.strip().lower()

        if mode_value not in ("off", "queue", "single"):
            await send_message(interaction, t("settings.loop_invalid", locale), ephemeral=True)
            return

        # Map "off" to "none" for internal storage
        internal_mode = "none" if mode_value == "off" else mode_value
        await settings.set_loop_mode(interaction.guild_id, internal_mode)

        # Update player state
        if interaction.guild.id in players:
            player = players[interaction.guild.id]
            # Snapshot queue if switching to queue loop
            if internal_mode == "queue" and player.queue:
                player.original_queue_snapshot = list(player.queue)

        key = f"loop.enabled_{mode_value}" if mode_value != "off" else "loop.disabled"
        await send_message(interaction, t(key, locale))

    async def do_settings_shuffle(interaction: discord.Interaction, mode: str) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        locale = await get_locale(interaction)

        if mode not in ("none", "full", "smart"):
            await send_message(interaction, t("settings.shuffle_invalid", locale), ephemeral=True)
            return

        await settings.set_shuffle_mode(interaction.guild_id, mode)
        await send_message(interaction, t("settings.shuffle_set", locale, mode=mode))

    async def do_settings_loop(interaction: discord.Interaction, mode: str) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        locale = await get_locale(interaction)

        if mode not in ("none", "queue", "single"):
            await send_message(interaction, t("settings.loop_invalid", locale), ephemeral=True)
            return

        await settings.set_loop_mode(interaction.guild_id, mode)

        # Update player snapshot if switching to queue loop
        if mode == "queue" and interaction.guild.id in players:
            player = players[interaction.guild.id]
            if player.queue:
                player.original_queue_snapshot = list(player.queue)

        await send_message(interaction, t("settings.loop_set", locale, mode=mode))

    async def do_settings_autodisconnect(interaction: discord.Interaction, state: str) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return
        locale = await get_locale(interaction)
        enabled = state.strip().lower() == "on"
        await settings.set_auto_disconnect_enabled(interaction.guild_id, enabled)

        player = players.get(interaction.guild_id)
        if player:
            if enabled:
                if player.is_idle():
                    await player.schedule_idle_disconnect()
            else:
                player.cancel_idle_disconnect()
                player.stop_warning_playback()

        key = "settings.autodisc.enabled_on" if enabled else "settings.autodisc.enabled_off"
        await send_message(interaction, t(key, locale))

    async def do_settings_autodisconnect_minutes(
        interaction: discord.Interaction, minutes: int
    ) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return
        locale = await get_locale(interaction)
        if minutes < 20 or minutes > 360:
            await send_message(
                interaction,
                t("settings.autodisc.minutes_invalid", locale, min=20, max=360),
                ephemeral=True,
            )
            return

        await settings.set_auto_disconnect_minutes(interaction.guild_id, minutes)
        settings_data = await settings.get_guild_settings(interaction.guild_id)

        player = players.get(interaction.guild_id)
        if player:
            if settings_data.auto_disconnect_enabled and player.is_idle():
                await player.schedule_idle_disconnect()

        await send_message(
            interaction, t("settings.autodisc.minutes_set", locale, minutes=minutes)
        )

    async def do_settings_show(interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return
        locale = await get_locale(interaction)
        settings_data = await settings.get_guild_settings(interaction.guild_id)
        enabled_text = (
            t("common.on", locale)
            if settings_data.auto_disconnect_enabled
            else t("common.off", locale)
        )

        autoplay_text = t("common.on", locale) if settings_data.autoplay_enabled else t("common.off", locale)
        warning_enabled_text = t("common.on", locale) if settings_data.auto_disconnect_warning_enabled else t("common.off", locale)
        lines = [
            f"**Language:** {settings_data.locale}",
            f"**Shuffle:** {settings_data.shuffle_mode}",
            f"**Loop:** {settings_data.loop_mode}",
            f"**Autoplay:** {autoplay_text}",
            f"**Auto-disconnect:** {enabled_text}",
            f"**Timeout:** {settings_data.auto_disconnect_minutes} min",
            f"**Warning time:** {settings_data.auto_disconnect_warn_minutes} min before disconnect",
            f"**Warning audio:** {warning_enabled_text}",
        ]
        await send_message(interaction, "\n".join(lines))

    async def do_warn_test(interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return
        locale = await get_locale(interaction)
        if not interaction.user.voice or not interaction.user.voice.channel:
            await send_message(
                interaction, t("errors.user_not_in_voice", locale), ephemeral=True
            )
            return

        target_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client
        if not voice_client:
            try:
                voice_client = await target_channel.connect()
            except Exception as e:
                await send_message(
                    interaction, t("errors.connect_failed", locale, error=e)
                )
                return
        elif voice_client.channel != target_channel:
            await voice_client.move_to(target_channel)

        if interaction.guild.id not in players:
            players[interaction.guild.id] = player_module.GuildPlayer(
                interaction.guild.id, client, interaction.channel
            )
        player = players[interaction.guild.id]
        player.interaction_channel = interaction.channel

        if not player.is_idle():
            await send_message(
                interaction, t("autodisc.warn_test_not_idle", locale), ephemeral=True
            )
            return

        settings_data = await settings.get_guild_settings(interaction.guild_id)
        await player._play_warning_clip(settings_data.auto_disconnect_warn_minutes)
        await send_message(interaction, t("autodisc.warn_test_started", locale))

    @client.tree.command(name="join", description="Join the voice channel")
    async def join(interaction: discord.Interaction) -> None:
        await do_join(interaction)

    @client.tree.command(name="leave", description="Leave the voice channel")
    async def leave(interaction: discord.Interaction) -> None:
        await do_leave(interaction)

    @client.tree.command(
        name="warn_test", description="Play the auto-disconnect warning audio"
    )
    async def warn_test(interaction: discord.Interaction) -> None:
        await do_warn_test(interaction)



    @client.tree.command(name="play", description="Play music (YouTube)")
    async def play(interaction: discord.Interaction, query: str) -> None:
        await do_play(interaction, query)

    @client.tree.command(name="playnext", description="Insert as next in queue")
    async def playnext(interaction: discord.Interaction, query: str) -> None:
        await do_playnext(interaction, query)

    @settings_group.command(name="autodisconnect", description="Toggle idle auto-disconnect")
    @app_commands.choices(state=AUTODISC_CHOICES)
    async def settings_autodisconnect(
        interaction: discord.Interaction, state: str
    ) -> None:
        await do_settings_autodisconnect(interaction, state)

    @settings_group.command(
        name="autodisconnect_minutes", description="Set auto-disconnect timeout"
    )
    async def settings_autodisconnect_minutes(
        interaction: discord.Interaction, minutes: int
    ) -> None:
        await do_settings_autodisconnect_minutes(interaction, minutes)

    @settings_group.command(name="show", description="Show current settings")
    async def settings_show(interaction: discord.Interaction) -> None:
        await do_settings_show(interaction)

    @settings_group.command(name="shuffle", description="Set shuffle mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="none"),
        app_commands.Choice(name="Full Random", value="full"),
        app_commands.Choice(name="Smart Shuffle", value="smart"),
    ])
    async def settings_shuffle(interaction: discord.Interaction, mode: str) -> None:
        await do_settings_shuffle(interaction, mode)

    @settings_group.command(name="loop", description="Set loop mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="none"),
        app_commands.Choice(name="Queue Loop", value="queue"),
        app_commands.Choice(name="Single Track", value="single"),
    ])
    async def settings_loop(interaction: discord.Interaction, mode: str) -> None:
        await do_settings_loop(interaction, mode)

    @settings_group.command(name="autoplay", description="Toggle autoplay mode")
    @app_commands.choices(state=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off"),
    ])
    async def settings_autoplay(interaction: discord.Interaction, state: str) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        locale = await get_locale(interaction)
        enabled = state.strip().lower() == "on"
        await settings.set_autoplay_enabled(interaction.guild_id, enabled)

        key = "autoplay.enabled" if enabled else "autoplay.disabled"
        await send_message(interaction, t(key, locale))

    @settings_group.command(name="language", description="Set server language")
    @app_commands.choices(locale=LOCALE_CHOICES)
    async def settings_language(interaction: discord.Interaction, locale: app_commands.Choice[str]) -> None:
        await set_language(interaction, locale.value)

    @settings_group.command(name="autodisconnect_warning", description="Toggle auto-disconnect warning audio")
    @app_commands.choices(state=AUTODISC_CHOICES)
    async def settings_autodisconnect_warning(interaction: discord.Interaction, state: str) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        locale = await get_locale(interaction)
        enabled = state.strip().lower() == "on"
        await settings.set_auto_disconnect_warning_enabled(interaction.guild_id, enabled)

        key = "settings.autodisc.warning_on" if enabled else "settings.autodisc.warning_off"
        await send_message(interaction, t(key, locale))

    @shortcuts_group.command(name="add", description="Add a shortcut")
    async def shortcuts_add(interaction: discord.Interaction, name: str, url: str) -> None:
        await do_shortcuts_add(interaction, name, url)

    async def do_shortcuts_add(
        interaction: discord.Interaction, name: str, url: str
    ) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        locale = await get_locale(interaction)
        name_value = name.strip()
        url_value = url.strip()
        if len(name_value) < 2 or len(name_value) > 32:
            await send_message(interaction, t("shortcuts.invalid_name", locale), ephemeral=True)
            return

        if await settings.get_shortcut_url(interaction.guild_id, name_value):
            await send_message(interaction, t("shortcuts.duplicate", locale), ephemeral=True)
            return

        if not (spotify.parse_spotify_url(url_value) or is_youtube_url(url_value)):
            await send_message(interaction, t("shortcuts.invalid_url", locale), ephemeral=True)
            return

        await settings.add_shortcut(interaction.guild_id, name_value, url_value)
        await send_message(interaction, t("shortcuts.added", locale, name=name_value))

    @shortcuts_group.command(name="remove", description="Remove a shortcut")
    async def shortcuts_remove(interaction: discord.Interaction, name: str) -> None:
        await do_shortcuts_remove(interaction, name)

    async def do_shortcuts_remove(interaction: discord.Interaction, name: str) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        locale = await get_locale(interaction)
        name_value = name.strip()
        if not await settings.get_shortcut_url(interaction.guild_id, name_value):
            await send_message(
                interaction, t("shortcuts.not_found", locale, name=name_value), ephemeral=True
            )
            return

        await settings.remove_shortcut(interaction.guild_id, name_value)
        await send_message(interaction, t("shortcuts.removed", locale, name=name_value))

    @shortcuts_group.command(name="play", description="Play a shortcut")
    async def shortcuts_play(interaction: discord.Interaction, name: str) -> None:
        await do_shortcuts_play(interaction, name)

    async def do_shortcuts_play(interaction: discord.Interaction, name: str) -> None:
        if not interaction.guild_id:
            await send_message(interaction, t("errors.guild_only", "tr"), ephemeral=True)
            return

        locale = await get_locale(interaction)
        name_value = name.strip()
        if name_value.isdigit():
            existing = await settings.get_shortcut_url(interaction.guild_id, name_value)
            if not existing:
                order = last_shortcut_order.get(interaction.guild_id)
                if not order:
                    await send_message(
                        interaction,
                        t("shortcuts.playnum_missing_list", locale),
                        ephemeral=True,
                    )
                    return
                number = int(name_value)
                if number < 1 or number > len(order):
                    await send_message(
                        interaction,
                        t("shortcuts.playnum_out_of_range", locale, max=len(order)),
                        ephemeral=True,
                    )
                    return
                name_value = order[number - 1]
        await play_shortcut(
            interaction,
            name_value,
            locale,
            confirm_ephemeral=False,
            suppress_info=False,
        )

    @client.tree.command(name="info", description="Bot information")
    async def info(interaction: discord.Interaction) -> None:
        await do_info(interaction)

    @client.tree.command(name="skip", description="Skip the current track")
    async def skip(interaction: discord.Interaction) -> None:
        await do_skip(interaction)

    @client.tree.command(name="next", description="Play the next track")
    async def next_track(interaction: discord.Interaction) -> None:
        await do_skip(interaction)

    @client.tree.command(name="prev", description="Play the previous track")
    async def prev(interaction: discord.Interaction) -> None:
        await do_prev(interaction)

    @client.tree.command(name="pause", description="Pause playback")
    async def pause(interaction: discord.Interaction) -> None:
        await do_pause(interaction)

    @client.tree.command(name="resume", description="Resume playback")
    async def resume(interaction: discord.Interaction) -> None:
        await do_resume(interaction)

    @client.tree.command(name="stop", description="Stop playback and clear the queue")
    async def stop(interaction: discord.Interaction) -> None:
        await do_stop(interaction)

    @client.tree.command(name="queue", description="Show the queue")
    async def queue(interaction: discord.Interaction) -> None:
        await do_queue(interaction)

    @client.tree.command(name="shuffle", description="Apply shuffle to queue")
    async def shuffle(interaction: discord.Interaction) -> None:
        await do_shuffle(interaction)

    @client.tree.command(name="loop", description="Set loop mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Queue", value="queue"),
        app_commands.Choice(name="Single", value="single"),
    ])
    async def loop_cmd(interaction: discord.Interaction, mode: str) -> None:
        await do_loop(interaction, mode)

    @client.tree.command(name="autoplay", description="Toggle autoplay mode")
    @app_commands.choices(state=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off"),
    ])
    async def autoplay_cmd(interaction: discord.Interaction, state: str) -> None:
        if not interaction.guild_id:
            locale = await get_locale(interaction)
            await send_message(interaction, t("errors.guild_only", locale), ephemeral=True)
            return

        locale = await get_locale(interaction)
        enabled = state.strip().lower() == "on"
        await settings.set_autoplay_enabled(interaction.guild_id, enabled)

        key = "autoplay.enabled" if enabled else "autoplay.disabled"
        await send_message(interaction, t(key, locale))

    @client.tree.command(name="netinfo", description="Show network health diagnostics")
    async def netinfo(interaction: discord.Interaction) -> None:
        """Display network health status and troubleshooting info."""
        locale = await get_locale(interaction)
        await interaction.response.defer(ephemeral=True)

        try:
            stats = await net_health.get_stats()
            diagnostics = net_health.get_diagnostics()

            # Build status message
            lines = []

            # State indicator
            state_emoji = {
                network_health.NetworkState.OK: "✅",
                network_health.NetworkState.DEGRADED: "⚠️",
                network_health.NetworkState.OFFLINE: "🔴"
            }
            emoji = state_emoji.get(stats.state, "❓")
            lines.append(f"{emoji} **Network Status:** {stats.state.value.upper()}")
            lines.append("")

            # Statistics
            lines.append("**Statistics:**")
            lines.append(f"• Consecutive failures: {stats.consecutive_failures}")
            lines.append(f"• Total failures: {stats.total_failures}")

            if stats.last_success_time:
                seconds_ago = diagnostics.get("seconds_since_success", 0)
                if seconds_ago < 60:
                    time_str = f"{seconds_ago}s ago"
                elif seconds_ago < 3600:
                    time_str = f"{seconds_ago // 60}m ago"
                else:
                    time_str = f"{seconds_ago // 3600}h ago"
                lines.append(f"• Last success: {time_str}")

            if stats.gateway_connect_time:
                seconds_ago = diagnostics.get("seconds_since_gateway_connect", 0)
                if seconds_ago < 60:
                    time_str = f"{seconds_ago}s ago"
                elif seconds_ago < 3600:
                    time_str = f"{seconds_ago // 60}m ago"
                else:
                    time_str = f"{seconds_ago // 3600}h ago"
                lines.append(f"• Discord gateway: Connected {time_str}")

            if stats.event_loop_lag_detected:
                lines.append("⚠️ Event loop lag detected")

            # Recent failures by type
            if "recent_failure_types" in diagnostics and diagnostics["recent_failure_types"]:
                lines.append("")
                lines.append("**Recent Failures (last 2 minutes):**")
                for error_type, count in diagnostics["recent_failure_types"].items():
                    lines.append(f"• {error_type}: {count}")

            # Last failure message
            if stats.last_failure_message:
                lines.append("")
                lines.append("**Last Error:**")
                # Truncate long error messages
                error_msg = stats.last_failure_message
                if len(error_msg) > 200:
                    error_msg = error_msg[:200] + "..."
                lines.append(f"```{error_msg}```")

            # WARP troubleshooting tips if network is not OK
            if stats.state != network_health.NetworkState.OK:
                lines.append("")
                lines.append("**Troubleshooting Tips for WARP/VPN:**")
                tips = network_health.get_warp_troubleshooting_tips()
                for tip in tips[:5]:  # Show first 5 tips
                    lines.append(tip)

            # Audio statistics section
            from . import audio_debug
            audio_stats = audio_debug.get_stats()
            lines.append("")
            lines.append("**Audio Statistics:**")
            lines.append(f"• Tracks played: {audio_stats['tracks_played']}")
            lines.append(f"• Tracks failed: {audio_stats['tracks_failed']}")
            lines.append(f"• FFmpeg retries: {audio_stats['ffmpeg_retries']}")
            if audio_stats['avg_download_time'] > 0:
                lines.append(f"• Avg download time: {audio_stats['avg_download_time']}s")
            debug_status = "enabled" if audio_stats['debug_enabled'] else "disabled"
            lines.append(f"• Debug mode: {debug_status}")

            # Show recent audio errors if any
            if audio_stats['recent_errors_by_type']:
                lines.append("")
                lines.append("**Recent Audio Errors (last 5 min):**")
                for error_type, count in audio_stats['recent_errors_by_type'].items():
                    lines.append(f"• {error_type}: {count}")

            message = "\n".join(lines)

            # Send as ephemeral message
            await interaction.followup.send(message, ephemeral=True)

        except Exception as e:
            logging.error("Error in netinfo command: %s", e)
            await interaction.followup.send(
                f"❌ Failed to retrieve network info: {e}",
                ephemeral=True
            )

    @client.tree.command(name="help", description="Show all available commands")
    async def help_cmd(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)
        embed = ui.make_embed("help.title", locale=locale)

        embed.add_field(name="🎵 " + t("help.playback", locale), value=t("help.playback_desc", locale), inline=False)
        embed.add_field(name="📋 " + t("help.queue", locale), value=t("help.queue_desc", locale), inline=False)
        embed.add_field(name="⚙️ " + t("help.settings", locale), value=t("help.settings_desc", locale), inline=False)
        embed.add_field(name="⭐ " + t("help.shortcuts", locale), value=t("help.shortcuts_desc", locale), inline=False)
        embed.add_field(name="🔊 " + t("help.voice", locale), value=t("help.voice_desc", locale), inline=False)
        embed.add_field(name="ℹ️ " + t("help.info", locale), value=t("help.info_desc", locale), inline=False)

        await send_message(interaction, embed=embed)

    @client.tree.command(name="clear", description="Clear all upcoming tracks from queue")
    async def clear(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)
        if not interaction.guild or interaction.guild.id not in players:
            await send_message(interaction, t("queue.nothing_to_clear", locale), ephemeral=True)
            return

        player = players[interaction.guild.id]
        count = len(player.override_queue) + len(player.insert_next_queue) + len(player.queue)

        if count == 0:
            await send_message(interaction, t("queue.nothing_to_clear", locale), ephemeral=True)
            return

        player.override_queue.clear()
        player.insert_next_queue.clear()
        player.queue.clear()

        await send_message(interaction, t("queue.cleared", locale, count=count))

    @client.tree.command(name="remove", description="Remove a track from queue by position")
    async def remove(interaction: discord.Interaction, position: int) -> None:
        locale = await get_locale(interaction)
        if not interaction.guild or interaction.guild.id not in players:
            await send_message(interaction, t("queue.empty", locale), ephemeral=True)
            return

        player = players[interaction.guild.id]
        queue_list = list(player.override_queue) + list(player.insert_next_queue) + list(player.queue)

        if position < 1 or position > len(queue_list):
            await send_message(interaction, t("queue.invalid_position", locale, max=len(queue_list)), ephemeral=True)
            return

        removed_track = queue_list[position - 1]

        # Remove from appropriate queue (override → insert_next → main)
        idx = position - 1
        override_len = len(player.override_queue)
        insert_next_len = len(player.insert_next_queue)

        if idx < override_len:
            temp = list(player.override_queue)
            temp.pop(idx)
            player.override_queue = deque(temp)
        elif idx < override_len + insert_next_len:
            temp = list(player.insert_next_queue)
            temp.pop(idx - override_len)
            player.insert_next_queue = deque(temp)
        else:
            temp = list(player.queue)
            temp.pop(idx - override_len - insert_next_len)
            player.queue = deque(temp)

        await send_message(interaction, t("queue.removed", locale, title=removed_track.title))

    def format_duration(seconds: float) -> str:
        """Format seconds as MM:SS"""
        total_seconds = int(seconds)
        minutes = total_seconds // 60
        secs = total_seconds % 60
        return f"{minutes}:{secs:02d}"

    @client.tree.command(name="timestamp", description="Show current track timeline")
    async def timestamp(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)

        if not interaction.guild or interaction.guild.id not in players:
            await send_message(interaction, t("timestamp.nothing_playing", locale), ephemeral=True)
            return

        player = players[interaction.guild.id]
        if not player.current or not player.current.duration:
            await send_message(interaction, t("timestamp.nothing_playing", locale), ephemeral=True)
            return

        # Get current position
        current_pos = player.get_current_position()
        if current_pos is None:
            current_pos = 0

        # Format times
        current_str = format_duration(int(current_pos))
        total_str = format_duration(player.current.duration)

        # Create progress bar (30 characters wide)
        bar_length = 30
        progress = min(current_pos / player.current.duration, 1.0) if player.current.duration > 0 else 0
        filled = int(bar_length * progress)

        # Build progress bar: ━━━━●─────
        bar = "━" * filled + "●" + "─" * (bar_length - filled - 1)

        embed = ui.make_embed("timestamp.title", locale=locale)
        embed.add_field(
            name=t("timestamp.current_track", locale),
            value=player.current.title,
            inline=False
        )
        embed.add_field(
            name=t("timestamp.progress", locale),
            value=f"`{current_str} {bar} {total_str}`",
            inline=False
        )

        await send_message(interaction, embed=embed)

    async def fetch_lyrics(artist: str, title: str) -> str | None:
        """Fetch lyrics from lyrics.ovh API"""
        import aiohttp
        url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("lyrics")
        except Exception as e:
            logging.error("Lyrics fetch error: %s", e)
        return None

    @client.tree.command(name="lyrics", description="Show lyrics for current track")
    async def lyrics(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)

        if not interaction.guild or interaction.guild.id not in players:
            await send_message(interaction, t("lyrics.nothing_playing", locale), ephemeral=True)
            return

        player = players[interaction.guild.id]
        if not player.current:
            await send_message(interaction, t("lyrics.nothing_playing", locale), ephemeral=True)
            return

        await interaction.response.defer()

        # Extract artist and title (usually "Artist - Title")
        title_parts = player.current.title.split(" - ", 1)
        if len(title_parts) == 2:
            artist, title = title_parts[0].strip(), title_parts[1].strip()
        else:
            artist, title = "", player.current.title.strip()

        lyrics_text = await fetch_lyrics(artist, title)

        if not lyrics_text:
            await send_message(interaction, t("lyrics.not_found", locale, title=player.current.title), ephemeral=True)
            return

        # Truncate if too long (Discord embed limit: 4096 chars)
        if len(lyrics_text) > 4000:
            lyrics_text = lyrics_text[:3997] + "..."

        embed = ui.make_embed("lyrics.title", locale=locale, title=player.current.title)
        embed.description = lyrics_text

        await send_message(interaction, embed=embed)

    @client.tree.command(name="invite", description="Get bot invite link")
    async def invite(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)

        # Required permissions: Send Messages, Connect, Speak, Use Voice Activity, Embed Links, Read Message History
        # Permission value: 36779584
        permissions = discord.Permissions(36779584)

        invite_url = discord.utils.oauth_url(
            client.user.id,
            permissions=permissions,
            scopes=["bot", "applications.commands"]
        )

        embed = ui.make_embed("invite.title", locale=locale)
        embed.description = t("invite.description", locale)
        embed.add_field(name="🔗 Link", value=f"[{t('invite.click_here', locale)}]({invite_url})", inline=False)

        await send_message(interaction, embed=embed)

    @client.tree.command(name="support", description="Support the developer")
    async def support(interaction: discord.Interaction) -> None:
        locale = await get_locale(interaction)

        embed = ui.make_embed("support.title", locale=locale)
        embed.description = t("support.description", locale)
        embed.add_field(
            name="☕ Buy Me a Coffee",
            value="https://www.buymeacoffee.com/gkhntpbs",
            inline=False
        )
        embed.set_thumbnail(url="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png")

        await send_message(interaction, embed=embed)

    client.run(DISCORD_TOKEN)



if __name__ == "__main__":
    main()
