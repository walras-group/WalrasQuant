from importlib.metadata import version, PackageNotFoundError


try:
    __version__ = version("walrasquant")
except PackageNotFoundError:
    __version__ = "unknown"
