"""Vercel Python entry point. Wraps the same Handler the Cloud Run image runs.

vercel.json rewrites every path here, so /, /api/*, /mcp and /static/* all
reach hackheat.http_api.Handler unchanged.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hackheat.http_api import Handler  # noqa: E402


class handler(Handler):  # noqa: N801 — Vercel looks up this exact name
    pass
