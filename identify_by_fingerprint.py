"""
Fill in missing artist/title metadata using real audio content
identification (AcoustID/Chromaprint), for mp3s whose folder doesn't map
to a single known MusicBrainz release (unknown album, or a genuine
multi-artist compilation where fix_missing_metadata.py's per-album
approach doesn't apply).

Each file is fingerprinted locally (ffmpeg decodes to PCM, chromaprint
computes the fingerprint via ctypes against libchromaprint.so - no fpcalc
binary needed) and looked up against the AcoustID web service, which
maps the fingerprint to a MusicBrainz recording (title + artist).

Requires a free AcoustID API key from https://acoustid.org/new-application
(the "Application API key" listed at https://acoustid.org/my-applications,
not your personal/account API key). Pass it via --api-key or the
ACOUSTID_API_KEY environment variable - never hardcode it in this file.

Run with --dry-run first to see proposed changes without writing them.
Low-confidence or nonsensical matches should be checked manually; pass
--skip "relative/path.mp3" (repeatable) to exclude specific files found
to be false positives.
"""

import argparse
import ctypes
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from mutagen.easyid3 import EasyID3
import mutagen

GENERIC_TITLE_RE = re.compile(r"\bTrack\s*\d+\b", re.IGNORECASE)

CHROMAPRINT_ALGORITHM_DEFAULT = 1
SAMPLE_RATE = 11025
CHANNELS = 1

_lib = None


def _chromaprint_lib():
    global _lib
    if _lib is None:
        _lib = ctypes.CDLL("libchromaprint.so.1")
        _lib.chromaprint_new.restype = ctypes.c_void_p
        _lib.chromaprint_new.argtypes = [ctypes.c_int]
        _lib.chromaprint_free.argtypes = [ctypes.c_void_p]
        _lib.chromaprint_start.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        _lib.chromaprint_start.restype = ctypes.c_int
        _lib.chromaprint_feed.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        _lib.chromaprint_feed.restype = ctypes.c_int
        _lib.chromaprint_finish.argtypes = [ctypes.c_void_p]
        _lib.chromaprint_finish.restype = ctypes.c_int
        _lib.chromaprint_get_fingerprint.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]
        _lib.chromaprint_get_fingerprint.restype = ctypes.c_int
        _lib.chromaprint_dealloc.argtypes = [ctypes.c_void_p]
    return _lib


def fingerprint_file(path, max_seconds=120):
    proc = subprocess.run(
        [
            "ffmpeg", "-i", path, "-t", str(max_seconds),
            "-f", "s16le", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE),
            "-loglevel", "error", "-",
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="replace"))
    pcm = proc.stdout

    lib = _chromaprint_lib()
    ctx = lib.chromaprint_new(CHROMAPRINT_ALGORITHM_DEFAULT)
    try:
        if not lib.chromaprint_start(ctx, SAMPLE_RATE, CHANNELS):
            raise RuntimeError("chromaprint_start failed")
        if not lib.chromaprint_feed(ctx, pcm, len(pcm) // 2):
            raise RuntimeError("chromaprint_feed failed")
        if not lib.chromaprint_finish(ctx):
            raise RuntimeError("chromaprint_finish failed")
        fp_ptr = ctypes.c_char_p()
        if not lib.chromaprint_get_fingerprint(ctx, ctypes.byref(fp_ptr)):
            raise RuntimeError("chromaprint_get_fingerprint failed")
        fingerprint = fp_ptr.value.decode()
        lib.chromaprint_dealloc(fp_ptr)
        return fingerprint
    finally:
        lib.chromaprint_free(ctx)


def acoustid_lookup(api_key, fp, duration):
    params = urllib.parse.urlencode(
        {
            "client": api_key,
            "duration": duration,
            "fingerprint": fp,
            "meta": "recordings+releasegroups+compress",
        },
        safe="+",
    )
    url = "https://api.acoustid.org/v2/lookup?" + params
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.load(resp)


def identify(api_key, path):
    audio = mutagen.File(path)
    duration = round(audio.info.length)
    fp = fingerprint_file(path)
    data = acoustid_lookup(api_key, fp, duration)
    results = data.get("results", [])
    if not results:
        return None
    best = max(results, key=lambda r: r.get("score", 0))
    recordings = best.get("recordings", [])
    if not recordings:
        return {"score": best["score"], "title": None, "artist": None}
    rec = recordings[0]
    artists = rec.get("artists", [])
    artist_name = "/".join(a["name"] for a in artists) if artists else None
    return {"score": best["score"], "title": rec.get("title"), "artist": artist_name}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", help="Folder to scan recursively for mp3s with a generic 'Track N' title")
    parser.add_argument("--api-key", default=os.environ.get("ACOUSTID_API_KEY"), help="AcoustID application API key (or set ACOUSTID_API_KEY)")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing them")
    parser.add_argument("--skip", action="append", default=[], help="Path (relative to folder) to exclude, repeatable")
    args = parser.parse_args()

    if not args.api_key:
        parser.error("an AcoustID API key is required: pass --api-key or set ACOUSTID_API_KEY")

    skip = {os.path.normpath(p) for p in args.skip}
    files = sorted(glob.glob(os.path.join(args.folder, "**", "*.mp3"), recursive=True))
    changed = 0

    for f in files:
        rel = os.path.normpath(os.path.relpath(f, args.folder))
        if rel in skip:
            continue

        audio = EasyID3(f)
        current_title = audio.get("title", [""])[0]
        if not GENERIC_TITLE_RE.search(current_title):
            continue

        try:
            result = identify(args.api_key, f)
        except Exception as e:
            print(f"SKIP (lookup failed): {f}: {e}")
            continue
        if not result or not result.get("title"):
            print(f"NO MATCH: {f}")
            continue

        file_changes = []
        if result["title"] != current_title:
            audio["title"] = result["title"]
            file_changes.append(f"title: {current_title!r} -> {result['title']!r}")
        if result.get("artist") and audio.get("artist", [""])[0] != result["artist"]:
            old = audio.get("artist", [None])[0]
            audio["artist"] = result["artist"]
            file_changes.append(f"artist: {old!r} -> {result['artist']!r}")

        if file_changes:
            changed += 1
            print(f"{f}  (score={result['score']:.3f})")
            for c in file_changes:
                print(f"    {c}")
            if not args.dry_run:
                audio.save()

        time.sleep(0.34)  # stay under the free API's ~3 req/s rate limit

    print(f"\n{changed} file(s) {'would be' if args.dry_run else ''} updated.")


if __name__ == "__main__":
    main()
