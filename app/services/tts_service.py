from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from pydub import AudioSegment
import math
import re
import struct
import wave
import os
import threading

MODEL_NAME = os.getenv(
    "QWEN_TTS_MODEL",
    "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
)

MODEL_DEVICE = os.getenv("QWEN_TTS_DEVICE", "cuda:0")
MODEL_DTYPE = os.getenv("QWEN_TTS_DTYPE", "bfloat16")
USE_FLASH_ATTENTION = os.getenv("QWEN_TTS_FLASH_ATTENTION", "false").lower() == "true"

_model = None
_model_lock = threading.Lock()


def get_tts_model():
    global _model

    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        import torch
        from qwen_tts import Qwen3TTSModel

        dtype = torch.bfloat16 if MODEL_DTYPE == "bfloat16" else torch.float16

        kwargs = {
            "device_map": MODEL_DEVICE,
            "dtype": dtype,
        }

        if USE_FLASH_ATTENTION:
            kwargs["attn_implementation"] = "flash_attention_2"
        else:
            kwargs["attn_implementation"] = "eager"

        _model = Qwen3TTSModel.from_pretrained(
            MODEL_NAME,
            **kwargs,
        )

        return _model


def generate_qwen_voice_design(
    text: str,
    language: str,
    voice_description: str,
    output_path: Path,
) -> None:
    import soundfile as sf

    model = get_tts_model()

    wavs, sr = model.generate_voice_design(
        text=text.strip(),
        language=language.strip() or "English",
        instruct=voice_description.strip() or "A warm, clear professional voice",
        non_streaming_mode=True,
        max_new_tokens=2048,
    )

    sf.write(str(output_path), wavs[0], sr)

@dataclass
class TextChunk:
    index: int
    text: str
    characters: int


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text_into_chunks(text: str, max_chars: int = 1200) -> list[TextChunk]:
    """
    Splits large documents into manageable TTS chunks.

    Strategy:
    1. Prefer paragraph boundaries.
    2. If a paragraph is too large, split by sentence.
    3. If a sentence is still too large, hard split.
    """

    text = normalize_text(text)

    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    def push_current():
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
            current = ""

    def add_piece(piece: str):
        nonlocal current

        piece = piece.strip()
        if not piece:
            return

        if len(piece) > max_chars:
            push_current()

            sentences = split_paragraph_into_sentences(piece)

            sentence_buffer = ""

            for sentence in sentences:
                if len(sentence) > max_chars:
                    if sentence_buffer.strip():
                        chunks.append(sentence_buffer.strip())
                        sentence_buffer = ""

                    for hard_part in hard_split(sentence, max_chars):
                        chunks.append(hard_part.strip())
                    continue

                candidate = join_text(sentence_buffer, sentence)

                if len(candidate) <= max_chars:
                    sentence_buffer = candidate
                else:
                    if sentence_buffer.strip():
                        chunks.append(sentence_buffer.strip())
                    sentence_buffer = sentence

            if sentence_buffer.strip():
                chunks.append(sentence_buffer.strip())

            return

        candidate = join_text(current, piece)

        if len(candidate) <= max_chars:
            current = candidate
        else:
            push_current()
            current = piece

    for paragraph in paragraphs:
        add_piece(paragraph)

    push_current()

    return [
        TextChunk(index=i + 1, text=chunk, characters=len(chunk))
        for i, chunk in enumerate(chunks)
    ]


def split_paragraph_into_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def hard_split(text: str, max_chars: int) -> Iterable[str]:
    for i in range(0, len(text), max_chars):
        yield text[i : i + max_chars]


def join_text(left: str, right: str) -> str:
    if not left:
        return right.strip()

    if not right:
        return left.strip()

    return f"{left.strip()}\n\n{right.strip()}"


def make_placeholder_wav(path: Path, seconds: float = 1.2, frequency: int = 440) -> None:
    sample_rate = 24000
    amplitude = 0.25
    total_samples = int(sample_rate * seconds)

    with wave.open(str(path), "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)

        for i in range(total_samples):
            value = amplitude * math.sin(2 * math.pi * frequency * i / sample_rate)
            packed = struct.pack("<h", int(value * 32767))
            wav.writeframes(packed)
            
def combine_wav_files(input_paths: list[Path], output_path: Path) -> None:
    if not input_paths:
        raise ValueError("No audio chunks supplied for combining.")

    combined = AudioSegment.empty()

    for path in input_paths:
        if path.exists():
            combined += AudioSegment.from_file(path)

    combined.export(output_path, format="wav")