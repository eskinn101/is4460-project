from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI


def _api_key() -> str | None:
	return os.getenv("MODERATION_AI_API_KEY") or os.getenv("OPENAI_API_KEY")


def _base_url() -> str | None:
	return os.getenv("MODERATION_AI_BASE_URL") or os.getenv("OPENAI_BASE_URL")


def _model() -> str:
	return os.getenv("MODERATION_AI_MODEL", "gpt-4o-mini")


def _client() -> OpenAI | None:
	api_key = _api_key()
	if not api_key:
		return None

	client_kwargs: dict[str, Any] = {"api_key": api_key}
	base_url = _base_url()
	if base_url:
		client_kwargs["base_url"] = base_url
	return OpenAI(**client_kwargs)


def _extract_json(text: str) -> dict[str, Any]:
	cleaned = text.strip()
	if not cleaned:
		return {}

	if cleaned.startswith("```"):
		cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
		cleaned = re.sub(r"\s*```$", "", cleaned)

	try:
		parsed = json.loads(cleaned)
		return parsed if isinstance(parsed, dict) else {}
	except json.JSONDecodeError:
		match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
		if not match:
			return {}

		try:
			parsed = json.loads(match.group(0))
			return parsed if isinstance(parsed, dict) else {}
		except json.JSONDecodeError:
			return {}


def generate_json_completion(system_prompt: str, user_prompt: str) -> dict[str, Any]:
	client = _client()
	if client is None:
		return {}

	try:
		response = client.chat.completions.create(
			model=_model(),
			messages=[
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": user_prompt},
			],
			temperature=0.2,
		)
		content = response.choices[0].message.content or ""
	except Exception:
		return {}

	return _extract_json(content)