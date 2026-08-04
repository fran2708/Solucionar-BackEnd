from __future__ import annotations
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from sqlalchemy import func

from routers.auth import get_current_user, SessionDep
from schema.users import User
from schema.auth import ProviderUpsertRequest, ProviderPublic
from schema.providers import ProviderProfile
from schema.services import Service
from schema.reservations import Reservation, ReservationStatus
from schema.reviews import ReservationReview
from schema.groups import Group
from core.enums import Role, CATEGORY_CHOICES, SERVICE_AREA_CHOICES

router = APIRouter(prefix="/providers", tags=["providers"])

@router.get("/me", response_model=ProviderPublic | None)
def get_my_provider(current_user: Annotated[User, Depends(get_current_user)], session: SessionDep):
    profile = session.exec(select(ProviderProfile).where(ProviderProfile.user_id == current_user.id)).first()
    if not profile:
        return None
    return ProviderPublic(
        id=profile.id,
        user_id=profile.user_id,
        legal_name=profile.legal_name,
        cuit_or_cuil=profile.cuit_or_cuil,
        tax_status=profile.tax_status,
        category=profile.category,
    )

@router.get("/me/dashboard")
def provider_dashboard(current_user: Annotated[User, Depends(get_current_user)], session: SessionDep):
    """
    Métricas básicas del proveedor. Placeholder hasta implementar Reservas/Pagos/Reseñas.
    """
    profile = session.exec(select(ProviderProfile).where(ProviderProfile.user_id == current_user.id)).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No sos proveedor activo")

    services_published = int(
        session.exec(
            select(func.count())
            .select_from(Service)
            .where(Service.provider_id == current_user.id, Service.active == True)  # noqa: E712
        ).one() or 0
    )

    reservations_total = int(
        session.exec(
            select(func.count())
            .select_from(Reservation)
            .join(Service, Reservation.service_id == Service.id)
            .where(Service.provider_id == current_user.id)
        ).one() or 0
    )

    reservations_completed = int(
        session.exec(
            select(func.count())
            .select_from(Reservation)
            .join(Service, Reservation.service_id == Service.id)
            .where(
                Service.provider_id == current_user.id,
                Reservation.status == ReservationStatus.COMPLETED.value,
            )
        ).one() or 0
    )

    rating_row = session.exec(
        select(func.avg(ReservationReview.rating), func.count(ReservationReview.id))
        .select_from(ReservationReview)
        .join(Service, ReservationReview.service_id == Service.id)
        .where(Service.provider_id == current_user.id)
    ).one()
    rating_average = float(rating_row[0]) if rating_row[0] is not None else 0.0
    rating_count = int(rating_row[1]) if rating_row[1] is not None else 0

    return {
        "provider_id": profile.id,
        "totals": {
            "services_published": services_published,
            "reservations_total": reservations_total,
            "reservations_completed": reservations_completed,
            "favorites_count": 0,
        },
        "ratings": {
            "average": round(rating_average, 2),
            "count": rating_count,
        },
        "revenue": {
            "total": 0.0,
            "currency": "ARS",
        }
    }

@router.put("/me", response_model=ProviderPublic)
def upsert_my_provider(payload: ProviderUpsertRequest, current_user: Annotated[User, Depends(get_current_user)], session: SessionDep):
    # Validate CUIT/CUIL: 11 digits + check digit (módulo 11)
    def _valid_cuit(cuit: str) -> bool:
        if not cuit or not cuit.isdigit() or len(cuit) != 11:
            return False
        weights = [5,4,3,2,7,6,5,4,3,2]
        total = sum(int(d)*w for d,w in zip(cuit[:10], weights))
        dv = 11 - (total % 11)
        if dv == 11: dv = 0
        if dv == 10: dv = 9
        return dv == int(cuit[-1])

    if not _valid_cuit(payload.cuit_or_cuil):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CUIT/CUIL inválido")

    if payload.has_invoice:
        if not (payload.bank_alias or payload.bank_cbu):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Debes informar bank_alias o bank_cbu para pagos")

    # Validar choices de categoría y zonas de trabajo si vienen informados
    if payload.category and payload.category not in CATEGORY_CHOICES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Categoría inválida")
    if payload.service_areas and payload.service_areas not in SERVICE_AREA_CHOICES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Zona de trabajo inválida")

    profile = session.exec(select(ProviderProfile).where(ProviderProfile.user_id == current_user.id)).first()
    if not profile:
        profile = ProviderProfile(user_id=current_user.id, **payload.model_dump())
        session.add(profile)
    else:
        for k, v in payload.model_dump().items():
            setattr(profile, k, v)
    # elevate user role if profile is valid
    current_user.role = Role.PROVIDER

    provider_group = session.exec(select(Group).where(Group.name == Role.PROVIDER.value)).first()
    if provider_group and provider_group not in current_user.groups:
        current_user.groups.append(provider_group)

    session.add(current_user)
    session.commit()
    session.refresh(profile)

    return ProviderPublic(
        id=profile.id,
        user_id=profile.user_id,
        legal_name=profile.legal_name,
        cuit_or_cuil=profile.cuit_or_cuil,
        tax_status=profile.tax_status,
        category=profile.category,
        fiscal_address=profile.fiscal_address,
        service_areas=profile.service_areas,
        has_invoice=profile.has_invoice,
        bank_alias=profile.bank_alias,
        bank_cbu=profile.bank_cbu,
    )

@router.get("/me/status")
def provider_onboarding_status(current_user: Annotated[User, Depends(get_current_user)], session: SessionDep):
    profile = session.exec(select(ProviderProfile).where(ProviderProfile.user_id == current_user.id)).first()
    if not profile:
        return {"completed": False, "percent": 0, "missing": [
            "legal_name","cuit_or_cuil","tax_status","has_invoice","bank_alias_or_cbu"
        ]}

    missing: list[str] = []
    def req(field: str, ok: bool):
        if not ok:
            missing.append(field)

    req("legal_name", bool(profile.legal_name))
    req("cuit_or_cuil", bool(profile.cuit_or_cuil))
    req("tax_status", bool(profile.tax_status))
    req("category", bool(profile.category))
    req("service_areas", bool(profile.service_areas))
    req("has_invoice", profile.has_invoice is True)
    req("bank_alias_or_cbu", bool(profile.bank_alias or profile.bank_cbu))

    total = 7
    done = total - len(missing)
    percent = max(0, min(100, int((done/total)*100)))
    return {"completed": len(missing)==0, "percent": percent, "missing": missing}
