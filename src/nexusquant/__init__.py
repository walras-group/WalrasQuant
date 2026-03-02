from importlib.metadata import version, PackageNotFoundError


try:
    __version__ = version("nexusquant")
except PackageNotFoundError:
    __version__ = "unknown"
