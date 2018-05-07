import sys


_PY2 = sys.version_info[0] == 2


def is_string_instance(value):
    if _PY2:
        return isinstance(value, basestring)
    else:
        return isinstance(value, str)


def escape_string(value):
    return value.replace('\\', '\\\\').replace('"', '\\"')


def argv_to_rsp(argv, rsp_file):
    if len(argv) < 2:
        return argv
    arg_rsp = [argv[0], '@{}'.format(rsp_file)]
    with open(rsp_file, mode='wt') as rsp_fh:
        for entry in argv[1:]:
            if '\\' in entry or '"' in entry:
                rsp_fh.writelines(['"', escape_string(entry), '"', '\n'])
            else:
                rsp_fh.writelines([escape_string(entry), '\n'])
    return arg_rsp
