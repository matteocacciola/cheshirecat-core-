from typing import Dict, List
from tinydb import TinyDB, Query
from uuid import uuid4

from cat.auth.permissions import get_full_permissions, get_base_permissions
from cat.auth.auth_utils import hash_password
from cat.db.crud_source import CrudSource
from cat.db.models import Setting


class DatabaseCrudSource(CrudSource):
    file: str

    def __init__(self):
        self.db = TinyDB(self.file)

    def get_settings(self, search: str = "", *args, **kwargs) -> List[Dict]:
        query = Query()
        return self.db.search(query.name.matches(search))

    def get_settings_by_category(self, category: str, *args, **kwargs) -> List[Dict]:
        query = Query()
        return self.db.search(query.category == category)

    def create_setting(self, payload: Setting, *args, **kwargs) -> Dict:
        # Missing fields (setting_id, updated_at) are filled automatically by pydantic
        self.db.insert(payload.model_dump())

        # retrieve the record we just created
        return self.get_setting_by_id(payload.setting_id)

    def get_setting_by_name(self, name: str, *args, **kwargs) -> Dict | None:
        query = Query()
        result = self.db.search(query.name == name)
        if len(result) > 0:
            return result[0]
        return None

    def get_setting_by_id(self, setting_id: str, *args, **kwargs) -> Dict | None:
        query = Query()
        result = self.db.search(query.setting_id == setting_id)
        if len(result) > 0:
            return result[0]
        return None

    def delete_setting_by_id(self, setting_id: str, *args, **kwargs) -> None:
        query = Query()
        self.db.remove(query.setting_id == setting_id)

    def delete_settings_by_category(self, category: str, *args, **kwargs) -> None:
        query = Query()
        self.db.remove(query.category == category)

    def update_setting_by_id(self, payload: Setting, *args, **kwargs) -> Dict:
        query = Query()
        self.db.update(payload, query.setting_id == payload.setting_id)

        return self.get_setting_by_id(payload.setting_id)

    def upsert_setting_by_name(self, payload: Setting, *args, **kwargs) -> Dict | None:
        old_setting = self.get_setting_by_name(payload.name)

        if not old_setting:
            self.create_setting(payload)
        else:
            query = Query()
            self.db.update(payload, query.name == payload.name)

        return self.get_setting_by_name(payload.name)
