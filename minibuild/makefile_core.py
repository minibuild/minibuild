import linecache
import sys
import traceback


if sys.version_info.major < 3:
    _CO_FUTURE_DIVISION         = 0x02000  # division
    _CO_FUTURE_ABSOLUTE_IMPORT  = 0x04000  # perform absolute imports by default
    _CO_FUTURE_WITH_STATEMENT   = 0x08000  # with statement
    _CO_FUTURE_PRINT_FUNCTION   = 0x10000  # print function

    _COMPILE_FLAGS = _CO_FUTURE_DIVISION | _CO_FUTURE_ABSOLUTE_IMPORT | _CO_FUTURE_WITH_STATEMENT | _CO_FUTURE_PRINT_FUNCTION
else:
    _COMPILE_FLAGS = 0


def exec_compile(source, fname):
    return compile(source, fname, 'exec', _COMPILE_FLAGS, 1)


def parse_traceback_of_makefile(etype, value, tb, issuer_fname, issuer_output, issuer_traceback):
    lines = []
    parsed = True if tb is None else False
    while tb is not None:
        file_info = None
        line = None
        f = tb.tb_frame
        lineno = tb.tb_lineno
        co = f.f_code
        filename = co.co_filename
        if filename == issuer_fname:
            parsed = True
        if filename == issuer_fname and issuer_output and issuer_traceback:
            file_info = '  File "{}", line {}'.format(issuer_traceback[lineno-1][0], issuer_traceback[lineno-1][1])
            line = issuer_output[lineno-1]
        elif parsed:
            file_info = '  File "{}", line {}, in {}'.format(filename, lineno, co.co_name)
            linecache.checkcache(filename)
            line = linecache.getline(filename, lineno, f.f_globals)
        if file_info:
            lines.append(file_info)
        if line:
            lines.append('    ' + line.strip())
        tb = tb.tb_next
    if parsed:
        lines.insert(0, 'Traceback (most recent call last):')
        exc_lines = traceback.format_exception_only(etype, value)
        for xln in exc_lines:
            exc_line = xln.rstrip('\r\n')
            if exc_line:
                lines.append(exc_line)
    return parsed, lines


def format_makefile_exception(etype, value):
    return parse_traceback_of_makefile(etype, value, None, None, None, None)
