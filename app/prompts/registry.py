"""Versioned prompt templates loaded from on-disk files with content hashes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PromptStatus = Literal["draft", "approved", "deprecated"]
TEMPLATES_ROOT = Path(__file__).resolve().parent / "templates"


@dataclass(frozen=True)
class PromptTemplate:
    """Immutable approved (or draft) prompt version."""

    prompt_id: str
    version: str
    description: str
    owner: str
    status: PromptStatus
    system_instructions: str
    developer_instructions: str
    compatible_models: tuple[str, ...]
    content_hash: str
    change_history: tuple[dict[str, str], ...] = ()


def _hash_content(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


class PromptRegistry:
    """
    On-disk prompt inventory.

    Trust assumption: only templates with status=approved may be used by the
    model gateway. Retrieved document text must never be written into these files
    or concatenated into system/developer instructions at runtime.
    """

    def __init__(self, templates_root: Path | None = None) -> None:
        self._root = templates_root or TEMPLATES_ROOT
        self._prompts: dict[str, PromptTemplate] = {}
        self._load()

    def _load(self) -> None:
        if not self._root.exists():
            raise FileNotFoundError(f"Prompt templates root missing: {self._root}")
        for metadata_path in sorted(self._root.glob("*/v*/metadata.json")):
            meta = json.loads(metadata_path.read_text(encoding="utf-8"))
            version_dir = metadata_path.parent
            system = (version_dir / "system.md").read_text(encoding="utf-8").strip()
            developer = (
                version_dir / "developer.md"
            ).read_text(encoding="utf-8").strip()
            prompt = PromptTemplate(
                prompt_id=meta["prompt_id"],
                version=meta["version"],
                description=meta["description"],
                owner=meta["owner"],
                status=meta["status"],
                system_instructions=system,
                developer_instructions=developer,
                compatible_models=tuple(meta.get("compatible_models", [])),
                content_hash=_hash_content(system, developer),
                change_history=tuple(meta.get("change_history", [])),
            )
            self._prompts[prompt.prompt_id] = prompt

    def get(self, prompt_id: str, *, require_approved: bool = False) -> PromptTemplate:
        prompt = self._prompts.get(prompt_id)
        if prompt is None:
            raise KeyError(f"Unknown prompt: {prompt_id}")
        if require_approved and prompt.status != "approved":
            raise PermissionError(f"Prompt {prompt_id} is not approved")
        return prompt

    def list(self) -> list[PromptTemplate]:
        return list(self._prompts.values())
