__all__ = ['create_toolset']

from .toolset_gcc import _create_clang_toolset


def create_toolset(sysinfo, loader, **kwargs):
    return _create_clang_toolset(sysinfo, loader, **kwargs)
