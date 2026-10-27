"""The layouts and the layout order, one set per tab (/api: Charts, /api/bt: Backtest)."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request

from .common import browser_write_ok, read_json, read_json_list, write_json


def register(app, *, route_prefix: str, layouts_path: Path, layout_order_path: Path) -> None:
        """The layouts + layout-order routes, parametrized by prefix and backing files -- registered
        once for /api (the Charts tab) and once for /api/bt (the Backtest tab, 2026-09-28 three-tabs
        plan): each tab's chart layouts are a separate namespace, so writing one never touches the
        other's file on disk. Route bodies identical to before this split."""

        @app.get(f"{route_prefix}/layouts")
        async def get_layouts():
            return read_json(layouts_path)

        @app.put(f"{route_prefix}/layouts/{{name:path}}")
        async def put_layout(name: str, request: Request):
            browser_write_ok(request)
            body = await request.json()
            if not isinstance(body, dict) or not isinstance(body.get("cells"), list):
                raise HTTPException(400, "a layout is {grid, cells: [...]}")
            all_ = read_json(layouts_path)
            all_[name] = body
            write_json(layouts_path, all_)
            return {"ok": True}

        @app.delete(f"{route_prefix}/layouts/{{name:path}}")
        async def delete_layout(name: str, request: Request):
            browser_write_ok(request)
            all_ = read_json(layouts_path)
            all_.pop(name, None)
            write_json(layouts_path, all_)
            return {"ok": True}

        @app.post(f"{route_prefix}/layouts/{{name:path}}/rename")
        async def rename_layout(name: str, request: Request):
            """One atomic dict-key move plus the same temp-file+rename write as every other layouts.json
            write (write_json) -- never a client-side PUT-new-then-DELETE-old, which would leave two copies
            on disk (and no way to tell which is live) if the DELETE leg failed after a successful PUT.
            A crash or a full disk here lands exactly like any other write_json failure: the file on disk is
            untouched (see test_a_failed_rename_leaves_the_saved_layouts_untouched), never half-renamed."""
            browser_write_ok(request)
            body = await request.json()
            new = body.get("to") if isinstance(body, dict) else None
            if not isinstance(new, str) or not new:
                raise HTTPException(400, "a rename is {to: <new name>}")
            # the browser resolves .../. and .../.. as path steps: the PUT/DELETE route would miss it
            if new in (".", ".."):
                raise HTTPException(400, "“.” and “..” cannot be layout names")
            all_ = read_json(layouts_path)
            if name not in all_:
                raise HTTPException(404, f"{name!r} is not a saved layout")
            if new == name:
                return {"ok": True}
            if new in all_:
                raise HTTPException(409, f"a layout named {new!r} already exists")
            all_[new] = all_.pop(name)
            write_json(layouts_path, all_)
            return {"ok": True}

        @app.get(f"{route_prefix}/layout-order")
        async def get_layout_order():
            # a distinct path from .../layouts/{name:path} on purpose -- sharing the prefix would make
            # "order" just another layout name under that route, whichever one FastAPI matched first
            return read_json_list(layout_order_path)

        @app.put(f"{route_prefix}/layout-order")
        async def put_layout_order(request: Request):
            browser_write_ok(request)
            body = await request.json()
            if not isinstance(body, list) or not all(isinstance(x, str) for x in body):
                raise HTTPException(400, "a layout order is a list of names")
            write_json(layout_order_path, body)
            return {"ok": True}
