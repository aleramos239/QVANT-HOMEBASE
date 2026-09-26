"""The strategy contract: the input schema and its validation."""
from __future__ import annotations

import pytest

from homebase.strategies.base import Input, Strategy, resolve_inputs


class Demo(Strategy):
    id, name, root = "demo", "Demo", "NQ"

    @classmethod
    def inputs(cls):
        return [Input("n", "N", "int", 3, 1, 10, 1)]


def test_resolve_inputs_validates_and_never_clamps():
    schema = [Input("n", "N", "int", 3, 1, 10, 1), Input("x", "X", "float", 1.5, 0.0, 2.0),
              Input("b", "B", "bool", False), Input("c", "C", "choice", "a", choices=("a", "b"))]
    assert resolve_inputs(schema, None) == {"n": 3, "x": 1.5, "b": False, "c": "a"}
    assert resolve_inputs(schema, {"n": 4.0, "x": 2}) == {"n": 4, "x": 2.0, "b": False, "c": "a"}
    for bad, msg in (({"zz": 1}, "unknown input"), ({"n": 11}, "within"), ({"n": 2.5}, "whole"),
                     ({"x": "1"}, "number"), ({"b": 1}, "true/false"), ({"c": "z"}, "one of"),
                     ({"n": True}, "number")):
        with pytest.raises(ValueError, match=msg):
            resolve_inputs(schema, bad)


def test_a_strategy_resolves_its_params_and_describes_itself():
    assert Demo().p == {"n": 3} and Demo({"n": 7}).p == {"n": 7}
    with pytest.raises(ValueError):
        Demo({"n": 0})
    d = Demo.describe()
    assert d == {"id": "demo", "name": "Demo", "root": "NQ", "session_window": ["09:25", "16:00"],
                 "bar_minutes": 0,
                 "inputs": [{"key": "n", "label": "N", "type": "int", "default": 3, "min": 1,
                             "max": 10, "step": 1, "choices": []}]}
    assert Demo.placement_ms == 85 and Demo().times() == [] and Demo().trades_on(None) is True
