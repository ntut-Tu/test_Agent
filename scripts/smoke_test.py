"""Shell entry point: parse arguments and display collection smoke results."""

import argparse
from pathlib import Path
from urllib.error import HTTPError, URLError

from codebase_analysis.application.smoke import CollectionSmokeTest
from codebase_analysis.bootstrap import build_collector
from codebase_analysis.infrastructure.settings import (
    SettingsError,
    load_collection_settings,
)


def _positive_number(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("PR/MR number must be a positive integer") from None
    if number < 1:
        raise argparse.ArgumentTypeError("PR/MR number must be a positive integer")
    return number


def _error_summary(error: Exception) -> str:
    # Remote exception text can include authenticated URLs or response content.
    cause = error
    while cause is not None:
        if isinstance(cause, HTTPError):
            return f"HTTP {cause.code}; check endpoint and access permissions"
        if isinstance(cause, URLError):
            return "Network error; check DNS, TLS, and service availability"
        cause = cause.__cause__
    return f"{type(error).__name__}; check configuration and remote response format"


def main() -> int:
    """Run live collection checks and return an exit code.

    Returns:
        Zero when all checks pass or warn, one for failed/skipped checks,
        or two for invalid configuration. argparse also uses two for bad input.
    """
    parser = argparse.ArgumentParser(description="Live remote smoke test without LLM calls")
    parser.add_argument("number", type=_positive_number, help="PR number or GitLab MR IID")
    parser.add_argument(
        "--values", type=Path,
        default=Path(__file__).resolve().parents[1] / "values.yaml",
        help="Values YAML path (default: project root/values.yaml)",
    )
    args = parser.parse_args()
    try:
        settings = load_collection_settings(args.values)
        collector = build_collector(settings)
    except SettingsError as exc:
        print(f"[FAIL] configuration: {exc}", flush=True)
        return 2
    except Exception as exc:
        print(f"[FAIL] configuration: {_error_summary(exc)}", flush=True)
        return 2

    print("[PASS] configuration; starting read-only remote checks (no LLM)", flush=True)
    failed = False
    for check in CollectionSmokeTest(collector).run(args.number):
        detail = _error_summary(check.error) if check.error is not None else check.detail
        print(f"[{check.status}] {check.name}: {detail}", flush=True)
        failed = failed or check.status in {"FAIL", "SKIP"}
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
