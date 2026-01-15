# Spotify Setup Guide (Free)

To support Spotify links, Dje uses the Spotify Developer API via the Client Credentials flow. This is completely free.

You do not need Spotify Premium. Dje does not stream audio from Spotify (that is not allowed). It only fetches track metadata (artist/title) and then plays audio via YouTube.

## Step-by-step

### 1) Open the Spotify Developer Dashboard

1. Go to https://developer.spotify.com/dashboard
2. Sign in with your Spotify account (Free or Premium).
3. If prompted, accept the developer terms.

### 2) Create an app

1. Click **Create app**.
2. **App name**: `Dje` (or any name you prefer).
3. **App description**: optional.
4. **Redirect URI**: set `http://localhost:8888/callback`
   - Dje does not use this redirect, but Spotify requires at least one value.
5. Save the app.

### 3) Copy Client ID and Client Secret

1. Open your newly created app.
2. Go to **Settings**.
3. Copy **Client ID**.
4. Click **View client secret** and copy **Client Secret**.

### 4) Update your `.env`

In the project root, set:

```env
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
```

### 5) Restart the bot

After updating `.env`, restart Dje:

```bash
python -m dje
```

Spotify URLs should now work with `/play <spotify-url>`.
