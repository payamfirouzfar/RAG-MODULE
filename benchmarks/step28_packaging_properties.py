"""Step 28 benchmark: packaging-related properties for regression
visibility -- wheel/sdist build time, clean-install time, import time,
and artifact size.

Run from the repository root with:
    python benchmarks/step28_packaging_properties.py

No threshold is asserted (matching this project's established benchmark
discipline, e.g. Step 18/23/27): this measures, it does not judge. The
purpose is catching an accidental regression (e.g. a dependency
accidentally added that slows import, or a stray large file bloating
the wheel), not optimizing packaging performance for its own sake.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _time(label: str, fn) -> float:
    start = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - start
    print(f"{label:40s} {elapsed:8.3f}s")
    return elapsed


def main() -> None:
    print("Step 28 packaging properties benchmark\n")

    with tempfile.TemporaryDirectory() as tmp:
        dist_dir = Path(tmp) / "dist"

        _time(
            "wheel + sdist build time",
            lambda: subprocess.run(
                [sys.executable, "-m", "build", "--outdir", str(dist_dir), str(REPO_ROOT)],
                capture_output=True,
                text=True,
                check=True,
                timeout=300,
            ),
        )

        wheel = next(dist_dir.glob("*.whl"))
        sdist = next(dist_dir.glob("*.tar.gz"))
        print(f"{'wheel size':40s} {wheel.stat().st_size / 1024:8.1f} KB")
        print(f"{'sdist size':40s} {sdist.stat().st_size / 1024:8.1f} KB")

        env_dir = Path(tmp) / "venv"
        _time("clean venv creation time", lambda: venv.create(env_dir, with_pip=True))

        python_path = (
            env_dir / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else env_dir / "bin" / "python"
        )

        _time(
            "clean install time (wheel only)",
            lambda: subprocess.run(
                [str(python_path), "-m", "pip", "install", "--quiet", str(wheel)],
                capture_output=True,
                text=True,
                check=True,
                timeout=300,
            ),
        )

        import_time_code = (
            "import time; start = time.perf_counter(); import ragtorch; "
            "print(f'{(time.perf_counter() - start) * 1000:.2f}')"
        )
        result = subprocess.run(
            [str(python_path), "-c", import_time_code],
            capture_output=True,
            text=True,
            cwd=str(Path(tmp)),
            check=True,
            timeout=30,
        )
        print(f"{'import ragtorch time (clean install)':40s} {result.stdout.strip():>8s} ms")

    print(
        "\nNo threshold asserted -- this measures packaging properties for "
        "regression visibility only, not a performance target."
    )


if __name__ == "__main__":
    main()
