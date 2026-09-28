"""Test setup: build_skin.py is imported from the repo root, and nothing touches a real EverQuest folder."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The one character name besides Sebik the repo may hold, and only in tests/, for a scenario that needs a second
# player. tools/release.py reads it from here, so the name appears nowhere else.
SECOND_PLAYER = 'Mera'
