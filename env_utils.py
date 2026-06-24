# env_utils.py
import os
import sys
import shutil
import tomllib
from pathlib import Path
from importlib import metadata
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from dotenv import dotenv_values, load_dotenv


# ══════════════════════════════════════════════
def summarize_value(value: str) -> str:
    lower = value.lower()
    if lower in ("true", "false"):
        return lower
    return "****" + value[-4:] if len(value) > 4 else "****"


def check_manual_installs(file_path: str):
    if not os.path.exists(file_path):
        return

    manual_installs = []
    with open(file_path, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("# Manual installs for checking:"):
                apps_str = stripped.split(":", 1)[1].strip()
                if apps_str:
                    manual_installs = [a.strip() for a in apps_str.split(",")]
                break

    if not manual_installs:
        return

    print("Manual Installs Check:")
    for app in manual_installs:
        if shutil.which(app):
            print(f"  ✅ {app}")
        else:
            print(f"  ⚠️  {app} not found in PATH")
    print()


def check_venv(expected_venv_path: str = ".venv"):
    issues = []
    current_prefix   = Path(sys.prefix).resolve()
    expected_path_obj = Path(expected_venv_path).resolve()

    in_venv = (
        hasattr(sys, "real_prefix")
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
    )
    uv_managed = current_prefix == expected_path_obj

    if not in_venv and not uv_managed:
        issues.append("⚠️  Virtual environment is not activated")
        issues.append("   Run: uv run python env_utils.py")
    else:
        print("✅ Running inside virtual environment")
        print(f"   Path: {current_prefix}")

    uv_available = shutil.which("uv") is not None
    if not uv_available:
        issues.append("⚠️  'uv' not found")
        issues.append("   Install: https://docs.astral.sh/uv/")
    else:
        print("✅ uv is available")

    if issues:
        print("\nVirtual Environment Issues:")
        for issue in issues:
            print(issue)
    print()


def doublecheck_env(file_path: str):
    if not os.path.exists(file_path):
        print(f"⚠️  {file_path} not found — skipping env check.\n")
        return

    required_keys = {}
    with open(file_path, "r") as f:
        is_required = False
        for line in f:
            stripped = line.strip()
            if stripped.startswith("#"):
                is_required = "required" in stripped.lower()
            elif "=" in stripped:
                key, val = stripped.split("=", 1)
                key = key.strip()
                val = val.strip()
                if is_required:
                    required_keys[key] = val

    parsed = dotenv_values(file_path)
    issues = []

    print("Environment Variables:")
    for key in parsed:
        current = os.getenv(key)
        if current:
            print(f"  {key}={summarize_value(current)}")
            if key in required_keys and current == required_keys[key]:
                issues.append(f"  ⚠️  {key} still has placeholder value")
        else:
            print(f"  {key}=<not set>")
            if key in required_keys:
                issues.append(f"  ⚠️  {key} is required but not set")

    if issues:
        print("\nIssues:")
        for i in issues:
            print(i)
    print()


def _fmt_row(cols, widths):
    return " | ".join(str(c).ljust(w) for c, w in zip(cols, widths))


def doublecheck_pkgs(pyproject_path: str = "pyproject.toml", verbose: bool = False):
    p = Path(pyproject_path)
    if not p.exists():
        print(f"❌ {pyproject_path} not found.\n")
        return

    with p.open("rb") as f:
        data = tomllib.load(f)

    project        = data.get("project", {})
    python_spec_str = project.get("requires-python", ">=3.11")
    py_ver         = Version(
        f"{sys.version_info.major}.{sys.version_info.minor}"
        f".{sys.version_info.micro}"
    )
    py_ok = py_ver in SpecifierSet(python_spec_str)

    deps = project.get("dependencies", [])
    if not deps:
        print("No dependencies found in pyproject.toml.\n")
        return

    results  = []
    problems = []

    for dep in deps:
        try:
            req  = Requirement(dep)
            name = req.name
            spec = str(req.specifier) if req.specifier else "(any)"
        except Exception:
            name, spec = dep, "(unparsed)"

        rec = {
            "package":   name,
            "required":  spec,
            "installed": "-",
            "status":    "❌ Missing",
        }

        try:
            installed_ver = metadata.version(name)
            rec["installed"] = installed_ver
            if spec not in ("(any)", "(unparsed)"):
                ok = Version(installed_ver) in SpecifierSet(spec)
                rec["status"] = "✅ OK" if ok else "⚠️ Version mismatch"
            else:
                rec["status"] = "✅ OK"
        except metadata.PackageNotFoundError:
            pass

        results.append(rec)
        if rec["status"] != "✅ OK":
            problems.append(rec)

    # چاپ نتایج
    print(
        f"Python {py_ver} "
        f"{'✅ satisfies' if py_ok else '❌ DOES NOT satisfy'} "
        f"requires-python: {python_spec_str}\n"
    )

    headers = ["package", "required", "installed", "status"]
    rows    = [[r[h] for h in headers] for r in results]
    widths  = [
        max(len(h), *(len(str(row[i])) for row in rows))
        for i, h in enumerate(headers)
    ]
    print(_fmt_row(headers, widths))
    print(_fmt_row(["-" * w for w in widths], widths))
    for row in rows:
        print(_fmt_row(row, widths))

    if problems:
        print("\nProblems detected:")
        for r in problems:
            print(
                f"  - {r['package']}: {r['status']} "
                f"(required {r['required']}, installed {r['installed']})"
            )

    print(f"\nExecutable: {sys.executable}\n")


# ══════════════════════════════════════════════
if __name__ == "__main__":
    check_venv()
    check_manual_installs(".env.example")
    load_dotenv()
    doublecheck_env(".env.example")
    doublecheck_pkgs(pyproject_path="pyproject.toml", verbose=True)