"""End-to-end Setup Wizard router (D-128).

A single guided flow from a fresh install to a working channel. Every step is
verified by the server on demand; the status returned is the stored result of a
real check, never an optimistic guess.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import get_setup_wizard_service
from backend.app.api.errors import ApiError
from backend.app.api.schemas.setup_wizard import (
    SetupStepRunIn,
    SetupWizardStateOut,
    TestPublicationIn,
    TestPublicationOut,
)
from backend.app.services.setup_wizard import (
    SetupWizardError,
    SetupWizardService,
    WizardView,
)

router = APIRouter(prefix="/setup-wizard", tags=["setup-wizard"])


def _state_out(view: WizardView) -> SetupWizardStateOut:
    return SetupWizardStateOut(
        steps=[
            {
                "key": s.key,
                "title": s.title,
                "description": s.description,
                "status": s.status,
                "status_title": s.status_title,
                "verified": s.verified,
                "message": s.message,
                "how_to_fix": s.how_to_fix,
                "route": s.route,
                "verified_at": s.verified_at,
                "attempts": s.attempts,
            }
            for s in view.steps
        ],
        completed_steps=view.completed_steps,
        total_steps=view.total_steps,
        ready=view.ready,
        progress_percent=view.progress_percent,
        current_step=view.current_step,
        test_publication_available=view.test_publication_available,
        test_publication_hint=view.test_publication_hint,
        notes=list(view.notes),
    )


@router.get("", response_model=SetupWizardStateOut)
async def wizard_state(
    service: SetupWizardService = Depends(get_setup_wizard_service),
) -> SetupWizardStateOut:
    return _state_out(await service.state())


@router.post("/steps/{key}/run", response_model=SetupWizardStateOut)
async def run_step(
    key: str,
    payload: SetupStepRunIn | None = None,
    service: SetupWizardService = Depends(get_setup_wizard_service),
) -> SetupWizardStateOut:
    account_id = payload.account_id if payload is not None else ""
    try:
        return _state_out(await service.run_step(key, account_id=account_id))
    except SetupWizardError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc


@router.post("/test-publication", response_model=TestPublicationOut)
async def test_publication(
    payload: TestPublicationIn,
    service: SetupWizardService = Depends(get_setup_wizard_service),
) -> TestPublicationOut:
    try:
        result = await service.test_publication(confirmed=payload.confirmed)
    except SetupWizardError as exc:
        raise ApiError(exc.status_code, exc.message, exc.how_to_fix) from exc
    return TestPublicationOut(**result)
