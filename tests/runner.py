"""Запуск тестов без pytest:  python tests/runner.py [фильтр по имени]

Подставляет те же фикстуры (app, client, make, tmp_path), что и conftest.py.
"""
import inspect
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
import test_e2e  # noqa: E402


def run(only: str = "") -> int:
    failed = 0
    tests = [(n, f) for n, f in vars(test_e2e).items() if n.startswith("test_") and callable(f) and only in n]
    for name, fn in tests:
        with tempfile.TemporaryDirectory() as d:
            app = helpers.make_app(Path(d))
            client = app.test_client()
            pool = {"app": app, "client": client, "make": helpers.make_factory(client, app), "tmp_path": Path(d)}
            try:
                fn(**{p: pool[p] for p in inspect.signature(fn).parameters})
                print(f"PASS  {name}")
            except Exception:
                failed += 1
                print(f"FAIL  {name}")
                traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if run(sys.argv[1] if len(sys.argv) > 1 else "") else 0)
