"""Runtime meta-audit engine: measure the Consistency Auditor by execution.

This package contains no assertions about *which* defects the auditor detects.
It builds an isolated copy of the source tree, injects one seeded defect, runs
the real auditor, compares the findings it actually produced against the
expected finding, and classifies the mutation as ``detected`` / ``missed`` at
runtime. The kill rate is then computed from those executions — never from a
pre-declared list of "detectable" ids (D-102).

Modules:

* :mod:`tests.meta_audit.engine` — sandbox, mutation runner, report writer.
* :mod:`tests.meta_audit.mutations` — the machine-readable mutation registry.
"""

from __future__ import annotations

from tests.meta_audit.engine import (
    ControlResult,
    Mutation,
    MutationResult,
    MutationSandbox,
    SuiteResult,
    run_suite,
    write_report,
)

__all__ = [
    "ControlResult",
    "Mutation",
    "MutationResult",
    "MutationSandbox",
    "SuiteResult",
    "run_suite",
    "write_report",
]
