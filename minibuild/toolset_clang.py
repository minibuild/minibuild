__all__ = ['create_toolset', 'describe_toolset']

from .toolset_gcc import _create_clang_toolset, _describe_clang_toolset


def create_toolset(sysinfo, loader, **kwargs):
    return _create_clang_toolset(sysinfo, loader, **kwargs)


def describe_toolset(config_proto, pragma_line, sys_platform, sys_arch, **kwargs):
    return _describe_clang_toolset(config_proto, pragma_line, sys_platform, sys_arch, **kwargs)
