"""
Voice Service: скачиваем голосовое сообщение из Telegram → конвертируем → отправляем в Google STT.
"""
import asyncio
import aiohttp
import aiofiles
import os
import json
import base64
from pathlib import Path
from typing import Optional
from loguru import logger
from core.config import settings


TEMP_DIR = Path("/tmp/voice")
TEMP_DIR.mkdir(exist_ok=True)


async def download_voice(bot, file_id: str) -> Optional[Path]:
    """Скачиваем voice message из Telegram."""
    try:
        file = await bot.get_file(file_id)
        file_path = TEMP_DIR / f"{file_id}.ogg"
        await bot.download_file(file.file_path, destination=str(file_path))
        return file_path
    except Exception as e:
        logger.error(f"Failed to download voice: {e}")
        return None


async def convert_ogg_to_wav(ogg_path: Path) -> Optional[Path]:
    """Конвертируем OGG → WAV через ffmpeg."""
    wav_path = ogg_path.with_suffix(".wav")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", str(ogg_path),
        "-ar", "16000", "-ac", "1", "-f", "wav",
        str(wav_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    if wav_path.exists():
        return wav_path
    return None


async def transcribe_google(wav_path: Path, language: str = "kk-KZ") -> Optional[str]:
    """
    Транскрибируем через Google Cloud Speech-to-Text REST API.
    language: "kk-KZ" для казахского, "en-US" для английского
    """
    if not settings.GOOGLE_STT_KEY:
        logger.warning("Google STT key not configured, using mock")
        return await _mock_transcribe(wav_path)

    async with aiofiles.open(wav_path, "rb") as f:
        audio_content = await f.read()

    audio_b64 = base64.b64encode(audio_content).decode("utf-8")

    payload = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": 16000,
            "languageCode": language,
            "alternativeLanguageCodes": ["ru-RU"],
            "enableAutomaticPunctuation": False,
        },
        "audio": {
            "content": audio_b64
        }
    }

    url = f"https://speech.googleapis.com/v1/speech:recognize?key={settings.GOOGLE_STT_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"Google STT error {resp.status}: {text}")
                return None
            data = await resp.json()

    results = data.get("results", [])
    if not results:
        return ""

    # Берём лучший вариант
    transcript = results[0]["alternatives"][0]["transcript"]
    return transcript.strip().lower()


async def _mock_transcribe(wav_path: Path) -> str:
    """Заглушка для тестирования без ключа."""
    logger.debug(f"Mock transcribe for {wav_path.name}")
    return "тест голоса"


async def cleanup(paths: list[Path]):
    """Удаляем временные файлы."""
    for p in paths:
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass


async def process_voice_message(
    bot,
    file_id: str,
    expected_text: str,
    language_code: str = "kk-KZ",
    threshold: float = 0.75,
) -> tuple[bool, str]:
    """
    Полный пайплайн: скачать → конвертировать → транскрибировать → сравнить.

    Возвращает: (is_correct, transcript)
    """
    files_to_cleanup = []

    try:
        ogg_path = await download_voice(bot, file_id)
        if not ogg_path:
            return False, ""
        files_to_cleanup.append(ogg_path)

        wav_path = await convert_ogg_to_wav(ogg_path)
        if not wav_path:
            return False, ""
        files_to_cleanup.append(wav_path)

        transcript = await transcribe_google(wav_path, language_code)
        if transcript is None:
            return False, ""

        # Сравниваем с ожидаемым текстом
        similarity = _levenshtein_similarity(
            transcript.lower(),
            expected_text.lower()
        )
        is_correct = similarity >= threshold

        return is_correct, transcript

    finally:
        await cleanup(files_to_cleanup)


def _levenshtein_similarity(a: str, b: str) -> float:
    import Levenshtein
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    distance = Levenshtein.distance(a, b)
    return 1 - distance / max(len(a), len(b))
