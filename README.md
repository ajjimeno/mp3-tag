# MP3 Auto-Tagger

A Python command-line tool that automatically organizes your music library. It identifies albums using [MusicBrainz](https://musicbrainz.org/), fetches metadata (track titles, artist, album, cover art), and applies ID3 tags and file renaming to your MP3 files.

**Features:**
-   Automatic release lookup based on folder structure (Artist/Album).
-   Interactive selection of MusicBrainz releases.
-   Renames files to `01 - Track Title.mp3` format.
-   Updates ID3 tags (Artist, Album, Title, Track Number) and embeds Cover Art.

## Prerequisites

This project uses [uv](https://github.com/astral-sh/uv) for extremely fast dependency management and virtual environment creation.

To install `uv`:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Via pip
pip install uv
```

## Installation

1.  **Clone the repository:**

    ```bash
    git clone <repository-url>
    cd <project-directory>
    ```

2.  **Create a virtual environment:**

    ```bash
    uv venv
    ```
    This creates a virtual environment in the `.venv` directory.

3.  **Activate the environment:**

    *   **macOS/Linux:** `source .venv/bin/activate`
    *   **Windows:** `.venv\Scripts\activate`

4.  **Install dependencies:**

    ```bash
    uv pip install click musicbrainzngs mutagen
    ```

## Usage

Run the script pointing to a folder containing MP3 files. The script expects the folder path to end in `.../Artist Name/Album Name` to help with the initial search.

```bash
python rename_and_tag.py "/path/to/music/Artist Name/Album Name"
```

## Fixing missing metadata across a whole library

`fix_missing_metadata.py` scans a media library (`<Artist>/<Album>/<track>.mp3`)
for files missing the `artist` tag or still carrying a generic ripper title
("Track N"), and fixes them:

-   Missing `artist` is copied from `albumartist` when available.
-   Generic "Track N" titles are replaced with the real tracklist pulled
    from a known MusicBrainz release (see `KNOWN_RELEASES` in the script).
    Ambiguous releases (same artist/album, different pressings) are
    disambiguated by comparing each MusicBrainz track's duration against
    the actual mp3's runtime.
-   A few known-wrong `artist`/`album` tags are corrected in place
    (see `ARTIST_TAG_FIXES` / `ALBUM_TAG_FIXES`).

Adding a new album requires finding its MusicBrainz release id and adding
an entry to `KNOWN_RELEASES`; it does not do automatic audio fingerprinting.

```bash
python fix_missing_metadata.py "/path/to/media/library" --dry-run
python fix_missing_metadata.py "/path/to/media/library"
```
