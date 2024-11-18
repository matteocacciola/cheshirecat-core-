from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Dict
from fastapi import APIRouter, Depends, Query

from cat.auth.permissions import AdminAuthResource, AuthPermission, get_full_admin_permissions
from cat.auth.auth_utils import hash_password
from cat.auth.connection import AdminConnectionAuth
from cat.db.cruds import users as crud_users
from cat.exceptions import CustomNotFoundException, CustomForbiddenException
from cat.looking_glass.bill_the_lizard import BillTheLizard

router = APIRouter()


class AdminBase(BaseModel):
    username: str = Field(min_length=2)
    permissions: Dict[str, List[str]] = get_full_admin_permissions()

    @field_validator("permissions")
    def validate_permissions(cls, v):
        if not v:
            raise ValueError("Permissions cannot be empty")
        for k_, v_ in v.items():
            if not v_:
                raise ValueError(f"Permissions for {k_} cannot be empty")
            if k_ not in AdminAuthResource:
                raise ValueError(f"Invalid resource: {k_}")
            if any([p not in AuthPermission for p in v_]):
                raise ValueError(f"Invalid permissions for {k_}")
        return v


class AdminCreate(AdminBase):
    password: str = Field(min_length=5)
    # no additional fields allowed
    model_config = ConfigDict(extra="forbid")


class AdminUpdate(AdminBase):
    username: str = Field(default=None, min_length=2)
    password: str = Field(default=None, min_length=4)
    permissions: Dict[str, List[str]] = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("permissions")
    def validate_permissions(cls, v):
        if v is None:
            return v
        return super().validate_permissions(v)


class AdminResponse(AdminBase):
    id: str


@router.post("/", response_model=AdminResponse)
def create_admin(
    new_user: AdminCreate,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.ADMINS, AuthPermission.WRITE)),
):
    created_user = crud_users.create_user(lizard.config_key, new_user.model_dump())
    if not created_user:
        raise CustomForbiddenException("Cannot duplicate admin")

    return created_user


@router.get("/", response_model=List[AdminResponse])
def read_admins(
    skip: int = Query(default=0, description="How many admins to skip."),
    limit: int = Query(default=100, description="How many admins to return."),
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.ADMINS, AuthPermission.LIST)),
):
    users_db = crud_users.get_users(lizard.config_key)

    users = list(users_db.values())[skip:(skip + limit)]
    return users


@router.get("/{user_id}", response_model=AdminResponse)
def read_admin(
    user_id: str,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.ADMINS, AuthPermission.READ)),
):
    users_db = crud_users.get_users(lizard.config_key)

    if user_id not in users_db:
        raise CustomNotFoundException("User not found")
    return users_db[user_id]


@router.put("/{user_id}", response_model=AdminResponse)
def update_admin(
    user_id: str,
    user: AdminUpdate,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.ADMINS, AuthPermission.EDIT)),
):
    stored_user = crud_users.get_user(lizard.config_key, user_id)
    if not stored_user:
        raise CustomNotFoundException("User not found")
    
    if user.password:
        user.password = hash_password(user.password)
    updated_info = {**stored_user, **user.model_dump(exclude_unset=True)}

    crud_users.update_user(lizard.config_key, user_id, updated_info)
    return updated_info


@router.delete("/{user_id}", response_model=AdminResponse)
def delete_admin(
    user_id: str,
    lizard: BillTheLizard = Depends(AdminConnectionAuth(AdminAuthResource.ADMINS, AuthPermission.DELETE)),
):
    deleted_user = crud_users.delete_user(lizard.config_key, user_id)
    if not deleted_user:
        raise CustomNotFoundException("User not found")

    return deleted_user
