import discord
from discord import Interaction

from .i18n import t

async def join_channel(interaction: Interaction, locale: str) -> None:
    """Handles joining the user's voice channel."""
    if not interaction.user or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(t("errors.guild_only", locale), ephemeral=True)
        return

    voice_state = interaction.user.voice
    if not voice_state or not voice_state.channel:
        await interaction.response.send_message(t("errors.user_not_in_voice", locale), ephemeral=True)
        return

    target_channel = voice_state.channel
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message(t("errors.guild_only", locale), ephemeral=True)
        return
        
    voice_client: discord.VoiceClient | None = guild.voice_client

    if voice_client:
        if voice_client.channel.id == target_channel.id:
            await interaction.response.send_message(
                t("voice.already_connected", locale, channel=target_channel.mention),
                ephemeral=True,
            )
            return
        
        await voice_client.move_to(target_channel)
        await interaction.response.send_message(t("voice.moved", locale, channel=target_channel.mention))
    else:
        await target_channel.connect()
        await interaction.response.send_message(t("voice.connected", locale, channel=target_channel.mention))

async def leave_channel(interaction: Interaction, locale: str) -> None:
    """Handles leaving the voice channel."""
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message(t("errors.guild_only", locale), ephemeral=True)
        return

    voice_client: discord.VoiceClient | None = guild.voice_client

    if not voice_client:
        await interaction.response.send_message(t("voice.not_connected", locale), ephemeral=True)
        return

    channel_name = voice_client.channel.name
    await voice_client.disconnect()
    await interaction.response.send_message(t("voice.disconnected", locale, channel=channel_name))
