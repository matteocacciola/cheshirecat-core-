from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.mad_hatter.mad_hatter import MadHatter
from cat.utils import singleton


@singleton
class MarchHare(MadHatter):
    def __init__(self):
        super().__init__(DEFAULT_SYSTEM_KEY)