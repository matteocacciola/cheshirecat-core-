from typing import Dict

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from fastapi import APIRouter, Body, HTTPException, Depends

from cat.factory.llm import get_llms_schemas
from cat.db import crud, models
from cat.log import log
from cat import utils

router = APIRouter()

# general LLM settings are saved in settings table under this category
LLM_SELECTED_CATEGORY = "llm"

# llm type and config are saved in settings table under this category
LLM_CATEGORY = "llm_factory"

# llm selected configuration is saved under this name
LLM_SELECTED_NAME = "llm_selected"


# get configured LLMs and configuration schemas
@router.get("/settings")
def get_llms_settings(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.LLM, AuthPermission.LIST)),
) -> Dict:
    """Get the list of the Large Language Models"""

    chatbot_id = cats.cheshire_cat.id

    llm_schemas = get_llms_schemas(chatbot_id)

    # get selected LLM, if any
    selected = crud.get_setting_by_name(name=LLM_SELECTED_NAME, chatbot_id=chatbot_id)
    if selected is not None:
        selected = selected["value"]["name"]

    saved_settings = crud.get_settings_by_category(category=LLM_CATEGORY, chatbot_id=chatbot_id)
    saved_settings = {s["name"]: s for s in saved_settings}

    settings = []
    for class_name, schema in llm_schemas.items():
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


# get LLM settings and its schema
@router.get("/settings/{languageModelName}")
def get_llm_settings(
    language_model_name: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.LLM, AuthPermission.READ)),
) -> Dict:
    """Get settings and schema of the specified Large Language Model"""

    chatbot_id = cats.cheshire_cat.id

    llm_schemas = get_llms_schemas(chatbot_id)

    # check that language_model_name is a valid name
    allowed_configurations = list(llm_schemas.keys())
    if language_model_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{language_model_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    setting = crud.get_setting_by_name(name=language_model_name, chatbot_id=chatbot_id)
    schema = llm_schemas[language_model_name]

    setting = {} if setting is None else setting["value"]

    return {"name": language_model_name, "value": setting, "schema": schema}


@router.put("/settings/{language_model_name}")
def upsert_llm_setting(
    language_model_name: str,
    payload: Dict = Body({"openai_api_key": "your-key-here"}),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.LLM, AuthPermission.EDIT)),
) -> Dict:
    """Upsert the Large Language Model setting"""

    ccat = cats.cheshire_cat
    chatbot_id = ccat.id

    llm_schemas = get_llms_schemas(chatbot_id)

    # check that language_model_name is a valid name
    allowed_configurations = list(llm_schemas.keys())
    if language_model_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{language_model_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    # create the setting and upsert it
    final_setting = crud.upsert_setting_by_name(
        models.Setting(name=language_model_name, category=LLM_CATEGORY, value=payload),
        chatbot_id=chatbot_id
    )

    crud.upsert_setting_by_name(
        models.Setting(name=LLM_SELECTED_NAME, category=LLM_SELECTED_CATEGORY, value={"name": language_model_name}),
        chatbot_id=chatbot_id
    )

    status = {"name": language_model_name, "value": final_setting["value"]}

    # reload llm and embedder of the cat
    ccat.load_natural_language()
    # crete new collections
    # (in case embedder is not configured, it will be changed automatically and aligned to vendor)
    # TODO: should we take this feature away?
    # Exception handling in case an incorrect key is loaded.
    try:
        ccat.load_memory()
    except Exception as e:
        log.error(e)
        crud.delete_settings_by_category(category=LLM_SELECTED_CATEGORY, chatbot_id=chatbot_id)
        crud.delete_settings_by_category(category=LLM_CATEGORY, chatbot_id=chatbot_id)
        raise HTTPException(
            status_code=400, detail={"error": utils.explicit_error_message(e)}
        )
    # recreate tools embeddings
    ccat.mad_hatter.find_plugins()

    return status
