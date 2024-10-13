from cat.mad_hatter.mad_hatter import MadHatter
from cat.rabbit_hole import RabbitHole

from tests.utils import get_class_from_decorated_singleton


def test_main_modules_loaded(lizard):
    assert isinstance(lizard.mad_hatter, MadHatter)
    assert isinstance(lizard.rabbit_hole, get_class_from_decorated_singleton(RabbitHole))
