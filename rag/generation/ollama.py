"""Generation via a local Ollama server.

Nothing leaves the machine. This is the concrete form of the project's data
sovereignty claim, so there is deliberately no cloud fallback anywhere in this
module: if Ollama is unreachable the answer fails, rather than quietly going
somewhere else.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from rag.generation.base import GenerationResult


class OllamaGenerator:
    """Text generation from a local Ollama server."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_name: str = "qwen2.5:7b-instruct-q4_K_M",
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: float = 180.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate(self, prompt: str, system: str | None = None) -> GenerationResult:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                # Low temperature on purpose. This system answers factual
                # questions about an institution; creative variation is a
                # defect here, not a feature.
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        if system:
            payload["system"] = system

        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate", json=payload, timeout=self.timeout
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Ollama generation failed against {self.base_url}: {exc}. "
                f"Check the server is up and `{self.model_name}` is pulled."
            ) from exc

        elapsed_ms = (time.perf_counter() - started) * 1000
        body = response.json()

        return GenerationResult(
            answer=(body.get("response") or "").strip(),
            model_name=self.model_name,
            latency_ms=elapsed_ms,
            prompt_tokens=body.get("prompt_eval_count"),
            completion_tokens=body.get("eval_count"),
            raw={k: v for k, v in body.items() if k != "response"},
        )

    def is_available(self) -> tuple[bool, str]:
        """Check the server is up and this model is pulled.

        Returns a reason rather than raising, so the CLI can print something
        actionable instead of a stack trace.
        """
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return False, f"cannot reach Ollama at {self.base_url}: {exc}"

        available = [m.get("name", "") for m in response.json().get("models", [])]
        if self.model_name not in available:
            return False, (
                f"model '{self.model_name}' is not pulled. Run: "
                f"ollama pull {self.model_name}"
            )
        return True, "ready"
