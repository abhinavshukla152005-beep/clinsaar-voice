import json
import os
import unittest

import gnani_client


class GnaniClientTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self._original_post = gnani_client._post
        os.environ["GNANI_API_KEY"] = "test-key"

    def tearDown(self):
        gnani_client._post = self._original_post

    def _fake_post(self, url, body, content_type, timeout=60):
        self.calls.append({"url": url, "body": body, "ctype": content_type})
        return self.response

    def test_transcribe_parses_literal_transcript(self):
        self.response = (
            "application/json",
            json.dumps({
                "success": True,
                "transcript": "3", "model": "prisma-v2.5", "end_to_end_latency": 0.163,
                "output": {"literal": "मुझे तीन दिन से बुखार है।"},
            }).encode(),
        )
        gnani_client._post = self._fake_post
        result = gnani_client.transcribe(b"RIFFaudio", language="hi-IN")
        self.assertEqual(result["transcript"], "मुझे तीन दिन से बुखार है।")
        self.assertEqual(result["model"], "prisma-v2.5")
        self.assertEqual(result["latency_ms"], 163)
        call = self.calls[0]
        self.assertEqual(call["url"], gnani_client.STT_URL)
        self.assertIn(b'name="language_code"', call["body"])
        self.assertIn(b"hi-IN", call["body"])
        self.assertIn(b'filename="speech.wav"', call["body"])
        self.assertIn(b"RIFFaudio", call["body"])

    def test_transcribe_surfaces_api_failure(self):
        self.response = ("application/json", json.dumps({"success": False, "message": "quota"}).encode())
        gnani_client._post = self._fake_post
        with self.assertRaises(gnani_client.GnaniError) as ctx:
            gnani_client.transcribe(b"RIFFaudio")
        self.assertIn("quota", str(ctx.exception))

    def test_transcribe_rejects_empty_audio(self):
        with self.assertRaises(gnani_client.GnaniError):
            gnani_client.transcribe(b"")

    def test_synthesise_sends_timbre_payload_and_returns_audio(self):
        self.response = ("audio/wav", b"RIFFwavdata")
        gnani_client._post = self._fake_post
        audio = gnani_client.synthesise("नमस्ते", language="hi-IN")
        self.assertEqual(audio, b"RIFFwavdata")
        payload = json.loads(self.calls[0]["body"])
        self.assertEqual(payload["model"], "timbre-v2.5")
        self.assertEqual(payload["voice"], gnani_client.DEFAULT_VOICE)
        self.assertEqual(payload["audio_config"]["container"], "wav")
        self.assertEqual(payload["language"], "hi-IN")

    def test_synthesise_rejects_json_error_body(self):
        self.response = ("application/json", b'{"success":false,"message":"No audio generated"}')
        gnani_client._post = self._fake_post
        with self.assertRaises(gnani_client.GnaniError):
            gnani_client.synthesise("test")

    def test_synthesise_truncates_long_text(self):
        self.response = ("audio/wav", b"RIFFwavdata")
        gnani_client._post = self._fake_post
        gnani_client.synthesise("x" * 5000)
        self.assertEqual(len(json.loads(self.calls[0]["body"])["text"]), 800)

    def test_missing_key_raises(self):
        os.environ["GNANI_API_KEY"] = ""
        with self.assertRaises(gnani_client.GnaniError):
            gnani_client.api_key()


if __name__ == "__main__":
    unittest.main()
