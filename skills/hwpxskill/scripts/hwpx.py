#!/usr/bin/env python3
"""설치 없이 스킬 폴더에서 바로 실행: python scripts/hwpx.py <명령> ..."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hwpxskill.cli import main  # noqa: E402

sys.exit(main())
