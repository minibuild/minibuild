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
    escaped = []
    for entry in argv[1:]:
        if '\\' in entry or '"' in entry:
            escaped.append('"' + escape_string(entry) + '"')
        else:
            escaped.append(entry)
    line = ' '.join(escaped)
    with open(rsp_file, mode='wt') as rsp_fh:
        rsp_fh.writelines([line])
    return arg_rsp
