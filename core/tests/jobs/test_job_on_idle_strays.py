import asyncio
import os

from cat.auth.permissions import AuthUserInfo, get_base_permissions
from cat.db.cruds import users as crud_users
from cat.jobs import job_on_idle_strays
from cat.looking_glass.stray_cat import StrayCat

from tests.utils import async_run


def test_job_on_idle_strays(lizard):
    current_straycat_timeout = os.getenv("CCAT_STRAYCAT_TIMEOUT")
    os.environ["CCAT_STRAYCAT_TIMEOUT"] = "0"

    loop = asyncio.get_event_loop()

    ccat = lizard.get_or_create_cheshire_cat("agent_test_1")

    user = AuthUserInfo(id="user_queen", name="Queen", permissions=get_base_permissions())
    stray = StrayCat(user_data=user, agent_id=ccat.id)
    ccat.add_stray(stray)

    # Run the job asynchronously
    job_on_idle_strays()

    assert ccat.get_stray(stray.user.id) is None
    assert ccat.has_strays() is False
    assert crud_users.get_user(lizard.config_key, stray.user.id) is None
    assert lizard.has_cheshire_cats is False

    # clean up
    if current_straycat_timeout:
        os.environ["CCAT_STRAYCAT_TIMEOUT"] = current_straycat_timeout
    else:
        del os.environ["CCAT_STRAYCAT_TIMEOUT"]
