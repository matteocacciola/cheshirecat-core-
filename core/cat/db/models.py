from datetime import datetime
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List


def generate_uuid():
    return str(uuid4())


def generate_timestamp():
    return int(datetime.now().timestamp())


# base class for crud setting
class CrudSettingBody(BaseModel):
    name: str
    value: Dict | List


# actual crud setting class, with additional auto generated id and update time
class CrudSetting(CrudSettingBody):
    updated_at: int = Field(default_factory=generate_timestamp)


# base class for setting, used to annotate fastAPI endpoints
class SettingBody(BaseModel):
    name: str
    value: Dict | List
    category: str | None = None

    @field_validator("name")
    def non_empty_name(cls, v):
        if not v:
            raise ValueError("Setting name cannot be empty")
        return v


# actual setting class, with additional auto generated id and update time
class Setting(SettingBody):
    setting_id: str = Field(default_factory=generate_uuid)
    updated_at: int = Field(default_factory=generate_timestamp)
