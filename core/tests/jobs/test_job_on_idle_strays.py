import asyncio
import os

from cat.auth.permissions import AuthUserInfo, get_base_permissions
from cat.bill_the_lizard import job_on_idle_strays, BillTheLizard
from cat.db.cruds import users as crud_users
from cat.looking_glass.stray_cat import StrayCat

from tests.utils import async_run_job


def test_job_on_idle_strays():
    current_straycat_timeout = os.getenv("CCAT_STRAYCAT_TIMEOUT")
    os.environ["CCAT_STRAYCAT_TIMEOUT"] = "0"

    loop = asyncio.get_event_loop()

    lizard = BillTheLizard()
    cheshire_cat = lizard.get_or_create_cheshire_cat("agent_test_1")

    user = AuthUserInfo(id="user_queen", name="Queen", permissions=get_base_permissions())
    stray = StrayCat(user_data=user, main_loop=loop, agent_id=cheshire_cat.id)

    # Run the job asynchronously
    loop.run_until_complete(async_run_job(job_on_idle_strays, lizard, loop))

    assert cheshire_cat.get_stray(stray.user_id) is None
    assert cheshire_cat.has_strays() is False
    assert crud_users.get_user(lizard.config_key, stray.user_id) is None
    assert lizard.has_cheshire_cats is False

    # clean up
    if current_straycat_timeout:
        os.environ["CCAT_STRAYCAT_TIMEOUT"] = current_straycat_timeout
    else:
        del os.environ["CCAT_STRAYCAT_TIMEOUT"]