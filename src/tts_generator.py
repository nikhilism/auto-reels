"""
tts_generator.py
────────────────
Converts a script string into an .mp3 audio file using Edge TTS (free).
Edge TTS runs locally via Microsoft's speech endpoint — no API key required.

Compatible with edge-tts >= 7.x

Different voices are assigned per channel in config.yaml.
"""

import asyncio
import logging
import os
import edge_tts

logger = logging.getLogger(__name__)


async def _synthesize(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    output_path: str,
) -> None:
    """Async helper that runs Edge TTS and saves the audio file."""
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        pitch=pitch,
        boundary="WordBoundary",
    )
    await communicate.save(output_path)


def generate_voiceover(
    script: str,
    output_path: str,
    voice: str = "en-US-AriaNeural",
    rate: str = "+5%",
    pitch: str = "+0Hz",
) -> str:
    """
    Generate an MP3 voiceover from a script using Edge TTS.

    Args:
        script      : The spoken text.
        output_path : Where to save the .mp3 file.
        voice       : Edge TTS voice name (e.g., "en-US-GuyNeural").
        rate        : Speaking rate adjustment (e.g., "+10%", "-5%").
        pitch       : Pitch adjustment (e.g., "+0Hz", "+5Hz").

    Returns:
        Absolute path to the generated .mp3 file.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    logger.info(f"Generating voiceover -> {output_path} (voice: {voice})")

    # Run the async synthesis in a fresh event loop
    asyncio.run(_synthesize(script, voice, rate, pitch, output_path))

    if not os.path.exists(output_path):
        raise RuntimeError(f"TTS failed -- output file not found: {output_path}")

    size_kb = os.path.getsize(output_path) / 1024
    logger.info(f"Voiceover saved ({size_kb:.1f} KB): {output_path}")
    return output_path


def list_available_voices() -> None:
    """Utility: print all available English Edge TTS voices."""

    async def _list():
        voices = await edge_tts.list_voices()
        en_voices = [v for v in voices if v["Locale"].startswith("en")]
        for v in en_voices:
            print(f"{v['ShortName']:40s} | {v['Gender']:6s} | {v['Locale']}")

    asyncio.run(_list())


if __name__ == "__main__":
    # Quick standalone test
    logging.basicConfig(level=logging.INFO)
    os.makedirs("temp", exist_ok=True)
    test_script = (
        "Did you know that the Mona Lisa has no eyebrows? "
        "It was actually fashionable in Renaissance Florence to shave them off. "
        "Follow for more mind-blowing art facts!"
    )
    generate_voiceover(
        script=test_script,
        output_path="temp/test_voiceover.mp3",
        voice="en-US-AriaNeural",
        rate="+5%",
    )
    print("Voiceover test complete -- check temp/test_voiceover.mp3")
