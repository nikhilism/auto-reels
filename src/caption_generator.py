"""
caption_generator.py
────────────────────
Uses faster-whisper (runs fully locally, no API key needed) to transcribe
a TTS audio file and extract word-level timestamps.

faster-whisper is 4x faster than openai-whisper on CPU, actively maintained,
and produces the same high-quality transcriptions.

These timestamps are used by video_editor.py to render animated captions
that highlight each word as it's spoken.
"""

import logging
import os
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

# Module-level model cache — load once, reuse across calls in same session
_whisper_model = None


def _load_model(model_size: str = "base") -> WhisperModel:
    """Load and cache the faster-whisper model."""
    global _whisper_model
    if _whisper_model is None:
        logger.info(
            f"Loading Whisper model '{model_size}' "
            "(first run downloads ~150MB, then cached)..."
        )
        # device="cpu", compute_type="int8" = fast & lightweight on any machine
        _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
        logger.info("Whisper model loaded.")
    return _whisper_model


def get_word_timestamps(
    audio_path: str,
    model_size: str = "base",
) -> list[dict]:
    """
    Transcribe an audio file and return word-level timestamps.

    Args:
        audio_path : Path to the .mp3 or .wav audio file.
        model_size : Whisper model size ("tiny", "base", "small", "medium").
                     "base" is recommended — good accuracy, fast on CPU.

    Returns:
        List of dicts, each with:
          {
            "word"  : str   — the spoken word,
            "start" : float — start time in seconds,
            "end"   : float — end time in seconds,
          }
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = _load_model(model_size)
    logger.info(f"Transcribing audio for captions: {audio_path}")

    segments, _ = model.transcribe(
        audio_path,
        word_timestamps=True,
        language="en",
    )

    words = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                word_text = w.word.strip()
                if word_text:
                    words.append({
                        "word": word_text,
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                    })

    logger.info(f"Extracted {len(words)} word timestamps.")
    return words


def group_into_caption_chunks(
    words: list[dict],
    max_words: int = 3,
) -> list[dict]:
    """
    Group individual word timestamps into caption chunks (phrases).
    Each chunk will be displayed as a single caption card on screen.

    Args:
        words     : Output from get_word_timestamps().
        max_words : Maximum words per caption card (recommended: 2-4).

    Returns:
        List of dicts:
          {
            "text"   : str   — the full chunk text,
            "words"  : list  — individual words with their timestamps,
            "start"  : float — chunk start time,
            "end"    : float — chunk end time,
          }
    """
    chunks = []
    for i in range(0, len(words), max_words):
        chunk_words = words[i: i + max_words]
        chunk = {
            "text": " ".join(w["word"] for w in chunk_words),
            "words": chunk_words,
            "start": chunk_words[0]["start"],
            "end": chunk_words[-1]["end"],
        }
        chunks.append(chunk)

    logger.info(
        f"Grouped into {len(chunks)} caption chunks (max {max_words} words each)."
    )
    return chunks


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    import json
    test_audio = "temp/test_voiceover.mp3"
    if os.path.exists(test_audio):
        words = get_word_timestamps(test_audio)
        chunks = group_into_caption_chunks(words, max_words=3)
        print(json.dumps(chunks[:5], indent=2))
    else:
        print(f"Test audio not found at {test_audio}. Run tts_generator.py first.")
