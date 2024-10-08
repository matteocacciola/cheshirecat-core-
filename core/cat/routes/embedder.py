from typing import Dict
from fastapi import APIRouter, Body, HTTPException, Depends

from cat import utils
from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.factory.embedder import get_allowed_embedder_models, get_embedders_schemas
from cat.db import crud, models
from cat.log import log

router = APIRouter()

# general embedder settings are saved in settings table under this category
EMBEDDER_SELECTED_CATEGORY = "embedder"

# embedder type and config are saved in settings table under this category
EMBEDDER_CATEGORY = "embedder_factory"

# embedder selected configuration is saved under this name
EMBEDDER_SELECTED_NAME = "embedder_selected"


# get configured Embedders and configuration schemas
@router.get("/settings")
def get_embedders_settings(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.EMBEDDER, AuthPermission.LIST)),
) -> Dict:
    """Get the list of the Embedders"""

    chatbot_id = cats.cheshire_cat.id

    supported_emdedding_models = get_allowed_embedder_models(chatbot_id)
    # get selected Embedder, if any
    selected = crud.get_setting_by_name(name=EMBEDDER_SELECTED_NAME, chatbot_id=chatbot_id)
    if selected is not None:
        selected = selected["value"]["name"]
    else:
        # TODO: take away automatic embedder settings in v2
        # If DB does not contain a selected embedder, it means an embedder was automatically selected.
        # Deduce selected embedder:
        ccat = cats.cheshire_cat
        for embedder_config_class in reversed(supported_emdedding_models):
            if isinstance(ccat.embedder, embedder_config_class._pyclass.default):
                selected = embedder_config_class.__name__

    saved_settings = crud.get_settings_by_category(category=EMBEDDER_CATEGORY, chatbot_id=chatbot_id)
    saved_settings = {s["name"]: s for s in saved_settings}

    settings = []
    for class_name, schema in get_embedders_schemas(chatbot_id).items():
        if class_name in saved_settings:
            saved_setting = saved_settings[class_name]["value"]
        else:
            saved_setting = {}

        settings.append(
            {
                "name": class_name,
                "value": saved_setting,
                "schema": schema,
            }
        )

    return {
        "settings": settings,
        "selected_configuration": selected,
    }


# get Embedder settings and its schema
@router.get("/settings/{language_embedder_name}")
def get_embedder_settings(
    language_embedder_name: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.EMBEDDER, AuthPermission.READ)),
) -> Dict:
    """Get settings and schema of the specified Embedder"""

    chatbot_id = cats.cheshire_cat.id

    embedder_schemas = get_embedders_schemas(chatbot_id)
    # check that language_embedder_name is a valid name
    allowed_configurations = list(embedder_schemas.keys())
    if language_embedder_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{language_embedder_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    setting = crud.get_setting_by_name(name=language_embedder_name, chatbot_id=chatbot_id)
    schema = embedder_schemas[language_embedder_name]

    setting = {} if setting is None else setting["value"]

    return {"name": language_embedder_name, "value": setting, "schema": schema}


@router.put("/settings/{language_embedder_name}")
def upsert_embedder_setting(
    language_embedder_name: str,
    payload: Dict = Body({"openai_api_key": "your-key-here"}),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.EMBEDDER, AuthPermission.EDIT)),
) -> Dict:
    """Upsert the Embedder setting"""

    ccat = cats.cheshire_cat
    chatbot_id = ccat.id

    embedder_schemas = get_embedders_schemas(chatbot_id)
    # check that language_embedder_name is a valid name
    allowed_configurations = list(embedder_schemas.keys())
    if language_embedder_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{language_embedder_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    # get selected config if any
    selected = crud.get_setting_by_name(name=EMBEDDER_SELECTED_NAME, chatbot_id=chatbot_id)

    # create the setting and upsert it
    final_setting = crud.upsert_setting_by_name(
        models.Setting(
            name=language_embedder_name, category=EMBEDDER_CATEGORY, value=payload
        ),
        chatbot_id=chatbot_id
    )

    crud.upsert_setting_by_name(
        models.Setting(
            name=EMBEDDER_SELECTED_NAME,
            category=EMBEDDER_SELECTED_CATEGORY,
            value={"name": language_embedder_name},
        ),
        chatbot_id=chatbot_id
    )

    status = {"name": language_embedder_name, "value": final_setting["value"]}

    # reload llm and embedder of the cat
    ccat.load_natural_language()
    # crete new collections (different embedder!)
    try:
        ccat.load_memory()
    except Exception as e:
        log.error(e)
        crud.delete_settings_by_category(category=EMBEDDER_SELECTED_CATEGORY, chatbot_id=chatbot_id)
        crud.delete_settings_by_category(category=EMBEDDER_CATEGORY, chatbot_id=chatbot_id)

        # if a selected config is present, restore it
        if selected is not None:
            current_settings = crud.get_setting_by_name(name=selected["value"]["name"], chatbot_id=chatbot_id)

            language_embedder_name = selected["value"]["name"]
            crud.upsert_setting_by_name(
                models.Setting(
                    name=language_embedder_name,
                    category=EMBEDDER_CATEGORY,
                    value=current_settings["value"],
                ),
                chatbot_id=chatbot_id
            )
            crud.upsert_setting_by_name(
                models.Setting(
                    name=EMBEDDER_SELECTED_NAME,
                    category=EMBEDDER_SELECTED_CATEGORY,
                    value={"name": language_embedder_name},
                ),
                chatbot_id=chatbot_id
            )
            # reload llm and embedder of the cat
            ccat.load_natural_language()

        raise HTTPException(
            status_code=400, detail={"error": utils.explicit_error_message(e)}
        )
    # recreate tools embeddings
    ccat.mad_hatter.find_plugins()

    return status
