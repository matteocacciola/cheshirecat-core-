from typing import Dict, List, Any

from cat.convo.messages import ConversationHistoryItem
from cat.db import crud


def format_key(agent_id: str, user_id: str) -> str:
    return f"{agent_id}:history:{user_id}"


def get_history(agent_id: str, user_id: str) -> List[Dict[str, Any]]:
    history = crud.read(format_key(agent_id, user_id))
    return history if history else []


def set_history(agent_id: str, user_id: str, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    crud.store(format_key(agent_id, user_id), history)
    return history


def update_history(agent_id: str, user_id: str, updated_info: ConversationHistoryItem) -> List[Dict[str, Any]]:
    updated_info = crud.serialize_to_redis_json(updated_info.model_dump())
    history_db = get_history(agent_id, user_id)
    history_db.append(updated_info)

    return set_history(agent_id, user_id, history_db)


def delete_history(agent_id: str, user_id: str) -> None:
    crud.delete(format_key(agent_id, user_id))


def destroy_all(agent_id: str) -> None:
    crud.destroy(format_key(agent_id, "*"))
