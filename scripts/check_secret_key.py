#!/usr/bin/env python3
"""Check that the signing-key guard rejects every key this repository ships.

Why this is a script and not only a test
----------------------------------------
`backend/tests/test_auth.py` contains the same assertion, but it can never run.
The API image is built with `context: ./backend`, and `.env.example` lives at
the repository root — outside that context and outside the bind mount — so
inside the container the file does not exist and the test skips. A skipped test
looks like a passing one in `pytest -q` output.

That matters more than usual here, because the bug this guards against is
exactly a guard that does not fire. `backend/app/core/config.py` declares
`secret_key` with one placeholder as a field default, while `.env.example`
overrides it with a different string. Copying `.env.example` to `.env` — the
documented first step — therefore produces a key the field default never sees.
A guard that knew only the field default would appear to cover the problem
while letting the realistic case straight through.

So this runs on the host, where the file is visible, and it reads the constants
out of `security.py` rather than restating them, so the two cannot drift.

Usage
-----
    python3 scripts/check_secret_key.py

Exit status is 0 if every shipped key is rejected, 1 otherwise. It also reports
what the live `.env` currently holds, which is advisory: a placeholder there is
only a warning while `APP_ENV=development`, and a hard refusal to issue tokens
once it is `production`.
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SECURITY = ROOT / "backend" / "app" / "core" / "security.py"

_CONSTANTS = {
    "INSECURE_DEFAULT_KEY",
    "INSECURE_EXAMPLE_KEY",
    "_PUBLISHED_KEYS",
    "_MIN_KEY_LENGTH",
}
_FUNCTION = "insecure_key_reason"


def load_checker():  # noqa: ANN201 - returns the extracted function
    """Pull `insecure_key_reason` and its constants out of `security.py`.

    Importing the module directly would drag in pydantic, passlib and the
    settings object, none of which are installed on the host. Extracting the
    handful of statements the check needs keeps this runnable from a clean
    checkout with nothing but the standard library — which is the whole point
    of a script you can run before the stack is up.
    """
    tree = ast.parse(SECURITY.read_text())
    kept: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in _CONSTANTS
            for target in node.targets
        ):
            kept.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == _FUNCTION:
            kept.append(node)

    namespace: dict[str, object] = {}
    module = ast.Module(body=kept, type_ignores=[])
    exec(compile(module, str(SECURITY), "exec"), namespace)  # noqa: S102

    checker = namespace.get(_FUNCTION)
    if checker is None:
        raise SystemExit(
            f"{_FUNCTION} is no longer defined in {SECURITY.relative_to(ROOT)}; "
            "this check needs updating"
        )
    return checker


def secret_keys(path: pathlib.Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.split("=", 1)[1].split("#")[0].strip()
        for line in path.read_text().splitlines()
        if line.startswith("SECRET_KEY=")
    ]


def main() -> int:
    checker = load_checker()

    example = ROOT / ".env.example"
    shipped = secret_keys(example)
    if not shipped:
        print("FAIL  no SECRET_KEY line in .env.example — has it been renamed?")
        return 1

    failures = 0
    print(f"Checking {len(shipped)} key(s) published in .env.example")
    for key in shipped:
        reason = checker(key)
        if reason is None:
            failures += 1
            print(f"  FAIL  {key!r}")
            print("        ships in .env.example but the guard would accept it.")
            print("        Add it to _PUBLISHED_KEYS in backend/app/core/security.py.")
        else:
            print(f"  ok    rejected — {reason}")

    live = secret_keys(ROOT / ".env")
    if live:
        reason = checker(live[0])
        print("\nYour live .env:")
        if reason is None:
            print("  ok    a real key; safe to set APP_ENV=production")
        else:
            print(f"  warn  unusable in production — {reason}")
            print("        Fine while APP_ENV=development. Replace it with")
            print("        `openssl rand -hex 32` before deploying.")

    print("\nPASS" if not failures else f"\nFAILED ({failures})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
