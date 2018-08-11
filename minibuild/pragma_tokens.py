import os.path
import shlex
import sys
import re

from .constants import *
from .error_utils import BuildSystemException
from .makefile_core import exec_compile, format_makefile_exception, parse_traceback_of_makefile


_RE_PRAGMA_BUILD = re.compile(r'^#pragma\s+build\b(.*)$')


def _parse_pragmas(fname):
    tb_parsed, tb_lines = None, None
    with open(fname, mode='rt') as fh:
        try:
            source = fh.read()
            ast = exec_compile(source, fname)
        except SyntaxError:
            etype, value, _ = sys.exc_info()
            tb_parsed, tb_lines = format_makefile_exception(etype, value)
            if not tb_parsed:
                raise
    if tb_parsed:
        tb_lines.insert(0, "Can't load makefile: '{}'".format(fname))
        raise BuildSystemException('\n'.join(tb_lines))
    with open(fname, mode='rt') as fh:
        lines = [ ln.rstrip('\r\n') for ln in fh.readlines() ]
    pragma_lines = []
    idx = 0
    continue_multiline = False
    for ln in lines:
        idx += 1
        ln_stripped = ln.strip()
        if ln_stripped and not ln_stripped.startswith('#'):
            if continue_multiline:
                raise BuildSystemException("Can't load makefile: '{}', got malformed muiltiline instruction #pragma at lines: {}-{}".format(fname, pragma_lines[-1][0], idx))
            break
        if not ln_stripped and continue_multiline:
            raise BuildSystemException("Can't load makefile: '{}', got malformed muiltiline instruction #pragma at lines: {}-{}".format(fname, pragma_lines[-1][0], idx))
        if continue_multiline:
            last = pragma_lines[-1]
            del pragma_lines[-1]
            continue_multiline = ln_stripped.endswith('\\')
            if continue_multiline:
                pragma_lines += [(last[0], last[1] + ln[1:len(ln)-1])]
            else:
                pragma_lines += [(last[0], last[1] + ln[1:])]
        elif ln_stripped.startswith('#pragma'):
            if ln_stripped.endswith('\\'):
                continue_multiline = True
                pragma_lines += [(idx, ln[0:len(ln)-1])]
            else:
                pragma_lines += [(idx, ln)]
    return pragma_lines


def makefile_is_project_landmark(fname):
    pragma_lines = _parse_pragmas(fname)
    pragma_line = 0
    for _, line in pragma_lines:
        pragma_line += 1
        m = _RE_PRAGMA_BUILD.match(line)
        if m:
            details = m.group(1)
            if details:
                return True, details.strip(), pragma_line
            return True, None, pragma_line
    return False, None, -1


def load_buildconf_pragma_lines(fname):
    buildconf_lines = []
    pragma_lines = _parse_pragmas(fname)
    for idx, line in pragma_lines:
        if _RE_PRAGMA_BUILD.match(line):
            continue
        ln = line.replace('#pragma', '').strip()
        buildconf_lines += [(idx, ln)]
    return buildconf_lines


class PragmaToken:
    def __init__(self, pragma_id, lineno, os_name, options):
        self.pragma_id = pragma_id
        self.lineno = lineno
        self.os_name = os_name
        self.options = options


def load_buildconf_pragmas(fname, sys_platform):
    result = []
    pragma_lines = load_buildconf_pragma_lines(fname)
    for idx, ln in pragma_lines:
        pragma_os = None
        shlex_err = None
        try:
            argv = shlex.split(ln)
        except ValueError as ex:
            shlex_err = str(ex)
        if shlex_err is not None:
            raise BuildSystemException("Can't load makefile: '{}', got malformed instruction #pragma at line: {}: {}".format(fname, idx, shlex_err))

        ok = True if argv else False
        for arg in argv:
            if not arg:
                ok = False
                break
            if pragma_os is None:
                if arg.startswith('os:'):
                    pragma_os = arg[3:]
        if not ok:
            raise BuildSystemException("Can't load makefile: '{}', got malformed instruction #pragma at line: {}".format(fname, idx))
        if not pragma_os:
            raise BuildSystemException("Can't load makefile: '{}', got malformed instruction #pragma at line: {}, OS value is unknown.".format(fname, idx))
        if pragma_os == sys_platform or pragma_os == TAG_PRAGMA_OS_VALUE_ALL:
            pragma_args = list(filter(lambda x : not x.startswith('os:'), argv))
            pragma_id = None
            if pragma_args:
                pragma_id = pragma_args[0]
            if not pragma_id:
                raise BuildSystemException("Can't load makefile: '{}', got malformed instruction #pragma at line: {}, no tokens.".format(fname, idx))
            if pragma_id not in TAG_KNOWN_PRAGMA_TOKENS:
                raise BuildSystemException("Can't load makefile: '{}', instruction #pragma at line: {}, got unknown token '{}'.".format(fname, idx, pragma_id))
            pragma_options = {}
            del pragma_args[0]
            for arg in pragma_args:
                if '=' not in arg:
                    raise BuildSystemException("Can't load makefile: '{}', instruction #pragma at line: {}, malformed token: '{}'.".format(fname, idx, arg))
                k, v = arg.split('=', 1)
                if v.startswith('@/'):
                    v = v[1:].lstrip('/').lstrip('\\')
                    v = os.path.normpath(os.path.join(os.path.dirname(fname), v))
                pragma_options[k] = v
            result.append(PragmaToken(pragma_id=pragma_id, lineno=idx, os_name=pragma_os, options=pragma_options))
    return result
