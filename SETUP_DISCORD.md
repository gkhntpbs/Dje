# Discord Setup Guide

This guide walks through creating a Discord application + bot user for running Dje on your own server.

## 1) Create the application and bot

1. Open the Discord Developer Portal: https://discord.com/developers/applications
2. Create a new application.
3. In the application settings, create/add a bot user.
4. Copy the bot token and keep it private.

Set it in your `.env`:

```env
DISCORD_TOKEN=your_bot_token_here
```

## 2) Intents

Dje uses slash commands and voice features. It does not require privileged gateway intents for basic operation.

If you change the bot to read messages or member data later, you may need to enable additional intents accordingly.

## 3) Invite the bot to your server (OAuth2)

When generating an invite URL, include:

- Scopes:
  - `bot`
  - `applications.commands` (required for slash commands)
- Bot permissions (recommended minimum):
  - View Channels
  - Send Messages
  - Embed Links
  - Connect
  - Speak

You can generate the URL using the Developer Portal’s OAuth2 URL Generator.

If you use `permissions=0`, you must grant the required permissions via server roles/channel overrides after inviting.

## 4) Optional: speed up command registration during development

Discord global slash command updates can take a while to appear. Dje supports per-guild command sync for faster iteration.

1. Enable Developer Mode in Discord.
2. Right-click your server and copy its ID.
3. Set it in your `.env`:

```env
DISCORD_GUILD_ID=your_server_id_here
```

Restart the bot after changing this value.

## 5) Run Dje

From the project root:

```bash
python -m dje
```

Or use the provided scripts:

- macOS/Linux: `./setup.sh` then `./run.sh`
- Windows: `setup.bat` then `run.bat`

