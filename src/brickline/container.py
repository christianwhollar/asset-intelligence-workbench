"""Container entry point. Published host ports must be restricted by the operator."""

import os

from .api import create_app

app = create_app(demo=os.environ.get("BRICKLINE_DEMO") == "1")
