"""Test setup: build_skin.py is imported from the repo root, and nothing touches a real EverQuest folder."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
