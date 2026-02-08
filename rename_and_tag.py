import os
import musicbrainzngs
from mutagen.easyid3 import EasyID3

musicbrainzngs.set_useragent("MyTaggerApp", "0.1", "your@email.com")

def rename_and_tag(folder_path, release_id=None):
    # 1. Detect Artist/Album from folder names
    path_parts = os.path.normpath(folder_path).split(os.sep)
    album_name = path_parts[-1]
    artist_name = path_parts[-2]

    # 2. Identify the Release
    if not release_id:
        print(f"\n--- Searching for: {artist_name} - {album_name} ---")
        result = musicbrainzngs.search_releases(artist=artist_name, release=album_name, limit=5)
        releases = result.get('release-list', [])
        
        if not releases:
            print("No matches found.")
            return

        for i, r in enumerate(releases):
            print(f"[{i}] {r['title']} ({r.get('date', 'N/A')}) - {r.get('track-count')} tracks")
        
        choice = input("\nSelect index (default 0) or 'q' to quit: ")
        if choice.lower() == 'q': return
        index = int(choice) if choice.strip() else 0
        release_id = releases[index]['id']

    # 3. Fetch Tracklist
    data = musicbrainzngs.get_release_by_id(release_id, includes=["recordings"])
    tracks = data['release']['medium-list'][0]['track-list']
    files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith('.mp3')])

    breakpoint()

    # 4. PROPOSE CHANGES
    proposed_changes = []
    print(f"\n{'CURRENT FILENAME':<30} | {'PROPOSED FILENAME':<30}")
    print("-" * 65)
    
    for i, filename in enumerate(files):
        if i < len(tracks):
            title = tracks[i]['recording']['title']
            new_filename = f"{str(i + 1).zfill(2)} - {title}.mp3"
            print(f"{filename:<30} -> {new_filename:<30}")
            proposed_changes.append((filename, new_filename, title, i+1))

    # 5. USER CONFIRMATION
    confirm = input("\nApply these changes? (y/n): ")
    if confirm.lower() != 'y':
        print("Aborted. No files were changed.")
        return

    # 6. EXECUTE
    for old_name, new_name, title, track_num in proposed_changes:
        old_path = os.path.join(folder_path, old_name)
        new_path = os.path.join(folder_path, new_name)

        # Update ID3
        try:
            audio = EasyID3(old_path)
            audio['title'] = title
            audio['artist'] = artist_name
            audio['album'] = album_name
            audio['tracknumber'] = str(track_num)
            audio.save()
            # Rename
            os.rename(old_path, new_path)
        except Exception as e:
            print(f"Error updating {old_name}: {e}")

    print("\nUpdate complete!")

# Usage:
# rename_and_tag("/path/to/artist/album")
rename_and_tag("/mnt/c/Users/antonio/Music/media/Iggy Pop/Lust for Life", release_id=)
