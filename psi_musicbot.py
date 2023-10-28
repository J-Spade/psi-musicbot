"""
Radio PSI discord music bot
"""
import asyncio
import json
import logging
import pathlib
import sys

import discord
from discord.ext import commands
import yt_dlp

CONFIG_FILE_PATH = pathlib.Path("config.json")

# The API token and voice channel ID must be configured locally
DEFAULT_BOT_CONFIG = {
    "discord_api_token": "",
    "discord_voice_channel_id": 0,
    "psi_twitch_url": "https://www.twitch.tv/radiopsi",
    "psi_icecast_url": "http://icecast.fobby.net/radiopsi.ogg.m3u",
    "test_twitch_url": "https://www.twitch.tv/gamesdonequick",
    "test_youtube_url": "https://www.youtube.com/watch?v=MGWEI_m-IpE",
}


YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": False,
    "nocheckcertificate": True,
    "ignoreerrors": True,
    "fixup": "detect_or_warn",
    "logtostderr": False,
    "default_search": "auto",
    "source_address": "0.0.0.0",
}

FFMPEG_OPTIONS = {
    "options": "-vn",
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
}

# depending on platform, opus might be any of these files
LIBOPUS_NAMES = [
    "libopus.so.0",
    "libopus.0.dylib",
    "libopus-0.dll",
]

YTDL = yt_dlp.YoutubeDL(YTDL_OPTIONS)

LOGGER = logging.getLogger("psi-musicbot")


class YtdlSource(discord.PCMVolumeTransformer):
    """
    Represents a playable audio source scraped with yt_dlp
    """

    def __init__(self, source, data, volume=0.4):
        super().__init__(source, volume)
        self.data = data

    @classmethod
    async def get_stream_from_url(cls, url):
        """Get the audio stream data from a provided URL."""
        try:
            stream_url = None
            data = YTDL.extract_info(url, download=False)
            # if this is a playlist, only stream the first source
            if "_type" in data and data["_type"] == "playlist":
                data = data["entries"][0]

            # for icecast, the the first format contains the stream URL
            if "icecast" in url:
                stream_url = data["formats"][0]["url"]

            # for twitch, there will be an "audio_only" format
            if "twitch" in url:
                for fmt in data["formats"]:
                    if fmt.get("format_id") == "audio_only":
                        stream_url = fmt.get("url")
                        break

            # for youtube, there is a "Default" format
            if "youtube" in url:
                for fmt in data["formats"]:
                    if fmt.get("format_note") == "Default":
                        stream_url = fmt.get("url")
                        break

            if stream_url is None:
                raise FileNotFoundError("Could not determine source URL")
            LOGGER.info("Resolved stream URL: %s", stream_url)
            stream = {
                "title": data["title"] if "title" in data else None,
                "source": cls(discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS), data=data),
            }
            return stream

        except Exception as e:
            LOGGER.error("Error retrieving audio from %s: %s", url, type(e))
            return None


class PsiMusicBot(commands.Bot):
    """
    Shim functionality between discord.py and yt_dlp
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def play_audio_url(self, url: str, voice_client: discord.VoiceClient = None):
        """Stream audio from a URL into the voice channel"""
        stream = await YtdlSource.get_stream_from_url(url)
        if stream is not None:
            self.listen_activity = discord.Activity(
                name=stream["title"] if stream["title"] else url,
                url=url,
                type=discord.ActivityType.listening,
                state="",
            )
            LOGGER.info("Now playing: %s", url)
            await self.change_presence(activity=self.listen_activity)
            voice_client.play(stream["source"])

            while voice_client.is_playing():
                await asyncio.sleep(1)
            await self.change_presence(activity=None)
            await voice_client.disconnect()


def main():
    """main entrypoint"""
    # if there's no config file, write a template and exit
    if not CONFIG_FILE_PATH.exists():
        with open(CONFIG_FILE_PATH, "w") as cfg:
            json.dump(DEFAULT_BOT_CONFIG, cfg, indent=4)
        LOGGER.info("No config file found! Wrote template config to %s", CONFIG_FILE_PATH)
        sys.exit(1)
    # load the config
    with open(CONFIG_FILE_PATH, "r") as cfg:
        config = json.load(cfg)
    LOGGER.info("Loaded config from %s", CONFIG_FILE_PATH)

    # libopus required for voice
    if not discord.opus.is_loaded():
        for libopus in LIBOPUS_NAMES:
            try:
                discord.opus.load_opus(libopus)
                LOGGER.info("Loaded: %s", libopus)
                break
            except OSError:
                pass
        if not discord.opus.is_loaded():
            LOGGER.warning("Failed to load libopus! Audio may be unavailable!")

    # command functionality requires message_content gateway intent
    gateway_intents = discord.Intents.default()
    gateway_intents.message_content = True

    bot = PsiMusicBot(
        voice_channel_id=config.get("discord_voice_channel_id"),
        command_prefix="$",
        intents=gateway_intents,
    )

    @bot.event
    async def on_ready():
        LOGGER.info("Connected as %s (%d)", bot.user.name, bot.user.id)

    @bot.command()
    async def play_icecast(ctx):
        """start streaming audio from icecast"""
        await bot.play_audio_url(config.get("psi_icecast_url"), ctx.voice_client)

    @bot.command()
    async def play_twitch(ctx):
        """start streaming audio from icecast"""
        await bot.play_audio_url(config.get("psi_twitch_url"), ctx.voice_client)

    @bot.command()
    async def twitch_test(ctx):
        """offline test"""
        await bot.play_audio_url(config.get("test_twitch_url"), ctx.voice_client)

    @bot.command()
    async def youtube_test(ctx):
        """offline test"""
        await bot.play_audio_url(config.get("test_youtube_url"), ctx.voice_client)

    @play_icecast.before_invoke
    @play_twitch.before_invoke
    @twitch_test.before_invoke
    @youtube_test.before_invoke
    async def _ensure_voice(ctx):
        if ctx.voice_client is None:
            channel = bot.get_channel(config.get("discord_voice_channel_id"))
            await channel.connect()
            LOGGER.info("Connected to voice channel %d", channel.id)
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    # start the bot
    bot.run(config.get("discord_api_token"))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s: %(message)s"
    )
    main()
