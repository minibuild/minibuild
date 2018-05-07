from __future__ import print_function

__all__ = ['create_toolset']

import os
import os.path
import shutil
import subprocess
import sys

if sys.version_info.major < 3:
    import _winreg as winreg
else:
    import winreg

from .build_art import BuildArtifact
from .constants import *
from .depends_check import *
from .error_utils import BuildSystemException
from .nasm_action import NasmSourceBuildAction
from .os_utils import *
from .string_utils import escape_string, argv_to_rsp
from .toolset_base import ToolsetBase, ToolsetModel


MSVS_VERSIONS_MAPPING = {
    '2005' : 'VS80COMNTOOLS',
    '2008' : 'VS90COMNTOOLS',
    '2013' : 'VS120COMNTOOLS',
    '2015' : 'VS140COMNTOOLS',
}

WINDOWS_SDKS_REG_LANDMARK = 'SOFTWARE\\Microsoft\\Microsoft SDKs\\Windows'

MSVS_COMPILER_EXECUTABLE = 'cl.exe'
MSVS_LINKER_EXECUTABLE = 'link.exe'
MSVS_LIB_EXECUTABLE = 'lib.exe'
MSVS_MANIFEST_TOOL = 'mt.exe'
MSVS_ASM_TOOL = 'ml.exe'
MSVS_ASM64_TOOL = 'ml64.exe'

MSVS_MODEL_FORMAT_WIN32 = 'msvs{}-win32'
MSVS_MODEL_FORMAT_WIN64 = 'msvs{}-win64'

MSVS_DEP_MARK = 'Note: including file:'
MSVS_DEP_MARK_LEN = len(MSVS_DEP_MARK)

ENV_DUMP_BATCH = '''@echo off
call "{0}" 1>nul 2>nul
if errorlevel 0 set
'''

TAG_MSVS_CL   = 'cl'
TAG_MSVS_MT   = 'mt'
TAG_MSVS_LIB  = 'lib'
TAG_MSVS_LINK = 'link'
TAG_MSVS_ASM  = 'ml'


def query_windows_sdk_path():
    sdk_versions = {}
    sdk_root = None
    try:
        sdk_root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, WINDOWS_SDKS_REG_LANDMARK, 0, winreg.KEY_READ|winreg.KEY_WOW64_64KEY)
    except OSError:
        pass
    if sdk_root is not None:
        index = 0
        while True:
            try:
                name = winreg.EnumKey(sdk_root, index)
                sdk_versions[name] = {}
                index += 1
            except OSError:
                break
        for name in sdk_versions.keys():
            regkey_name = '\\'.join([WINDOWS_SDKS_REG_LANDMARK, name])
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, regkey_name, 0, winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as sdk_key:
                index = 0
                while True:
                    try:
                        value_name, value_data, value_type = winreg.EnumValue(sdk_key, index)
                        if value_type == winreg.REG_SZ:
                            sdk_versions[name][value_name] = value_data
                        index += 1
                    except OSError:
                        break
    checked_sdk_version = None
    checked_sdk_path = None
    for name in sdk_versions.keys():
        is_sdk = False
        parsed_version = None
        vbits = []
        version_text = name.lower()
        if version_text.startswith('v'):
            version_text = version_text[1:]
            vbits = version_text.split('.')
        if len(vbits) == 2 and vbits[0].isdigit() and len(vbits[1]) > 0:
            vprobe = ''
            for c in vbits[1]:
                vprobe1 = vprobe + c
                if vprobe1.isdigit():
                    vprobe = vprobe1
                else:
                    break
            if vprobe.isdigit():
                vpart3 = vbits[1][len(vprobe):]
                parsed_version = [int(vbits[0]), int(vprobe), vpart3]
        if parsed_version is not None and 'InstallationFolder' in sdk_versions[name]:
            sdk_path = sdk_versions[name]['InstallationFolder']
            bin_dir = os.path.join(sdk_path, 'Bin')
            lib_dir = os.path.join(sdk_path, 'Lib')
            inc_dir = os.path.join(sdk_path, 'Include')
            if os.path.isdir(bin_dir) and os.path.isdir(lib_dir) and os.path.isdir(bin_dir):
                is_sdk = True
        if is_sdk:
            sdk_path = sdk_versions[name]['InstallationFolder']
            if checked_sdk_version is None:
                checked_sdk_version = parsed_version
                checked_sdk_path = sdk_versions[name]['InstallationFolder']
            elif checked_sdk_version < parsed_version:
                checked_sdk_version = parsed_version
                checked_sdk_path = sdk_versions[name]['InstallationFolder']


    if checked_sdk_path is not None:
        checked_sdk_path = os.path.normpath(checked_sdk_path)
    return checked_sdk_path


def map_msvs_tools_info(sdk_home, cl_path32, cl_path64, is_on_win64, msvs_version):
    bin32_home = os.path.dirname(cl_path32)
    bin64_home = os.path.dirname(cl_path64)
    tools32 = {TAG_MSVS_CL: cl_path32}
    tools64 = {TAG_MSVS_CL: cl_path64}
    sdk_path32 = None
    sdk_path64 = None
    if sdk_home is not None:
        sdk_path32 = os.path.normpath(os.path.join(sdk_home, "Bin"))
        sdk_path64 = os.path.normpath(os.path.join(sdk_home, "Bin/x64"))

    for tag, tool32, tool64, try_native, try_sdk in [
            (TAG_MSVS_LIB, MSVS_LIB_EXECUTABLE, MSVS_LIB_EXECUTABLE, False, False),
            (TAG_MSVS_LINK, MSVS_LINKER_EXECUTABLE, MSVS_LINKER_EXECUTABLE, False, False),
            (TAG_MSVS_ASM, MSVS_ASM_TOOL, MSVS_ASM64_TOOL, False, False),
            (TAG_MSVS_MT, MSVS_MANIFEST_TOOL, MSVS_MANIFEST_TOOL, True, True),
        ]:
        tool_path32 = os.path.join(bin32_home, tool32)
        tool_path64 = os.path.join(bin64_home, tool64)
        if try_native:
            if is_on_win64:
                if not os.path.isfile(tool_path32) and os.path.isfile(tool_path64):
                    tool_path32 = tool_path64
                if not os.path.isfile(tool_path64) and os.path.isfile(tool_path32):
                    tool_path64 = tool_path32
            else:
                if not os.path.isfile(tool_path64) and os.path.isfile(tool_path32):
                    tool_path64 = tool_path32

        if try_sdk:
            if not os.path.isfile(tool_path32):
                if is_on_win64:
                    if sdk_path64 is not None:
                        tool_path32 = os.path.join(sdk_path64, tool32)
                else:
                    if sdk_path32 is not None:
                        tool_path32 = os.path.join(sdk_path32, tool32)

            if not os.path.isfile(tool_path64):
                if is_on_win64:
                    if sdk_path64 is not None:
                        tool_path64 = os.path.join(sdk_path64, tool64)
                else:
                    if sdk_path32 is not None:
                        tool_path64 = os.path.join(sdk_path32, tool64)

        if not os.path.isfile(tool_path32):
            raise BuildSystemException("Cannot bootstrap MSVS({}): file '{}' not found.".format(msvs_version, tool_path32))

        if not os.path.isfile(tool_path64):
            raise BuildSystemException("Cannot bootstrap MSVS({}): file '{}' not found.".format(msvs_version, tool_path64))

        tools32[tag] = tool_path32
        tools64[tag] = tool_path64
    return tools32, tools64


def split_path(value):
    paths = []
    for path in value.split(';'):
        if path:
            paths.append(path)
    return paths


def split_if_path(value):
    if ';' not in value:
        return value
    return split_path(value)


def get_path_difference(original, final):
    orig_paths = split_path(original)
    final_paths = split_path(final)
    new_paths = []
    for path in final_paths:
        if path not in orig_paths:
            new_paths.append(path)
    return new_paths


def resolve_compiler_path(msvs_new_paths):
    for msvs_path in msvs_new_paths:
        cl_path_variant = os.path.normpath(os.path.join(msvs_path, MSVS_COMPILER_EXECUTABLE))
        if os.path.isfile(cl_path_variant):
            return cl_path_variant
    return None


def get_cl_and_envmap_from_dump(msvs_version, env_dump):
    env_map = {}
    cl_path = None
    for env_entry in env_dump.splitlines():
        var_name, var_value = env_entry.split('=', 1)
        is_path = var_name.upper() == 'PATH'
        if not is_path and var_name in os.environ:
            continue
        if is_path:
            paths_to_add = get_path_difference(os.environ[var_name], var_value)
            cl_path = resolve_compiler_path(paths_to_add)
            env_map[var_name] = paths_to_add
        else:
            env_map[var_name] = split_if_path(var_value)
    if cl_path is None:
        raise BuildSystemException("Cannot bootstrap MSVS({}): file '{}' not found.".format(msvs_version, MSVS_COMPILER_EXECUTABLE))
    return (cl_path, env_map)


def init_msvs_toolset(msvs_version, bootstrap_dir):
    is_on_win64 = is_windows_64bit()
    cache_dir = os.path.join(bootstrap_dir, 'msvs-{}'.format(msvs_version))
    stamp_file = os.path.join(cache_dir, 'init.stamp')
    stamp_file_sdk = os.path.join(cache_dir, 'init_sdk.stamp')
    sdk_path_file = os.path.join(cache_dir, 'sdk_path.py')
    cl_path_file32 = os.path.join(cache_dir, 'cl_path32.py')
    env_patch_file32 = os.path.join(cache_dir, 'env_patch32.py')
    cl_path_file64 = os.path.join(cache_dir, 'cl_path64.py')
    env_patch_file64 = os.path.join(cache_dir, 'env_patch64.py')

    sdk_path = None
    if not os.path.exists(stamp_file_sdk):
        sdk_path = query_windows_sdk_path()
        if sdk_path is not None:
            mkdir_safe(cache_dir)
            with open(sdk_path_file, mode='wt') as sdk_file:
                sdk_file.writelines(['"', escape_string(sdk_path), '"'])
            with open(stamp_file_sdk, mode='w') as _:
                pass
    else:
        if os.path.exists(sdk_path_file):
            sdk_path = load_py_object(sdk_path_file)

    if os.path.exists(stamp_file):
        cl_path32 = load_py_object(cl_path_file32)
        env_patch32 = load_py_object(env_patch_file32)
        cl_path64 = load_py_object(cl_path_file64)
        env_patch64 = load_py_object(env_patch_file64)
        tools32, tools64 = map_msvs_tools_info(sdk_path, cl_path32, cl_path64, is_on_win64, msvs_version)
        return tools32, env_patch32, tools64, env_patch64

    msvs_landmark = MSVS_VERSIONS_MAPPING.get(msvs_version)
    if msvs_landmark is None:
        raise BuildSystemException("Unknown MSVS version: '{}'.".format(msvs_version))
    msvs_vars_dir = os.environ.get(msvs_landmark)
    if msvs_vars_dir is None:
        raise BuildSystemException("Cannot bootstrap MSVS({}): variable '{}' not found in environment.".format(msvs_version, msvs_landmark))
    msvs_vars_batch32 = os.path.join(msvs_vars_dir, 'vsvars32.bat')
    if not os.path.exists(msvs_vars_batch32):
        raise BuildSystemException("Cannot bootstrap MSVS({}): file '{}' not found.".format(msvs_version, msvs_vars_batch32))
    mkdir_safe(cache_dir)
    msvs_vars_wrapper32 = os.path.join(cache_dir, 'vars_dump32.bat')
    with open(msvs_vars_wrapper32, mode='wt') as wrapper_file32:
        wrapper_file32.write(ENV_DUMP_BATCH.format(msvs_vars_batch32))
    env_dump32 = subprocess.check_output(msvs_vars_wrapper32, shell=True, universal_newlines=True)
    cl_path32, env_map32 = get_cl_and_envmap_from_dump(msvs_version, env_dump32)

    cl_home = os.path.dirname(cl_path32)
    if is_on_win64:
        msvs_vars_batch64_variants = [ os.path.join(cl_home, 'amd64', 'vcvarsamd64.bat'), os.path.join(cl_home, 'amd64', 'vcvars64.bat') ]
    else:
        msvs_vars_batch64_variants = [ os.path.join(cl_home, 'x86_amd64', 'vcvarsx86_amd64.bat') ]

    msvs_vars_batch64 = None
    for batch64 in msvs_vars_batch64_variants:
        if os.path.isfile(batch64):
            msvs_vars_batch64 = batch64
            break

    if msvs_vars_batch64 is None:
        if len(msvs_vars_batch64_variants) == 1:
            raise BuildSystemException("Cannot bootstrap MSVS({}): file '{}' not found.".format(msvs_version, msvs_vars_batch64_variants[0]))
        else:
            raise BuildSystemException("Cannot bootstrap MSVS({}): files not found:\n    {}".format(msvs_version, '\n    '.join(msvs_vars_batch64_variants)))

    msvs_vars_wrapper64 = os.path.join(cache_dir, 'vars_dump64.bat')
    with open(msvs_vars_wrapper64, mode='wt') as wrapper_file64:
        wrapper_file64.write(ENV_DUMP_BATCH.format(msvs_vars_batch64))
    env_dump64 = subprocess.check_output(msvs_vars_wrapper64, shell=True, universal_newlines=True)
    cl_path64, env_map64 = get_cl_and_envmap_from_dump(msvs_version, env_dump64)

    for cl_path, env_map, cl_path_file, env_patch_file in [
                    (cl_path32, env_map32, cl_path_file32, env_patch_file32),
                    (cl_path64, env_map64, cl_path_file64, env_patch_file64) ]:
        with open(cl_path_file, mode='wt') as cl_file:
            cl_file.writelines(['"', escape_string(cl_path), '"'])
        align = 4 * ' '
        with open(env_patch_file, mode='wt') as env_file:
            env_file.writelines(['{\n'])
            for var_name in sorted(env_map.keys()):
                env_file.writelines([align, '"', var_name, '"', ': '])
                var_value = env_map[var_name]
                if isinstance(var_value, list):
                    env_file.writelines(['['])
                    for pth in var_value:
                        env_file.writelines(['\n', 2 * align, '"', escape_string(pth), '",'])
                    env_file.writelines(['\n', align, '],', '\n'])
                else:
                    env_file.writelines(['"', escape_string(var_value), '"', ',\n'])
            env_file.writelines(['}\n'])

    with open(stamp_file, mode='w') as _:
        pass
    cl_path32 = load_py_object(cl_path_file32)
    env_patch32 = load_py_object(env_patch_file32)
    cl_path64 = load_py_object(cl_path_file64)
    env_patch64 = load_py_object(env_patch_file64)
    tools32, tools64 = map_msvs_tools_info(sdk_path, cl_path32, cl_path64, is_on_win64, msvs_version)
    return tools32, env_patch32, tools64, env_patch64


def merge_env_value(patch, original=None):
    if not isinstance(patch, list):
        return patch
    path_ext = os.pathsep.join(patch)
    if original is None:
        return path_ext
    return os.pathsep.join([path_ext, original])


def apply_environ_patch(env_patch=None):
    if env_patch is None:
        return None
    custom_env = {}
    custom_env.update(os.environ)
    env_upkeys = { x.upper(): x for x in custom_env.keys() }
    for var_name, var_value_patch in env_patch.items():
        var_name_upper = var_name.upper()
        original_value = None
        patched_var_name = var_name
        if var_name_upper in env_upkeys:
            patched_var_name = env_upkeys[var_name_upper]
            original_value = custom_env.get(patched_var_name)
        patched_value = merge_env_value(var_value_patch, original_value)
        custom_env[patched_var_name] = patched_value
    return custom_env


class MasmSourceBuildAction:
    def __init__(self, ml_path, env, sysinfo, description, asm_file_path, obj_directory, obj_name, build_model, build_config):
        self.ml = ml_path
        self.env = env
        self.asm_path = asm_file_path
        self.obj_path = os.path.join(obj_directory, ''.join([obj_name, sysinfo[TAG_CFG_OBJ_SUFFIX]]))
        self.include_dirs = eval_include_dirs_in_description(description, sysinfo[TAG_CFG_DIR_PROJECT_ROOT], BUILD_TYPE_ASM)
        self.definitions = eval_definitions_list_in_description(description, build_model, BUILD_TYPE_ASM)
        self.extra_deps = []
        self.extra_deps.extend(description.self_file_parts)

    def __call__(self, force, verbose):
        target_is_ready = False
        if not force:
            target_is_ready, _ = is_target_up_to_date(self.obj_path, [self.asm_path], self.extra_deps, verbose)
        if target_is_ready:
            if verbose:
                print("BUILDSYS: up-to-date: {}".format(self.asm_path))
            return False

        if verbose:
            print("BUILDSYS: ASM: {}".format(self.asm_path))

        argv = [self.ml, '/c', '/nologo']

        for incd in self.include_dirs:
            argv += [ '/I{}'.format(incd) ]

        for _def in self.definitions:
            argv += [ '/D{}'.format(_def) ]

        argv += [ '/Fo{}'.format(self.obj_path), self.asm_path]

        if verbose:
            print("BUILDSYS: EXEC: {}".format(' '.join(argv)))
        p = subprocess.Popen(argv, env=self.env)
        p.communicate()
        if p.returncode != 0:
            raise BuildSystemException(self.asm_path, exit_code=p.returncode)
        return True


class SourceBuildActionMSVS:
    def __init__(self, cl_path, env, sysinfo, description, source_path, source_type, obj_directory, obj_name, build_model, build_config):
        self.cl = cl_path
        self.env = env
        self.source_path = source_path
        self.source_type = source_type
        self.pdb_path = os.path.join(obj_directory, ''.join([obj_name, sysinfo[TAG_CFG_PDB_SUFFIX]]))
        self.obj_path = os.path.join(obj_directory, ''.join([obj_name, sysinfo[TAG_CFG_OBJ_SUFFIX]]))
        self.dep_path = os.path.join(obj_directory, ''.join([obj_name, sysinfo[TAG_CFG_DEP_SUFFIX]]))
        self.project_root = sysinfo[TAG_CFG_DIR_PROJECT_ROOT]
        self.common_prefix = sysinfo[TAG_CFG_PROJECT_ROOT_COMMON_PREFIX]
        self.build_config = build_config
        self.include_dirs = eval_include_dirs_in_description(description, self.project_root, source_type)
        self.definitions  = build_model.get_arch_defines()
        self.definitions += eval_definitions_list_in_description(description, build_model, source_type)
        self.disabled_warnings = []
        if description.disabled_warnings:
            self.disabled_warnings = description.disabled_warnings
        self.extra_deps = []
        self.extra_deps.extend(description.self_file_parts)

    def __call__(self, force, verbose):
        target_is_ready = False
        if not force:
            target_is_ready = is_target_with_deps_up_to_date(self.project_root, self.source_path, self.obj_path, self.dep_path, self.extra_deps, verbose)
        if target_is_ready:
            if verbose:
                print("BUILDSYS: up-to-date: {}".format(self.source_path))
            return False

        if verbose:
            if self.source_type == BUILD_TYPE_CPP:
                print("BUILDSYS: CXX: {}".format(self.source_path))
            else:
                print("BUILDSYS: C: {}".format(self.source_path))

        argv = [self.cl, '/c', '/nologo', '/showIncludes']
        if self.source_type == BUILD_TYPE_CPP:
            argv += ['/TP', '/EHsc', '/GR', '/Zc:forScope', '/Zc:wchar_t']
        elif self.source_type == BUILD_TYPE_C:
            argv += ['/TC']
        else:
            raise BuildSystemException("Unsupported build type is given for file: '{}'".format(self.source_path))

        # W3 - production quality warnings
        # treat as error: C4013: undefined; assuming extern returning int
        argv += ['/W3', '/we4013']

        for wd in self.disabled_warnings:
            argv += [ '/wd{}'.format(wd) ]

        if self.build_config == BUILD_CONFIG_RELEASE:
            argv += ['/O2', '/Ob1', '/Zi', '/MD']
        elif self.build_config == BUILD_CONFIG_DEBUG:
            argv += ['/Od', '/Ob0', '/Zi', '/MDd']
        else:
            raise BuildSystemException("Unsupported build config: '{}'".format(self.build_config))

        for incd in self.include_dirs:
            argv += [ '/I{}'.format(incd) ]

        for _def in self.definitions:
            argv += [ '/D{}'.format(_def) ]

        if self.build_config != BUILD_CONFIG_DEBUG:
            argv += ['/DNDEBUG']

        argv += [ '/Fo{}'.format(self.obj_path), '/Fd{}'.format(self.pdb_path), self.source_path ]

        if verbose:
            print("BUILDSYS: EXEC: {}".format(' '.join(argv)))
        p = subprocess.Popen(argv, env=self.env, stdout=subprocess.PIPE, universal_newlines=True)

        stdout_data, _ = p.communicate()
        depends = self._parse_stdout(stdout_data, p.returncode)
        if p.returncode != 0:
            raise BuildSystemException(self.source_path, exit_code=p.returncode)
        with open(self.dep_path, mode='wt') as dep_content:
            dep_content.writelines(['[\n'])
            for dep_item in depends:
                dep_content.writelines(['    "', escape_string(dep_item), '",\n'])
            dep_content.writelines([']\n'])
        return True

    def _parse_stdout(self, stdout_data, return_code):
        depends = []
        common_prefix_len = len(self.common_prefix)
        for line in stdout_data.splitlines():
            if not line.startswith(MSVS_DEP_MARK):
                print(line)
                continue
            if return_code != 0:
                continue
            dep_source = line[MSVS_DEP_MARK_LEN:].lstrip()
            dep_item = os.path.normcase(dep_source)
            if not dep_item.startswith(self.common_prefix):
                continue
            dep_item = dep_source[common_prefix_len:]
            depends.append(dep_item)
        return depends


class StaticLibLinkActionMSVS:
    def __init__(self, lib_tool, env, sysinfo, description, lib_directory, obj_directory, obj_names, build_model, build_config):
        self.lib_tool = lib_tool
        self.env = env
        self.outlib_path = os.path.join(lib_directory, ''.join([description.module_name, '.lib']))
        self.module_name = description.module_name
        self.rsp_file = os.path.join(obj_directory, '{}.rsplnk'.format(self.module_name))
        self.obj_list = []
        self.primary_deps = []

        for obj_name in obj_names:
            obj_path = os.path.join(obj_directory, ''.join([obj_name, sysinfo[TAG_CFG_OBJ_SUFFIX]]))
            self.obj_list.append(obj_path)
            self.primary_deps.append(obj_path)

        self.extra_deps = []
        self.extra_deps.extend(description.self_file_parts)

    def __call__(self, force, verbose):
        build_result = [BuildArtifact(BUILD_RET_TYPE_LIB, self.outlib_path, BUILD_RET_ATTR_DEFAULT)]
        target_is_ready = False
        if not force:
            target_is_ready, _ = is_target_up_to_date(self.outlib_path, self.primary_deps, self.extra_deps, verbose)
        if target_is_ready:
            print("BUILDSYS: up-to-date: '{}', LIB: {}".format(self.module_name, self.outlib_path))
            return (False, build_result)

        argv = [self.lib_tool, '/nologo', '/out:{}'.format(self.outlib_path)] + self.obj_list
 
        print("BUILDSYS: Create LIB module '{}' ...".format(self.module_name))
        argv = argv_to_rsp(argv, self.rsp_file)
        if verbose:
            print("BUILDSYS: EXEC: {}".format(' '.join(argv)))
        p = subprocess.Popen(argv, env=self.env)
        p.communicate()
        if p.returncode != 0:
            raise BuildSystemException(self.outlib_path, exit_code=p.returncode)
        return (True, build_result)


class LinkActionMSVS:
    def __init__(self, link_tool, mt_tool, env, sysinfo, loader, description, exe_directory, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config):
        self.linker = link_tool
        self.mt_tool = mt_tool
        self.env = env
        self.sharedlib_directory = sharedlib_directory
        self.is_dll = True if exe_directory is None else False
        self.link_public_dir = sharedlib_directory if self.is_dll else exe_directory
        self.link_private_dir = os.path.join(obj_directory, 'raw')
        self.link_stamp_file = os.path.join(self.link_private_dir, 'link.stamp')
        self.lib_directory = lib_directory
        self.primary_deps = [ self.link_stamp_file ]
        self.extra_deps = []
        self.extra_deps.extend(description.self_file_parts)
        self.use_wmain = description.wmain
        self.win_console = description.win_console
        self.win_stack_size = description.win_stack_size
        self.zip_section = None

        if description.zip_section is not None:
            zip_section_file = normalize_path_optional(description.zip_section, description.self_dirname)
            self.zip_section = zip_section_file
            self.primary_deps.append(zip_section_file)

        if self.is_dll:
            self.bin_basename = ''.join([description.module_name, '.dll'])
            self.implib_basename = ''.join([description.module_name, '.lib'])
            self.pdb_basename = ''.join([description.module_name, '.pdb'])
        else:
            exe_name = description.module_name
            if description.exe_name:
                exe_name = description.exe_name
            self.bin_basename = ''.join([exe_name, '.exe'])
            self.pdb_basename = ''.join([exe_name, '.pdb'])

        self.bin_path_public = os.path.join(self.link_public_dir, self.bin_basename)
        self.bin_path_private = os.path.join(self.link_private_dir, self.bin_basename)
        self.pdb_path_public = os.path.join(self.link_public_dir, self.pdb_basename)
        self.pdb_path_private = os.path.join(self.link_private_dir, self.pdb_basename)

        if self.is_dll:
            self.implib_path_public = os.path.join(self.link_public_dir, self.implib_basename)
            self.implib_path_private = os.path.join(self.link_private_dir, self.implib_basename)
            self.exports_def_file = verify_exports_def_file(description)
            if self.exports_def_file is not None:
                self.extra_deps.append(self.exports_def_file)
            self.export_list = description.export

        self.manifest_stub = os.path.join(self.link_private_dir, ''.join([description.module_name, '.manifest-stub']))
        self.manifest_builtin = os.path.join(self.link_private_dir, ''.join([description.module_name, '.manifest']))
        self.module_name = description.module_name
        self.rsp_file = os.path.join(self.link_private_dir, '{}.rsplnk'.format(self.module_name))
        self.obj_list = []
        self.build_config = build_config
        for obj_name in obj_names:
            obj_path = os.path.join(obj_directory, ''.join([obj_name, sysinfo[TAG_CFG_OBJ_SUFFIX]]))
            self.obj_list.append(obj_path)
            self.primary_deps.append(obj_path)
        self.link_libstatic_names = []
        self.link_libshared_names = []
        eval_libnames_in_description(loader, description, self.link_libstatic_names, self.link_libshared_names)
        self.prebuilt_lib_names = eval_prebuilt_lib_list_in_description(description, build_model)
        self.linker_options = build_model.get_linker_options()

    def __call__(self, force, verbose):
        mod_type_id = BUILD_RET_TYPE_DLL if self.is_dll else BUILD_RET_TYPE_EXE
        build_result = [BuildArtifact(mod_type_id, self.bin_path_public, BUILD_RET_ATTR_DEFAULT), BuildArtifact(BUILD_RET_TYPE_PDB, self.pdb_path_public, BUILD_RET_ATTR_DEFAULT)]
        if self.is_dll:
            build_result += [BuildArtifact(BUILD_RET_TYPE_LIB, self.implib_path_public, BUILD_RET_ATTR_DEFAULT)]
        target_is_ready = False
        if not force:
            target_is_ready, _ = is_target_up_to_date(self.bin_path_public, self.primary_deps, self.extra_deps, verbose)
        mod_type = 'DLL' if self.is_dll else 'EXE'
        if target_is_ready:
            print("BUILDSYS: up-to-date: '{}', {}: {}".format(self.module_name, mod_type, self.bin_path_public))
            return (False, build_result)

        print("BUILDSYS: Link {} module '{}' ...".format(mod_type, self.module_name))
        for built_item_info in build_result:
            if os.path.exists(built_item_info.path):
                if verbose:
                    print("BUILDSYS: remove file: {}".format(built_item_info.path))
                os.remove(built_item_info.path)
        cleanup_dir(self.link_private_dir)
        link_stamp_file_tmp = self.link_stamp_file + '.tmp'
        with open(link_stamp_file_tmp, mode='wb'):
            pass

        argv = [self.linker, '/nologo', '/incremental:no']
        argv += ['/debug', '/pdb:{}'.format(self.pdb_path_private)]

        if self.build_config == BUILD_CONFIG_RELEASE:
            argv += ['/OPT:REF,ICF=2']
        elif self.build_config == BUILD_CONFIG_DEBUG:
            argv += ['/OPT:NOREF,NOICF']
        else:
            raise BuildSystemException("Unsupported build config: '{}'".format(self.build_config))

        argv += [ '-out:{}'.format(self.bin_path_private)]

        if self.obj_list:
            argv += self.obj_list
        else:
            # LINK : warning LNK4001: no object files specified; libraries used
            argv += ['/IGNORE:4001']

        if self.link_libstatic_names:
            argv += ['/libpath:{}'.format(self.lib_directory) ]
            for libname in self.link_libstatic_names:
                argv += ['{}.lib'.format(libname) ]

        if self.link_libshared_names:
            argv += ['/libpath:{}'.format(self.sharedlib_directory) ]
            for libname in self.link_libshared_names:
                argv += ['{}.lib'.format(libname) ]

        for libname in self.prebuilt_lib_names:
            argv += ['{}.lib'.format(libname) ]

        argv += self.linker_options

        argv += ['/manifest', '/manifestfile:{}'.format(self.manifest_stub)]

        if self.is_dll:
            argv += ['/dll', '/implib:{}'.format(self.implib_path_private) ]
            if self.exports_def_file is not None:
                argv += ['/def:{}'.format(self.exports_def_file) ]
            if self.export_list:
                for export_entry in self.export_list:
                    argv += ['/EXPORT:{}'.format(export_entry)]
        else:
            if self.win_console:
                argv += ['/subsystem:console']
            else:
                argv += ['/subsystem:windows']
            if self.use_wmain:
                argv += ['/ENTRY:wmainCRTStartup']
            if self.win_stack_size:
                argv += ['/STACK:{}'.format(self.win_stack_size)]

        argv = argv_to_rsp(argv, self.rsp_file)
        if verbose:
            print("BUILDSYS: EXEC: {}".format(' '.join(argv)))
        p = subprocess.Popen(argv, env=self.env)
        p.communicate()
        if p.returncode != 0:
            raise BuildSystemException(self.bin_path_private, exit_code=p.returncode)

        manifest_id = '2' if self.is_dll else '1'
        argv = [self.mt_tool, '/nologo', '/verbose', '/manifest', self.manifest_stub,
                '/out:{}'.format(self.manifest_builtin), '/outputresource:{};{}'.format(self.bin_path_private, manifest_id) ]
        if verbose:
            print("BUILDSYS: EXEC: {}".format(' '.join(argv)))
        p = subprocess.Popen(argv, env=self.env)
        p.communicate()
        if p.returncode != 0:
            raise BuildSystemException(bin_path, exit_code=p.returncode)

        if self.zip_section is not None:
            if not os.path.isfile(self.zip_section):
                raise BuildSystemException("File '{}' for zip-section not found".format(self.zip_section))
            if verbose:
                print("BUILDSYS: EXEC: {} << {}".format(self.bin_path_private, self.zip_section))
            with open(self.bin_path_private, 'ab') as fhbin:
                with open(self.zip_section, 'rb') as fhzip:
                    shutil.copyfileobj(fhzip, fhbin)

        os.rename(self.bin_path_private, self.bin_path_public)
        os.rename(self.pdb_path_private, self.pdb_path_public)
        if self.is_dll:
            os.rename(self.implib_path_private, self.implib_path_public)
        os.rename(link_stamp_file_tmp, self.link_stamp_file)
        os.utime(self.link_stamp_file, None)
        os.utime(self.bin_path_public, None)

        return (True, build_result)


class MsvsModelWin32(ToolsetModel):
    def __init__(self, msvs_version):
        ToolsetModel.__init__(self)
        self._name = MSVS_MODEL_FORMAT_WIN32.format(msvs_version)
        self._is_native = is_windows_32bit()

    @property
    def model_name(self):
        return self._name

    @property
    def platform_name(self):
        return TAG_PLATFORM_WINDOWS

    @property
    def platform_alias(self):
        return None

    @property
    def architecture_abi_name(self):
        return TAG_ARCH_X86

    def is_native(self):
        return self._is_native

    def get_arch_defines(self):
        return [ '_WIN32_WINNT=0x0501', 'WINVER=0x0501']

    def get_linker_options(self):
        return [ '/MACHINE:X86']


class MsvsModelWin64(ToolsetModel):
    def __init__(self, msvs_version):
        ToolsetModel.__init__(self)
        self._name = MSVS_MODEL_FORMAT_WIN64.format(msvs_version)
        self._is_native = is_windows_64bit()

    @property
    def model_name(self):
        return self._name

    @property
    def platform_name(self):
        return TAG_PLATFORM_WINDOWS

    @property
    def platform_alias(self):
        return None

    @property
    def architecture_abi_name(self):
        return TAG_ARCH_X86_64

    def is_native(self):
        return self._is_native

    def get_arch_defines(self):
        return [ '_WIN32_WINNT=0x0502', 'WINVER=0x0502']

    def get_linker_options(self):
        return [ '/MACHINE:X64']


class ToolsetMSVS(ToolsetBase):
    def __init__(self, msvs_version, sysinfo, loader, tools_path32, custom_env32, tools_path64, custom_env64, nasm_executable):
        ToolsetBase.__init__(self)
        self._msvs_version = msvs_version
        self._sysinfo = sysinfo
        self._loader = loader
        self._tools_path32 = tools_path32
        self._custom_env32 = custom_env32
        self._tools_path64 = tools_path64
        self._custom_env64 = custom_env64
        self._nasm_executable = nasm_executable
        self._nasm_checked = False

    @property
    def toolset_name(self):
        return 'msvs'

    @property
    def platform_name(self):
        return TAG_PLATFORM_WINDOWS

    @property
    def supported_models(self):
        model_win32 = MsvsModelWin32(self._msvs_version)
        model_win64 = MsvsModelWin64(self._msvs_version)
        models = {
            model_win32.model_name : model_win32,
            model_win64.model_name : model_win64,
        }
        return models

    def _select_tool(self, tag, build_model):
        arch = build_model.architecture_abi_name
        if arch == TAG_ARCH_X86:
            tool = self._tools_path32[tag]
        elif arch == TAG_ARCH_X86_64:
            tool = self._tools_path64[tag]
        else:
            raise BuildSystemException("Unsupported build model: '{}'".format(model_name))
        return tool

    def _select_env(self, build_model):
        arch = build_model.architecture_abi_name
        if arch == TAG_ARCH_X86:
            env = self._custom_env32
        elif arch == TAG_ARCH_X86_64:
            env = self._custom_env64
        else:
            raise BuildSystemException("Unsupported build model: '{}'".format(model_name))
        return env

    def create_cpp_build_action(self, description, cpp_source, obj_directory, obj_name, build_model, build_config):
        cl = self._select_tool(TAG_MSVS_CL, build_model)
        env = self._select_env(build_model)
        return SourceBuildActionMSVS(cl, env, self._sysinfo, description, cpp_source, BUILD_TYPE_CPP, obj_directory, obj_name, build_model, build_config)

    def create_c_build_action(self, description, c_source, obj_directory, obj_name, build_model, build_config):
        cl = self._select_tool(TAG_MSVS_CL, build_model)
        env = self._select_env(build_model)
        return SourceBuildActionMSVS(cl, env, self._sysinfo, description, c_source, BUILD_TYPE_C, obj_directory, obj_name, build_model, build_config)

    def create_asm_build_action(self, description, asm_source, obj_directory, obj_name, build_model, build_config):
        if description.nasm:
            if not self._nasm_checked:
                try:
                    subprocess.check_output([self._nasm_executable, '-v'], stderr=subprocess.STDOUT)
                    self._nasm_checked = True
                except Exception as _:
                    pass
            if not self._nasm_checked:
                raise BuildSystemException("NASM executable '{}' is not ready, it is required to compile: '{}'".format(self._nasm_executable, asm_source))

            return NasmSourceBuildAction(self._nasm_executable, self._sysinfo, description, asm_source, obj_directory, obj_name, build_model, build_config)
        else:
            ml = self._select_tool(TAG_MSVS_ASM, build_model)
            env = self._select_env(build_model)
            return MasmSourceBuildAction(ml, env, self._sysinfo, description, asm_source, obj_directory, obj_name, build_model, build_config)

    def create_lib_static_link_action(self, description, lib_directory, obj_directory, obj_names, build_model, build_config):
        lib_tool = self._select_tool(TAG_MSVS_LIB, build_model)
        env = self._select_env(build_model)
        return StaticLibLinkActionMSVS(lib_tool, env, self._sysinfo, description, lib_directory, obj_directory, obj_names, build_model, build_config)

    def create_exe_link_action(self, description, exe_directory, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config):
        link_tool = self._select_tool(TAG_MSVS_LINK, build_model)
        mt_tool = self._select_tool(TAG_MSVS_MT, build_model)
        env = self._select_env(build_model)
        return LinkActionMSVS(link_tool, mt_tool, env, self._sysinfo, self._loader, description, exe_directory, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config)

    def create_lib_shared_link_action(self, description, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config):
        link_tool = self._select_tool(TAG_MSVS_LINK, build_model)
        mt_tool = self._select_tool(TAG_MSVS_MT, build_model)
        env = self._select_env(build_model)
        return LinkActionMSVS(link_tool, mt_tool, env, self._sysinfo, self._loader, description, None, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config)


def create_toolset(sysinfo, loader, **kwargs):
    msvs_version = kwargs['msvs_version']
    nasm_executable = kwargs.get('nasm_executable', 'nasm')
    bootstrap_dir = sysinfo[TAG_CFG_DIR_BOOTSTRAP]
    tools_path32, env_patch32, tools_path64, env_patch64 = init_msvs_toolset(msvs_version, bootstrap_dir)
    custom_env32 = apply_environ_patch(env_patch32)
    custom_env64 = apply_environ_patch(env_patch64)
    return ToolsetMSVS(msvs_version, sysinfo, loader, tools_path32, custom_env32, tools_path64, custom_env64, nasm_executable)
