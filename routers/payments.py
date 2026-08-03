from __future__ import annotations
from typing import List, Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from datetime import datetime

from database import get_session
from schema.payments import Payment, PaymentCreate, PaymentPublic, PaymentStatus
from schema.reservations import Reservation, ReservationStatus
from schema.users import User
from routers.auth import get_current_user
from pydantic import BaseModel
from uuid import uuid4
from core.payment_gateways import get_gateway_adapter

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
)

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]

# Default commission rate for the application (10%)
DEFAULT_COMMISSION_RATE = 0.10


@router.post("/", response_model=PaymentPublic, status_code=status.HTTP_201_CREATED)
def create_payment(payload: PaymentCreate, session: SessionDep, current_user: CurrentUser):
    """
    Create a payment intent for a service reservation (reservation is NOT created yet).
    The payment stores the reservation intent (`service_id`, `reservation_datetime`, `notes`) and the `client_id`.
    """
    # validate service exists and is active
    # Explicitly validate service via Service model
    from schema.services import Service

    service = session.get(Service, payload.service_id) if payload.service_id else None
    if not service or not service.active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Servicio no encontrado o inactivo")

    if service.provider_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No puedes reservar tu propio servicio.")

    # Compute commission/net_amount if not provided
    commission = payload.commission if payload.commission is not None and payload.amount else (round((payload.amount or 0) * DEFAULT_COMMISSION_RATE, 2))
    net_amount = payload.net_amount if payload.net_amount is not None and payload.amount else (round((payload.amount or 0) - commission, 2) if payload.amount is not None else None)

    updates = {
        "client_id": current_user.id,
        "status": PaymentStatus.INITIALIZED,
        "external_reference": str(uuid4()),
        "commission": commission,
        "net_amount": net_amount,
    }

    db_payment = Payment.model_validate(payload, update=updates)

    session.add(db_payment)
    session.commit()
    session.refresh(db_payment)
    return db_payment


class InitiateResponse(BaseModel):
    payment_id: int
    payment_url: str
    external_reference: str


@router.post("/{payment_id}/initiate", response_model=InitiateResponse)
def initiate_payment(payment_id: int, session: SessionDep, current_user: CurrentUser):
    """
    Simula la creación de una preferencia en MercadoPago y devuelve una URL de pago.
    Actualiza el `estado` del pago a `pending`.
    """
    payment = session.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pago no encontrado")

    # ensure current user is the payer for this payment
    if payment.client_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")

    adapter = get_gateway_adapter(payment.gateway)
    initiation = adapter.initiate(payment)

    payment.status = PaymentStatus.PENDING
    payment.updated_at = datetime.utcnow()
    session.add(payment)
    session.commit()
    session.refresh(payment)

    return InitiateResponse(
        payment_id=payment.id,
        payment_url=initiation.payment_url,
        external_reference=initiation.external_reference,
    )


class GatewayCallback(BaseModel):
    external_reference: str | None = None
    payment_id: int | None = None
    transaction_id: str
    status: str  # e.g., "approved", "rejected"
    raw: dict | None = None


@router.post("/gateway-callback")
def gateway_callback(payload: GatewayCallback, session: SessionDep):
    """
    Endpoint público (webhook) que el gateway llamaría al finalizar el pago.
    Actualiza `transaction_id`, `estado` y la reserva asociada.
    """
    payment = None
    if payload.payment_id is not None:
        payment = session.get(Payment, payload.payment_id)
    elif payload.external_reference:
        stmt = select(Payment).where(Payment.external_reference == payload.external_reference)
        payment = session.exec(stmt).first()

    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pago no encontrado")

    # Update transaction id and state via adapter
    payment.transaction_id = payload.transaction_id
    payment.updated_at = datetime.utcnow()

    adapter = get_gateway_adapter(payment.gateway)
    normalized = adapter.normalize_status(payload.status)
    payment.transaction_status = normalized.transaction_status
    payment.status = normalized.payment_status

    # store entire gateway payload for audit
    if payload.raw is not None:
        payment.gateway_response = payload.raw
    else:
        # store minimal details if raw not provided
        payment.gateway_response = {"status": payload.status, "transaction_id": payload.transaction_id}

    # If payment approved, create reservation from intent if missing
    if payment.status == PaymentStatus.COMPLETED and not payment.reservation_id:
        if not payment.service_id or not payment.reservation_datetime or not payment.client_id:
            # insufficient data to create reservation
            payment.status = PaymentStatus.FAILED
        else:
            new_res = Reservation(
                service_id=payment.service_id,
                reservation_datetime=payment.reservation_datetime,
                notes=payment.notes,
                client_id=payment.client_id,
                status=ReservationStatus.PENDING,
            )
            session.add(new_res)
            session.commit()
            session.refresh(new_res)
            payment.reservation_id = new_res.id
            session.add(new_res)

    session.add(payment)
    session.commit()
    session.refresh(payment)

    return {"ok": True, "payment_id": payment.id, "status": payment.status}


@router.post("/{payment_id}/complete", response_model=PaymentPublic)
def complete_payment(payment_id: int, session: SessionDep, current_user: CurrentUser):
    """
    Marca un pago como completado (simula el callback del gateway).
    Actualiza el estado de la reserva asociada a `pending` si corresponde.
    """
    payment = session.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pago no encontrado")

    # Ensure the user is the payer
    if payment.client_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")

    payment.status = PaymentStatus.COMPLETED
    payment.updated_at = datetime.utcnow()

    # Create reservation if not present
    if not payment.reservation_id:
        if not payment.service_id or not payment.reservation_datetime:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient reservation intent data on payment")
        new_res = Reservation(
            service_id=payment.service_id,
            reservation_datetime=payment.reservation_datetime,
            notes=payment.notes,
            client_id=payment.client_id,
            status=ReservationStatus.PENDING,
        )
        session.add(new_res)
        session.commit()
        session.refresh(new_res)
        payment.reservation_id = new_res.id
        session.add(new_res)

    session.add(payment)
    session.commit()
    session.refresh(payment)
    return payment


@router.get("/my-payments", response_model=List[PaymentPublic])
def list_my_payments(session: SessionDep, current_user: CurrentUser):
    """Lista los pagos relacionados con las reservas del usuario actual."""
    statement = select(Payment).where(Payment.client_id == current_user.id).order_by(Payment.created_at.desc())
    payments = session.exec(statement).all()
    return payments


@router.get("/{payment_id}", response_model=PaymentPublic)
def get_payment(payment_id: int, session: SessionDep, current_user: CurrentUser):
    payment = session.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pago no encontrado")
    if payment.client_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")

    return payment
