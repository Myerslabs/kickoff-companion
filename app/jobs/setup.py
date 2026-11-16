"""The weekly jobs in run order (A, then B and C as they are built), for the server and for the command line without
a server. One place, so both run the same work."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from app.cfbd.client import CfbdClient
from app.config import Settings
from app.jobs import JobRuns
from app.jobs.circle_of_blame import NAME as CIRCLE_OF_BLAME
from app.jobs.circle_of_blame import BlameJob
from app.jobs.imperialism import NAME as IMPERIALISM
from app.jobs.imperialism import ImperialismJob
from app.jobs.talent_edge import NAME as TALENT_EDGE
from app.jobs.talent_edge import TalentEdgeJob
from app.jobs.weekly import WeeklyJobs
from app.services import plan


def build_jobs(client: CfbdClient, settings: Settings) -> dict[str, Callable[..., Awaitable[dict[str, Any]]]]:
    return {  # the spec's order: Talent Edge, then the map (its hover card reads Talent Edge's line), then the Circle of Blame (it reads both)
        TALENT_EDGE: TalentEdgeJob(client, settings.data_dir, settings.season).run,
        IMPERIALISM: ImperialismJob(client, settings.data_dir, settings.season).run,
        CIRCLE_OF_BLAME: BlameJob(client, settings).run,
    }


def build_weekly(client: CfbdClient, settings: Settings) -> WeeklyJobs:
    # Kickoff Companion 2.0: on a Free key Talent Edge (about 20 calls: every roster, seven recruiting classes, the portal)
    # is rebuilt every four weeks, not every week, so the month's 1,000 calls last
    return WeeklyJobs(JobRuns(settings.data_dir), settings.season, build_jobs(client, settings), lean=lambda: plan.lean(client), lean_every={TALENT_EDGE: timedelta(days=28)})
