"""Earth Engine authentication helpers."""

import ee


def authenticate_ee(project_id: str) -> None:
    """
    Initialize (and authenticate if needed) Google Earth Engine on a project.

    Tries a silent ``ee.Initialize()`` first (works when credentials are
    already cached, e.g. in a previously-authenticated Colab session). If
    that fails, it falls back to the interactive ``ee.Authenticate()`` flow.

    Parameters
    ----------
    project_id : str
        Your registered Earth Engine / Google Cloud project id. The project
        must be registered for Earth Engine access at
        https://code.earthengine.google.com/register

    Returns
    -------
    None
    """
    try:
        ee.Initialize(project=project_id)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project_id)
    print(f"✓ Earth Engine initialized on project: {project_id}")
