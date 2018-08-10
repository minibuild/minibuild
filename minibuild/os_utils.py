import os
import os.path
import shutil
import struct
import sys
import ctypes
import platform


_VOID_PTR_SIZE = struct.calcsize("P")

def mkdir_safe(dname):
    if os.path.exists(dname):
        return
    try:
        os.makedirs(dname)
    except:
        if os.path.exists(dname):
            return
        raise


def cleanup_dir(dir_name):
    if os.path.exists(dir_name):
        fsitems = os.listdir(dir_name)
        for fsitem in fsitems:
            path = os.path.join(dir_name, fsitem)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    else:
        mkdir_safe(dir_name)


def touch_file(fname):
    with open(fname, 'ab'):
        pass


def normalize_path_optional(path, not_abs_dir_prefix):
    if not os.path.isabs(path):
        path = os.path.join(not_abs_dir_prefix, path)
    return os.path.normpath(path)


def load_py_object(fname):
    with open(fname, mode='rt') as file:
        source = file.read()
    ast = compile(source, fname, 'eval')
    return eval(ast, {"__builtins__": None}, {})


def is_windows_64bit():
    if sys.platform == 'win32':
        if _VOID_PTR_SIZE == 8:
            return True
        kernel32 = ctypes.windll.kernel32
        process = kernel32.GetCurrentProcess()
        ret = ctypes.c_int()
        kernel32.IsWow64Process(process, ctypes.byref(ret))
        is64bit = (ret.value != 0)
        return is64bit
    return False


def is_windows_32bit():
    if sys.platform == 'win32':
        if _VOID_PTR_SIZE == 8:
            return False
        kernel32 = ctypes.windll.kernel32
        process = kernel32.GetCurrentProcess()
        ret = ctypes.c_int()
        kernel32.IsWow64Process(process, ctypes.byref(ret))
        is32bit = (ret.value == 0)
        return is32bit
    return False


def is_macosx_x86_64():
    if sys.platform == 'darwin':
        ver, _, arch = platform.mac_ver()
        if ver and arch == 'x86_64':
            return True
    return False


def is_linux_x86_64():
    if sys.platform.startswith('linux'):
        machine = os.uname()[4]
        if machine == 'x86_64':
            return True
    return False


def is_linux_x86():
    if sys.platform.startswith('linux'):
        machine = os.uname()[4]
        if machine == 'i686':
            return True
    return False


def is_linux_arm():
    if sys.platform.startswith('linux'):
        machine = os.uname()[4]
        if machine.startswith('arm'):
            return True
    return False


def is_linux_arm64():
    if sys.platform.startswith('linux'):
        machine = os.uname()[4]
        if machine.startswith('aarch64'):
            return True
    return False
