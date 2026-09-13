"""
Fill in missing artist/title metadata on mp3 files under a media library
organized as <Artist>/<Album>/<track>.mp3 or <Artist>/<track>.mp3.

Two kinds of gaps are handled:

1. Files that already have a real title and an `albumartist` tag but are
   missing `artist` -> `artist` is copied from `albumartist`.

2. Files whose `title` is still the generic ripper placeholder ("Track N")
   -> the real tracklist is pulled from MusicBrainz (see KNOWN_RELEASES)
   and both `artist` and `title` are filled in from it.

Run with --dry-run first to see what would change without writing anything.
"""

import argparse
import glob
import os
import re
import unicodedata

import musicbrainzngs as mb
from mutagen.easyid3 import EasyID3

mb.set_useragent("mp3-tag-metadata-fixer", "0.1", "antonio.jimeno@gmail.com")

GENERIC_TITLE_RE = re.compile(r"^Track\s*\d+", re.IGNORECASE)

# Album folders (relative to the library root) whose files only have a
# generic "Track N" title and need real tracklist data. Each maps to a
# MusicBrainz release id and, for multi-disc releases, the disc/medium
# number within that release.
KNOWN_RELEASES = {
    "The Beatles/1962-1966 - disc 1": ("3b9bd384-c20e-49d7-84ea-e41a179cc2e7", 1),
    "The Beatles/1962-1966 - disc 2": ("3b9bd384-c20e-49d7-84ea-e41a179cc2e7", 2),
    "The Beatles/1967-1970 - disc 1": ("0f5ed3b2-a2e0-4b9c-8707-499bd5338026", 1),
    "The Beatles/1967-1970 - disc 2": ("0f5ed3b2-a2e0-4b9c-8707-499bd5338026", 2),
    "Everything But The Girl/Amplified Heart": ("5987c6db-fd13-4d2e-a92b-2d3be0a48e3f", 1),
}

# The "1967-1970" disc folders on disk have their album tag swapped
# (disc 1 files are tagged as "disc 2" and vice versa). Fix it up while
# we're here since it's the same underlying "wrong song info" problem.
ALBUM_TAG_FIXES = {
    "The Beatles/1967-1970 - disc 1": "1967-1970 - disc 1",
    "The Beatles/1967-1970 - disc 2": "1967-1970 - disc 2",
}


def normalize(text):
    # MusicBrainz titles use curly quotes/dashes; keep tags plain ASCII
    # so they match what's already in the rest of the library.
    replacements = {
        "’": "'", "‘": "'",
        "“": '"', "”": '"',
        "–": "-", "—": "-", "‐": "-",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return unicodedata.normalize("NFC", text)


def fetch_tracklist(release_id, disc_number):
    data = mb.get_release_by_id(release_id, includes=["recordings"])
    medium = data["release"]["medium-list"][disc_number - 1]
    return {int(t["number"]): normalize(t["recording"]["title"]) for t in medium["track-list"]}


def album_key(filepath, root):
    rel = os.path.relpath(filepath, root)
    parts = rel.split(os.sep)
    return "/".join(parts[:-1]) if len(parts) >= 2 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", help="Path to the media library root")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing them")
    args = parser.parse_args()

    root = args.root
    files = sorted(glob.glob(os.path.join(root, "**", "*.mp3"), recursive=True))

    tracklist_cache = {}
    changed = 0

    for f in files:
        try:
            audio = EasyID3(f)
        except Exception as e:
            print(f"SKIP (unreadable): {f}: {e}")
            continue

        key = album_key(f, root)
        file_changes = []

        if key in KNOWN_RELEASES:
            if key not in tracklist_cache:
                release_id, disc_number = KNOWN_RELEASES[key]
                tracklist_cache[key] = fetch_tracklist(release_id, disc_number)
            tracklist = tracklist_cache[key]

            track_num = int(audio.get("tracknumber", ["0"])[0].split("/")[0])
            current_title = audio.get("title", [""])[0]
            if track_num in tracklist and GENERIC_TITLE_RE.match(current_title):
                new_title = tracklist[track_num]
                if current_title != new_title:
                    audio["title"] = new_title
                    file_changes.append(f"title: {current_title!r} -> {new_title!r}")

        if key in ALBUM_TAG_FIXES:
            correct_album = ALBUM_TAG_FIXES[key]
            current_album = audio.get("album", [""])[0]
            if current_album != correct_album:
                audio["album"] = correct_album
                file_changes.append(f"album: {current_album!r} -> {correct_album!r}")

        if "artist" not in audio and "albumartist" in audio:
            new_artist = audio["albumartist"][0]
            audio["artist"] = new_artist
            file_changes.append(f"artist: None -> {new_artist!r}")

        if file_changes:
            changed += 1
            print(f"{f}")
            for c in file_changes:
                print(f"    {c}")
            if not args.dry_run:
                audio.save()

    print(f"\n{changed} file(s) {'would be' if args.dry_run else ''} updated.")


if __name__ == "__main__":
    main()
