"""LLM client for NZ Agent — Google Gemini via its REST API (stdlib only).

With a key (NZ_GEMINI_API_KEY) it calls the real Gemini API. Without one
it runs in clearly labelled MOCK mode: every reply starts with
``[MOCK MODE — no API key]`` so a mock answer can never be mistaken for
a real model answer.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

MOCK_PREFIX = "[MOCK MODE — no API key]"


class GeminiClient:
    def __init__(self, api_key: str = "", model: str = "gemini-2.0-flash", timeout_seconds: int = 30) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def is_mock(self) -> bool:
        return not self.api_key

    def generate(self, prompt: str) -> str:
        if self.is_mock:
            return self._mock_generate(prompt)
        return self._real_generate(prompt)

    def _mock_generate(self, prompt: str) -> str:
        # Deterministic, honest mock: echo the request back, labelled.
        first_line = next((ln.strip() for ln in prompt.splitlines() if ln.strip()), "")
        return (
            f"{MOCK_PREFIX} I received your message about: {first_line[:120]}. "
            "Set NZ_GEMINI_API_KEY to get real Gemini answers. "
            "I can still use tools — ask me the time, or to remember a fact."
        )

    def _real_generate(self, prompt: str) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            return f"Error: Gemini API returned HTTP {exc.code}: {detail}"
        except (urllib.error.URLError, TimeoutError) as exc:
            return f"Error: could not reach Gemini API: {exc}."
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError):
            return "Error: unexpected response from Gemini API."
        return text.strip() or "Error: Gemini returned an empty response."
