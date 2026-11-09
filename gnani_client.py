"""Gnani Speech API client — Prisma (STT) and Timbre (TTS).

Stdlib only. The API key never leaves the server: it is read from `.env` (or the
environment) and sent only in the `X-API-Key-ID` header.
"""
import json
import os
import urllib.error
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))

STT_URL = "https://api.vachana.ai/stt/v3"
TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"
STT_MODEL = "prisma-v2.5"
TTS_MODEL = "timbre-v2.5"
DEFAULT_VOICE = "Nalini"
USER_AGENT = "ClinSaarVoice/1.0 (+https://github.com/abhinavshukla152005)"


class GnaniError(RuntimeError):
    """Upstream Gnani failure, safe to surface to the client."""


def _load_env():
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_env()


def api_key():
    key = os.environ.get("GNANI_API_KEY", "").strip()
    if not key:
        raise GnaniError("GNANI_API_KEY is not configured")
    return key


def _multipart(fields, files):
    boundary = "clinsaar" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    for name, (filename, payload, ctype) in files.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n".encode()
        )
        chunks.append(payload)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return boundary, b"".join(chunks)


def _post(url, body, content_type, timeout=60):
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "X-API-Key-ID": api_key(),
            "Content-Type": content_type,
            # The API sits behind Cloudflare, which rejects the default urllib agent.
            "User-Agent": USER_AGENT,
            "Accept": "application/json, audio/wav",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "replace")
        raise GnaniError(f"Gnani API {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GnaniError(f"Gnani API unreachable: {exc.reason}") from exc


def transcribe(audio, filename="speech.wav", content_type="audio/wav", language="hi-IN"):
    """Speech → text with Prisma. Returns transcript, model and latency."""
    if not audio:
        raise GnaniError("empty audio")
    boundary, body = _multipart(
        {"language_code": language},
        {"audio_file": (filename, audio, content_type)},
    )
    ctype, raw = _post(STT_URL, body, f"multipart/form-data; boundary={boundary}")
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise GnaniError("Gnani STT returned a non-JSON body") from exc
    if not payload.get("success"):
        raise GnaniError(payload.get("message") or "Gnani STT failed")
    output = payload.get("output") or {}
    return {
        "transcript": output.get("literal") or payload.get("transcript") or "",
        "model": payload.get("model") or STT_MODEL,
        "latency_ms": int(round(float(payload.get("end_to_end_latency") or 0) * 1000)),
    }


def synthesise(text, language="hi-IN", voice=DEFAULT_VOICE, speed=1.0):
    """Text → WAV bytes with Timbre."""
    text = (text or "").strip()
    if not text:
        raise GnaniError("empty text")
    payload = {
        "text": text[:800],
        "voice": voice,
        "model": TTS_MODEL,
        "language": language,
        "speed": speed,
        "audio_config": {
            "sample_rate": 24000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }
    ctype, raw = _post(TTS_URL, json.dumps(payload).encode(), "application/json")
    if not raw:
        raise GnaniError("Gnani TTS returned no audio")
    if not ctype.startswith("audio/"):
        detail = raw[:300].decode("utf-8", "replace")
        raise GnaniError(f"Gnani TTS failed: {detail}")
    return raw
