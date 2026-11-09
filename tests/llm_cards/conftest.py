import os
import sys

PACK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PACK_ROOT not in sys.path:
    sys.path.insert(0, PACK_ROOT)

_TESTS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)

import v3_helpers  # noqa: E402

v3_helpers.install_default_hidden()
