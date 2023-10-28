# psi-musicbot

A discord bot for streaming Radio PSI audio into the official Discord channel. Uses `discord.py` for Discord functionality and `yt-dlp` for scraping audio sources.

## Requirements:
* Python 3.9+
* [libopus](https://opus-codec.org/)
* [ffmpeg](https://www.ffmpeg.org/)

## Setup:

Install the Python package requirements into a virtual environment:

```bash
$ python3 -m venv env
$ source ./env/bin/activate
(env) $ pip install -r ./requirements.txt
```

Start the bot by running `psi_musicbot.py` with the environment active:
```bash
(env) $ python3 psi_musicbot.py
```

The first time you run the bot, it will create a template config JSON file and exit. For the bot to function properly, you will need to provide a Discord API token and voice channel ID.

The bot uses `$` as a command prefix. Use `$help` to view a list of commands.
