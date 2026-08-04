# ------------------------------------------------------------
# Autorización basada en el modelo de seguridad GRUPO/ACCION.
# Reemplaza los chequeos ad-hoc de `current.role != Role.X`.
# ------------------------------------------------------------
from __future__ import annotations
from typing import Annotated
from fastapi import Depends, HTTPException, status

from schema.users import User
from routers.auth import get_current_user


def user_has_action(user: User, action_key: str) -> bool:
    """Verifica si `user` tiene la acción `modulo:nombre` a través de alguno
    de sus grupos activos. Implementa USUARIO.puedeEjecutar(accion)."""
    modulo, nombre = action_key.split(":", 1)
    return any(
        action.modulo == modulo and action.name == nombre
        for group in user.groups
        if group.active
        for action in group.actions
    )


def require_action(action_key: str):
    """Dependencia de FastAPI: exige que el usuario actual tenga la acción dada."""
    def _dep(current: Annotated[User, Depends(get_current_user)]) -> User:
        if not user_has_action(current, action_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No autorizado para esta acción",
            )
        return current
    return _dep
