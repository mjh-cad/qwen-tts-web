from pathlib import Path
from datetime import datetime
import re
from uuid import uuid4

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import os

from app.services.tts_service import (
    split_text_into_chunks,
    make_placeholder_wav,
    generate_qwen_voice_design,
    combine_wav_files,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUTS_DIR = BASE_DIR / "outputs"
UPLOADS_DIR = BASE_DIR / "uploads"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Qwen TTS Web UI")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def safe_filename(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value[:60] or "audio"


async def read_uploaded_text(file: UploadFile) -> str:
    raw = await file.read()

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="ignore")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {}
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "time": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/api/history")
async def history():
    files = []

    for path in sorted(OUTPUTS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file() and path.suffix.lower() in [".wav", ".mp3", ".ogg"]:
            stat = path.stat()
            files.append(
                {
                    "filename": path.name,
                    "url": f"/outputs/{path.name}",
                    "size_bytes": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                }
            )

    return {
        "items": files,
    }

@app.delete("/api/history/{filename:path}")
async def delete_history_item(filename: str):
    clean_name = Path(filename).name
    path = OUTPUTS_DIR / clean_name

    existing_files = [p.name for p in OUTPUTS_DIR.glob("*") if p.is_file()]

    if not path.exists():
        return JSONResponse(
            status_code=404,
            content={
                "error": "Audio file not found.",
                "requested": clean_name,
                "outputs_dir": str(OUTPUTS_DIR),
                "existing_files": existing_files,
            },
        )

    if path.suffix.lower() not in [".wav", ".mp3", ".ogg"]:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid audio file type."
            },
        )

    path.unlink()

    return {
        "status": "ok",
        "deleted": clean_name,
    }
    
@app.post("/api/generate")
async def generate_audio(
    text: str = Form(""),
    language: str = Form("English"),
    voice_description: str = Form("A warm, clear professional voice"),
    max_chars_per_chunk: int = Form(1200),
    files: list[UploadFile] = File(default=[]),
):
    use_mock_tts = os.getenv("USE_MOCK_TTS", "false").lower() == "true"

    jobs = []

    clean_text = text.strip()

    if clean_text:
        jobs.append(
            {
                "source_name": "typed-text",
                "text": clean_text,
            }
        )

    for file in files:
        if not file.filename:
            continue

        file_text = await read_uploaded_text(file)

        if file_text.strip():
            upload_path = UPLOADS_DIR / f"{uuid4().hex}_{safe_filename(file.filename)}.txt"
            upload_path.write_text(file_text, encoding="utf-8")

            jobs.append(
                {
                    "source_name": file.filename,
                    "text": file_text.strip(),
                }
            )

    if not jobs:
        return JSONResponse(
            status_code=400,
            content={
                "error": "No text supplied. Type text or upload at least one text file."
            },
        )

    results = []

    for job_index, job in enumerate(jobs, start=1):
        chunks = split_text_into_chunks(
            job["text"],
            max_chars=max(300, min(max_chars_per_chunk, 4000)),
        )

        if not chunks:
            continue

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = safe_filename(job["source_name"])

        temp_chunk_paths: list[Path] = []

        for chunk in chunks:
            chunk_name = (
                f"_tmp_{stamp}_job-{job_index:03d}_"
                f"chunk-{chunk.index:04d}_{base}.wav"
            )

            chunk_path = OUTPUTS_DIR / chunk_name

            if use_mock_tts:
                make_placeholder_wav(
                    chunk_path,
                    seconds=1.2,
                    frequency=420 + (chunk.index % 8) * 40,
                )
            else:
                generate_qwen_voice_design(
                    text=chunk.text,
                    language=language,
                    voice_description=voice_description,
                    output_path=chunk_path,
                )

            temp_chunk_paths.append(chunk_path)

        final_name = f"{stamp}_job-{job_index:03d}_{base}.wav"
        final_path = OUTPUTS_DIR / final_name

        if len(temp_chunk_paths) == 1:
            temp_chunk_paths[0].replace(final_path)
        else:
            combine_wav_files(temp_chunk_paths, final_path)

            for temp_path in temp_chunk_paths:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

        results.append(
            {
                "source_name": job["source_name"],
                "filename": final_name,
                "url": f"/outputs/{final_name}",
                "characters": len(job["text"]),
                "chunks": len(chunks),
                "language": language,
                "voice_description": voice_description,
            }
        )

    return {
        "status": "ok",
        "count": len(results),
        "items": results,
    }


class PublicGenerateRequest(BaseModel):
    text: str
    language: str = "English"
    voice_description: str = "A warm, clear professional voice"
    max_chars_per_chunk: int = 1200


def build_output_url(request: Request, filename: str) -> str:
    return str(request.url_for("outputs", path=filename))


async def generate_audio_results(
    jobs,
    language: str,
    voice_description: str,
    max_chars_per_chunk: int,
    request: Request | None = None,
):
    results = []

    for job_index, job in enumerate(jobs, start=1):
        chunks = split_text_into_chunks(
            job["text"],
            max_chars=max(300, min(max_chars_per_chunk, 4000)),
        )

        if not chunks:
            continue

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = safe_filename(job["source_name"])

        temp_chunk_paths: list[Path] = []

        for chunk in chunks:
            chunk_name = (
                f"_tmp_{stamp}_job-{job_index:03d}_"
                f"chunk-{chunk.index:04d}_{base}.wav"
            )

            chunk_path = OUTPUTS_DIR / chunk_name

            if os.getenv("USE_MOCK_TTS", "false").lower() == "true":
                make_placeholder_wav(
                    chunk_path,
                    seconds=1.2,
                    frequency=420 + (chunk.index % 8) * 40,
                )
            else:
                generate_qwen_voice_design(
                    text=chunk.text,
                    language=language,
                    voice_description=voice_description,
                    output_path=chunk_path,
                )

            temp_chunk_paths.append(chunk_path)

        final_name = f"{stamp}_job-{job_index:03d}_{base}.wav"
        final_path = OUTPUTS_DIR / final_name

        if len(temp_chunk_paths) == 1:
            temp_chunk_paths[0].replace(final_path)
        else:
            combine_wav_files(temp_chunk_paths, final_path)

            for temp_path in temp_chunk_paths:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

        results.append(
            {
                "source_name": job["source_name"],
                "filename": final_name,
                "url": build_output_url(request, final_name) if request else f"/outputs/{final_name}",
                "characters": len(job["text"]),
                "chunks": len(chunks),
                "language": language,
                "voice_description": voice_description,
            }
        )

    return results


@app.post("/api/public/generate")
async def public_generate_audio(
    request: Request,
    payload: PublicGenerateRequest,
):
    clean_text = payload.text.strip()

    if not clean_text:
        return JSONResponse(
            status_code=400,
            content={
                "error": "No text supplied. Provide a non-empty text field.",
            },
        )

    jobs = [
        {
            "source_name": "public-api",
            "text": clean_text,
        }
    ]

    results = await generate_audio_results(
        jobs=jobs,
        language=payload.language,
        voice_description=payload.voice_description,
        max_chars_per_chunk=payload.max_chars_per_chunk,
        request=request,
    )

    if not results:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Audio generation failed.",
            },
        )

    return {
        "status": "ok",
        "count": len(results),
        "download_url": results[0]["url"],
        "items": results,
    }
