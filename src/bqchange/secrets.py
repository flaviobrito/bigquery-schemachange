"""Secret masking.

Any variable whose name contains "secret" (case-insensitive), or that sits under a
key named "secrets", is treated as a secret. Its value is replaced by "****" in
logs, rendered output, run summaries and error messages, as schemachange does.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

MASK = "****"


def collect_secrets(variables: Mapping[str, Any], inside_secrets: bool = False) -> set[str]:
    """String values of secret variables, searched recursively."""
    found: set[str] = set()
    for key, value in variables.items():
        is_secret = inside_secrets or "secret" in str(key).lower()
        if isinstance(value, Mapping):
            found |= collect_secrets(value, is_secret or str(key).lower() == "secrets")
        elif is_secret and value not in (None, ""):
            found.add(str(value))
    return found


class Redactor:
    def __init__(self, secrets: Iterable[str] = ()):
        # Longest first, so a secret containing another one is masked whole.
        self._secrets = sorted({s for s in secrets if s}, key=len, reverse=True)

    def __call__(self, text: object) -> str:
        result = str(text)
        for secret in self._secrets:
            result = result.replace(secret, MASK)
        return result

    def install(self) -> None:
        """Mask secrets in every log record emitted from now on."""
        redact = self

        class _Filter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                record.msg = redact(record.getMessage())
                record.args = ()
                return True

        for handler in logging.getLogger().handlers:
            handler.addFilter(_Filter())


NO_SECRETS = Redactor()
