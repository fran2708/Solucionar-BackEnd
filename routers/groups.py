# ------------------------------------------------------------
# Administración del modelo de seguridad: GRUPO, ACCION y su
# asignación a USUARIO. Solo ADMIN (acción usuarios:administrar_permisos).
# ------------------------------------------------------------
from __future__ import annotations
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, SQLModel, select

from database import get_session
from core.permissions import require_action
from schema.users import User
from schema.groups import Group, Action, GroupPublic, GroupCreate, ActionPublic, ActionCreate

router = APIRouter(prefix="/groups", tags=["groups"])

SessionDep = Annotated[Session, Depends(get_session)]
AdminUser = Annotated[User, Depends(require_action("usuarios:administrar_permisos"))]


@router.get("/", response_model=List[GroupPublic])
def list_groups(session: SessionDep, current: AdminUser):
    return session.exec(select(Group)).all()


@router.post("/", response_model=GroupPublic, status_code=status.HTTP_201_CREATED)
def create_group(payload: GroupCreate, session: SessionDep, current: AdminUser):
    existing = session.exec(select(Group).where(Group.name == payload.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya existe un grupo con ese nombre")
    group = Group(name=payload.name, description=payload.description)
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


@router.get("/actions", response_model=List[ActionPublic])
def list_actions(session: SessionDep, current: AdminUser):
    return session.exec(select(Action)).all()


@router.post("/actions", response_model=ActionPublic, status_code=status.HTTP_201_CREATED)
def create_action(payload: ActionCreate, session: SessionDep, current: AdminUser):
    action = Action(name=payload.name, description=payload.description, modulo=payload.modulo)
    session.add(action)
    session.commit()
    session.refresh(action)
    return action


@router.post("/{group_id}/acciones/{action_id}", response_model=GroupPublic)
def asignar_accion(group_id: int, action_id: int, session: SessionDep, current: AdminUser):
    """GRUPO.asignar(accion)"""
    group = session.get(Group, group_id)
    action = session.get(Action, action_id)
    if not group or not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo o acción no encontrada")
    if action not in group.actions:
        group.actions.append(action)
        session.add(group)
        session.commit()
        session.refresh(group)
    return group


@router.delete("/{group_id}/acciones/{action_id}", response_model=GroupPublic)
def revocar_accion(group_id: int, action_id: int, session: SessionDep, current: AdminUser):
    """GRUPO.revocar(accion)"""
    group = session.get(Group, group_id)
    action = session.get(Action, action_id)
    if not group or not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo o acción no encontrada")
    if action in group.actions:
        group.actions.remove(action)
        session.add(group)
        session.commit()
        session.refresh(group)
    return group


@router.post("/users/{user_id}/grupos/{group_id}")
def agregar_a_grupo(user_id: int, group_id: int, session: SessionDep, current: AdminUser):
    """USUARIO.agregarAGrupo(grupo)"""
    user = session.get(User, user_id)
    group = session.get(Group, group_id)
    if not user or not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario o grupo no encontrado")
    if group not in user.groups:
        user.groups.append(group)
        session.add(user)
        session.commit()
    return {"status": "ok"}


@router.delete("/users/{user_id}/grupos/{group_id}")
def quitar_de_grupo(user_id: int, group_id: int, session: SessionDep, current: AdminUser):
    """USUARIO.quitarDeGrupo(grupo)"""
    user = session.get(User, user_id)
    group = session.get(Group, group_id)
    if not user or not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario o grupo no encontrado")
    if group in user.groups:
        user.groups.remove(group)
        session.add(user)
        session.commit()
    return {"status": "ok"}


class BloquearRequest(SQLModel):
    motivo: str | None = None


@router.post("/users/{user_id}/bloquear")
def bloquear_usuario(user_id: int, payload: BloquearRequest, session: SessionDep, current: AdminUser):
    """USUARIO.bloquear(motivo)"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    user.is_active = False
    user.motivo_bloqueo = payload.motivo
    session.add(user)
    session.commit()
    return {"status": "ok"}


@router.post("/users/{user_id}/desbloquear")
def desbloquear_usuario(user_id: int, session: SessionDep, current: AdminUser):
    """USUARIO.desbloquear()"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    user.is_active = True
    user.motivo_bloqueo = None
    session.add(user)
    session.commit()
    return {"status": "ok"}
