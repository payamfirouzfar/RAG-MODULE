"""Clean-install consumer smoke test (Step 25).

Builds a real wheel and sdist via `python -m build`, installs the
built WHEEL into a fresh, isolated virtual environment (never the
repository's own dev venv, never editable/`-e` mode), and verifies the
installed artifact from *outside* the source checkout -- proving the
package actually works for a real consumer, not merely that the
source tree is importable.

Marked `packaging` and excluded from the default test run (see
`pyproject.toml`'s `addopts`) because this is slow (builds artifacts,
creates a venv, installs a package) and belongs to a different test
category than unit/integration tests -- run explicitly:

    pytest -m packaging tests/packaging/

or via the dedicated CI packaging job.
"""

from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

import pytest

pytestmark = pytest.mark.packaging

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the package once for this module's tests and return the
    path to the resulting wheel."""
    dist_dir = tmp_path_factory.mktemp("dist")
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir), str(REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"python -m build failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, found {wheels}"
    return wheels[0]


@pytest.fixture(scope="module")
def clean_env_python(tmp_path_factory: pytest.TempPathFactory, built_wheel: Path) -> Path:
    """Create a fresh venv (no editable install, no dev dependencies)
    and install only the built wheel into it. Returns the path to that
    venv's python executable."""
    env_dir = tmp_path_factory.mktemp("clean_env") / "venv"
    venv.create(env_dir, with_pip=True)

    if sys.platform == "win32":
        python_path = env_dir / "Scripts" / "python.exe"
    else:
        python_path = env_dir / "bin" / "python"

    install = subprocess.run(
        [str(python_path), "-m", "pip", "install", "--quiet", str(built_wheel)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert install.returncode == 0, (
        f"pip install of the built wheel failed:\nstdout:\n{install.stdout}\n"
        f"stderr:\n{install.stderr}"
    )
    return python_path


def _run_in_clean_env(python_path: Path, code: str) -> subprocess.CompletedProcess[str]:
    # cwd=REPO_ROOT.parent avoids accidentally importing the repo's own
    # src/ragtorch via an implicit sys.path entry -- the whole point of
    # this test is verifying the INSTALLED artifact, not the checkout.
    return subprocess.run(
        [str(python_path), "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(REPO_ROOT.parent),
    )


def test_wheel_builds_successfully(built_wheel: Path) -> None:
    assert built_wheel.exists()
    assert built_wheel.suffix == ".whl"


def test_import_ragtorch_from_clean_install(clean_env_python: Path) -> None:
    result = _run_in_clean_env(clean_env_python, "import ragtorch")
    assert result.returncode == 0, result.stderr


def test_installed_version_matches_pyproject(clean_env_python: Path) -> None:
    result = _run_in_clean_env(
        clean_env_python, "import ragtorch; print(ragtorch.__version__, end='')"
    )
    assert result.returncode == 0, result.stderr

    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text()
    version_line = next(
        line for line in pyproject_text.splitlines() if line.strip().startswith("version =")
    )
    expected_version = version_line.split('"')[1]
    assert result.stdout == expected_version


def test_documented_public_api_imports_from_clean_install(clean_env_python: Path) -> None:
    code = (
        "from ragtorch import ("
        "Module, Sequential, Block, RAGModule, ExecutionEngine, "
        "ExecutionContext, EventScope, EventBus, event_bus, "
        "ListenerDeliveryError, CompositionGraph, GraphNode, Connection, "
        "InputPort, OutputPort, is_compatible, check_connection"
        ")"
    )
    result = _run_in_clean_env(clean_env_python, code)
    assert result.returncode == 0, result.stderr


def test_full_all_export_list_imports_from_clean_install(clean_env_python: Path) -> None:
    code = (
        "import ragtorch\n"
        "names = sorted(ragtorch.__all__)\n"
        "names.remove('__version__')\n"
        "exec('from ragtorch import ' + ', '.join(names))\n"
        "print(len(names), end='')\n"
    )
    result = _run_in_clean_env(clean_env_python, code)
    assert result.returncode == 0, result.stderr
    assert int(result.stdout) > 0


def test_installed_package_is_functional_end_to_end(clean_env_python: Path) -> None:
    """Not just importable -- actually runs a small pipeline through
    the installed artifact, proving Module/Sequential execution works
    outside the source checkout."""
    code = (
        "from ragtorch import Module, Sequential\n"
        "\n"
        "class UpperCase(Module):\n"
        "    def forward(self, input):\n"
        "        return input.upper()\n"
        "\n"
        "class Reverse(Module):\n"
        "    def forward(self, input):\n"
        "        return input[::-1]\n"
        "\n"
        "pipeline = Sequential(UpperCase(), Reverse())\n"
        "result = pipeline('hello')\n"
        "assert result == 'OLLEH', result\n"
        "print('OK', end='')\n"
    )
    result = _run_in_clean_env(clean_env_python, code)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "OK"


def test_execution_engine_works_from_clean_install(clean_env_python: Path) -> None:
    """Step 28 gap fix: the prior functional smoke test only exercised
    Module/Sequential -- ExecutionEngine (Run/Trace/Metrics) and the
    evaluation API were never actually run against the installed
    artifact, only imported (test_documented_public_api_imports_from_
    clean_install). This runs ExecutionEngine.execute() for real,
    outside the source checkout."""
    code = (
        "from ragtorch import ExecutionEngine, Module, ObservabilityLevel, RunStatus\n"
        "\n"
        "class Doubler(Module):\n"
        "    def forward(self, input):\n"
        "        return input * 2\n"
        "\n"
        "engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)\n"
        "result = engine.execute(Doubler(), 21)\n"
        "assert result.output == 42, result.output\n"
        "assert result.run.status == RunStatus.SUCCEEDED, result.run.status\n"
        "assert result.trace is not None\n"
        "print('OK', end='')\n"
    )
    result = _run_in_clean_env(clean_env_python, code)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "OK"


def test_evaluation_api_works_from_clean_install(clean_env_python: Path) -> None:
    """Step 28 gap fix: ragtorch.evaluation was never actually exercised
    against the installed artifact, only imported. Runs a real
    Evaluator.evaluate() call outside the source checkout."""
    code = (
        "from ragtorch.evaluation import EvaluationCase, Evaluator, ExactMatch\n"
        "\n"
        "cases = [\n"
        "    EvaluationCase(input=1, expected=1, name='case-1'),\n"
        "    EvaluationCase(input=2, expected=2, name='case-2'),\n"
        "]\n"
        "result = Evaluator([ExactMatch()]).evaluate(lambda x: x, cases)\n"
        "assert result.case_count == 2, result.case_count\n"
        "assert result.error_count == 0, result.error_count\n"
        "assert result.mean('exact_match') == 1.0, result.mean('exact_match')\n"
        "print('OK', end='')\n"
    )
    result = _run_in_clean_env(clean_env_python, code)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "OK"


def test_ragtorch_file_location_is_the_installed_site_packages_not_the_checkout(
    clean_env_python: Path,
) -> None:
    """Directly proves this test exercises the INSTALLED package, not
    an accidental import of the source checkout (e.g. via a stray
    sys.path entry or being run from inside the repo)."""
    result = _run_in_clean_env(
        clean_env_python, "import ragtorch; print(ragtorch.__file__, end='')"
    )
    assert result.returncode == 0, result.stderr
    installed_path = Path(result.stdout)
    repo_src_path = REPO_ROOT / "src" / "ragtorch" / "__init__.py"
    assert installed_path.resolve() != repo_src_path.resolve()
    assert "site-packages" in str(installed_path).replace("\\", "/")


def test_wheel_contains_only_intended_runtime_files(built_wheel: Path) -> None:
    """No test files, no cache directories, no development-tooling
    artifacts, no secrets -- only ragtorch's own runtime package plus
    standard wheel metadata."""
    import zipfile

    with zipfile.ZipFile(built_wheel) as archive:
        names = archive.namelist()

    for name in names:
        assert not name.startswith("tests/"), f"wheel must not contain test files: {name}"
        assert "__pycache__" not in name, f"wheel must not contain bytecode caches: {name}"
        assert not name.endswith((".pyc", ".pyo")), f"wheel must not contain compiled files: {name}"
        assert ".claude" not in name, f"wheel must not contain local dev tooling: {name}"
        assert ".env" not in name, f"wheel must not contain env files: {name}"

    ragtorch_files = [n for n in names if n.startswith("ragtorch/")]
    assert all(n.endswith(".py") for n in ragtorch_files), (
        f"unexpected non-Python file(s) under ragtorch/: "
        f"{[n for n in ragtorch_files if not n.endswith('.py')]}"
    )


def test_sdist_does_not_contain_local_dev_tooling_artifacts(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Regression test for the exact defect this step's audit found:
    .claude/scheduled_tasks.lock (a local development artifact that was
    not covered by .gitignore) leaked into the sdist. Fixed by adding
    .claude/ to .gitignore (hatchling's default sdist selection follows
    it) plus an explicit [tool.hatch.build.targets.sdist] allowlist in
    pyproject.toml as defense in depth -- this test pins both."""
    import tarfile

    dist_dir = tmp_path_factory.mktemp("sdist_check")
    result = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--outdir", str(dist_dir), str(REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr

    sdists = list(dist_dir.glob("*.tar.gz"))
    assert len(sdists) == 1
    with tarfile.open(sdists[0]) as archive:
        names = archive.getnames()

    for name in names:
        assert ".claude" not in name, f"sdist must not contain local dev tooling: {name}"
        assert ".mypy_cache" not in name, f"sdist must not contain caches: {name}"
        assert ".ruff_cache" not in name, f"sdist must not contain caches: {name}"
        assert ".pytest_cache" not in name, f"sdist must not contain caches: {name}"
        assert ".venv" not in name, f"sdist must not contain a virtual environment: {name}"
        assert ".env" not in name, f"sdist must not contain env files: {name}"
        assert ".coverage" not in name, f"sdist must not contain coverage data: {name}"


def test_dev_only_dependencies_are_not_runtime_dependencies() -> None:
    """pytest/ruff/mypy/build must remain in the dev extra only, never
    the core runtime dependency list -- confirms the project's
    zero-runtime-dependency, provider-independent design is reflected
    accurately in pyproject.toml, not merely claimed in prose."""
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10 has no stdlib tomllib (3.11+ only)
        import tomli as tomllib  # type: ignore[no-redef]

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    runtime_deps = pyproject["project"]["dependencies"]
    assert runtime_deps == [], f"expected zero runtime dependencies, found {runtime_deps}"

    dev_deps = pyproject["project"]["optional-dependencies"]["dev"]
    dev_dep_names = {dep.split(">=")[0].split("==")[0].strip() for dep in dev_deps}
    assert dev_dep_names >= {"pytest", "ruff", "mypy", "build"}


def test_build_and_install_artifacts_stay_outside_the_repository_checkout(
    clean_env_python: Path, built_wheel: Path
) -> None:
    """Confirms this module's fixtures used real, isolated temporary
    directories (pytest's own tmp_path_factory), not anything under
    the repository checkout -- no test artifact from this file can
    accidentally pollute the repo."""
    assert not str(built_wheel).startswith(str(REPO_ROOT))
    assert not str(clean_env_python).startswith(str(REPO_ROOT))
