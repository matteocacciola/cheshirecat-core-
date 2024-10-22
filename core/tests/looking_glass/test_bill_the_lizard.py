import pytest

from cat.mad_hatter.mad_hatter import MadHatter
from cat.rabbit_hole import RabbitHole

from tests.utils import get_class_from_decorated_singleton


def test_main_modules_loaded(lizard):
    assert isinstance(lizard.mad_hatter, MadHatter)
    assert isinstance(lizard.rabbit_hole, get_class_from_decorated_singleton(RabbitHole))


@pytest.mark.asyncio  # to test async functions
async def test_shutdown(lizard):
    white_rabbit = lizard.white_rabbit

    await lizard.shutdown()

    assert white_rabbit.get_job(lizard.job_ids[0]) is None
    assert lizard.mad_hatter is None
    assert lizard.rabbit_hole is None
    assert lizard.core_auth_handler is None
    assert lizard.main_agent is None
    assert lizard.embedder is None
    assert lizard.white_rabbit is None
    assert lizard.has_cheshire_cats is False
