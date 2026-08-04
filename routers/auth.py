# ------------------------------------------------------------
# Endpoints de autenticación:
#   - POST /auth/register  
#   - POST /auth/login     
#   - GET  /auth/me        
# ------------------------------------------------------------
from __future__ import annotations
from datetime import datetime
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from database import get_session
from schema.users import User
from schema.auth import RegisterRequest, UserPublic
from schema.groups import Group
from core.security import hash_password, verify_password
from core.jwt import create_access_token, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])
SessionDep = Annotated[Session, Depends(get_session)]

# -------------------- REGISTER --------------------
@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, session: SessionDep):
    # RegisterRequest contains: full_name, email, password, phone?, province?, city?
    exists = session.exec(select(User).where(User.email == data.email)).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email ya registrado")
    user = User(
        full_name=data.full_name,
        email=data.email,
        password_hash=hash_password(data.password),
        phone=data.phone,
        province=data.province,
        city=data.city,
        tipo_documento=data.tipo_documento,
        nro_documento=data.nro_documento,
        fecha_nacimiento=data.fecha_nacimiento,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    user_group = session.exec(select(Group).where(Group.name == user.role)).first()
    if user_group:
        user.groups.append(user_group)
        session.add(user)
        session.commit()

    return UserPublic(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
    )

# -------------------- LOGIN --------------------
class TokenResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str | None = None
    role: str
    is_active: bool
    access_token: str
    token_type: str = "bearer"

@router.post("/login", response_model=TokenResponse)
def login(
    session: SessionDep,
    form_data: OAuth2PasswordRequestForm = Depends(),  # espera fields: username, password
):
    # En el front, mandar email en el campo "username"
    user = session.exec(select(User).where(User.email == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    if not user.is_active:
        detail = "Usuario bloqueado"
        if user.motivo_bloqueo:
            detail = f"Usuario bloqueado: {user.motivo_bloqueo}"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    user.ultimo_acceso = datetime.utcnow()
    session.add(user)
    session.commit()

    token = create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role}
    )

    return TokenResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=(user.role.value if hasattr(user, "role") and hasattr(user.role, "value") else str(user.role)),
        is_active=True,
        access_token=token,
    )

# -------------------- ME --------------------
from fastapi.security import OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")  # dónde se obtiene el token

def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep) -> User:
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    user = session.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no válido")
    return user

@router.get("/me", response_model=UserPublic)
def me(current_user: Annotated[User, Depends(get_current_user)]):
    return UserPublic(
        id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        role=current_user.role,
    )

@router.post("/refresh")
def refresh_token(current: User = Depends(get_current_user)):
    """
    Renueva el access token del usuario autenticado.
    Mantiene sub/email/role y sólo actualiza la expiración.
    """
    new_access = create_access_token(
        {"sub": str(current.id), "email": current.email, "role": current.role}
    )
    return {
        "access_token": new_access,
        "token_type": "bearer",
    }
