"""
Ampache2Mastodon shared library.

Common functions for posting songs from Ampache to Mastodon/Pixelfed.
"""

import json
import hashlib
import time
import os
import re
import requests
from pathlib import Path
from datetime import datetime


def load_env_config(script_dir):
    """Load configuration from .env file."""
    from dotenv import load_dotenv
    load_dotenv(script_dir / ".env")
    
    config = {
        # Ampache
        'ampache_server': os.getenv('AMPACHE_SERVER'),
        'ampache_user': os.getenv('AMPACHE_USER'),
        'ampache_password': os.getenv('AMPACHE_PASSWORD'),
        'ampache_target_user': os.getenv('AMPACHE_TARGET_USER'),
        
        # Mastodon
        'mastodon_instance': os.getenv('MASTODON_INSTANCE'),
        'mastodon_token_file': Path(os.getenv('MASTODON_TOKEN_FILE', '').replace('~', str(Path.home()))),
        
        # Pixelfed
        'pixelfed_instance': os.getenv('PIXELFED_INSTANCE'),
        'pixelfed_token_file': Path(os.getenv('PIXELFED_TOKEN_FILE', '').replace('~', str(Path.home()))),
        
        # Cross-post accounts
        'fosstodon_instance': os.getenv('FOSTODON_INSTANCE'),
        'fosstodon_username': os.getenv('FOSTODON_USERNAME'),
        'fosstodon_token_file': Path(os.getenv('FOSTODON_TOKEN_FILE', '').replace('~', str(Path.home()))),
        'mastodon_social_instance': os.getenv('MASTODON_SOCIAL_INSTANCE'),
        'mastodon_social_username': os.getenv('MASTODON_SOCIAL_USERNAME'),
        'mastodon_social_token_file': Path(os.getenv('MASTODON_SOCIAL_TOKEN_FILE', '').replace('~', str(Path.home()))),
        
        # Lyrics API
        'lyrics_api': os.getenv('LYRICS_API_URL'),
        
        # State file
        'state_file': script_dir / os.getenv('STATE_FILE', 'posted_songs_state.json'),
    }
    
    return config


def get_ampache_token(server, user, password):
    """Authenticate with Ampache and get session token."""
    timestamp = int(time.time())
    pass_hash = hashlib.sha256(password.encode()).hexdigest()
    auth = hashlib.sha256(f"{timestamp}{pass_hash}".encode()).hexdigest()
    
    url = f"{server}/server/json.server.php?action=handshake&user={user}&timestamp={timestamp}&auth={auth}&version=6"
    resp = requests.get(url)
    data = resp.json()
    
    if 'auth' not in data:
        raise Exception(f"Auth failed: {data}")
    
    return data['auth']


def get_recent_songs(server, token, target_user, limit=30):
    """Get recent songs played by the user."""
    url = f"{server}/server/json.server.php?action=stats&auth={token}&type=song&filter=recent&username={target_user}&limit={limit}"
    resp = requests.get(url)
    data = resp.json()
    
    if 'song' not in data:
        return []
    
    songs_with_details = []
    for song in data['song']:
        details = get_song_details(server, token, song['id'])
        if details:
            songs_with_details.append(details)
    
    return songs_with_details


def get_song_details(server, token, song_id):
    """Get detailed info for a song including album art."""
    url = f"{server}/server/json.server.php?action=song&auth={token}&filter={song_id}"
    resp = requests.get(url)
    data = resp.json()
    
    if not data or 'id' not in data:
        return None
    
    song = data
    
    album_id = song.get('album', {}).get('id')
    if album_id:
        album_url = f"{server}/server/json.server.php?action=album&auth={token}&filter={album_id}"
        album_resp = requests.get(album_url)
        album_data = album_resp.json()
        if 'art' in album_data:
            song['album']['art'] = album_data['art']
    
    return song


def load_state(state_file):
    """Load posted song IDs from state file."""
    if not state_file.exists():
        return {"posted_songs": [], "last_post": None}
    with open(state_file, 'r') as f:
        return json.load(f)


def save_state(state_file, state):
    """Save posted song IDs to state file."""
    state["last_post"] = datetime.now().isoformat()
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)


def download_album_art(url, song_id, tmp_dir="/tmp/now_playing_post"):
    """Download album art to temp file."""
    os.makedirs(tmp_dir, exist_ok=True)
    
    ext = url.split('.')[-1] if '.' in url else 'jpg'
    filepath = os.path.join(tmp_dir, f"{song_id}.{ext}")
    
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200 or len(resp.content) < 1000:
        return None
    
    with open(filepath, 'wb') as f:
        f.write(resp.content)
    
    return filepath


def upload_media_mastodon(instance, image_path, alt_text, token):
    """Upload an image to Mastodon."""
    url = f"{instance}/api/v2/media"
    headers = {"Authorization": f"Bearer {token}"}
    
    with open(image_path, 'rb') as f:
        files = {'file': f}
        data = {'description': alt_text}
        response = requests.post(url, headers=headers, files=files, data=data)
    
    if response.status_code not in [200, 202]:
        raise Exception(f"Media upload failed: {response.status_code} - {response.text}")
    
    return response.json()['id']


def upload_media_pixelfed(instance, image_path, alt_text, token):
    """Upload an image to Pixelfed."""
    url = f"{instance}/api/v2/media"
    headers = {"Authorization": f"Bearer {token}"}
    
    with open(image_path, 'rb') as f:
        files = {'file': f}
        data = {'description': alt_text}
        response = requests.post(url, headers=headers, files=files, data=data)
    
    if response.status_code not in [200, 202]:
        raise Exception(f"Pixelfed media upload failed: {response.status_code} - {response.text}")
    
    return response.json()['id']


def post_status_mastodon(instance, text, media_id, token):
    """Post a status to Mastodon."""
    url = f"{instance}/api/v1/statuses"
    headers = {"Authorization": f"Bearer {token}"}
    
    data = {
        "status": text,
        "visibility": "public",
        "media_ids[]": media_id
    }
    
    response = requests.post(url, headers=headers, data=data)
    
    if response.status_code != 200:
        raise Exception(f"Status post failed: {response.status_code} - {response.text}")
    
    return response.json()


def post_status_pixelfed(instance, text, media_id, token):
    """Post a status to Pixelfed."""
    url = f"{instance}/api/v1/statuses"
    headers = {"Authorization": f"Bearer {token}"}
    
    data = {
        "status": text,
        "visibility": "public",
        "media_ids[]": media_id
    }
    
    response = requests.post(url, headers=headers, data=data)
    
    if response.status_code != 200:
        raise Exception(f"Pixelfed status post failed: {response.status_code} - {response.text}")
    
    return response.json()


def boost_and_favourite(source_url, target):
    """Boost and favourite a post on a target instance."""
    token = target['token_file'].read_text().strip()
    target_name = f"@{target['username']}@{target['instance'].replace('https://', '')}"
    
    search_url = f"{target['instance']}/api/v2/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": source_url, "type": "statuses", "resolve": "true"}
    
    resp = requests.get(search_url, headers=headers, params=params)
    if resp.status_code != 200:
        print(f"  [{target_name}] Search failed: {resp.status_code}")
        return False
    
    results = resp.json()
    if not results.get('statuses'):
        print(f"  [{target_name}] Status not found (may need time to federate)")
        return False
    
    local_status = results['statuses'][0]
    local_id = local_status['id']
    
    if not local_status.get('favourited', False):
        fav_url = f"{target['instance']}/api/v1/statuses/{local_id}/favourite"
        resp = requests.post(fav_url, headers=headers)
        if resp.status_code == 200:
            print(f"  [{target_name}] ✓ Favourited")
        else:
            print(f"  [{target_name}] ✗ Favourite failed: {resp.status_code}")
    else:
        print(f"  [{target_name}] ✓ Already favourited")
    
    if not local_status.get('reblogged', False):
        boost_url = f"{target['instance']}/api/v1/statuses/{local_id}/reblog"
        resp = requests.post(boost_url, headers=headers)
        if resp.status_code == 200:
            print(f"  [{target_name}] ✓ Boosted")
        else:
            print(f"  [{target_name}] ✗ Boost failed: {resp.status_code}")
    else:
        print(f"  [{target_name}] ✓ Already boosted")
    
    return True


def generate_alt_text(song):
    """Generate alt text for album art."""
    artist = song.get('artist', {}).get('name', 'Unknown Artist')
    album = song.get('album', {}).get('name', 'Unknown Album')
    title = song.get('name', 'Unknown Title')
    year = song.get('year', '')
    
    alt = f'Album art for "{album}" by {artist}'
    if year:
        alt += f' ({year})'
    alt += f'. Now playing: "{title}".'
    
    return alt


def format_lyrics(lyrics_text):
    """Format lyrics as blockquote, trimmed to reasonable length."""
    if not lyrics_text:
        return None
    
    lyrics = lyrics_text.replace('<br />', '\n').replace('<br>', '\n').replace('&quot;', '"')
    lyrics = re.sub(r'<[^>]+>', '', lyrics)
    
    lines = [l.strip() for l in lyrics.split('\n') if l.strip()]
    
    if not lines:
        return None
    
    lines = lines[:6]
    return '\n'.join(f'> {line}' for line in lines)


def fetch_lyrics_from_api(api_url, artist, title):
    """Fetch lyrics from the lyrics API when Ampache doesn't have them."""
    try:
        params = {"artist_name": artist, "track_name": title}
        resp = requests.get(api_url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                # Try plain_lyrics first (our API format), then lyrics
                if 'plain_lyrics' in data and data['plain_lyrics']:
                    return data['plain_lyrics']
                elif 'lyrics' in data and data['lyrics']:
                    return data['lyrics']
    except Exception as e:
        print(f"  Lyrics API error: {e}")
    return None


# Country flags for known artists
COUNTRY_FLAGS = {
    "Xenobiotic": "🇦🇺",
    "Cryptic Shift": "🇬🇧",
    "Nocturnal Ceremony": "🇨🇱",
    "Devilplan": "🇨🇦",
}


def build_post_text(song, lyrics, is_tuesday=False):
    """Build the post text with proper formatting."""
    artist = song.get('artist', {}).get('name', 'Unknown Artist')
    album = song.get('album', {}).get('name', 'Unknown Album')
    title = song.get('name', 'Unknown Title')
    year = song.get('year', '')
    genres = song.get('genre', [])
    
    if isinstance(genres, list):
        genre_names = [g.get('name', '') for g in genres if g.get('name')]
    else:
        genre_names = []
    
    lines = ["🎸 Now Playing", ""]
    lines.append(f'**{artist} — "{title}"**')
    
    album_line = f"*from {album}*"
    if year:
        album_line = f"*from {album} ({year})*"
    lines.append(album_line)
    
    if lyrics:
        formatted_lyrics = format_lyrics(lyrics)
        if formatted_lyrics:
            lines.append("")
            lines.append(formatted_lyrics)
    
    context_line = ""
    if artist in COUNTRY_FLAGS:
        context_line = COUNTRY_FLAGS[artist]
    
    if genre_names:
        genre_str = " ".join(f"#{g.replace(' ', '')}" for g in genre_names[:2])
        if context_line:
            context_line += f" {genre_str}"
        else:
            context_line = genre_str
    
    if context_line:
        lines.append("")
        lines.append(context_line)
    
    lines.append("")
    
    # Hashtags: always include #NowPlaying, only #TuneTuesday on Tuesday
    if is_tuesday:
        lines.append("#TuneTuesday #Metal #NowPlaying #DeathMetal #TechnicalDeathMetal #BlackMetal #Music #Ampache #MusicTherapy #PowerAmpache #Playlist #HeavyMetal")
    else:
        lines.append("#Metal #NowPlaying #DeathMetal #TechnicalDeathMetal #BlackMetal #Music #Ampache #MusicTherapy #PowerAmpache #Playlist #HeavyMetal")
    
    return "\n".join(lines)


def get_target_accounts(config):
    """Get list of cross-post accounts from config."""
    return [
        {
            "instance": config['fosstodon_instance'],
            "username": config['fosstodon_username'],
            "token_file": config['fosstodon_token_file'],
        },
        {
            "instance": config['mastodon_social_instance'],
            "username": config['mastodon_social_username'],
            "token_file": config['mastodon_social_token_file'],
        },
    ]