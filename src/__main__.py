"""Run Phase 1 acquisition and validation: python -m src"""

from __future__ import annotations

import sys

from src.validation.validate import main

if __name__ == "__main__":
    sys.exit(main())
