"""The chart service's HTTP and websocket routes, by area. Each module's register(app, *, ...) adds its routes to the
app create_app (charts/server.py) builds, in the order they always had; what a route reads is passed in by keyword."""
from . import common, depthbook, drawings, events, journal, layouts, pages, settings, ws  # noqa: F401
