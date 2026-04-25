FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    ffmpeg \
    sox \
    libsox-fmt-all \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN python3.12 -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

RUN python -m pip install --upgrade pip setuptools wheel

COPY requirements.txt .

# Install app dependencies first.
RUN pip install -r requirements.txt


COPY app ./app

ENV HOST=0.0.0.0
ENV PORT=7811

ENV USE_MOCK_TTS=false
ENV QWEN_TTS_DEVICE=cuda:0
ENV QWEN_TTS_DTYPE=bfloat16
ENV QWEN_TTS_FLASH_ATTENTION=false
ENV QWEN_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign

EXPOSE 7811

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7811"]