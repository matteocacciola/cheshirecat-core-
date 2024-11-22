import pytest

from cat.agents.main_agent import MainAgent
from cat.factory.custom_auth_handler import CoreAuthHandler
from cat.factory.custom_file_manager import BaseFileManager
from cat.looking_glass.white_rabbit import WhiteRabbit
from cat.mad_hatter.tweedledum import Tweedledum
from cat.rabbit_hole import RabbitHole

from tests.utils import get_class_from_decorated_singleton


def test_main_modules_loaded(lizard):
    assert isinstance(lizard.plugin_manager, get_class_from_decorated_singleton(Tweedledum))
    assert isinstance(lizard.rabbit_hole, get_class_from_decorated_singleton(RabbitHole))
    assert isinstance(lizard.core_auth_handler, CoreAuthHandler)
    assert isinstance(lizard.file_manager, BaseFileManager)
    assert isinstance(lizard.main_agent, MainAgent)
    assert isinstance(lizard.white_rabbit, get_class_from_decorated_singleton(WhiteRabbit))


@pytest.mark.asyncio  # to test async functions
async def test_shutdown(lizard):
    white_rabbit = lizard.white_rabbit

    await lizard.shutdown()

    assert lizard.plugin_manager is None
    assert lizard.rabbit_hole is None
    assert lizard.core_auth_handler is None
    assert lizard.file_manager is None
    assert lizard.main_agent is None
    assert lizard.embedder is None
    assert lizard.white_rabbit is None
    assert lizard.has_cheshire_cats is False
    assert white_rabbit.get_job(lizard.job_ids[0]) is None
