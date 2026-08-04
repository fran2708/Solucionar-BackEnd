from __future__ import annotations
from typing import List, Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from database import get_session
from schema.reservations import (
    Reservation,
    ReservationCreate,
    ReservationPublic,
    ReservationStatus,
    ReservationStatusUpdate,
)
from schema.reviews import ReservationReview, ReservationReviewPublic
from schema.services import Service
from schema.users import User
from core.permissions import user_has_action
from routers.auth import get_current_user

router = APIRouter(
    prefix="/reservations",
    tags=["reservations"],
)

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

@router.post("/", response_model=ReservationPublic, status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: ReservationCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """
    Crea una nueva reserva para un servicio.
    El usuario actual (cliente) realiza la reserva.
    """
    service = session.get(Service, payload.service_id)
    if not service or not service.active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Servicio no encontrado o inactivo",
        )

    if service.provider_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes reservar tu propio servicio.",
        )

    # Validar que la fecha de reserva esté dentro de la disponibilidad del servicio
    if service.availability_start_date and payload.reservation_datetime.date() < service.availability_start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha de reserva es anterior a la disponibilidad del servicio.",
        )
    if service.availability_end_date and payload.reservation_datetime.date() > service.availability_end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha de reserva es posterior a la disponibilidad del servicio.",
        )

    # TODO: Añadir validación más compleja, ej:
    # - No superponer con otras reservas confirmadas para el mismo servicio/proveedor.
    # - Validar contra los `ServiceSchedule` (horarios por día de semana).

    # New flow: reservations must be created only after successful payment.
    # Direct reservation creation is disabled; instruct the client to create a payment intent instead.
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Las reservas ahora se crean solo después del pago. Crea un intent de pago en /payments/ con los datos de la reserva.",
    )


@router.get("/my-reservations", response_model=List[ReservationPublic])
def get_my_reservations(session: SessionDep, current_user: CurrentUser):
    """
    Obtiene todas las reservas hechas por el usuario actual (como cliente).
    """
    statement = select(Reservation).where(Reservation.client_id == current_user.id)
    reservations = session.exec(statement.order_by(Reservation.reservation_datetime.desc())).all()
    return _hydrate_reviews(reservations, session)


@router.get("/provider-reservations", response_model=List[ReservationPublic])
def get_provider_reservations(session: SessionDep, current_user: CurrentUser):
    """
    Obtiene todas las reservas para los servicios ofrecidos por el usuario actual (como proveedor).
    """
    if not user_has_action(current_user, "reservations:gestionar_como_proveedor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No eres un proveedor.",
        )

    # Obtener los IDs de todos los servicios del proveedor actual
    provider_services_ids_stmt = select(Service.id).where(Service.provider_id == current_user.id)
    provider_services_ids = list(session.exec(provider_services_ids_stmt))

    if not provider_services_ids:
        return []

    statement = select(Reservation).where(Reservation.service_id.in_(provider_services_ids))
    reservations = session.exec(statement.order_by(Reservation.reservation_datetime.desc())).all()
    return _hydrate_reviews(reservations, session)


FINAL_STATUSES = {
    ReservationStatus.CANCELLED_BY_CLIENT,
    ReservationStatus.CANCELLED_BY_PROVIDER,
    ReservationStatus.COMPLETED,
}


def _hydrate_reviews(reservations: List[Reservation], session: Session) -> List[ReservationPublic]:
    if not reservations:
        return []
    reservation_ids = [reservation.id for reservation in reservations]
    review_stmt = select(ReservationReview).where(ReservationReview.reservation_id.in_(reservation_ids))
    reviews = session.exec(review_stmt).all()
    review_map = {review.reservation_id: review for review in reviews}

    payloads: List[ReservationPublic] = []
    for reservation in reservations:
        payload = ReservationPublic.model_validate(reservation, from_attributes=True)
        review = review_map.get(reservation.id)
        if review:
            payload.review = ReservationReviewPublic.model_validate(review, from_attributes=True)
        payloads.append(payload)
    return payloads


@router.patch("/{reservation_id}/status", response_model=ReservationPublic)
def update_reservation_status(
    reservation_id: int,
    payload: ReservationStatusUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    reservation = session.get(Reservation, reservation_id)
    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reserva no encontrada",
        )

    if reservation.status in FINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La reserva ya fue finalizada y no admite cambios.",
        )

    new_status = payload.status

    if new_status == ReservationStatus.CANCELLED_BY_CLIENT:
        if reservation.client_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el cliente puede cancelar esta reserva.",
            )
    elif new_status in (ReservationStatus.CANCELLED_BY_PROVIDER, ReservationStatus.COMPLETED):
        if not user_has_action(current_user, "reservations:gestionar_como_proveedor"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el proveedor puede realizar esta acción.",
            )
        service = session.get(Service, reservation.service_id)
        if not service or service.provider_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos sobre esta reserva.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Estado solicitado no soportado.",
        )

    reservation.status = new_status
    session.add(reservation)
    session.commit()
    session.refresh(reservation)
    return reservation
