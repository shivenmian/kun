"""LiteLLM wrapper. Provider-agnostic; model id comes from mission.yaml.

Reads ANTHROPIC_API_KEY from backend/.env or the environment. If no key (or
litellm is unavailable), ``available()`` is False and the loop uses the
heuristic path — so the build/demo can run end-to-end with no key.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional


def _load_dotenv() -> None:
    """Minimal .env loader (no python-dotenv dep). Looks at backend/.env."""
    here = os.path.dirname(__file__)
    candidates = [
        os.path.abspath(os.path.join(here, "..", "..", ".env")),  # backend/.env
        os.path.abspath(os.path.join(here, "..", "..", "..", ".env")),  # repo/.env
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    os.environ.setdefault(k, v)
        except OSError:
            pass


_load_dotenv()


class LLMClient:
    def __init__(self, model: str):
        self.model = model
        self._litellm = None
        try:
            import litellm  # noqa

            self._litellm = litellm
        except Exception:  # pragma: no cover
            self._litellm = None

    def available(self) -> bool:
        if self._litellm is None:
            return False
        # Anthropic models need a key; allow other providers if their key exists.
        return bool(
            os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )

    def complete_json(
        self, system: str, user: str, max_tokens: int = 800
    ) -> Optional[Dict[str, Any]]:
        """Call the model and parse a single JSON object from the reply.

        Returns the parsed dict, or None on any failure (caller falls back).
        """
        if not self.available():
            return None
        try:
            resp = self._litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0.4,
            )
            text = resp["choices"][0]["message"]["content"]
            return _extract_json(text)
        except Exception:
            return None


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    # Strip ```json fences if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    # Grab the first balanced {...} block.
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None
