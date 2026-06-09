"""API access layer.

Each module here speaks one upstream API and returns plain data objects —
no Canvas, no Scene, no registry. Scenes call into this package from their
``fetch`` and map the results into their own display dataclasses, so the
HTTP/parsing logic stays independently testable.

Credentials are resolved by the scenes (config first, then environment).
A ``.env`` file in the working directory is honoured if python-dotenv is
installed.
"""

from __future__ import annotations

try:  # optional: .env support for local development
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass
