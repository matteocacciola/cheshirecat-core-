from abc import ABC, abstractmethod
from typing import Dict, List
from tinydb import TinyDB, Query

from cat.db.models import CrudSetting, Setting
from cat.env import get_env
from cat.utils import singleton


class CrudSource(ABC):
    @abstractmethod
    def get_settings(self, search: str = "", *args, **kwargs) -> List[Dict]:
        pass

    @abstractmethod
    def get_settings_by_category(self, category: str, *args, **kwargs) -> List[Dict]:
        pass

    @abstractmethod
    def create_setting(self, payload: Setting, *args, **kwargs) -> Dict:
        pass

    @abstractmethod
    def get_setting_by_name(self, name: str, *args, **kwargs) -> Dict | None:
        pass

    @abstractmethod
    def get_setting_by_id(self, setting_id: str, *args, **kwargs) -> Dict | None:
        pass

    @abstractmethod
    def delete_setting_by_id(self, setting_id: str, *args, **kwargs) -> None:
        pass

    @abstractmethod
    def delete_settings_by_category(self, category: str, *args, **kwargs) -> None:
        pass

    @abstractmethod
    def update_setting_by_id(self, payload: Setting, *args, **kwargs) -> Dict:
        pass

    @abstractmethod
    def upsert_setting_by_name(self, payload: Setting, *args, **kwargs) -> Setting:
        pass


@singleton
class CrudSourceSettings:
    def __init__(self):
        self.db = TinyDB(self.get_file_name())

    def get_file_name(self):
        tinydb_file = get_env("CCAT_CRUD_SETTINGS_FILE")
        return tinydb_file


def get_db():
    return CrudSourceSettings().db


def get_crud_settings() -> CrudSetting | None:
    crud_config = get_db().search(Query().name.exists())
    if not crud_config:
        return None

    return CrudSetting(**crud_config[0])


def upsert_setting_by_name(payload: CrudSetting) -> CrudSetting:
    old_setting = get_crud_settings()

    if not old_setting:
        # Create a new crud setting; missing fields (setting_id, updated_at) are filled automatically by pydantic
        get_db().insert(payload.model_dump())
    else:
        query = Query()
        get_db().update(payload, query.name == payload.name)

    return get_crud_settings()
