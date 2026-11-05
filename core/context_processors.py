from .version import APP_BUILT_AT, APP_COMMIT, APP_VERSION


def app_version(request):
    """The version for the footer; commit and build time are shown in the admin panel only."""
    return {"app_version": APP_VERSION, "app_commit": APP_COMMIT, "app_built_at": APP_BUILT_AT}
