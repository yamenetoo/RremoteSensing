"""Earth Engine authentication / initialisation."""
from __future__ import annotations

import os

from .utils import logger

_INITIALISED = False


def init_ee(project: str | None = None, authenticate: bool = True, force: bool = False, **kwargs) -> None:
    """Initialise Earth Engine, authenticating interactively if needed.

    `project` falls back to the EE_PROJECT / GOOGLE_CLOUD_PROJECT environment variables.
    If EE_SERVICE_ACCOUNT and EE_PRIVATE_KEY_FILE are set, a service account is used (no browser login).
    """
    global _INITIALISED
    if _INITIALISED and not force:
        return
    import ee

    project = project or os.environ.get("EE_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    account, key_file = os.environ.get("EE_SERVICE_ACCOUNT"), os.environ.get("EE_PRIVATE_KEY_FILE")
    if account and key_file:        # headless servers (e.g. the REST API): service-account login
        ee.Initialize(ee.ServiceAccountCredentials(account, key_file), project=project, **kwargs)
        _INITIALISED = True
        logger.info("Earth Engine initialised with service account %s (project=%s)", account, project)
        return
    try:
        ee.Initialize(project=project, **kwargs)
    except Exception:
        if not authenticate:
            raise
        logger.info("Earth Engine needs authentication ...")
        ee.Authenticate()
        ee.Initialize(project=project, **kwargs)
    _INITIALISED = True
    logger.info("Earth Engine initialised (project=%s)", project)
