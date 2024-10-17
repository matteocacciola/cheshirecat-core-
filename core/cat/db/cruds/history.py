from typing import Dict, List, Any

from cat.convo.messages import ConversationHistoryInfo
from cat.db import crud


def format_key(agent_id: str, user_id: str) -> str:
    return f"history:{agent_id}:{user_id}"


def get_history(agent_id: str, user_id: str) -> List[Dict[str, Any]]:
    history = crud.read(format_key(agent_id, user_id))
    return history if history else []


def set_history(agent_id: str, user_id: str, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    history = crud.store(format_key(agent_id, user_id), history)
    return history


def update_history(agent_id: str, user_id: str, updated_info: ConversationHistoryInfo) -> List[Dict[str, Any]]:
    updated_info = updated_info.model_dump()

    updated_info["who"] = str(updated_info["who"])
    updated_info["role"] = str(updated_info["role"])

    history_db = get_history(agent_id, user_id)
    history_db.append(updated_info)

    return set_history(agent_id, user_id, history_db)


def delete_history(agent_id: str, user_id: str) -> None:
    crud.delete(format_key(agent_id, user_id))
