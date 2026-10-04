"""Pilot parameterisation: NQ defaults unchanged, ES via PP_PILOT / --pilot (constants, paths, draft names, cost mix)."""
import os
import subprocess
import sys
from pathlib import Path

R = Path(__file__).resolve().parent
REPO = R.parents[2]


def py(code: str, env=None, argv=()) -> str:
    e = {**os.environ, "PYTHONPATH": str(REPO)}
    e.pop("PP_PILOT", None), e.pop("PP_DIR", None), e.pop("PP_ROOT", None)
    e.update(env or {})
    out = subprocess.run([sys.executable, "-c", "import sys; sys.argv=['x',*sys.argv[1:]]\n" + code, *argv], cwd=R, env=e,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-800:]
    return out.stdout.strip()


CODE = ("import evalcore as E, a3_pass2 as A\n"
        "print(E.ROOT, E.D.name, E.TICK_USD, E.PT_USD, E.DRAFT_PREFIX, round(A.cost_mix(10, 10.0), 6), round(A.cost_mix(20, 10.0), 6), sys.argv[1:])")


def test_nq_defaults_unchanged():
    root, d, tick, pt, pre, c10, c20, av = py(CODE).split(" ", 7)
    assert (root, d, tick, pt, pre) == ("NQ", R.name, "0.5", "2.0", "draft_pp_")
    assert abs(float(c10) - (4 + 2 * 5.0) / (20.0 * 10.0)) < 1e-9          # 1 NQ: $14 RT / ($20 x 10 pts)
    assert abs(float(c20) - (2 * 14.0) / (2 * 20.0 * 10.0)) < 1e-9


def test_es_constants_paths_and_cost_mix():
    root, d, tick, pt, pre, c10, c20, av = py(CODE, {"PP_PILOT": "es"}).split(" ", 7)
    assert (root, d, tick, pt, pre) == ("ES", "2026-09-30-es", "1.25", "5.0", "draft_pp_es_")
    assert abs(float(c10) - (4 + 2 * 12.5) / (50.0 * 10.0)) < 1e-9         # 1 ES: $29 RT / ($50 x 10 pts)
    assert abs(float(c20) - (2 * 29.0) / (2 * 50.0 * 10.0)) < 1e-9


def test_pilot_flag_is_stripped_from_argv_and_equals_env():
    a = py(CODE, argv=["--pilot", "es", "orb"])
    assert a.startswith("ES 2026-09-30-es 1.25 5.0 draft_pp_es_") and a.endswith("['orb']")
    b = py(CODE, argv=["--pilot=es", "--dir", str(R), "-q"])
    assert b.startswith("ES " + R.name) and b.endswith("['-q']")


def test_es_drafts_are_generated_with_root_es_and_own_ids():
    import gen_drafts as G
    import pilot
    assert pilot.NAME == "nq"
    news, rolls = {}, ["2024-03-11"]
    tpl = (R / "template.py").read_text()
    code = G.gen("orb", tpl, news, rolls)
    assert 'root = "NQ"' in code and "draft_pp_orb" in code and "__ROOT__" not in code
    out = py("import gen_drafts as G\n"
             "tpl=(G.R/'template.py').read_text()\n"
             "c=G.gen('orb', tpl, {}, ['2024-03-11'])\n"
             "print('root = \"ES\"' in c, 'id = \"draft_pp_es_orb\"' in c, 'PPEsOrb' in c, '__' in c.split('class ')[1].split(':')[0])",
             {"PP_PILOT": "es"})
    assert out == "True True True False"
