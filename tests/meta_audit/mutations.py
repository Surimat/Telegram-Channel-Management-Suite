"""The machine-readable mutation registry (D-102).

Each entry describes one seeded defect: how to inject it and which finding the
auditor *should* produce. There is deliberately **no** ``detected`` field — the
engine measures detection at runtime.

The core mutations mirror the original "проверка проверяющего" suite. Gaps M
(write-only setting), N (unused DB field), O (backend service without caller),
P (frontend control without behaviour) and Q (channel-aware module drift) are now
closed and are therefore expected to be **detected**; ``KNOWN_GAP_IDS`` is empty.
``U_help_reference`` is an extra mutation used to prove the total is computed
dynamically (no hardcoded count).

Severities are the *impact if the defect is missed*, used for ``critical_misses``
and ``high_misses``.
"""

from __future__ import annotations

import dataclasses

from backend.app.services import consistency_checks as cc
from tests.meta_audit.engine import Mutation, MutationSandbox


# ---------------------------------------------------------------------------
# In-sandbox helpers
# ---------------------------------------------------------------------------
def _set_implemented(key: str, value: bool) -> None:
    cc.CAPABILITIES = tuple(
        dataclasses.replace(c, implemented=value) if c.key == key else c
        for c in cc.CAPABILITIES
    )


def _set_requires(key: str, requires: tuple[str, ...]) -> None:
    cc.CAPABILITIES = tuple(
        dataclasses.replace(c, requires=requires) if c.key == key else c
        for c in cc.CAPABILITIES
    )


def _drop_anchor(key: str) -> None:
    cc.CAPABILITY_SERVICE_ANCHORS = {
        k: v for k, v in cc.CAPABILITY_SERVICE_ANCHORS.items() if k != key
    }


async def _seed_setting(session, key: str, value: str = "1") -> None:
    from backend.app.db.repositories.settings import SettingRepository

    await SettingRepository(session).upsert(key, value, value_type="str")


# ---------------------------------------------------------------------------
# Static mutations (file / registry defects in the isolated copy)
# ---------------------------------------------------------------------------
def _apply_false_capability(box: MutationSandbox) -> None:
    # ``media_conversion`` is a registered capability that is deliberately not
    # implemented and has no service anchor. Flipping it to implemented must be
    # caught by the "no anchor" check (config_sync is now implemented, so it can
    # no longer serve as the false-capability probe).
    _set_implemented("media_conversion", True)


def _apply_stray_string_mask(box: MutationSandbox) -> None:
    _set_implemented("reaction", True)
    box.delete("backend/app/services/reaction_service.py")
    box.write(
        "backend/app/services/zz_stray.py",
        "# reaction is coming someday\nclass ReactionService:  # not the real one\n"
        "    pass\n",
    )


def _apply_capability_dependency(box: MutationSandbox) -> None:
    _set_requires("donor_discovery", ("media_conversion",))


def _apply_missing_i18n(box: MutationSandbox) -> None:
    cc.i18n.MESSAGES["ghost.key"] = {"ru": "Привет"}


def _apply_unused_db_field(box: MutationSandbox) -> None:
    box.patch(
        "backend/app/db/models/setting.py",
        "    value_type: Mapped[str] = mapped_column",
        '    ghost_unused: Mapped[str] = mapped_column(String(8), default="", nullable=False)\n'
        "    value_type: Mapped[str] = mapped_column",
    )


STATIC_MUTATIONS: list[Mutation] = [
    Mutation(
        id="A_frontend_route",
        name="broken_frontend_route",
        expected_finding_id="frontend.route.views/GhostView.vue",
        expected_severity="error",
        severity="high",
        apply=lambda b: b.append(
            "frontend/src/router.ts",
            "\n  { path: '/ghost', name: 'ghost', "
            "component: () => import('@/views/GhostView.vue') },\n",
        ),
    ),
    Mutation(
        id="B_api_consumer",
        name="broken_api_consumer",
        expected_finding_id="api.frontend_unknown",
        expected_severity="error",
        severity="high",
        apply=lambda b: b.append("frontend/src/api/client.ts", "\n// uses /api/v1/ghostarea\n"),
    ),
    Mutation(
        id="C_orphan_endpoint",
        name="orphan_backend_endpoint",
        expected_finding_id="api.router_unregistered.ghostarea",
        expected_severity="error",
        severity="high",
        apply=lambda b: b.write(
            "backend/app/api/v1/ghostarea.py",
            'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/ghostarea")\n',
        ),
    ),
    Mutation(
        id="D_scheduler_handler",
        name="scheduler_job_without_handler",
        expected_finding_id="scheduler.job_without_handler",
        expected_severity="error",
        severity="high",
        apply=lambda b: b.write(
            "backend/app/services/zz_ghost_jobs.py", '_JOB_KIND = "ghost.job"\n'
        ),
    ),
    Mutation(
        id="E1_provider_missing",
        name="missing_fake_provider",
        expected_finding_id="providers.audience.fake_audience.py",
        expected_severity="error",
        severity="high",
        apply=lambda b: b.delete("backend/app/providers/fake_audience.py"),
    ),
    Mutation(
        id="E2_registry_missing_module",
        name="registry_mapping_without_module",
        expected_finding_id="providers.registry_missing.ghost_provider",
        expected_severity="error",
        severity="high",
        apply=lambda b: b.append(
            "backend/app/providers/registry.py",
            "\n\ndef build_ghost():\n"
            "    from backend.app.providers.ghost_provider import Ghost\n"
            "    return Ghost()\n",
        ),
    ),
    Mutation(
        id="F_false_capability",
        name="false_capability",
        expected_finding_id="capabilities.no_anchor.media_conversion",
        expected_severity="error",
        severity="critical",
        apply=_apply_false_capability,
    ),
    Mutation(
        id="F2_stray_string_mask",
        name="false_capability_masked_by_stray_string",
        expected_finding_id="capabilities.unimplemented.reaction",
        expected_severity="error",
        severity="critical",
        apply=_apply_stray_string_mask,
    ),
    Mutation(
        id="G_capability_dependency",
        name="capability_dependency_on_unimplemented",
        expected_finding_id="capabilities.dep_unimplemented.donor_discovery.media_conversion",
        expected_severity="error",
        severity="high",
        apply=_apply_capability_dependency,
    ),
    Mutation(
        id="H_i18n_missing",
        name="missing_i18n_translation",
        expected_finding_id="i18n.missing.ghost.key",
        expected_severity="error",
        severity="medium",
        apply=_apply_missing_i18n,
    ),
    Mutation(
        id="I_hardcoded_ui_string",
        name="hardcoded_ui_string",
        expected_finding_id="ux.hardcoded_string.views/DashboardView.vue",
        expected_severity="warning",
        severity="low",
        apply=lambda b: b.append(
            "frontend/src/views/DashboardView.vue",
            "\n<template><p>Эта функция ещё не реализована</p></template>\n",
        ),
    ),
    Mutation(
        id="J_help_reference",
        name="missing_help_topic",
        expected_finding_id="help.missing_topic",
        expected_severity="error",
        severity="medium",
        apply=lambda b: b.append(
            "frontend/src/views/DashboardView.vue",
            '\n<template><InfoHint topic="ghost_topic" /></template>\n',
        ),
    ),
    Mutation(
        id="K_model_migration",
        name="model_without_migration",
        expected_finding_id="db.model_without_migration",
        expected_severity="error",
        severity="critical",
        apply=lambda b: b.write(
            "backend/app/db/models/ghost.py",
            "from backend.app.db.base import Base\n\n\n"
            'class Ghost(Base):\n    __tablename__ = "ghost_table"\n',
        ),
    ),
    Mutation(
        id="K2_column_migration",
        name="column_without_migration",
        expected_finding_id="db.model_without_migration",
        expected_severity="error",
        severity="critical",
        apply=lambda b: b.write(
            "backend/app/db/models/ghost2.py",
            "from sqlalchemy import String\nfrom sqlalchemy.orm import Mapped, mapped_column\n\n"
            "from backend.app.db.base import Base\n\n\n"
            "class Ghost2(Base):\n"
            '    __tablename__ = "ghost2_table"\n'
            '    name: Mapped[str] = mapped_column(String(32), default="", nullable=False)\n',
        ),
    ),
    Mutation(
        id="N_unused_db_field",
        name="unused_db_field",
        expected_finding_id="db.unused_column.setting.Setting.ghost_unused",
        expected_severity="info",
        severity="medium",
        note=(
            "A column added to an existing model that no application code reads "
            "or writes. Detected by static ORM-column usage analysis (D-103/N)."
        ),
        apply=_apply_unused_db_field,
    ),
    Mutation(
        id="O_service_without_caller",
        name="backend_service_without_caller",
        expected_finding_id="dead.service.zz_dead_service.DeadService",
        expected_severity="info",
        severity="medium",
        note=(
            "A public service class no module references. Detected by static "
            "class-usage analysis (D-103/O)."
        ),
        apply=lambda b: b.write(
            "backend/app/services/zz_dead_service.py",
            "class DeadService:\n    def run(self) -> None:\n        return None\n",
        ),
    ),
    Mutation(
        id="P_control_without_behavior",
        name="frontend_control_without_behavior",
        expected_finding_id="frontend.control_unwired.runGhostAction",
        expected_severity="warning",
        severity="medium",
        note=(
            "A template event handler with no defined function. Detected by "
            "static Vue control-wiring analysis (D-103/P)."
        ),
        apply=lambda b: b.append(
            "frontend/src/views/DashboardView.vue",
            '\n<template><button @click="runGhostAction">Запустить</button></template>\n',
        ),
    ),
    Mutation(
        id="Q_channel_aware_module",
        name="channel_aware_module_without_channel",
        expected_finding_id="channel-aware.module.zz_channel_consumer",
        expected_severity="warning",
        severity="high",
        note="Channel-aware code that bypasses the canonical Channel Registry.",
        apply=lambda b: b.write(
            "backend/app/services/zz_channel_consumer.py",
            "class ChannelConsumer:\n"
            "    def handle(self, payload: dict) -> None:\n"
            "        return None\n",
        ),
    ),
    Mutation(
        id="M_write_only_setting",
        name="write_only_setting",
        expected_finding_id="settings.write_only.zz_write_only_setting",
        expected_severity="warning",
        severity="high",
        note=(
            "A setting with a real write path but no reader: saved, yet it never "
            "changes behaviour. Detected by static write/read analysis (D-100/M)."
        ),
        apply=lambda b: b.write(
            "backend/app/services/zz_write_only.py",
            "from backend.app.services.settings_service import SettingsService\n\n\n"
            "class GhostWriter:\n"
            "    async def save(self, session) -> None:\n"
            '        await SettingsService(session).set("zz_write_only_setting", True)\n',
        ),
    ),
    Mutation(
        id="R1_backup_destination_no_provider",
        name="backup_destination_without_provider",
        expected_finding_id="backup.destination_no_module.ghost_disk",
        expected_severity="error",
        severity="high",
        apply=lambda b: b.patch(
            "backend/app/db/models/backup_destination.py",
            '    TELEGRAM = "telegram"',
            '    TELEGRAM = "telegram"\n    GHOST_DISK = "ghost_disk"',
        ),
    ),
    Mutation(
        id="R2_backup_provider_missing",
        name="backup_provider_file_missing",
        expected_finding_id="backup.destination_missing.yandex_disk",
        expected_severity="error",
        severity="high",
        apply=lambda b: b.delete("backend/app/services/backup_backends/yandex.py"),
    ),
    Mutation(
        id="S_notification_routing",
        name="notification_category_without_routing",
        expected_finding_id="notifications.no_routing.ghost",
        expected_severity="error",
        severity="high",
        apply=lambda b: b.patch(
            "backend/app/manager/bus.py",
            'CATEGORY_WORKERS = "workers"',
            'CATEGORY_WORKERS = "workers"\nCATEGORY_GHOST = "ghost"',
        ),
    ),
    Mutation(
        id="T_doc_endpoint_claim",
        name="documented_endpoint_that_does_not_exist",
        expected_finding_id="docs.api_unknown_prefix",
        expected_severity="warning",
        severity="low",
        apply=lambda b: b.append("docs/API.md", "\n## Ghost area\n\nGET /api/v1/ghostarea/list\n"),
    ),
    # --- extra mutation: proves the total is computed, not hardcoded ----------
    Mutation(
        id="U_help_reference",
        name="broken_help_reference_extra",
        expected_finding_id="help.missing_topic",
        expected_severity="error",
        severity="medium",
        apply=lambda b: b.append(
            "frontend/src/views/SettingsView.vue",
            '\n<template><InfoHint topic="ghost_extra_topic" /></template>\n',
        ),
    ),
    # --- AI Gateway (v1.8) ---------------------------------------------------
    Mutation(
        id="V_gateway_capability_anchor",
        name="gateway_capability_without_anchor",
        expected_finding_id="capabilities.no_anchor.ai_gateway",
        expected_severity="error",
        severity="high",
        note=(
            "The AI Gateway capability is marked implemented but its service "
            "anchor is removed: the capability would advertise a feature with no "
            "implementation behind it (D-099)."
        ),
        apply=lambda b: _drop_anchor("ai_gateway"),
    ),
    Mutation(
        id="W_frontend_unknown_gateway",
        name="frontend_calls_missing_gateway_area",
        expected_finding_id="api.frontend_unknown",
        expected_severity="error",
        severity="medium",
        note=(
            "The frontend client calls an AI Gateway area the backend does not "
            "expose; the route would 404."
        ),
        apply=lambda b: b.append(
            "frontend/src/api/client.ts",
            "\n// zz: ghost gateway area\n"
            "export const zzGhost = () => fetch('/api/v1/ghostgateway/x')\n",
        ),
    ),
]


# ---------------------------------------------------------------------------
# Runtime (DB-backed) mutations
# ---------------------------------------------------------------------------
RUNTIME_MUTATIONS: list[Mutation] = [
    Mutation(
        id="L_orphan_setting",
        name="orphan_setting_runtime",
        expected_finding_id="settings.dead.zz_ghost_setting",
        expected_severity="info",
        severity="medium",
        note="Detected by the runtime dead-setting check, not a static consumer graph.",
        runtime_setup=lambda s: _seed_setting(s, "zz_ghost_setting"),
    ),
]

#: All seeded defects, static then runtime. The engine runs each one.
MUTATIONS: list[Mutation] = STATIC_MUTATIONS + RUNTIME_MUTATIONS

#: Mutations the auditor is *known* not to catch yet (documented gaps, D-100).
#: They are still executed and classified at runtime — this set only tells the
#: per-defect test not to demand detection. All original gaps (M, N, O, P, Q) are
#: now closed, so this set is empty; it stays as the honest escape hatch for a
#: future gap.
KNOWN_GAP_IDS: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Negative controls
# ---------------------------------------------------------------------------
#: A clean tree must not produce the expected mutation finding. If it does, the
#: auditor is a false-positive source and the run fails (D-102).
NEGATIVE_CONTROLS: list[Mutation] = [
    Mutation(
        id="NC1_clean_frontend_route",
        name="clean_tree_no_frontend_route_finding",
        expected_finding_id="frontend.route.views/GhostView.vue",
        expected_severity="error",
        severity="low",
        apply=lambda b: None,
    ),
    Mutation(
        id="NC2_clean_settings",
        name="clean_tree_no_write_only_setting_finding",
        expected_finding_id="settings.write_only.language",
        expected_severity="warning",
        severity="low",
        runtime_setup=lambda s: _seed_setting(s, "language", "ru"),
    ),
    Mutation(
        id="NC3_clean_capability",
        name="clean_tree_no_false_capability_finding",
        expected_finding_id="capabilities.no_anchor.media_conversion",
        expected_severity="error",
        severity="low",
        apply=lambda b: None,
    ),
    Mutation(
        id="NC4_setting_with_reader",
        name="setting_with_a_reader_is_not_write_only",
        expected_finding_id="settings.write_only.zz_round_trip_setting",
        expected_severity="warning",
        severity="low",
        note="A setting that is written *and* read must not be flagged (M precision).",
        apply=lambda b: b.write(
            "backend/app/services/zz_round_trip.py",
            "from backend.app.services.settings_service import SettingsService\n\n\n"
            "class RoundTrip:\n"
            "    async def save(self, session) -> None:\n"
            "        svc = SettingsService(session)\n"
            '        await svc.set("zz_round_trip_setting", True)\n\n'
            "    async def load(self, session) -> object:\n"
            "        svc = SettingsService(session)\n"
            '        return await svc.get_typed("zz_round_trip_setting", False)\n',
        ),
    ),
    Mutation(
        id="NC5_channel_aware_with_registry",
        name="channel_aware_module_using_registry_is_not_flagged",
        expected_finding_id="channel-aware.module.zz_channel_ok",
        expected_severity="warning",
        severity="low",
        note=(
            "A channel-aware module that uses ChannelRepository must not be "
            "flagged (Q precision)."
        ),
        apply=lambda b: b.write(
            "backend/app/services/zz_channel_ok.py",
            "from backend.app.db.repositories.channels import ChannelRepository\n\n\n"
            "class ChannelConsumer:\n"
            "    def __init__(self, session) -> None:\n"
            "        self.channels = ChannelRepository(session)\n\n"
            "    async def handle(self, channel_id: str) -> None:\n"
            "        await self.channels.get(channel_id)\n",
        ),
    ),
    Mutation(
        id="NC6_used_db_column",
        name="referenced_column_is_not_flagged_unused",
        expected_finding_id="db.unused_column.setting.Setting.zz_live_column",
        expected_severity="info",
        severity="low",
        note=(
            "A model column that some module reads must not be flagged (N "
            "precision): the mutation adds the column *and* a reader."
        ),
        apply=lambda b: (
            b.patch(
                "backend/app/db/models/setting.py",
                "    value_type: Mapped[str] = mapped_column",
                '    zz_live_column: Mapped[str] = mapped_column(String(8), default="")\n'
                "    value_type: Mapped[str] = mapped_column",
            ),
            b.append(
                "backend/app/services/settings_service.py",
                "\n\ndef _zz_read_live(setting) -> str:\n"
                "    return setting.zz_live_column\n",
            ),
        ),
    ),
    Mutation(
        id="NC7_referenced_service",
        name="referenced_service_class_is_not_flagged",
        expected_finding_id="dead.service.zz_live_service.LiveService",
        expected_severity="info",
        severity="low",
        note=(
            "A service class that another module instantiates must not be flagged "
            "(O precision): the mutation adds the class *and* a caller."
        ),
        apply=lambda b: (
            b.write(
                "backend/app/services/zz_live_service.py",
                "class LiveService:\n    def run(self) -> None:\n        return None\n",
            ),
            b.write(
                "backend/app/services/zz_live_consumer.py",
                "from backend.app.services.zz_live_service import LiveService\n\n\n"
                "def _zz_call() -> None:\n    LiveService().run()\n",
            ),
        ),
    ),
    Mutation(
        id="NC8_wired_frontend_control",
        name="defined_handler_is_not_flagged_unwired",
        expected_finding_id="frontend.control_unwired.zzWiredAction",
        expected_severity="warning",
        severity="low",
        note=(
            "A control whose handler is defined with a non-empty body must not be "
            "flagged (P precision): the mutation adds both the control and its "
            "handler."
        ),
        apply=lambda b: (
            b.patch(
                "frontend/src/views/DashboardView.vue",
                '<script setup lang="ts">',
                '<script setup lang="ts">\n'
                "const zzWiredAction = () => { window.alert('ok') }",
            ),
            b.append(
                "frontend/src/views/DashboardView.vue",
                '\n<template><button @click="zzWiredAction">Ок</button></template>\n',
            ),
        ),
    ),
]
