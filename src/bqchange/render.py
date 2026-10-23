"""Jinja rendering of migration scripts, with an optional shared modules folder."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import jinja2

from bqchange.config import Config, env_var


class Renderer:
    def __init__(self, root_folder: Path, modules_folder: Path | None = None):
        loaders: list[jinja2.BaseLoader] = [jinja2.FileSystemLoader(root_folder)]
        if modules_folder:
            loaders.append(
                jinja2.PrefixLoader({"modules": jinja2.FileSystemLoader(modules_folder)})
            )
        self._environment = jinja2.Environment(
            loader=jinja2.ChoiceLoader(loaders),
            undefined=jinja2.StrictUndefined,
            autoescape=False,
            keep_trailing_newline=False,
        )
        self._environment.globals["env_var"] = env_var

    @classmethod
    def from_config(cls, config: Config) -> Renderer:
        return cls(config.root_folder, config.modules_folder)

    def source(self, relative_path: str) -> str:
        """Raw template text: identical in every environment."""
        loader = self._environment.loader
        text, _, _ = loader.get_source(self._environment, relative_path)
        return text.strip()

    def render(self, relative_path: str, variables: dict[str, Any]) -> str:
        content = self._environment.get_template(relative_path).render(**variables).strip()
        if not content:
            raise ValueError(f"{relative_path} rendered to an empty script")
        return content


def checksum(content: str) -> str:
    return hashlib.sha224(content.encode("utf-8")).hexdigest()
