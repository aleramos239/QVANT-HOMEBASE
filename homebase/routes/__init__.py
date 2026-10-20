"""The desk server's routes, one module per concern (homebase.server.create_app registers them).

Each module has `register(app, *, what it needs)` (the charts modules' pattern): the keyword arguments are exactly
the desk state its routes read, handed over by create_app. The routes land on the app itself, as before. A route module never imports homebase.server."""

from . import accounts, control, lab, records, status, strategies  # noqa: F401  (create_app calls routes.<name>.register)
