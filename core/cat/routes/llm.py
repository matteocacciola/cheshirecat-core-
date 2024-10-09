from typing import Dict
from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from fastapi import APIRouter, Body, HTTPException, Depends

from cat.exceptions import LoadMemoryException
from cat.factory.llm import get_llms_schemas
from cat.db import crud

router = APIRouter()


# get configured LLMs and configuration schemas
@router.get("/settings")
def get_llms_settings(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.LLM, AuthPermission.LIST)),
) -> Dict:
    """Get the list of the Large Language Models"""

    chatbot_id = cats.cheshire_cat.id
    llm_schemas = get_llms_schemas(chatbot_id)

    # get selected LLM, if any
    # llm selected configuration is saved under "llm_selected" name
    selected = crud.get_setting_by_name(name="llm_selected", chatbot_id=chatbot_id)
    if selected is not None:
        selected = selected["value"]["name"]

    # llm type and config are saved in settings table under "llm_factory" category
    saved_settings = crud.get_settings_by_category(category="llm_factory", chatbot_id=chatbot_id)
    saved_settings = {s["name"]: s for s in saved_settings}

    settings = [{
        "name": class_name,
        "value": saved_settings[class_name]["value"] if class_name in saved_settings else {},
        "schema": schema,
    } for class_name, schema in llm_schemas.items()]

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
    llm_schemas = get_llms_schemas(ccat.id)

    # check that language_model_name is a valid name
    allowed_configurations = list(llm_schemas.keys())
    if language_model_name not in allowed_configurations:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"{language_model_name} not supported. Must be one of {allowed_configurations}"
            },
        )

    try:
        status = ccat.replace_llm(language_model_name, payload)
    except LoadMemoryException as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})

    return status
