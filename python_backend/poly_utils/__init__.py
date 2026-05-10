"""Utility helpers shared across update scripts."""

try:
    from . import api_client
except ImportError:
    import api_client

# Lazy import of utils to avoid importing polars for api_client-only uses
def __getattr__(name):
    if name == 'utils':
        try:
            from . import utils
        except ImportError:
            import utils
        return utils
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
