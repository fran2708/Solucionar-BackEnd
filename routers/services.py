from __future__ import annotations

from typing import List, Optional, Annotated
from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlmodel import select, Session

from core.enums import TipoArea
from core.permissions import user_has_action
from routers.auth import get_current_user
from schema.users import User
from schema.services import Category, Service, ServiceImage, ServiceSchedule
from sqlmodel import SQLModel
from datetime import date
from database import get_session

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix="/services", tags=["services"])

# ----------------------- Categorías -----------------------

@router.post("/categorias", response_model=Category)
def create_category(payload: Category, session: SessionDep, current: CurrentUser):
    if not user_has_action(current, "categorias:crear"):
        raise HTTPException(status_code=403, detail="Solo ADMIN")
    # slug uniqueness check
    existing = session.exec(select(Category).where(Category.slug == payload.slug)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Slug ya existe")
    session.add(payload)
    session.commit()
    session.refresh(payload)
    return payload

@router.get("/categorias", response_model=List[Category])
def list_categories(session: SessionDep):
    return session.exec(select(Category).order_by(Category.name)).all()

@router.get("/categorias/{cat_id}", response_model=Category)
def get_category(cat_id: int, session: SessionDep):
    cat = session.get(Category, cat_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    return cat

@router.delete("/categorias/{cat_id}")
def delete_category(cat_id: int, session: SessionDep, current: CurrentUser):
    if not user_has_action(current, "categorias:eliminar"):
        raise HTTPException(status_code=403, detail="Solo ADMIN")
    cat = session.get(Category, cat_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    # TODO: decidir política (bloquear si hay servicios asociados)
    session.delete(cat)
    session.commit()
    return {"status": "ok"}

# ----------------------- Servicios -----------------------

class ServiceCreatePayload(SQLModel):
    category_id: int
    title: str
    description: str
    price: float | None = None
    currency: str = "ARS"
    duration_min: int = 0  # 0 = indefinido
    area_type: TipoArea = TipoArea.PRESENCIAL
    location_note: Optional[str] = None
    price_to_agree: bool = False
    radius_km: Optional[float] = None
    # Nuevos campos de disponibilidad
    availability_start_date: Optional[date] = None
    availability_end_date: Optional[date] = None

@router.post("/", response_model=Service)
@router.post("", response_model=Service)  # allow both /services and /services/ without redirect
def create_service(payload: ServiceCreatePayload, session: SessionDep, current: CurrentUser):
    if not user_has_action(current, "servicios:crear"):
        raise HTTPException(status_code=403, detail="Solo proveedores")
    # Validaciones nuevas (permiten precio a convenir y duración indefinida = 0)
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Título requerido")
    if not payload.description.strip():
        raise HTTPException(status_code=400, detail="Descripción requerida")
    if payload.price is None and not payload.price_to_agree:
        raise HTTPException(status_code=400, detail="Precio requerido salvo 'a convenir'")
    if payload.price is not None and payload.price <= 0:
        raise HTTPException(status_code=400, detail="Precio debe ser > 0")
    if payload.duration_min < 0:
        raise HTTPException(status_code=400, detail="Duración inválida")
    if payload.area_type == TipoArea.PERSONALIZADO and not payload.location_note:
        raise HTTPException(status_code=400, detail="location_note requerido para PERSONALIZADO")
    if payload.availability_start_date and payload.availability_end_date:
        if payload.availability_start_date > payload.availability_end_date:
            raise HTTPException(status_code=400, detail="La fecha de inicio de disponibilidad no puede ser posterior a la de fin.")

    cat = session.get(Category, payload.category_id)
    if not cat:
        raise HTTPException(status_code=400, detail="Categoría inválida")
    kwargs = dict(
        provider_id=current.id,
        category_id=payload.category_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        price=(payload.price if not payload.price_to_agree else 0),
        currency=payload.currency,
        duration_min=payload.duration_min,
        area_type=payload.area_type,
        location_note=payload.location_note,
        price_to_agree=payload.price_to_agree,
        radius_km=payload.radius_km,
        availability_start_date=payload.availability_start_date,
        availability_end_date=payload.availability_end_date,
    )
    svc = Service(**kwargs)
    session.add(svc)
    session.commit()
    session.refresh(svc)
    return svc

@router.get("/", response_model=List[Service])
@router.get("", response_model=List[Service])  # allow without trailing slash
def list_services(session: SessionDep, q: Optional[str] = Query(None), category_id: Optional[int] = None):
    stmt = select(Service).where(Service.active == True)  # noqa: E712
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Service.title.ilike(like))
    if category_id:
        stmt = stmt.where(Service.category_id == category_id)
    return session.exec(stmt.order_by(Service.created_at.desc())).all()

@router.get("/mios", response_model=List[Service])
def list_my_services(session: SessionDep, current: CurrentUser, active: Optional[bool] = None):
    puede_ver_todos = user_has_action(current, "servicios:ver_todos")
    if not (puede_ver_todos or user_has_action(current, "servicios:administrar")):
        raise HTTPException(status_code=403, detail="Solo proveedores o admin")
    stmt = select(Service)
    if not puede_ver_todos:
        stmt = stmt.where(Service.provider_id == current.id)
    if active is not None:
        stmt = stmt.where(Service.active == active)
    return session.exec(stmt.order_by(Service.created_at.desc())).all()

@router.get("/{service_id}", response_model=Service)
def get_service(service_id: int, session: SessionDep):
    svc = session.get(Service, service_id)
    if not svc or not svc.active:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    return svc

class ServiceUpdatePayload(SQLModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    duration_min: Optional[int] = None
    area_type: Optional[TipoArea] = None
    location_note: Optional[str] = None
    price_to_agree: Optional[bool] = None
    category_id: Optional[int] = None
    radius_km: Optional[float] = None
    # Nuevos campos de disponibilidad
    availability_start_date: Optional[date] = None
    availability_end_date: Optional[date] = None

@router.put("/{service_id}", response_model=Service)
def update_service(service_id: int, payload: ServiceUpdatePayload, session: SessionDep, current: CurrentUser):
    svc = session.get(Service, service_id)
    if not svc or not svc.active:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    if not user_has_action(current, "servicios:editar_cualquiera") and svc.provider_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado")
    if payload.price is not None and payload.price <= 0:
        raise HTTPException(status_code=400, detail="Precio debe ser > 0")
    if payload.duration_min is not None and payload.duration_min < 0:
        raise HTTPException(status_code=400, detail="Duración inválida")
    if payload.area_type == TipoArea.PERSONALIZADO and payload.location_note is None:
        raise HTTPException(status_code=400, detail="location_note requerido para PERSONALIZADO")

    # Validar fechas de disponibilidad
    start_date = payload.availability_start_date if payload.availability_start_date is not None else svc.availability_start_date
    end_date = payload.availability_end_date if payload.availability_end_date is not None else svc.availability_end_date
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="La fecha de inicio de disponibilidad no puede ser posterior a la de fin.")

    # update fields
    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(svc, field, val)
    session.add(svc)
    session.commit()
    session.refresh(svc)
    return svc

@router.delete("/{service_id}")
def deactivate_service(service_id: int, session: SessionDep, current: CurrentUser):
    svc = session.get(Service, service_id)
    if not svc or not svc.active:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    if not user_has_action(current, "servicios:editar_cualquiera") and svc.provider_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado")
    svc.active = False
    session.add(svc)
    session.commit()
    return {"status": "ok"}

# ----------------------- Imágenes -----------------------

@router.post("/{service_id}/imagenes", response_model=List[ServiceImage])
def upsert_images(service_id: int, images: List[ServiceImage], session: SessionDep, current: CurrentUser):
    svc = session.get(Service, service_id)
    if not svc or not svc.active:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    if not user_has_action(current, "servicios:editar_cualquiera") and svc.provider_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado")
    # remove old
    old = session.exec(select(ServiceImage).where(ServiceImage.service_id == service_id)).all()
    for o in old:
        session.delete(o)
    cover_count = sum(1 for i in images if i.is_cover)
    if cover_count > 1:
        raise HTTPException(status_code=400, detail="Solo una imagen de portada")
    for img in images:
        img.id = None
        img.service_id = service_id
        session.add(img)
    session.commit()
    return session.exec(select(ServiceImage).where(ServiceImage.service_id == service_id).order_by(ServiceImage.sort_order)).all()

@router.get("/{service_id}/imagenes", response_model=List[ServiceImage])
def list_images(service_id: int, session: SessionDep):
    return session.exec(select(ServiceImage).where(ServiceImage.service_id == service_id).order_by(ServiceImage.sort_order)).all()

# ----------------------- Horarios -----------------------

@router.post("/{service_id}/horarios", response_model=List[ServiceSchedule])
def upsert_schedule(service_id: int, items: List[ServiceSchedule], session: SessionDep, current: CurrentUser):
    svc = session.get(Service, service_id)
    if not svc or not svc.active:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    if not user_has_action(current, "servicios:editar_cualquiera") and svc.provider_id != current.id:
        raise HTTPException(status_code=403, detail="No autorizado")
    # validate
    for i in items:
        if not (0 <= i.weekday <= 6):
            raise HTTPException(status_code=400, detail="weekday fuera de rango")
        if i.time_from >= i.time_to:
            raise HTTPException(status_code=400, detail="Rango horario inválido")
    # replace all
    old = session.exec(select(ServiceSchedule).where(ServiceSchedule.service_id == service_id)).all()
    for o in old:
        session.delete(o)
    for i in items:
        i.id = None
        i.service_id = service_id
        session.add(i)
    session.commit()
    return session.exec(select(ServiceSchedule).where(ServiceSchedule.service_id == service_id).order_by(ServiceSchedule.weekday, ServiceSchedule.time_from)).all()

@router.get("/{service_id}/horarios", response_model=List[ServiceSchedule])
def list_schedule(service_id: int, session: SessionDep):
    return session.exec(select(ServiceSchedule).where(ServiceSchedule.service_id == service_id).order_by(ServiceSchedule.weekday, ServiceSchedule.time_from)).all()
