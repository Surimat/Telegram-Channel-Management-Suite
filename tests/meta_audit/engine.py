"""Runtime meta-audit engine (D-102).

The engine measures the Consistency Auditor by *execution*, not by declaration:

1. build an isolated copy of the source tree (or a fresh temp DB for runtime
   checks);
2. apply exactly one seeded defect;
3. run the real auditor;
4. collect the findings it actually produced;
5. compare them (semantically) with the expected finding;
6. record ``detected`` / ``missed`` for that mutation;
7. compute the kill rate from those records.

Nothing here reads a pre-declared list of "detectable" or "missed" ids: if a
detector is removed, the corresponding mutation becomes ``missed`` and the kill
rate drops automatically.

The working tree is never mutated — every defect is applied to a throwaway copy
under a temporary directory.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import json
import shutil
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from backend.app import __version__
from backend.app.services import consistency_checks as cc
from backend.app.services.consistency import ConsistencyAuditor
from backend.app.services.consistency_types import Finding

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Directories copied into each isolated sandbox. Mirrors the original mutation
#: harness so every static check sees a complete source tree.
_COPY_DIRS = ("backend/app", "frontend/src", "migrations/versions", "docs")

#: Marker written into the report so a reader can tell the numbers came from a
#: real run and not from hand-maintained metadata.
RESULT_SOURCE = "computed from runtime mutation executions"


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------
class MutationSandbox:
    """An isolated copy of the source tree with the auditor pointed at it.

    ``cc`` module globals are repointed for the duration and restored on exit.
    In-memory registries (``CAPABILITIES``, ``i18n.MESSAGES``) are snapshotted so
    a mutation that patches them cannot leak into another mutation.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._caps = cc.CAPABILITIES
        # ``i18n.MESSAGES`` is mutated in place by some mutations, so snapshot a
        # deep copy — restoring the same dict object would not undo added keys.
        self._messages = copy.deepcopy(cc.i18n.MESSAGES)
        self._globals = {
            name: getattr(cc, name)
            for name in ("ROOT", "BACKEND", "FRONTEND", "MIGRATIONS", "DOCS")
        }

    @classmethod
    def create(cls, parent: Path) -> MutationSandbox:
        root = parent / "repo"
        for rel in _COPY_DIRS:
            src = REPO_ROOT / rel
            if src.is_dir():
                shutil.copytree(
                    src,
                    root / rel,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
        # Construct first so ``__init__`` snapshots the *original* globals, then
        # repoint the auditor at the sandbox.
        box = cls(root=root)
        cc.ROOT = root
        cc.BACKEND = root / "backend" / "app"
        cc.FRONTEND = root / "frontend" / "src"
        cc.MIGRATIONS = root / "migrations" / "versions"
        cc.DOCS = root / "docs"
        return box

    # -- file helpers -------------------------------------------------------
    def write(self, rel: str, content: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def patch(self, rel: str, old: str, new: str) -> None:
        path = self.root / rel
        text = path.read_text(encoding="utf-8")
        assert old in text, f"patch anchor not found in {rel}: {old!r}"
        path.write_text(text.replace(old, new), encoding="utf-8")

    def append(self, rel: str, extra: str) -> None:
        path = self.root / rel
        path.write_text(path.read_text(encoding="utf-8") + extra, encoding="utf-8")

    def delete(self, rel: str) -> None:
        (self.root / rel).unlink()

    # -- in-memory registry helpers ----------------------------------------
    def set_capabilities(self, capabilities: Iterable) -> None:
        cc.CAPABILITIES = tuple(capabilities)

    def restore(self) -> None:
        cc.CAPABILITIES = self._caps
        cc.i18n.MESSAGES = self._messages
        for name, value in self._globals.items():
            setattr(cc, name, value)

    def __enter__(self) -> MutationSandbox:
        return self

    def __exit__(self, *exc: object) -> None:
        self.restore()


# ---------------------------------------------------------------------------
# Mutation + results
# ---------------------------------------------------------------------------
#: Applies a file/registry defect to a sandbox.
ApplyFn = Callable[[MutationSandbox], None]
#: Seeds a runtime defect into a database session.
RuntimeFn = Callable[["object"], Awaitable[None]]


@dataclass(frozen=True)
class Mutation:
    """A machine-readable seeded defect.

    ``expected_finding_id`` is the finding that *should* appear. It carries no
    ``detected`` flag — whether the auditor produces it is measured at runtime.
    """

    id: str
    name: str
    expected_finding_id: str
    expected_severity: str
    severity: str  # impact if this mutation is missed (critical/high/medium/low)
    note: str = ""
    apply: ApplyFn | None = None
    runtime_setup: RuntimeFn | None = None

    @property
    def kind(self) -> str:
        return "runtime" if self.runtime_setup is not None else "static"


@dataclass
class MutationResult:
    id: str
    name: str
    detected: bool
    expected: dict
    actual_findings: list[dict]
    severity: str
    note: str
    error: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class ControlResult:
    id: str
    name: str
    passed: bool  # the expected mutation finding is absent on a clean tree
    findings: list[dict]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class SuiteResult:
    mutations: list[MutationResult] = field(default_factory=list)
    controls: list[ControlResult] = field(default_factory=list)

    # -- derived, always computed from the execution records ---------------
    @property
    def total(self) -> int:
        return len(self.mutations)

    @property
    def detected(self) -> int:
        return sum(1 for m in self.mutations if m.detected)

    @property
    def missed(self) -> int:
        return self.total - self.detected

    @property
    def kill_rate(self) -> float:
        return round(self.detected / self.total * 100, 1) if self.total else 0.0

    @property
    def false_positives(self) -> int:
        return sum(1 for c in self.controls if not c.passed)

    @property
    def critical_misses(self) -> int:
        return sum(1 for m in self.mutations if not m.detected and m.severity == "critical")

    @property
    def high_misses(self) -> int:
        return sum(1 for m in self.mutations if not m.detected and m.severity == "high")

    @property
    def status(self) -> str:
        if self.false_positives:
            return "false_positives"
        return "gaps_found" if self.missed else "clean"

    def verify(self) -> None:
        """Self-consistency: the arithmetic must hold, always."""
        assert self.detected + self.missed == self.total, "detected + missed != total"
        assert 0.0 <= self.kill_rate <= 100.0, "kill rate out of range"
        assert self.false_positives == sum(1 for c in self.controls if not c.passed)
        assert all(m.error is None for m in self.mutations), "a mutation errored during execution"

    def to_dict(self) -> dict:
        return {
            "version": __version__,
            "baseline_sha": _baseline_sha(),
            "generated_at": datetime.now(UTC).isoformat(),
            "result_source": RESULT_SOURCE,
            "total": self.total,
            "detected": self.detected,
            "missed": self.missed,
            "kill_rate": self.kill_rate,
            "false_positives": self.false_positives,
            "critical_misses": self.critical_misses,
            "high_misses": self.high_misses,
            "status": self.status,
            "mutations": [m.to_dict() for m in self.mutations],
            "negative_controls": [c.to_dict() for c in self.controls],
        }


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def _matches(finding_id: str, expected_id: str) -> bool:
    """Semantic match: exact id, or a family of ids sharing the expected prefix.

    A finding with an unrelated id is never a match — an unexpected finding is
    not a detection. The expected id may be a family prefix (e.g.
    ``ux.hardcoded_string.views/DashboardView.vue`` matches the per-line
    ``…:202`` variant); the character after the prefix must be a separator.
    """
    if finding_id == expected_id:
        return True
    if not finding_id.startswith(expected_id):
        return False
    return finding_id[len(expected_id)] in ".:/"


def _finding_summary(f: Finding) -> dict:
    return {"id": f.id, "severity": f.severity, "category": f.category}


def _classify(findings: list[Finding], expected_id: str, expected_severity: str) -> bool:
    hits = [f for f in findings if _matches(f.id, expected_id)]
    return any(f.severity == expected_severity for f in hits)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
@contextlib.asynccontextmanager
async def _fresh_session(db_path: Path) -> AsyncIterator:
    """A fresh SQLite database with the full schema, disposed afterwards."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.app.db import models  # noqa: F401  (registers metadata)
    from backend.app.db.base import Base

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@contextlib.contextmanager
def _disabled_checks(names: tuple[str, ...]):
    """Temporarily replace named static checks with no-op detectors."""
    originals = {name: getattr(cc, name) for name in names}

    def _noop() -> list:
        return []

    try:
        for name in names:
            setattr(cc, name, _noop)
        yield
    finally:
        for name, fn in originals.items():
            setattr(cc, name, fn)


async def run_mutation(
    mutation: Mutation,
    workdir: Path,
    *,
    disabled_checks: tuple[str, ...] = (),
) -> MutationResult:
    """Apply one mutation to an isolated sandbox and measure detection."""
    sandbox = MutationSandbox.create(workdir)
    findings: list[Finding] = []
    error: str | None = None
    try:
        with _disabled_checks(disabled_checks):
            if mutation.runtime_setup is not None:
                async with _fresh_session(workdir / "audit.db") as factory:
                    async with factory() as session:
                        await mutation.runtime_setup(session)
                        await session.commit()
                        report = await ConsistencyAuditor(session).run()
                        findings = list(report.findings)
            else:
                assert mutation.apply is not None
                mutation.apply(sandbox)
                findings = cc.run_static_checks()
    except Exception as exc:  # a broken mutation is reported, never hidden
        error = f"{type(exc).__name__}: {exc}"
    finally:
        sandbox.restore()

    detected = _classify(findings, mutation.expected_finding_id, mutation.expected_severity)
    return MutationResult(
        id=mutation.id,
        name=mutation.name,
        detected=detected,
        expected={
            "finding_id": mutation.expected_finding_id,
            "severity": mutation.expected_severity,
        },
        actual_findings=[_finding_summary(f) for f in findings],
        severity=mutation.severity,
        note=mutation.note,
        error=error,
    )


async def run_controls(
    controls: list[Mutation],
    workdir: Path,
) -> list[ControlResult]:
    """Negative controls: a clean tree must not produce the expected finding."""
    results: list[ControlResult] = []
    for index, control in enumerate(controls):
        sandbox = MutationSandbox.create(workdir / f"control_{index}")
        try:
            if control.runtime_setup is not None:
                async with _fresh_session(workdir / f"control_{index}.db") as factory:
                    async with factory() as session:
                        report = await ConsistencyAuditor(session).run()
                        findings = list(report.findings)
            else:
                findings = cc.run_static_checks()
        finally:
            sandbox.restore()
        present = _classify(
            findings, control.expected_finding_id, control.expected_severity
        )
        results.append(
            ControlResult(
                id=control.id,
                name=control.name,
                passed=not present,
                findings=[_finding_summary(f) for f in findings],
            )
        )
    return results


async def run_suite(
    workdir: Path,
    mutations: list[Mutation],
    controls: list[Mutation],
    *,
    disabled_checks: tuple[str, ...] = (),
) -> SuiteResult:
    """Run every mutation + control and return the computed result set."""
    results: list[MutationResult] = []
    for mutation in mutations:
        results.append(
            await run_mutation(
                mutation, workdir / mutation.id, disabled_checks=disabled_checks
            )
        )
    suite = SuiteResult(mutations=results, controls=await run_controls(controls, workdir))
    suite.verify()
    return suite


# ---------------------------------------------------------------------------
# Report I/O
# ---------------------------------------------------------------------------
def _baseline_sha() -> str:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - git always present in CI/dev
        return ""


def report_path() -> Path:
    return REPO_ROOT / "agent" / "META_AUDIT_RESULT.json"


def load_committed_report() -> dict | None:
    path = report_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:  # pragma: no cover - defensive
        return None


def write_report(suite: SuiteResult, path: Path | None = None) -> dict:
    payload = suite.to_dict()
    target = path or report_path()
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def regression_against(baseline: dict, suite: SuiteResult) -> list[str]:
    """Return ids that the committed baseline detected but this run missed.

    This is how CI notices a silently-removed detector *without* hardcoding a
    percentage: the freshly computed result is compared with the previously
    generated one.
    """
    baseline_by_id = {m["id"]: m for m in baseline.get("mutations", [])}
    regressions: list[str] = []
    for result in suite.mutations:
        old = baseline_by_id.get(result.id)
        if old is not None and old.get("detected") and not result.detected:
            regressions.append(result.id)
    return regressions


# ---------------------------------------------------------------------------
# CLI: generate the report from a real run (used by CI and by hand)
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """Run the suite and write ``agent/META_AUDIT_RESULT.json``.

    Exits non-zero if any mutation errored, a negative control failed, or a
    previously-detected mutation is now missed (a silently removed detector).
    """
    import argparse
    import asyncio
    import sys
    import tempfile

    from tests.meta_audit.mutations import MUTATIONS, NEGATIVE_CONTROLS

    parser = argparse.ArgumentParser(description="Run the runtime meta-audit engine.")
    parser.add_argument("--out", type=Path, default=report_path())
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="skip the regression check against the previously generated report",
    )
    args = parser.parse_args(argv)

    baseline = None if args.no_baseline else load_committed_report()

    async def _run() -> SuiteResult:
        with tempfile.TemporaryDirectory() as td:
            return await run_suite(Path(td), MUTATIONS, NEGATIVE_CONTROLS)

    suite = asyncio.run(_run())
    regressions = regression_against(baseline, suite) if baseline else []
    payload = write_report(suite, args.out)

    print(json.dumps({k: payload[k] for k in (
        "total", "detected", "missed", "kill_rate", "false_positives",
        "critical_misses", "high_misses", "status",
    )}, ensure_ascii=False))
    if regressions:
        print(f"REGRESSIONS: {regressions}", file=sys.stderr)
        return 1
    if payload["false_positives"]:
        print("FALSE POSITIVES detected", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
