import os

import click
import musicbrainzngs
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC

musicbrainzngs.set_useragent("MyTaggerApp", "0.1", "your@email.com")


def rename_and_tag(folder_path, release_id=None):
    # 1. Detect Artist/Album from folder names
    path_parts = os.path.normpath(folder_path).split(os.sep)
    album_name = path_parts[-1]
    artist_name = path_parts[-2]
    release_data = None

    # 2. Identify the Release
    if not release_id:
        print(f"\n--- Searching for: {artist_name} - {album_name} ---")
        result = musicbrainzngs.search_releases(
            artist=artist_name, release=album_name, limit=5
        )
        releases = result.get("release-list", [])

        if not releases:
            print("No matches found.")
            return

        candidates = []
        for i, r in enumerate(releases):
            try:
                details = musicbrainzngs.get_release_by_id(r["id"], includes=["recordings"])
                rel = details["release"]
                mediums = rel.get("medium-list", [])
                tracks = [t["recording"]["title"] for m in mediums for t in m["track-list"]]
                print(
                    f"[{i}] {rel['title']} ({rel.get('date', 'N/A')}) - {len(tracks)} tracks"
                )
                for t in tracks:
                    print(f"    - {t}")
                candidates.append(rel)
            except Exception as e:
                print(f"[{i}] Error fetching details: {e}")
                candidates.append(None)

        choice = input("\nSelect index (default 0) or 'q' to quit: ")
        if choice.lower() == "q":
            return
        index = int(choice) if choice.strip() else 0
        if index < 0 or index >= len(candidates) or not candidates[index]:
            print("Invalid selection.")
            return
        release_data = candidates[index]
        release_id = release_data["id"]

    # 3. Fetch Tracklist
    if not release_data:
        data = musicbrainzngs.get_release_by_id(release_id, includes=["recordings"])
        release_data = data["release"]

    mediums = release_data["medium-list"]

    if len(mediums) > 1:
        print(f"\nFound {len(mediums)} records (discs):")
        for i, m in enumerate(mediums):
            print(
                f"  Record {i+1}: {m.get('format', 'Unknown')} - {len(m['track-list'])} tracks"
            )

    tracks = [t for m in mediums for t in m["track-list"]]
    files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(".mp3")])

    # Fetch Cover Art
    cover_art = None
    try:
        print("Fetching cover art...")
        cover_art = musicbrainzngs.get_image_front(release_id)
    except Exception:
        print("Cover art not found.")

    # 4. PROPOSE CHANGES
    proposed_changes = []
    print(f"\n{'CURRENT FILENAME':<30} | {'PROPOSED FILENAME':<30}")
    print("-" * 65)

    for i, filename in enumerate(files):
        if i < len(tracks):
            title = tracks[i]["recording"]["title"]
            new_filename = f"{str(i + 1).zfill(2)} - {title}.mp3"
            print(f"{filename:<30} -> {new_filename:<30}")
            proposed_changes.append((filename, new_filename, title, i + 1))

    # 5. USER CONFIRMATION
    confirm = input("\nApply these changes? (y/n): ")
    if confirm.lower() != "y":
        print("Aborted. No files were changed.")
        return

    # 6. EXECUTE
    for old_name, new_name, title, track_num in proposed_changes:
        old_path = os.path.join(folder_path, old_name)
        new_path = os.path.join(folder_path, new_name)

        # Update ID3
        try:
            audio = EasyID3(old_path)
            audio["title"] = title
            audio["artist"] = artist_name
            audio["album"] = album_name
            audio["tracknumber"] = str(track_num)
            audio.save()

            # Update Cover Art
            if cover_art:
                audio_id3 = ID3(old_path)
                mime = "image/png" if cover_art.startswith(b"\x89PNG") else "image/jpeg"
                audio_id3.add(
                    APIC(
                        encoding=3,  # 3 is UTF-8
                        mime=mime,
                        type=3,  # 3 is the cover image
                        desc="Cover",
                        data=cover_art,
                    )
                )
                audio_id3.save()

            # Rename
            os.rename(old_path, new_path)
        except Exception as e:
            print(f"Error updating {old_name}: {e}")

    print("\nUpdate complete!")


@click.command()
@click.argument("folder_path", type=click.Path(exists=True, file_okay=False))
@click.option("--release-id", default=None, help="MusicBrainz Release ID")
def main(folder_path, release_id):
    rename_and_tag(folder_path, release_id)


if __name__ == "__main__":
    main()
