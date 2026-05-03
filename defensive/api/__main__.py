"""Run the defensive API.

  python -m defensive.api          # binds 127.0.0.1:8788
  DEFENSIVE_API_PORT=9000 python -m defensive.api
"""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    port = int(os.environ.get("DEFENSIVE_API_PORT", "8788"))
    uvicorn.run(
        "defensive.api.server:app",
        host="127.0.0.1",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
