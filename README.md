# Ampache2Mastodon

Post your currently playing songs from Ampache to Mastodon, Pixelfed, and cross-boost to multiple accounts.

---

## Overview

This project contains two scripts that share a common codebase and state file:

| Script | Purpose | Trigger |
|--------|---------|---------|
| `now_playing_post.py` | Manual on-demand posts | User request ("make a now playing post") |
| `tune_tuesday.py` | Scheduled #TuneTuesday posts | Cron job every Tuesday |

**Both scripts:**
- Fetch recent songs from Ampache (your music server)
- Skip songs that have already been posted (tracked in shared state file)
- Fetch lyrics from Ampache or fallback API
- Post to Mastodon with album art
- Cross-post to Pixelfed
- Boost and favourite on secondary accounts
- Use the same formatting style (country flags, genre tags, lyrics blockquote)

---

## How It Works

### The Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AMPACHE SERVER                              │
│                     (your music library)                            │
│                                                                     │
│  You listen to music → Ampache records play history                 │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           SCRIPT                                     │
│                                                                      │
│  1. Authenticate with Ampache (using service account)              │
│  2. Fetch recent songs played by target user                        │
│  3. Check posted_songs_state.json → skip if already posted          │
│  4. Skip if no album art available                                   │
│  5. Fetch lyrics from Ampache (if present) or Lyrics API            │
│  6. Download album art to temp file                                  │
│  7. Build post text with formatting                                  │
│  8. Post to Mastodon → get URL                                       │
│  9. Post to Pixelfed (same image, same text)                        │
│  10. Search for post on other accounts → boost + favourite          │
│  11. Save song ID to state file                                      │
│  12. Cleanup temp files                                               │
└─────────────────────────────────────────────────────────────────────┘
```

### Ampache Authentication

The scripts use a **service account** pattern:

- **`AMPACHE_USER`**: Authenticates with Ampache API. This is an admin/service account with API access.
- **`AMPACHE_TARGET_USER`**: The actual user whose play history is fetched.

This separation allows the script to access Ampache without needing the target user's direct credentials.

### Authentication Flow

```
1. Generate SHA256 hash of password
2. Concatenate: timestamp + password_hash
3. Generate SHA256 of that concatenation
4. Call /handshake endpoint with user, timestamp, auth hash
5. Receive session token
6. Use token for all subsequent API calls
```

---

## File Structure

```
Ampache2Mastodon/
├── .env                    # Secrets and configuration (gitignored)
├── .env-example            # Template for .env
├── .gitignore              # Git ignore rules
├── README.md               # This file
├── ampache2mastodon.py     # Shared library (common functions)
├── posted_songs_state.json # Shared state file (gitignored)
├── now_playing_post.py     # Manual on-demand posts
└── tune_tuesday.py         # Scheduled Tuesday posts
```

---

## Configuration

### The `.env` File

Copy `.env-example` to `.env` and fill in your values:

```bash
cp .env-example .env
```

#### Ampache Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `AMPACHE_SERVER` | Your Ampache server URL | `https://music.example.com` |
| `AMPACHE_USER` | Service account for API auth | `bot` |
| `AMPACHE_PASSWORD` | Password for the service account | `your-password` |
| `AMPACHE_TARGET_USER` | User whose plays to fetch | `your-username` |

#### Mastodon Settings (Main Account)

| Variable | Description | Example |
|----------|-------------|---------|
| `MASTODON_INSTANCE` | Your Mastodon server | `https://mastodon.social` |
| `MASTODON_TOKEN_FILE` | Path to API token file | `~/.config/mastodon/token` |

The token file should contain just the access token (one line, no newline):

```
your-mastodon-access-token-here
```

To create a token: Settings → Development → New Application → Read + Write scopes

#### Pixelfed Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `PIXELFED_INSTANCE` | Pixelfed server | `https://pixelfed.social` |
| `PIXELFED_TOKEN_FILE` | Path to Pixelfed token file | `~/.config/pixelfed/token` |

#### Cross-Post Accounts (Boost + Favourite)

These accounts will search for your main post and boost/favourite it:

| Variable | Description | Example |
|----------|-------------|---------|
| `FOSTODON_INSTANCE` | Secondary Mastodon server | `https://fosstodon.org` |
| `FOSTODON_USERNAME` | Your username on that server | `your-username` |
| `FOSTODON_TOKEN_FILE` | Path to token file | `~/.config/fosstodon/token` |
| `MASTODON_SOCIAL_INSTANCE` | Another Mastodon server | `https://mastodon.social` |
| `MASTODON_SOCIAL_USERNAME` | Your username | `your-username` |
| `MASTODON_SOCIAL_TOKEN_FILE` | Path to token file | `~/.config/mastodon_social/token` |

#### Lyrics API

| Variable | Description | Example |
|----------|-------------|---------|
| `LYRICS_API_URL` | Lyrics lookup API endpoint | `https://lyrics.example.com/api/lyrics` |

The API should accept `?artist_name=X&track_name=Y` and return JSON with a `plain_lyrics` or `lyrics` field.

#### State File

| Variable | Description | Default |
|----------|-------------|---------|
| `STATE_FILE` | Filename for tracking posted songs | `posted_songs_state.json` |

This file is relative to the script directory. It's shared between both scripts to prevent duplicate posts.

---

## State File Format

`posted_songs_state.json`:

```json
{
  "posted_songs": ["12345", "12346", "..."],
  "last_post": "2026-03-18T12:00:00.000000"
}
```

- `posted_songs`: Array of Ampache song IDs that have been posted
- `last_post`: ISO timestamp of last successful post

The state file prevents the same song from being posted twice. Both scripts read/write to the same file, so a song posted manually won't be posted again on TuneTuesday.

---

## Post Format

The scripts generate posts in this format:

```
🎸 Now Playing

**Artist — "Title"**
*from Album (Year)*

> Lyrics excerpt line 1
> Lyrics excerpt line 2
> (up to 6 lines, if available)

🇦🇺 #DeathMetal #TechnicalDeathMetal

#Metal #NowPlaying #DeathMetal #TechnicalDeathMetal #BlackMetal #Music #Ampache #MusicTherapy #PowerAmpache #Playlist #HeavyMetal
```

### Country Flags

Known artists are mapped to country flags in the `COUNTRY_FLAGS` dictionary in `ampache2mastodon.py`. Add more mappings as needed. If an artist isn't in the dict, the flag is omitted and only genre tags appear.

### Lyrics

1. **First**, try to get lyrics from Ampache's `song` endpoint (if stored in your library)
2. **Fallback**, query the Lyrics API: `GET /api/lyrics?artist_name=X&track_name=Y`
3. Format as blockquote (up to 6 lines)
4. Strip HTML tags and clean up

### Hashtags

| Script | Hashtags |
|--------|----------|
| `now_playing_post.py` (non-Tuesday) | `#Metal #NowPlaying #DeathMetal ...` |
| `now_playing_post.py` (Tuesday) | `#TuneTuesday #Metal #NowPlaying #DeathMetal ...` |
| `tune_tuesday.py` (Tuesday only) | `#TuneTuesday #Metal #NowPlaying #DeathMetal ...` |

---

## Usage

### Manual Now Playing Post

Run when you want to post your current song:

```bash
cd /path/to/Ampache2Mastodon
python3 now_playing_post.py
```

### TuneTuesday (Scheduled)

Run automatically by cron. Test manually:

```bash
cd /path/to/Ampache2Mastodon
python3 tune_tuesday.py
```

The script checks if today is Tuesday and exits early if not.

---

## Cron Job Setup

### Option 1: OpenClaw Cron (Recommended)

If you're using OpenClaw as your assistant/automation platform:

```bash
# Add the TuneTuesday cron job
openclaw cron add \
  --name "TuneTuesday Post" \
  --cron "0 0,6,12,18 * * 2" \
  --tz "America/Toronto" \
  --session isolated \
  --message 'Run the TuneTuesday script: python3 /path/to/Ampache2Mastodon/tune_tuesday.py'
```

**What this does:**
- `--cron "0 0,6,12,18 * * 2"` — Run at 00:00, 06:00, 12:00, 18:00 on Tuesdays (day 2)
- `--tz "America/Toronto"` — Use your timezone
- `--session isolated` — Run in a fresh isolated session (cleaner error handling)
- `--message` — The instruction passed to the agent

**Managing the job:**

```bash
# List all cron jobs
openclaw cron list

# View job details (replace with your job ID)
openclaw cron list --json | jq '.jobs[] | select(.name == "TuneTuesday Post")'

# Run immediately for testing
openclaw cron run <job-id>

# Edit the job (e.g., change schedule)
openclaw cron edit <job-id> --cron "0 12 * * 2"
```

### Option 2: Systemd Timer

Create a systemd service and timer for more control:

**`~/.config/systemd/user/tunetuesday.service`:**
```ini
[Unit]
Description=TuneTuesday Mastodon Post
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/Ampache2Mastodon
ExecStart=/usr/bin/python3 /path/to/Ampache2Mastodon/tune_tuesday.py

[Install]
WantedBy=default.target
```

**`~/.config/systemd/user/tunetuesday.timer`:**
```ini
[Unit]
Description=Run TuneTuesday every Tuesday

[Timer]
OnCalendar=Tuesday *-*-* 00,06,12,18:00:00 America/Toronto
Persistent=true

[Install]
WantedBy=timers.target
```

**Enable:**
```bash
systemctl --user daemon-reload
systemctl --user enable tunetuesday.timer
systemctl --user start tunetuesday.timer
```

### Option 3: Classic Crontab

Edit your user crontab:

```bash
crontab -e
```

Add:

```crontab
# TuneTuesday - every Tuesday at 00:00, 06:00, 12:00, 18:00
# Adjust path to match your setup
0 0,6,12,18 * * 2 cd /path/to/Ampache2Mastodon && /usr/bin/python3 tune_tuesday.py >> /tmp/tunetuesday.log 2>&1
```

**Cron format explained:**
```
┌───────────── minute (0)
│ ┌───────────── hour (0, 6, 12, 18)
│ │ ┌───────────── day of month (*)
│ │ │ ┌─────────── month (*)
│ │ │ │ ┌───────── day of week (2 = Tuesday)
│ │ │ │ │
0 0,6,12,18 * * 2
```

---

## Dependencies

```bash
pip install requests python-dotenv
```

- `requests`: HTTP client for Ampache, Mastodon, Pixelfed APIs
- `python-dotenv`: Load environment variables from `.env`

---

## Code Structure

### Shared Library (`ampache2mastodon.py`)

| Function | Purpose |
|----------|---------|
| `load_env_config()` | Load all config from `.env` |
| `get_ampache_token()` | Authenticate and get session token |
| `get_recent_songs()` | Fetch last N songs played by target user |
| `get_song_details()` | Get full song info including album art URL |
| `load_state()` / `save_state()` | Read/write posted songs to JSON |
| `download_album_art()` | Save album art to temp file |
| `upload_media_mastodon()` | Upload image to Mastodon |
| `upload_media_pixelfed()` | Upload image to Pixelfed |
| `post_status_mastodon()` | Post text + media to Mastodon |
| `post_status_pixelfed()` | Post text + media to Pixelfed |
| `boost_and_favourite()` | Find and boost/fav on secondary accounts |
| `generate_alt_text()` | Create accessibility description for image |
| `format_lyrics()` | Clean and format lyrics as blockquote |
| `fetch_lyrics_from_api()` | Fallback lyrics fetch from API |
| `build_post_text()` | Build formatted post text |
| `get_target_accounts()` | Get list of cross-post accounts |
| `COUNTRY_FLAGS` | Dict mapping artist names to flag emojis |

### Scripts

| Script | Description |
|--------|-------------|
| `now_playing_post.py` | Manual on-demand posts (Mastodon + Pixelfed + boost) |
| `tune_tuesday.py` | Scheduled Tuesday posts (Mastodon + boost, no Pixelfed) |

---

## Troubleshooting

### "Auth failed" error

- Check `AMPACHE_USER` and `AMPACHE_PASSWORD` in `.env`
- Verify the service account has API access in Ampache

### "No new songs to post"

- Check `posted_songs_state.json` — your recent songs may already be posted
- Listen to more music in Ampache
- Delete IDs from state file to repost

### "Failed to download album art"

- The album may not have cover art in Ampache
- Check if the art URL is accessible

### Cross-post search fails

- Federation takes time — the post may not have propagated yet
- Try again in a few seconds

### Lyrics not appearing

- Ampache may not have lyrics stored for this track
- The Lyrics API may not have the track
- Some tracks genuinely don't have lyrics (instrumental)

---

## Extending

### Adding More Cross-Post Accounts

Add to `.env`:

```env
# Another Mastodon instance
ANOTHER_INSTANCE=https://instance.example
ANOTHER_USERNAME=your-username
ANOTHER_TOKEN_FILE=/path/to/token
```

Then update `get_target_accounts()` in `ampache2mastodon.py`.

### Adding Country Flags

Edit the `COUNTRY_FLAGS` dictionary in `ampache2mastodon.py`:

```python
COUNTRY_FLAGS = {
    "Archspire": "🇨🇦",
    "Bloodbath": "🇸🇪",
    "Portal": "🇦🇺",
    # Add more as needed
}
```

---

## License

MIT