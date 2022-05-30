from datetime import datetime
from pathlib import Path
from typing import Optional

from discord import Forbidden, User
from discord.ext import tasks
from discord.utils import format_dt, utcnow

from PyDrocsid.cog import Cog
from PyDrocsid.config import Config
from PyDrocsid.environment import OWNER_ID
from PyDrocsid.translations import t
from PyDrocsid.util import send_editable_log

from ...contributor import Contributor


tg = t.g
t = t.heartbeat


class HeartbeatCog(Cog, name="Heartbeat"):
    CONTRIBUTORS = [Contributor.Defelo, Contributor.wolflu]

    def __init__(self):
        super().__init__()

        self.initialized = False

    def get_owner(self) -> Optional[User]:
        return self.bot.get_user(OWNER_ID)

    @tasks.loop(seconds=20)
    async def status_loop(self):
        if (owner := self.get_owner()) is None:
            return
        try:
            await send_editable_log(
                owner,
                t.online_status,
                t.status_description(Config.NAME, Config.VERSION),
                t.heartbeat,
                format_dt(now := utcnow(), style="D") + " " + format_dt(now, style="T"),
            )
            Path("health").write_text(str(int(datetime.now().timestamp())))
        except Forbidden:
            pass

    async def on_ready(self):
        if (owner := self.get_owner()) is not None:
            try:
                await send_editable_log(
                    owner,
                    t.online_status,
                    t.status_description(Config.NAME, Config.VERSION),
                    t.logged_in,
                    format_dt(now := utcnow(), style="D") + " " + format_dt(now, style="T"),
                    force_resend=True,
                    force_new_embed=not self.initialized,
                )
            except Forbidden:
                pass

        if owner is not None:
            try:
                self.status_loop.start()
            except RuntimeError:
                self.status_loop.restart()

        self.initialized = True
