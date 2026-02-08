from glob import glob

import click
import eyed3


def decompose_path(filename):
    tokens = filename.split("/")

    return tokens[-3], tokens[-2], tokens[-1].replace(".mp3", "")


@click.command()
@click.argument("folder")
def main(folder):
    for filename in glob(f"{folder}/*.mp3"):
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
        # audio_file.tag.track_num = int(title.replace(".mp3", "").replace("Track ", ""))

        audio_file.tag.save()


if __name__ == "__main__":
    main()
