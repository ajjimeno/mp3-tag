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

GENERIC_TITLE_RE = re.compile(r"\bTrack\s*\d+\b", re.IGNORECASE)

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
    # Matched by track count + per-track duration against mp3 runtimes.
    "Blondie/Maria": ("036d9cb8-8e5b-411f-9166-93ebd4f96d93", 1),
    "Blondie/The Best of Blondie": ("e6f8c54e-d1f2-37ab-9d1e-a86682c07f22", 1),
    "Counting Crows/august and Everything after": ("4cc9676f-38fb-42a3-96d3-cd3b8e1b282e", 1),
    "Guns N' Roses/Appetite for Destruction": ("7e1aaffd-3f00-4534-bddc-5ff88dc8600b", 1),
    "Led Zeppelin/mothership-disk1": ("f70e6138-2c32-43c6-b6a7-ade6fc7527be", 1),
    "Led Zeppelin/mothership-disk2": ("f70e6138-2c32-43c6-b6a7-ade6fc7527be", 2),
    "The Cranberries/Stars": ("fc3ca3a4-e79a-4854-8457-c3004daaa88e", 1),
    "The Rolling Stones/disk1": ("da943433-d90b-4100-9f3e-6a5be1183cd8", 1),
    "ACDC/High Voltage": ("9cb006e6-aa89-4938-b2b2-a14dcca08e59", 1),
    "Bon Jovi/Greatest Hits": ("ab4d85e8-a106-4af1-80ca-62fb66bcc13f", 1),
    "Iggy Pop/Lust for Life": ("72dcb7c6-b1bc-38a4-aa37-e02de0117f4f", 1),
    # Folder is labeled "disc1" but its content/durations match this
    # release's medium 2, and vice versa for "disc2" - see PINK_FLOYD note.
    "Pink Floyd/The Wall - disc1": ("93c4f215-15ae-34a2-981a-9a5fbd700004", 2),
    "Pink Floyd/The Wall - disc2": ("93c4f215-15ae-34a2-981a-9a5fbd700004", 1),
    "Steve Miller Band/Greatest Hits 1974-1978": ("53835da5-8df7-48ff-b226-45130145ef27", 1),
    "The Clash/The story of the Clash - disc1": ("1925f834-93bc-40c3-93da-e4e56d3cb46a", 1),
    "The Clash/The story of the Clash - disc2": ("1925f834-93bc-40c3-93da-e4e56d3cb46a", 2),
    "Madness/The Best of Madness": ("ced96108-0ada-41b9-8269-3db8257515f6", 1),
    "Mano Negra/Best of Mano Negra": ("60e25926-a13a-4d96-8630-237c5e744005", 1),
    "Paco de Lucia/Concierto de Aranjuez": ("d55a412e-4b09-4e70-8497-42ab1a9a5c72", 1),
    "Paco de Lucia/Entre Dos Aguas": ("41b40029-896b-3aac-bde9-76dc014827ec", 1),
    "The Mamas & The Papas/California Dreaming": ("3f288778-2a59-47d4-ae4b-cb2f3a4d6022", 1),
}

# Files whose artist/albumartist tag is outright wrong (not just missing)
# and needs to be overwritten to the real name.
ARTIST_TAG_FIXES = {
    "ACDC/High Voltage": "AC/DC",
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
    # Use the sequential `position` rather than `number`: vinyl-style
    # releases label tracks "A1", "B2", etc. instead of plain integers.
    return {int(t["position"]): normalize(t["recording"]["title"]) for t in medium["track-list"]}


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
            if track_num in tracklist and GENERIC_TITLE_RE.search(current_title):
                new_title = tracklist[track_num]
                if current_title != new_title:
                    audio["title"] = new_title
                    file_changes.append(f"title: {current_title!r} -> {new_title!r}")

        if key in ARTIST_TAG_FIXES:
            correct_artist = ARTIST_TAG_FIXES[key]
            for field in ("artist", "albumartist"):
                if audio.get(field, [""])[0] != correct_artist:
                    old = audio.get(field, [None])[0]
                    audio[field] = correct_artist
                    file_changes.append(f"{field}: {old!r} -> {correct_artist!r}")

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
