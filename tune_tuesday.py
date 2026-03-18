#!/usr/bin/env python3
"""
#TuneTuesday - Post the last played song to Mastodon.
Runs every Tuesday, checks for already-posted songs, skips if needed.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Import shared library
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))
from ampache2mastodon import (
    load_env_config,
    get_ampache_token,
    get_recent_songs,
    load_state,
    save_state,
    download_album_art,
    upload_media_mastodon,
    post_status_mastodon,
    boost_and_favourite,
    fetch_lyrics_from_api,
    build_post_text,
    get_target_accounts,
)


def main():
    print("=" * 60)
    print("#TuneTuesday")
    print("=" * 60)
    print(f"Time: {datetime.now().isoformat()}\n")
    
    # Check if today is Tuesday (weekday 1)
    if datetime.now().weekday() != 1:
        print("Not Tuesday, skipping.")
        return
    
    print("It's Tuesday! Posting...\n")
    
    # Load config
    config = load_env_config(SCRIPT_DIR)
    
    # Load state
    state = load_state(config['state_file'])
    posted_ids = set(state.get("posted_songs", []))
    
    # Authenticate with Ampache
    print("Authenticating with Ampache...")
    token = get_ampache_token(
        config['ampache_server'],
        config['ampache_user'],
        config['ampache_password']
    )
    
    # Get recent songs
    print("Fetching recent songs...")
    songs = get_recent_songs(
        config['ampache_server'],
        token,
        config['ampache_target_user'],
        limit=50
    )
    print(f"Found {len(songs)} recent songs")
    
    # Find a song to post
    song_to_post = None
    for song in songs:
        song_id = str(song.get('id'))
        
        if song_id in posted_ids:
            print(f"Skipping '{song.get('name')}' - already posted")
            continue
        
        album_art = song.get('album', {}).get('art', '')
        if not album_art:
            print(f"Skipping '{song.get('name')}' - no album art")
            continue
        
        song_to_post = song
        break
    
    if not song_to_post:
        print("\nNo new songs to post")
        return
    
    # Extract song info
    artist = song_to_post.get('artist', {}).get('name', 'Unknown Artist')
    album = song_to_post.get('album', {}).get('name', 'Unknown Album')
    title = song_to_post.get('name', 'Unknown Title')
    year = song_to_post.get('year', '')
    album_art = song_to_post.get('album', {}).get('art', '')
    song_id = str(song_to_post.get('id'))
    lyrics = song_to_post.get('lyrics', '')
    
    print(f"\nSelected song:")
    print(f"  Artist: {artist}")
    print(f"  Album: {album}")
    print(f"  Title: {title}")
    print(f"  Year: {year}")
    
    # Fetch lyrics if not in Ampache
    if not lyrics:
        print("  Fetching lyrics from API...")
        lyrics = fetch_lyrics_from_api(config['lyrics_api'], artist, title)
        if lyrics:
            print(f"  Found lyrics ({len(lyrics)} chars)")
        else:
            print("  No lyrics found")
    
    # Download album art
    print("\nDownloading album art...")
    art_path = download_album_art(album_art, song_id, tmp_dir="/tmp/tune_tuesday")
    if not art_path:
        print("Failed to download album art")
        return
    print(f"Saved to: {art_path}")
    
    # Build post text (Tuesday format with #TuneTuesday)
    post_text = build_post_text(song_to_post, lyrics, is_tuesday=True)
    print(f"\nPost text ({len(post_text)} chars):")
    print(post_text)
    
    # Generate alt text
    alt_text = f'Album art for "{album}" by {artist}'
    if year:
        alt_text += f' ({year})'
    alt_text += f'. Now playing: "{title}".'
    print(f"\nAlt text: {alt_text}")
    
    # Mastodon
    print("\n" + "=" * 40)
    print("MASTODON")
    print("=" * 40)
    
    mastodon_token = config['mastodon_token_file'].read_text().strip()
    
    print("Uploading to Mastodon...")
    media_id = upload_media_mastodon(
        config['mastodon_instance'],
        art_path,
        alt_text,
        mastodon_token
    )
    print(f"Media ID: {media_id}")
    
    print("Posting status...")
    result = post_status_mastodon(
        config['mastodon_instance'],
        post_text,
        media_id,
        mastodon_token
    )
    post_url = result.get('url', 'success')
    print(f"Posted: {post_url}")
    
    # Cross-post (boost + favourite)
    print("\n" + "=" * 40)
    print("CROSS-POST (Boost + Favourite)")
    print("=" * 40)
    
    target_accounts = get_target_accounts(config)
    for target in target_accounts:
        try:
            boost_and_favourite(post_url, target)
        except Exception as e:
            print(f"  Error: {e}")
    
    # Save state
    posted_ids.add(song_id)
    state["posted_songs"] = list(posted_ids)[-200:]
    save_state(config['state_file'], state)
    print(f"\nState saved. Posted songs: {len(state['posted_songs'])}")
    
    # Cleanup
    if os.path.exists(art_path):
        os.remove(art_path)
    
    print("\n" + "=" * 60)
    print("Done!")
    print(f"Mastodon: {post_url}")
    print("=" * 60)


if __name__ == "__main__":
    main()