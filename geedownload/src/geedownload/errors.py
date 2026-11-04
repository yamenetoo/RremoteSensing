"""Exceptions raised by geedownload."""


class GeeDownloadError(Exception):
    """Base class for every error raised by this package."""


class AreaNotFound(GeeDownloadError):
    """The place name returned no result from the geocoder."""


class NoImagesError(GeeDownloadError):
    """No image matches the dataset / date / cloud filters for the area."""


class DownloadError(GeeDownloadError):
    """A download request to Earth Engine failed."""
