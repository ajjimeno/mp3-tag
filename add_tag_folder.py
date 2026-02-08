import eyed3
from glob import glob
import sys


if len(sys.argv) != 2:
    raise ValueError("Pass the folder where the mp3 files are")


def decompose_path(filename):
    tokens = filename.split("/")

    return tokens[-3], tokens[-2], tokens[-1].replace(".mp3", "")

for filename in glob(f"{sys.argv[1]}/*.mp3"):
    print(filename)

    artist, album, title = decompose_path(filename)

    audio_file = eyed3.load(filename)

    if not audio_file.tag:
        audio_file.initTag()

    audio_file.tag.artist = artist
    audio_file.tag.album = album
    audio_file.tag.album_artist = artist
    audio_file.tag.title = title
    audio_file.tag.track_num = int(title[:2])
    #audio_file.tag.track_num = int(title.replace(".mp3", "").replace("Track ", ""))


    audio_file.tag.save()
