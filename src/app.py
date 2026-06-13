#!/usr/bin/env python3
"""Application entry point"""
import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import init_gi  # noqa: F401, E402
from main import RyzenadjApp  # noqa: E402

# Initialize and run the app

if __name__ == "__main__":
    app = RyzenadjApp()
    sys.exit(app.run(sys.argv))

