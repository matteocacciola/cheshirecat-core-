from typing import Type, Dict, List
from pydantic import BaseModel, ConfigDict

from cat.db.crud_source import CrudSource, get_crud_settings
from cat.db.database_source import DatabaseCrudSource
from cat.db.redis_source import RedisCrudSource
from cat.env import get_env
# from cat.mad_hatter.mad_hatter import MadHatter


# Base class to manage the source of crud.
class CrudSettings(BaseModel):
    # class instantiating the model
    _pyclass: Type = None

    # instantiate a crud from configuration
    @classmethod
    def get_crud_source_from_config(cls, config) -> CrudSource:
        if cls._pyclass is None:
            raise Exception(
                "Configuration class has self._pyclass==None. Should be a valid CrudSource class"
            )
        return cls._pyclass.default(**config)


class TinyDbCrudConfig(CrudSettings):
    file: str
    _pyclass: Type = DatabaseCrudSource

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "TinyDb Database Crud Source",
            "description": "Configuration source of Crud based on TinyDB.",
        }
    )


class RedisCrudConfig(CrudSettings):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    _pyclass: Type = RedisCrudSource

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Redis Crud Source",
            "description": "Configuration source of Crud on Redis.",
        }
    )


def get_allowed_crud_sources() -> List:
    return [TinyDbCrudConfig, RedisCrudConfig]

    # mad_hatter_instance = MadHatter()
    # list_configuration_sources = mad_hatter_instance.execute_hook(
    #     "factory_allowed_crud_sources", list_crud_sources_default, cat=None
    # )
    # return list_configuration_sources


def get_crud_source_from_name(name_crud: str) -> CrudSettings | None:
    """Find the crud adapter class by name"""
    for cls in get_allowed_crud_sources():
        if cls.__name__ == name_crud:
            return cls
    return None


def get_crud_sources_schemas() -> Dict:
    # CRUDSOURCE_SCHEMAS contains metadata to let any client know
    # which fields are required to create the crud source model.
    CRUDSOURCE_SCHEMAS = {}
    for config_class in get_allowed_crud_sources():
        schema = config_class.model_json_schema()
        # useful for clients in order to call the correct config endpoints
        schema["configurationSourceName"] = schema["title"]
        CRUDSOURCE_SCHEMAS[schema["title"]] = schema

    return CRUDSOURCE_SCHEMAS


def get_db() -> CrudSource:
    crud_settings = get_crud_settings()
    if not crud_settings:
        return TinyDbCrudConfig.get_crud_source_from_config({"file": get_env("CCAT_METADATA_FILE")})

    try:
        FactoryClass = get_crud_source_from_name(crud_settings.name)
        crud_source = FactoryClass.get_crud_source_from_config(crud_settings.value)
    except Exception:
        import traceback

        traceback.print_exc()
        crud_source = TinyDbCrudConfig.get_crud_source_from_config({"file": get_env("CCAT_METADATA_FILE")})

    return crud_source
