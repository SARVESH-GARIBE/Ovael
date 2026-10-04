"""Makes the `ovael` package importable from tests/ without requiring
an editable install. Adds the repo root (this file's directory) to
sys.path, the standard dependency-free way to make a flat-layout
package importable by pytest.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
