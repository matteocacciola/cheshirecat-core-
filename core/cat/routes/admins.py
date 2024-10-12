from typing import List

from fastapi import Depends, APIRouter, HTTPException

from cat.db import crud
from cat.auth.permissions import AuthPermission, AuthResource
from cat.auth.auth_utils import hash_password
from cat.auth.connection import ConnectionSuperAdminAuth
from cat.looking_glass.bill_the_lizard import BillTheLizard
from cat.routes.models.users import UserResponse, UserCreate, UserUpdate

router = APIRouter()


@router.post("/", response_model=UserResponse)
def create_admin(
    new_user: UserCreate,
    lizard: BillTheLizard = Depends(ConnectionSuperAdminAuth(AuthResource.ADMIN, AuthPermission.LIST)),
):
    created_user = crud.create_user(lizard.config_key, new_user.model_dump())
    if not created_user:
        raise HTTPException(status_code=403, detail={"error": "Cannot duplicate admin"})

    return created_user


@router.get("/", response_model=List[UserResponse])
def read_admins(
    skip: int = 0,
    limit: int = 100,
    lizard: BillTheLizard = Depends(ConnectionSuperAdminAuth(AuthResource.ADMIN, AuthPermission.LIST)),
):
    users_db = crud.get_users(lizard.config_key)

    users = list(users_db.values())[skip: skip + limit]
    return users


@router.get("/{user_id}", response_model=UserResponse)
def read_admin(
    user_id: str,
    lizard: BillTheLizard = Depends(ConnectionSuperAdminAuth(AuthResource.ADMIN, AuthPermission.READ)),
):
    users_db = crud.get_users(lizard.config_key)

    if user_id not in users_db:
        raise HTTPException(status_code=404, detail={"error": "User not found"})
    return users_db[user_id]


@router.put("/{user_id}", response_model=UserResponse)
def update_admin(
    user_id: str,
    user: UserUpdate,
    lizard: BillTheLizard = Depends(ConnectionSuperAdminAuth(AuthResource.ADMIN, AuthPermission.EDIT)),
):
    stored_user = crud.get_user(lizard.config_key, user_id)
    if not stored_user:
        raise HTTPException(status_code=404, detail={"error": "User not found"})
    
    if user.password:
        user.password = hash_password(user.password)
    updated_info = stored_user | user.model_dump(exclude_unset=True)

    crud.update_user(lizard.config_key, user_id, updated_info)
    return updated_info


@router.delete("/{user_id}", response_model=UserResponse)
def delete_admin(
    user_id: str,
    lizard: BillTheLizard = Depends(ConnectionSuperAdminAuth(AuthResource.ADMIN, AuthPermission.DELETE)),
):
    deleted_user = crud.delete_user(lizard.config_key, user_id)
    if not deleted_user:
        raise HTTPException(status_code=404, detail={"error": "User not found"})

    return deleted_user
