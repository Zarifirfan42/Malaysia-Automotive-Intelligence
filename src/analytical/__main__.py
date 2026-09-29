"""Rebuild the DuckDB analytical layer: python -m src.analytical"""

from __future__ import annotations

import sys

from src.analytical.build import main

if __name__ == "__main__":
    sys.exit(main())
