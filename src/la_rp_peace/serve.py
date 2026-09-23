"""One command for the whole app: build the UI, then serve it and the API on one port.

uv run python -m la_rp_peace.serve            # install + build UI, start on :8000
uv run python -m la_rp_peace.serve --no-build # reuse the last UI build
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import uvicorn

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _node_dir() -> Path:
    """First directory on PATH with Node.js 20+ (older ones cannot run the build)."""
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        node = shutil.which("node", path=entry)
        if node is None:
            continue
        version = subprocess.run([node, "--version"], capture_output=True, text=True, check=False).stdout  # noqa: S603
        if version.startswith("v") and int(version[1:].split(".")[0]) >= 20:
            return Path(node).parent
    sys.exit("Нужен Node.js 20+ в PATH для сборки интерфейса")


def _pnpm(node_dir: Path) -> list[str]:
    """Return pnpm itself when installed, otherwise the one npx of that Node fetches."""
    if found := shutil.which("pnpm", path=str(node_dir)):
        return [found]
    npx = shutil.which("npx", path=str(node_dir))
    if npx is None:
        sys.exit(f"В {node_dir} нет npx")
    return [npx, "--yes", "--package=pnpm", "--", "pnpm"]


def build_ui() -> None:
    """Install the frontend dependencies and build the static SPA into frontend/build."""
    node_dir = _node_dir()
    env = {**os.environ, "PATH": f"{node_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    pnpm = _pnpm(node_dir)
    subprocess.run([*pnpm, "install", "--frozen-lockfile"], cwd=FRONTEND, env=env, check=True)  # noqa: S603
    subprocess.run([*pnpm, "build"], cwd=FRONTEND, env=env, check=True)  # noqa: S603


def main() -> None:
    """Build the UI unless --no-build, then serve UI and API with uvicorn."""
    parser = argparse.ArgumentParser(description="Build the UI and start the app")
    parser.add_argument("--no-build", action="store_true", help="skip pnpm install/build")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not args.no_build:
        build_ui()
    Path("data").mkdir(exist_ok=True)
    print(f"App: http://{args.host}:{args.port}/  API docs: http://{args.host}:{args.port}/docs", flush=True)
    uvicorn.run("la_rp_peace.api.app:create_app", factory=True, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
