"""Optional LLM hook (disabled unless ANTHROPIC_API_KEY is set and --llm is passed).

Only ambiguous request texts reach it.  Every call is cached on disk and counted in a
usage ledger so the usage report can state measured numbers.  No key is ever stored.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request

from .common import CACHE_DIR

MODEL = os.environ.get("AUDIT_LLM_MODEL", "claude-haiku-5-5")
CACHE_FILE = CACHE_DIR / "llm_cache.json"
LEDGER_FILE = CACHE_DIR / "usage_ledger.json"
PROMPT_FILE = CACHE_DIR.parent / "prompts" / "intent_classifier.md"


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class LLM:
    def __init__(self):
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        self.cache = _load(CACHE_FILE, {})
        self.ledger = _load(LEDGER_FILE, {"model": MODEL, "calls": 0, "input_tokens": 0, "output_tokens": 0})

    @property
    def available(self) -> bool:
        return bool(self.key)

    def is_deletion_request(self, text: str) -> bool:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if h not in self.cache:
            self.cache[h] = self._ask(PROMPT_FILE.read_text(encoding="utf-8").replace("{request_text}", text))
            CACHE_FILE.write_text(json.dumps(self.cache, indent=1), encoding="utf-8")
        return self.cache[h].strip().upper().startswith("DELETE")

    def _ask(self, prompt: str) -> str:
        if not self.key:
            return "NOT_DELETE"
        body = json.dumps({"model": MODEL, "max_tokens": 5,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        self.ledger["calls"] += 1
        self.ledger["input_tokens"] += data["usage"]["input_tokens"]
        self.ledger["output_tokens"] += data["usage"]["output_tokens"]
        LEDGER_FILE.write_text(json.dumps(self.ledger, indent=1), encoding="utf-8")
        return data["content"][0]["text"]
