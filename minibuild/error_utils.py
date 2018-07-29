import inspect
import linecache
import os.path
import traceback


class BuildSystemException(Exception):
    def __init__(self, text, exit_code=None, frame=1):
        if exit_code is None:
            frame_info = inspect.stack()[frame]
            msg = '[{}({})] {}'.format(os.path.basename(frame_info[1]), frame_info[2], text)
        else:
            msg = text
        Exception.__init__(self, msg)
        self.exit_code = 126
        if exit_code is not None:
            self.exit_code = exit_code

    def to_exit_code(self):
        return self.exit_code


class BuildSystemPureVirtualCall(BuildSystemException):
    def __init__(self, class_instance):
        frame_info = inspect.stack()[1]
        BuildSystemException.__init__(self, "Pure virtual call - {}::{}".format(type(class_instance).__name__, frame_info[3]), frame=3)


class BuildSystemSysExit(BuildSystemException):
    def __init__(self, exit_code):
        BuildSystemException.__init__(self, None, exit_code)


def buildsys_error_to_string(err):
    return 'BUILDSYS: ERROR: ' + str(err)


def traceback_to_string(etype, value, tb):
    lines = []
    while tb is not None:
        file_info = None
        line = None
        f = tb.tb_frame
        lineno = tb.tb_lineno
        co = f.f_code
        filename = co.co_filename
        file_info = '  File "{}", line {}, in {}'.format(filename, lineno, co.co_name)
        linecache.checkcache(filename)
        line = linecache.getline(filename, lineno, f.f_globals)
        lines.append(file_info)
        lines.append('    ' + line.strip())
        tb = tb.tb_next
    lines.insert(0, 'Traceback (most recent call last):')
    exc_lines = traceback.format_exception_only(etype, value)
    for xln in exc_lines:
        exc_line = xln.rstrip('\r\n')
        if exc_line:
            lines.append(exc_line)
    return '\n'.join(lines)
