import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import gnani_client
from extract import extract, validate

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_AUDIO_BYTES = 12 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(ROOT, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/health":
            self._send(200, json.dumps({
                "ok": True,
                "stt": {"provider": "gnani", "model": gnani_client.STT_MODEL},
                "tts": {"provider": "gnani", "model": gnani_client.TTS_MODEL},
                "key_configured": bool(os.environ.get("GNANI_API_KEY")),
            }))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/transcribe":
                self._transcribe(parse_qs(parsed.query))
            elif parsed.path == "/extract":
                self._extract()
            elif parsed.path == "/speak":
                self._speak()
            else:
                self._send(404, json.dumps({"error": "not found"}))
        except gnani_client.GnaniError as exc:
            self._send(502, json.dumps({"error": str(exc)}))
        except Exception as exc:  # boundary: untrusted client input
            self._send(400, json.dumps({"error": str(exc)}))

    def _transcribe(self, query):
        audio = self._body()
        if not audio:
            self._send(400, json.dumps({"error": "empty audio body"}))
            return
        if len(audio) > MAX_AUDIO_BYTES:
            self._send(413, json.dumps({"error": "audio too large"}))
            return
        language = (query.get("lang") or ["hi-IN"])[0]
        ctype = self.headers.get("Content-Type") or "audio/wav"
        name = "speech.webm" if "webm" in ctype else "speech.wav"
        result = gnani_client.transcribe(audio, filename=name, content_type=ctype, language=language)
        self._send(200, json.dumps(result, ensure_ascii=False))

    def _extract(self):
        payload = json.loads(self._body() or b"{}")
        fields, warnings = extract(payload.get("text", ""))
        fields = validate(fields)
        self._send(200, json.dumps({"fields": fields, "warnings": warnings}, ensure_ascii=False))

    def _speak(self):
        payload = json.loads(self._body() or b"{}")
        audio = gnani_client.synthesise(
            payload.get("text", ""),
            language=payload.get("lang") or "hi-IN",
            voice=payload.get("voice") or gnani_client.DEFAULT_VOICE,
        )
        self._send(200, audio, "audio/wav")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8787"))
    if not os.environ.get("GNANI_API_KEY"):
        print("WARNING: GNANI_API_KEY missing — /transcribe and /speak will return 502")
    print(f"ClinSaar Voice running at http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
