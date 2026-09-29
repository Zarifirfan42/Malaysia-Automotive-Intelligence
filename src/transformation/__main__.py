"""Run Phase 2 cleaning: python -m src.transformation"""

from __future__ import annotations

import sys

from src.transformation.build import main

if __name__ == "__main__":
    sys.exit(main())
