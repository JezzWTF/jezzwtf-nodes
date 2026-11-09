import os
import sys

PACK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PACK_ROOT not in sys.path:
    sys.path.insert(0, PACK_ROOT)
