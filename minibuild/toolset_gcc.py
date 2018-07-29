from __future__ import print_function

__all__ = ['create_toolset', 'describe_toolset']

import ctypes
import os
import os.path
import re
import shutil
import subprocess
import sys

from .arch_parse import parse_arch_specific_tokens
from .build_art import BuildArtifact
from .constants import *
from .depends_check import *
from .error_utils import BuildSystemException
from .nasm_action import NasmSourceBuildAction
from .os_utils import *
from .string_utils import escape_string, argv_to_rsp
from .toolset_base import ToolsetBase, ToolsetModel, ToolsetActionBase, ToolsetActionResult
from .winapi_level import *
from .winrc_manifest import WINRC_MANIFEST


GCC_MODEL_LINUX_X86 = 'gcc-linux-x86'
GCC_MODEL_LINUX_X86_64 = 'gcc-linux-x86_64'
GCC_MODEL_LINUX_ARM = 'gcc-linux-arm'
GCC_MODEL_LINUX_ARM64 = 'gcc-linux-arm64'

CLANG_MODEL_MACOSX_X86_64 = 'clang-macosx-x86_64'

GCC_CROSSTOOL_MODEL_LINUX_X86 = 'gcc-xt-linux-x86'
GCC_CROSSTOOL_MODEL_LINUX_X86_64 = 'gcc-xt-linux-x86_64'
GCC_CROSSTOOL_MODEL_LINUX_ARM = 'gcc-xt-linux-arm'
GCC_CROSSTOOL_MODEL_LINUX_ARM64 = 'gcc-xt-linux-arm64'

GCC_MODEL_MINGW32 = 'mingw-win32'
GCC_MODEL_MINGW64 = 'mingw-win64'

CROSSTOOL_MODEL_NAMES = {
    TAG_ARCH_X86: GCC_CROSSTOOL_MODEL_LINUX_X86,
    TAG_ARCH_X86_64: GCC_CROSSTOOL_MODEL_LINUX_X86_64,
    TAG_ARCH_ARM: GCC_CROSSTOOL_MODEL_LINUX_ARM,
    TAG_ARCH_ARM64: GCC_CROSSTOOL_MODEL_LINUX_ARM64,
}

LINUX_GCC_MODEL_NAMES = {
    TAG_ARCH_X86: GCC_MODEL_LINUX_X86,
    TAG_ARCH_X86_64: GCC_MODEL_LINUX_X86_64,
    TAG_ARCH_ARM: GCC_MODEL_LINUX_ARM,
    TAG_ARCH_ARM64: GCC_MODEL_LINUX_ARM64,
}

CROSSTOOL_NATIVE_STATUS = {
    TAG_ARCH_X86: is_linux_x86(),
    TAG_ARCH_X86_64: is_linux_x86_64(),
    TAG_ARCH_ARM: is_linux_arm(),
    TAG_ARCH_ARM64: is_linux_arm64(),
}

_RE_VERSION = re.compile(r'(\d+\.[\d\.]+)')


def split_version_string(version_text, strip_ebraced):
    bits = version_text.split()
    reparsed = []
    embrased = False
    for v in bits:
        if v.startswith('('):
            embrased = True
            v = v[1:]
        end_embrace = v.endswith(')')
        if end_embrace:
            v = v[:-1]
        if not embrased or not strip_ebraced:
            reparsed.append(v)
        if end_embrace:
            embrased = False
    return reparsed


def parse_clang_version_string(version_text):
    for value in split_version_string(version_text, False):
        if value.startswith('clang-'):
            return value[6:]
    return None


def parse_gcc_version_string(version_text):
    for value in split_version_string(version_text, True):
        m = _RE_VERSION.match(value)
        if m:
            version = m.group(1)
            if version:
                return version
    return None


def load_export_list_from_def_file(def_file, winapi_only, for_winapi):
    export_section_found = False
    export_list = []
    lines = [line.rstrip('\r\n') for line in open(def_file)]
    line_number = 0
    inside_export = False
    for line in lines:
        line_number += 1
        text = line.lstrip()
        if not text or text[0] == ';':
            continue
        tokens = text.split()
        line_is_keyword = False
        if len(line) == len(text):
            line_is_keyword = True
        if line_is_keyword:
            if inside_export:
                inside_export = False
            elif len(tokens) == 1 and tokens[0] == 'EXPORTS':
                if export_section_found:
                    raise BuildSystemException("'EXPORTS' section found more then once inside DEF file: '{}'".format(def_file))
                export_section_found = True
                inside_export = True
            continue
        if inside_export:
            if tokens and not tokens[0].startswith('@'):
                symbol = tokens[0]
                symbol_enabled = True
                if winapi_only and not for_winapi:
                    if symbol in winapi_only:
                        symbol_enabled = False
                if symbol_enabled:
                    export_list.append(symbol)
    if not export_section_found:
        raise BuildSystemException("'EXPORTS' section not found inside DEF file: '{}'".format(def_file))
    if not export_list:
        raise BuildSystemException("Cannot load symbols information from 'EXPORTS' section inside DEF file: '{}'".format(def_file))
    return export_list


class SourceBuildActionGCC(ToolsetActionBase):
    def __init__(self, tools, sysinfo, description, source_path, source_type, obj_directory, obj_name, build_model, build_config):
        self.tools = tools
        self.source_path = source_path
        self.source_type = source_type
        self.pdb_path = os.path.join(obj_directory, obj_name + sysinfo[TAG_CFG_PDB_SUFFIX])
        self.obj_path = os.path.join(obj_directory, obj_name + sysinfo[TAG_CFG_OBJ_SUFFIX])
        self.dep_path = os.path.join(obj_directory, obj_name + sysinfo[TAG_CFG_DEP_SUFFIX])
        self.deptmp_path = self.dep_path + 'tmp'
        self.project_root = sysinfo[TAG_CFG_DIR_PROJECT_ROOT]
        self.common_prefix = sysinfo[TAG_CFG_PROJECT_ROOT_COMMON_PREFIX]
        self.arch_flags = []
        self.arch_flags += build_model.get_arch_compile_flags()
        self.symbol_visibility_default = description.symbol_visibility_default
        self.build_config = build_config
        self.include_dirs = eval_include_dirs_in_description(description, self.project_root, source_type)
        self.definitions  = eval_definitions_list_in_description(description, build_model, source_type)
        self.disabled_warnings = []
        if description.disabled_warnings and source_type != BUILD_TYPE_ASM:
            self.disabled_warnings = description.disabled_warnings
        self.extra_deps = []
        self.extra_deps.extend(description.self_file_parts)

    def execute(self, output, ctx):
        target_is_ready = False
        if not ctx.force:
            target_is_ready = is_target_with_deps_up_to_date(
                self.project_root, self.source_path, self.obj_path, self.dep_path, self.extra_deps, ctx.verbose)
        if target_is_ready:
            if ctx.verbose:
                output.report_message("BUILDSYS: up-to-date: {}".format(self.source_path))
            return ToolsetActionResult(rebuilt=False, artifacts=None)

        if ctx.verbose:
            if self.source_type == BUILD_TYPE_CPP:
                output.report_message("BUILDSYS: CXX: {}".format(self.source_path))
            elif self.source_type == BUILD_TYPE_C:
                output.report_message("BUILDSYS: C: {}".format(self.source_path))
            elif self.source_type == BUILD_TYPE_ASM:
                output.report_message("BUILDSYS: ASM: {}".format(self.source_path))

        argv = [self.tools.gpp, '-Werror-implicit-function-declaration']
        argv += self.arch_flags

        if self.source_type == BUILD_TYPE_CPP:
            argv += ['-x', 'c++']
        elif self.source_type == BUILD_TYPE_C:
            argv += ['-x', 'c']
        elif self.source_type == BUILD_TYPE_ASM:
            argv += ['-x', 'assembler-with-cpp']
        else:
            raise BuildSystemException("Unsupported build type is given for file: '{}'".format(self.source_path))

        if not self.tools.is_mingw:
            argv += ['-fpic', '-fstack-protector']
        if not self.symbol_visibility_default:
            argv += ['-fvisibility=hidden']
        argv += ['-Wall', '-MD', '-MF', self.deptmp_path]

        for wd in self.disabled_warnings:
            argv += [ '-Wno-{}'.format(wd) ]

        if self.build_config == BUILD_CONFIG_RELEASE:
            argv += ['-O3']
        elif self.build_config == BUILD_CONFIG_DEBUG:
            argv += ['-O0', '-g']
        else:
            raise BuildSystemException("Unsupported build config: '{}'".format(self.build_config))

        for incd in self.include_dirs:
            argv += [ '-I{}'.format(incd) ]

        for _def in self.definitions:
            argv += [ '-D{}'.format(_def) ]

        argv += [ '-c', '-o', self.obj_path, self.source_path ]

        ctx.subprocess_communicate(output, argv, issuer=self.source_path, title=os.path.basename(self.source_path))

        depends = parse_gnu_makefile_depends(self.common_prefix, self.source_path, self.deptmp_path, self.obj_path)
        with open(self.dep_path, mode='wt') as dep_content:
            dep_content.writelines(['[\n'])
            for dep_item in depends:
                dep_content.writelines(['    "', escape_string(dep_item), '",\n'])
            dep_content.writelines([']\n'])
        return ToolsetActionResult(rebuilt=True, artifacts=None)


class StaticLibLinkActionGCC(ToolsetActionBase):
    def __init__(self, tools, sysinfo, description, lib_directory, obj_directory, obj_names, build_model, build_config):
        self.tools = tools
        self.module_name = description.module_name
        self.rsp_file = os.path.join(obj_directory, self.module_name + '.rsplnk')
        self.outlib_path = os.path.join(lib_directory, 'lib' + self.module_name + '.a')
        self.obj_list = []
        self.primary_deps = []

        for obj_name in obj_names:
            obj_path = os.path.join(obj_directory, obj_name + sysinfo[TAG_CFG_OBJ_SUFFIX])
            self.obj_list.append(obj_path)
            self.primary_deps.append(obj_path)

        self.extra_deps = []
        self.extra_deps.extend(description.self_file_parts)

    def execute(self, output, ctx):
        build_result = [BuildArtifact(BUILD_RET_TYPE_LIB, self.outlib_path, BUILD_RET_ATTR_DEFAULT)]
        target_is_ready = False
        if not ctx.force:
            target_is_ready, _ = is_target_up_to_date(self.outlib_path, self.primary_deps, self.extra_deps, ctx.verbose)
        if target_is_ready:
            if ctx.verbose:
                output.report_message("BUILDSYS: up-to-date: '{}', lib: {}".format(self.module_name, self.outlib_path))
            return ToolsetActionResult(rebuilt=False, artifacts=build_result)

        output.report_message("BUILDSYS: create LIB module '{}' ...".format(self.module_name))

        if self.tools.is_clang:
            with open(self.rsp_file, mode='wt') as rsp_fh:
                for rsp_entry in self.obj_list:
                    rsp_fh.writelines([rsp_entry, '\n'])
            argv = [self.tools.ar, '-static', '-filelist', self.rsp_file, '-o', self.outlib_path]
        else:
            argv = [self.tools.ar, 'ru', self.outlib_path]
            argv += self.obj_list
            argv = argv_to_rsp(argv, self.rsp_file)

        ctx.subprocess_communicate(output, argv, issuer=self.outlib_path)
        return ToolsetActionResult(rebuilt=True, artifacts=build_result)


class LinkActionGCC(ToolsetActionBase):
    def __init__(self, tools, sysinfo, loader, description, exe_directory, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config):
        self.tools = tools
        self.sharedlib_directory = sharedlib_directory
        self.is_dll = True if exe_directory is None else False
        self.link_public_dir = sharedlib_directory if self.is_dll else exe_directory
        self.link_private_dir = os.path.join(obj_directory, 'raw')
        self.link_stamp_file = os.path.join(self.link_private_dir, 'link.stamp')
        self.lib_directory = lib_directory
        self.primary_deps = [ self.link_stamp_file ]
        self.extra_deps = []
        self.extra_deps.extend(description.self_file_parts)
        self.win_stack_size = description.win_stack_size
        self.use_wmain = description.wmain
        self.zip_section = None
        self.macosx_framework_list = []
        self.macosx_install_name_options = None

        if build_model.platform_name == TAG_PLATFORM_MACOSX:
            self.macosx_framework_list = description.macosx_framework_list
            if description.macosx_install_name_options:
                self.macosx_install_name_options = description.macosx_install_name_options.split()

        if description.zip_section is not None:
            zip_section_file = normalize_path_optional(description.zip_section, description.self_dirname)
            self.zip_section = zip_section_file
            self.primary_deps.append(zip_section_file)

        self.module_name = description.module_name
        self.module_name_private = description.module_name

        if self.is_dll:
            if self.tools.is_mingw:
                self.bin_basename = description.module_name +'.dll'
            else:
                self.bin_basename = 'lib' + description.module_name + '.so'
        else:
            exe_name = description.module_name
            if description.exe_name:
                exe_name = description.exe_name
                self.module_name_private = description.exe_name
            if self.tools.is_mingw:
                self.bin_basename = exe_name + '.exe'
            else:
                self.bin_basename = exe_name

        self.bin_path_public = os.path.join(self.link_public_dir, self.bin_basename)
        self.bin_path_private = os.path.join(self.link_private_dir, self.bin_basename)

        if self.is_dll:
            self.export_def_file = verify_exports_def_file(description)
            if self.export_def_file is not None:
                self.extra_deps.append(self.export_def_file)
            self.export_list = description.export
            self.export_winapi_only = description.export_winapi_only
            self.export_map_file = None
            if self.export_list or (self.export_def_file and not self.tools.is_mingw):
                self.export_map_file = os.path.join(self.link_private_dir, 'symbols.map')

        if self.tools.is_mingw:
            self.res_file = None
            self.include_dirs = None
            self.winrc_file = verify_winrc_file(description)
            if self.winrc_file is not None:
                self.include_dirs = eval_include_dirs_in_description(description, sysinfo[TAG_CFG_DIR_PROJECT_ROOT], None)
                self.extra_deps.append(self.winrc_file)
                self.res_file = os.path.join(self.link_private_dir, self.module_name_private + '.res.o')
                self.winrc_definitions = description.winrc_definitions
            if description.with_default_manifest:
                self.manifest_res_file = os.path.join(self.link_private_dir, self.module_name_private + '.manifest.res.o')
            else:
                self.manifest_res_file = None

        self.rsp_file = os.path.join(self.link_private_dir, self.module_name_private + '.rsplnk')
        self.obj_list = []
        self.arch_flags = []
        self.arch_flags += build_model.get_arch_link_flags(description)
        self.build_config = build_config
        for obj_name in obj_names:
            obj_path = os.path.join(obj_directory, obj_name + sysinfo[TAG_CFG_OBJ_SUFFIX])
            self.obj_list.append(obj_path)
            self.primary_deps.append(obj_path)
        self.link_libstatic_names = []
        self.link_libshared_names = []
        eval_libnames_in_description(loader, description, build_model, self.link_libstatic_names, self.link_libshared_names)
        self.prebuilt_lib_names = eval_prebuilt_lib_list_in_description(description, build_model)

    def execute(self, output, ctx):
        mod_type_id = BUILD_RET_TYPE_DLL if self.is_dll else BUILD_RET_TYPE_EXE
        mod_attr = BUILD_RET_ATTR_DEFAULT if self.is_dll or self.tools.is_mingw else BUILD_RET_ATTR_FLAG_EXECUTABLE
        build_result = [BuildArtifact(mod_type_id, self.bin_path_public, mod_attr)]
        target_is_ready = False
        if not ctx.force:
            target_is_ready, _ = is_target_up_to_date(self.bin_path_public, self.primary_deps, self.extra_deps, ctx.verbose)
        mod_type = 'DLL' if self.is_dll else 'EXE'
        if target_is_ready:
            output.report_message("BUILDSYS: up-to-date: '{}', {}: {}".format(self.module_name, mod_type, self.bin_path_public))
            return ToolsetActionResult(rebuilt=True, artifacts=build_result)

        output.report_message("BUILDSYS: link {} module '{}' ...".format(mod_type, self.module_name))
        for built_item_info in build_result:
            if os.path.exists(built_item_info.path):
                if ctx.verbose:
                    output.report_message("BUILDSYS: remove file: {}".format(built_item_info.path))
                os.remove(built_item_info.path)
        cleanup_dir(self.link_private_dir)
        link_stamp_file_tmp = self.link_stamp_file + '.tmp'
        with open(link_stamp_file_tmp, mode='wb'):
            pass

        if self.tools.is_mingw:
            if self.winrc_file is not None:
                argv = [self.tools.windres, self.winrc_file, self.res_file]
                for incd in self.include_dirs:
                    argv += [ '-I{}'.format(incd) ]
                for defrc in self.winrc_definitions:
                    argv += [ '-D{}'.format(defrc) ]
                ctx.subprocess_communicate(output, argv, issuer=self.winrc_file, title=os.path.basename(self.winrc_file))

            if self.manifest_res_file is not None:
                manifest_builtin = os.path.join(self.link_private_dir, self.module_name_private + '.manifest')
                manifest_rc = os.path.join(self.link_private_dir, self.module_name_private + '.manifest.rc')
                with open(manifest_builtin, mode='wt') as fh_manifest:
                    fh_manifest.writelines([WINRC_MANIFEST])
                manifest_id = '2' if self.is_dll else '1'
                with open(manifest_rc, mode='wt') as fh_manifest_rc:
                    fh_manifest_rc.writelines([
                        '#include <winuser.h>\n',
                        '{} RT_MANIFEST {}\n'.format(manifest_id, self.module_name_private + '.manifest')
                    ])
                argv = [self.tools.windres, manifest_rc, self.manifest_res_file]
                ctx.subprocess_communicate(output, argv, issuer=manifest_rc, title=os.path.basename(manifest_rc))

        argv = [ self.tools.gpp ]
        argv += self.arch_flags

        if self.tools.is_mingw:
            argv += ['-Wl,--enable-stdcall-fixup']

        if self.is_dll:
            argv += ['-shared']
            if not self.tools.is_clang:
                argv += ['-Wl,--no-undefined' ]

            if self.export_map_file is not None:
                actual_export_list = []
                if self.export_def_file is not None:
                    export_list_from_def = load_export_list_from_def_file(self.export_def_file, self.export_winapi_only, self.tools.is_mingw)
                    actual_export_list.extend(export_list_from_def)
                if self.export_list:
                    for explicit_export in self.export_list:
                        if self.export_winapi_only and not self.tools.is_mingw:
                            if explicit_export in self.export_winapi_only:
                                continue
                        actual_export_list.append(explicit_export)
                if self.tools.is_clang:
                    with open(self.export_map_file, 'wt') as fh:
                        for export_entry in actual_export_list:
                            print('_{}'.format(export_entry), file=fh)
                    argv += [ '-Wl,-exported_symbols_list,{}'.format(self.export_map_file) ]
                else:
                    with open(self.export_map_file, 'wt') as fh:
                        print("{", file=fh)
                        print("    global:", file=fh)
                        for export_entry in actual_export_list:
                            print("        {};".format(export_entry), file=fh)
                        print("\n    local: *;", file=fh)
                        print("};", file=fh)
                    argv += [ '-Wl,--version-script={}'.format(self.export_map_file) ]

        else:
            if self.tools.is_mingw:
                if self.use_wmain:
                    argv += ['-municode']
                if self.win_stack_size:
                    argv += ['-Wl,--stack,{}'.format(self.win_stack_size)]
            else:
                if not self.tools.is_clang:
                    argv += ['-pie']

        if not self.tools.is_mingw and not self.tools.is_clang:
            argv += ['-Wl,-z,noexecstack']

        if not self.tools.is_clang:
            argv += ['-Wl,--as-needed']

        argv += [ '-o', self.bin_path_private ]

        if self.is_dll and self.tools.is_mingw:
            if self.export_def_file and not self.export_map_file:
                argv += [ self.export_def_file ]

        if self.tools.is_mingw:
            if self.res_file is not None:
                argv += [ self.res_file ]
            if self.manifest_res_file is not None:
                argv += [ self.manifest_res_file ]

        argv += self.obj_list

        if not self.tools.is_clang:
            argv += ['-static-libgcc']

        wrap_libs_in_group = False
        if self.link_libstatic_names or self.link_libshared_names:
            if not self.tools.is_clang:
                wrap_libs_in_group = True

        if wrap_libs_in_group:
            argv += [ '-Wl,--start-group' ]

        if self.link_libstatic_names:
            argv += [ '-L{}'.format(self.lib_directory) ]
            for libname in self.link_libstatic_names:
                argv += [ '-l{}'.format(libname) ]

        if self.link_libshared_names:
            argv += [ '-L{}'.format(self.sharedlib_directory) ]
            for libname in self.link_libshared_names:
                argv += [ '-l{}'.format(libname) ]

        if wrap_libs_in_group:
            argv += [ '-Wl,--end-group' ]

        for libname in self.prebuilt_lib_names:
            argv += [ '-l{}'.format(libname) ]

        if self.tools.is_clang:
            argv += [ '-Wl,-install_name,{}'.format(self.bin_basename) ]

        if self.macosx_framework_list:
            for framework_name in self.macosx_framework_list:
                argv += [ '-framework', framework_name ]

        argv = argv_to_rsp(argv, self.rsp_file)
        ctx.subprocess_communicate(output, argv, issuer=self.bin_path_private)

        if self.macosx_install_name_options:
            argv = ['install_name_tool']
            argv += self.macosx_install_name_options
            argv += [ self.bin_path_private ]
            ctx.subprocess_communicate(output, argv, issuer=self.bin_path_private)

        if self.zip_section is not None:
            if not os.path.isfile(self.zip_section):
                raise BuildSystemException("File '{}' for zip-section not found".format(self.zip_section))
            if ctx.verbose:
                output.report_message("BUILDSYS: EXEC: {} << {}".format(self.bin_path_private, self.zip_section))
            with open(self.bin_path_private, 'ab') as fhbin:
                with open(self.zip_section, 'rb') as fhzip:
                    shutil.copyfileobj(fhzip, fhbin)

        os.rename(self.bin_path_private, self.bin_path_public)
        os.rename(link_stamp_file_tmp, self.link_stamp_file)
        os.utime(self.link_stamp_file, None)
        os.utime(self.bin_path_public, None)

        return ToolsetActionResult(rebuilt=True, artifacts=build_result)


class GccModel(ToolsetModel):
    def __init__(self, model_name, toolset_version, is_native, target_os, target_os_alias, arch_name, arch_flags, arch_link_flags, os_version=None, crosstool=False):
        ToolsetModel.__init__(self)

        self._model_name = model_name
        self._toolset_version = toolset_version
        self._is_native = is_native
        self._target_os = target_os
        self._target_os_alias = target_os_alias
        self._arch_name = arch_name
        self._arch_compile_flags = arch_flags
        self._arch_link_flags = arch_link_flags
        self._os_version = os_version
        self._crosstool = crosstool

    @property
    def model_name(self):
        return self._model_name

    @property
    def platform_name(self):
        return self._target_os

    @property
    def platform_alias(self):
        return self._target_os_alias

    @property
    def architecture_abi_name(self):
        return self._arch_name

    @property
    def toolset_version(self):
        return self._toolset_version

    def is_native(self):
        return self._is_native

    def is_crosstool(self):
        return self._crosstool

    def get_arch_compile_flags(self):
        return self._arch_compile_flags

    def get_arch_link_flags(self, description):
        if self._target_os == TAG_PLATFORM_WINDOWS:
            flags = self._arch_link_flags[:]
            if description.win_console:
                flags.append('-Wl,-subsystem:console:{}'.format(self._os_version))
            else:
                flags.append('-Wl,-subsystem:windows:{}'.format(self._os_version))
            return flags
        else:
            return self._arch_link_flags


class ToolsetGCC(ToolsetBase):
    def __init__(self, name, tools, sysinfo, loader):
        ToolsetBase.__init__(self)
        self._name = name
        self._platform_name = None
        self._sysinfo = sysinfo
        self._loader = loader
        self._tools = tools
        self._nasm_checked = False

        models = []
        toolset_version = tools.eval_version_info()

        if self._tools.is_mingw:
            self._platform_name = TAG_PLATFORM_WINDOWS

            if TAG_ARCH_X86 in self._tools.arch_list:
                winapi_level_x86 = self._tools.api_levels[TAG_ARCH_X86]
                ntddi_level_x86 = IMPLIED_NTDDI_VALUES[winapi_level_x86]
                os_version_x86 = IMPLIED_WINDOWS_SUBSYSTEM_VALUES[winapi_level_x86]

                mingw_x86_compile_flags = ['-m32',
                    '-D_WIN32_WINNT={}'.format(winapi_level_x86),
                    '-DWINVER={}'.format(winapi_level_x86),
                    '-DNTDDI_VERSION={}'.format(ntddi_level_x86)]

                mingw_x86_link_flags = ['-m32']

                model_win32 = GccModel(
                    model_name=GCC_MODEL_MINGW32, toolset_version=toolset_version, is_native=is_windows_32bit(),
                    target_os=TAG_PLATFORM_WINDOWS, target_os_alias=None, arch_name=TAG_ARCH_X86,
                    arch_flags=mingw_x86_compile_flags, arch_link_flags=mingw_x86_link_flags, os_version=os_version_x86)

                models.append(model_win32)

            if TAG_ARCH_X86_64 in self._tools.arch_list:
                winapi_level_x86_64 = self._tools.api_levels[TAG_ARCH_X86_64]
                ntddi_level_x86_64 = IMPLIED_NTDDI_VALUES[winapi_level_x86_64]
                os_version_x86_64 = IMPLIED_WINDOWS_SUBSYSTEM_VALUES[winapi_level_x86_64]

                mingw_x86_64_compile_flags = ['-m64',
                    '-D_WIN32_WINNT={}'.format(winapi_level_x86_64),
                    '-DWINVER={}'.format(winapi_level_x86_64),
                    '-DNTDDI_VERSION={}'.format(ntddi_level_x86_64)]

                mingw_x86_64_link_flags = ['-m64']

                model_win64 = GccModel(
                    model_name=GCC_MODEL_MINGW64, toolset_version=toolset_version, is_native=is_windows_64bit(),
                    target_os=TAG_PLATFORM_WINDOWS, target_os_alias=None, arch_name=TAG_ARCH_X86_64,
                    arch_flags=mingw_x86_64_compile_flags, arch_link_flags=mingw_x86_64_link_flags, os_version=os_version_x86_64)

                models.append(model_win64)

        elif self._tools.is_crosstool:
            self._platform_name = TAG_PLATFORM_LINUX

            for x_arch in self._tools.arch_list:
                x_model_name = CROSSTOOL_MODEL_NAMES[x_arch]
                x_is_native = CROSSTOOL_NATIVE_STATUS[x_arch]

                x_model = GccModel(
                    model_name=x_model_name, toolset_version=toolset_version, is_native=x_is_native,
                    target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=x_arch,
                    arch_flags=[], arch_link_flags=[], crosstool=True)

                models.append(x_model)

        else:
            if is_linux_x86_64():
                self._platform_name = TAG_PLATFORM_LINUX

                model_linux_x86 = GccModel(
                    model_name=GCC_MODEL_LINUX_X86, toolset_version=toolset_version, is_native=False,
                    target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_X86,
                    arch_flags=['-m32'], arch_link_flags=['-m32'])

                model_linux_x86_64 = GccModel(
                    model_name=GCC_MODEL_LINUX_X86_64, toolset_version=toolset_version, is_native=True,
                    target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_X86_64,
                    arch_flags=[], arch_link_flags=[])

                models.extend([model_linux_x86, model_linux_x86_64])

            elif is_linux_x86():
                self._platform_name = TAG_PLATFORM_LINUX

                model_linux_x86 = GccModel(
                    model_name=GCC_MODEL_LINUX_X86, toolset_version=toolset_version, is_native=True,
                    target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_X86,
                    arch_flags=[], arch_link_flags=[])

                models.append(model_linux_x86)

            elif is_linux_arm():
                self._platform_name = TAG_PLATFORM_LINUX

                model_linux_arm = GccModel(
                    model_name=GCC_MODEL_LINUX_ARM, toolset_version=toolset_version, is_native=True,
                    target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_ARM,
                    arch_flags=[], arch_link_flags=[])

                models.append(model_linux_arm)

            elif is_linux_arm64():
                self._platform_name = TAG_PLATFORM_LINUX

                model_linux_arm = GccModel(
                    model_name=GCC_MODEL_LINUX_ARM64, toolset_version=toolset_version, is_native=True,
                    target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_ARM64,
                    arch_flags=[], arch_link_flags=[])

                models.append(model_linux_arm)

            elif is_macosx_x86_64():
                if self._name == 'clang':
                    self._platform_name = TAG_PLATFORM_MACOSX

                    model_macosx_x86_64 = GccModel(
                        model_name=CLANG_MODEL_MACOSX_X86_64, toolset_version=toolset_version, is_native=True,
                        target_os=TAG_PLATFORM_MACOSX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_X86_64,
                        arch_flags=[], arch_link_flags=[])

                    models.append(model_macosx_x86_64)

            if self._platform_name is None:
                platform = sys.platform
                if platform.startswith('linux'):
                    platform = 'linux'
                machine = os.uname()[4]
                raise BuildSystemException("Unsupported platform: '{},{}'".format(platform, machine))

        self._models = {}
        for model in models:
            self._models[model.model_name] = model

    @property
    def supported_models(self):
        return self._models

    @property
    def toolset_name(self):
        return self._name

    @property
    def platform_name(self):
        return self._platform_name

    def create_cpp_build_action(self, description, cpp_source, obj_directory, obj_name, build_model, build_config):
        return SourceBuildActionGCC(self._tools, self._sysinfo, description, cpp_source, BUILD_TYPE_CPP, obj_directory, obj_name, build_model, build_config)

    def create_c_build_action(self, description, c_source, obj_directory, obj_name, build_model, build_config):
        return SourceBuildActionGCC(self._tools, self._sysinfo, description, c_source, BUILD_TYPE_C, obj_directory, obj_name, build_model, build_config)

    def create_asm_build_action(self, description, asm_source, obj_directory, obj_name, build_model, build_config):
        if description.nasm:
            if not self._tools.nasm_enabled:
                raise BuildSystemException("NASM is not enabled for build model '{}', it is required to compile: '{}'".format(build_model.model_name, asm_source))
            if not self._nasm_checked:
                try:
                    subprocess.check_output([self._tools.nasm_executable, '-v'], stderr=subprocess.STDOUT)
                    self._nasm_checked = True
                except Exception:
                    pass
            if not self._nasm_checked:
                raise BuildSystemException("NASM executable '{}' is not ready, it is required to compile: '{}'".format(self._tools.nasm_executable, asm_source))

            return NasmSourceBuildAction(self._tools.nasm_executable, self._sysinfo, description, asm_source, obj_directory, obj_name, build_model, build_config)
        else:
            return SourceBuildActionGCC(self._tools, self._sysinfo, description, asm_source, BUILD_TYPE_ASM, obj_directory, obj_name, build_model, build_config)

    def create_lib_static_link_action(self, description, lib_directory, obj_directory, obj_names, build_model, build_config):
        return StaticLibLinkActionGCC(self._tools, self._sysinfo, description, lib_directory, obj_directory, obj_names, build_model, build_config)

    def create_exe_link_action(self, description, exe_directory, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config):
        return LinkActionGCC(self._tools, self._sysinfo, self._loader, description, exe_directory, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config)

    def create_lib_shared_link_action(self, description, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config):
        return LinkActionGCC(self._tools, self._sysinfo, self._loader, description, None, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config)


class ToolsInfoGCC:
    def __init__(self, dir_prefix=None, bin_prefix=None, is_mingw=None, is_clang=None, is_crosstool=None, arch_list=None, nasm=None, api_levels=None):
        tool_gcc = 'clang' if is_clang else 'gcc'
        tool_gpp = 'clang' if is_clang else 'g++'
        tool_ar  = 'libtool' if is_clang else 'ar'
        tool_windres = 'windres' if is_mingw else None

        if bin_prefix is not None:
            tool_gcc = bin_prefix + tool_gcc
            tool_gpp = bin_prefix + tool_gpp
            tool_ar  = bin_prefix + tool_ar
            if tool_windres is not None:
                tool_windres = bin_prefix + tool_windres

        if dir_prefix is not None:
            tool_gcc = os.path.join(dir_prefix, tool_gcc)
            tool_gpp = os.path.join(dir_prefix, tool_gpp)
            tool_ar  = os.path.join(dir_prefix, tool_ar)
            if tool_windres is not None:
                tool_windres = os.path.join(dir_prefix, tool_windres)

        self.is_mingw = is_mingw
        self.is_clang = is_clang
        self.is_crosstool = is_crosstool
        self.arch_list = arch_list
        self.api_levels = api_levels

        self.gcc = tool_gcc
        self.gpp = tool_gpp
        self.ar  = tool_ar
        self.windres = tool_windres
        self.nasm_executable = nasm if nasm else 'nasm'
        self.nasm_enabled = False

        if is_mingw:
            self.nasm_enabled = True

        elif is_crosstool:
            self.nasm_enabled = False
            if arch_list:
                if (TAG_ARCH_X86 in arch_list) or (TAG_ARCH_X86_64 in arch_list):
                    self.nasm_enabled = True
        else:
            if is_linux_x86_64() or is_linux_x86() or is_macosx_x86_64():
                self.nasm_enabled = True

    def eval_version_info(self):
        argv = [self.gpp, '--version']
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        version_text, _ = p.communicate()
        version_bits = version_text.split('\n')
        if version_bits and version_bits[0] and version_bits[0].rstrip('\r\n').strip():
            version_text = version_bits[0].rstrip('\r\n').strip()
        if p.returncode != 0:
            errmsg = ' '.join(argv) + '\n' + version_text
            raise BuildSystemException(errmsg, exit_code=p.returncode)
        version = None
        if self.is_clang:
            version = parse_clang_version_string(version_text)
        else:
            version = parse_gcc_version_string(version_text)
        if version is None:
            errmsg = ' '.join(argv) + '\n' + version_text + "\n   Failed to parse version string given above."
            raise BuildSystemException(errmsg)
        return version


def init_mingw_tools(sysinfo, mingw, nasm):
    package_path = mingw.get('package_path')
    if package_path is None:
        raise BuildSystemException("Malformed MinGW config: 'package_path' is not given in project config file.")
    package_path = os.path.normpath(os.path.expanduser(package_path))
    if not os.path.isabs(package_path):
        package_path = os.path.join(sysinfo[TAG_CFG_DIR_PROJECT_ROOT], package_path)
    if not os.path.isdir(package_path):
        raise BuildSystemException("Malformed MinGW config: 'package_path' resolved as '{}' is not a directory.".format(package_path))
    package_path_bin = os.path.join(package_path, 'bin')
    if not os.path.isdir(package_path_bin):
        raise BuildSystemException("Malformed MinGW config: '{}' is not a directory.".format(package_path_bin))
    bin_prefix = mingw.get('prefix')
    arch_list = mingw.get('arch')
    if not isinstance(arch_list, list) or not arch_list:
        raise BuildSystemException("Malformed MinGW config: 'arch' list is not given or empty in project config file.")
    arch_parsed = []
    api_levels = {}
    for arch in arch_list:
        winapi_level = None
        if ':' in arch:
            arch_value, winapi_level = arch.split(':', 1)
            winapi_level = winapi_level.strip()
        else:
            arch_value = arch
        if arch_value not in TAG_ALL_KNOWN_MINGW_ARCH_LIST:
            raise BuildSystemException("Malformed MinGW config: unknown arch value '{}' is given. Only the following values are supported: {}.".format(arch_value, ', '.join(TAG_ALL_KNOWN_MINGW_ARCH_LIST)))
        if not winapi_level:
            winapi_level = WINDOWS_API_DEFAULT_LEVEL[arch]
        else:
            if winapi_level not in WINDOWS_API_LEVELS:
                raise BuildSystemException("Malformed MinGW config: unknown Windows API level '{}' is given. Only the following values are supported: {}.".format(winapi_level, ', '.join(WINDOWS_API_LEVELS)))
        arch_parsed.append(arch_value)
        api_levels[arch_value] = winapi_level

    tools = ToolsInfoGCC(dir_prefix=package_path_bin, bin_prefix=bin_prefix, is_mingw=True, arch_list=arch_parsed, nasm=nasm, api_levels=api_levels)
    return tools


def init_cross_tools(sysinfo, xtools_cfg, nasm):
    package_path = xtools_cfg.get('package_path')
    if package_path is None:
        raise BuildSystemException("Malformed cross-tools config: 'package_path' is not given in project config file.")
    package_path = os.path.normpath(os.path.expanduser(package_path))
    if not os.path.isabs(package_path):
        package_path = os.path.join(sysinfo[TAG_CFG_DIR_PROJECT_ROOT], package_path)
    if not os.path.isdir(package_path):
        raise BuildSystemException("Malformed cross-tools config: 'package_path' resolved as '{}' is not a directory.".format(package_path))
    package_path_bin = os.path.join(package_path, 'bin')
    if not os.path.isdir(package_path_bin):
        raise BuildSystemException("Malformed cross-tools config: '{}' is not a directory.".format(package_path_bin))

    cross_arch_list = xtools_cfg.get('arch')
    if not isinstance(cross_arch_list, list) or not cross_arch_list:
        raise BuildSystemException("Malformed cross-tools config: 'arch' list is not given or empty in project config file.")

    for arch in cross_arch_list:
        if arch not in TAG_ALL_KNOWN_ARCH_LIST:
            raise BuildSystemException("Malformed cross-tools config: unknown arch value '{}' is given. The following are supported: {}.".format(arch, ', '.join(TAG_ALL_KNOWN_ARCH_LIST)))

    bin_prefix = xtools_cfg.get('prefix')
    tools = ToolsInfoGCC(dir_prefix=package_path_bin, bin_prefix=bin_prefix, is_crosstool=True, arch_list=cross_arch_list, nasm=nasm)
    return tools


def create_toolset(sysinfo, loader, **kwargs):
    nasm_executable = kwargs.get('nasm_executable')
    if 'mingw' in kwargs:
        mingw = kwargs['mingw']
        mingw_tools = init_mingw_tools(sysinfo, mingw, nasm_executable)
        return ToolsetGCC('gcc', mingw_tools, sysinfo, loader)

    if 'x-tools' in kwargs:
        xtools_cfg = kwargs['x-tools']
        cross_tools = init_cross_tools(sysinfo, xtools_cfg, nasm_executable)
        return ToolsetGCC('gcc', cross_tools, sysinfo, loader)

    gcc_tools = ToolsInfoGCC(nasm=nasm_executable)
    return ToolsetGCC('gcc', gcc_tools, sysinfo, loader)


def _describe_toolset_imp(native_id, config_proto, pragma_line, sys_platform, sys_arch, **kwargs):
    nasm_executable = kwargs.get('nasm_executable')
    toolset_id = None
    config_parts = []
    conflicts = None
    models_per_arch = {}

    if 'mingw' in kwargs:
        mingw_parts = []
        mingw = kwargs['mingw']
        required = mingw.get('required', 0)
        mingw_package = mingw.get('package')
        mingw_prefix = mingw.get('prefix')
        if mingw_package:
            if not os.path.isdir(os.path.expanduser(mingw_package)):
                if not required:
                    print("BUILDSYS: makefile: '{}', line: {}\n  MinGW 'package' directory not found: '{}'".format(config_proto, pragma_line, mingw_package))
                    return None, None, None, None
                raise BuildSystemException("Can't process makefile: '{}', line: {}, MinGW 'package' directory not found: '{}'.".format(config_proto, pragma_line, mingw_package))
            mingw_parts += ["'package_path':'{}'".format(escape_string(mingw_package))]
        if mingw_prefix:
            mingw_parts += ["'prefix':'{}'".format(mingw_prefix)]
        mingw_arch = mingw.get('arch')
        if not mingw_arch:
            raise BuildSystemException("Can't process makefile: '{}', line: {}, MinGW 'arch' list is not given or empty.".format(config_proto, pragma_line))
        mingw_arch_list, winapi_levels = parse_arch_specific_tokens(mingw_arch, arch_supported=[TAG_ARCH_X86, TAG_ARCH_X86_64], allow_empty_tokens=True, supported_tokens=WINDOWS_API_LEVELS)
        if mingw_arch_list is None or (TAG_ARCH_X86 not in mingw_arch_list and TAG_ARCH_X86_64 not in mingw_arch_list):
            raise BuildSystemException("Can't process makefile: '{}', line: {}, token 'arch' is malformed: '{}'".format(config_proto, pragma_line, mingw_arch))
        win32_api_level = None
        win64_api_level = None
        if TAG_ARCH_X86 in winapi_levels:
            if winapi_levels[TAG_ARCH_X86]:
                win32_api_level = winapi_levels[TAG_ARCH_X86]
        if TAG_ARCH_X86_64 in winapi_levels:
            if winapi_levels[TAG_ARCH_X86_64]:
                win64_api_level = winapi_levels[TAG_ARCH_X86_64]
        if not win32_api_level:
            win32_api_level = WINDOWS_API_DEFAULT_LEVEL[TAG_ARCH_X86]
        if not win64_api_level:
            win64_api_level = WINDOWS_API_DEFAULT_LEVEL[TAG_ARCH_X86_64]

        if TAG_ARCH_X86 in mingw_arch_list and TAG_ARCH_X86_64 in mingw_arch_list:
            toolset_id = 'mingw-multiarch'
            mingw_parts += [ "'arch':['{}:{}','{}:{}']".format(TAG_ARCH_X86, win32_api_level, TAG_ARCH_X86_64, win64_api_level) ]
            conflicts = ['mingw-{}'.format(TAG_ARCH_X86), 'mingw-{}'.format(TAG_ARCH_X86_64)]
            models_per_arch[TAG_ARCH_X86] = GCC_MODEL_MINGW32
            models_per_arch[TAG_ARCH_X86_64] = GCC_MODEL_MINGW64

        elif TAG_ARCH_X86 in mingw_arch_list:
            toolset_id = 'mingw-{}'.format(TAG_ARCH_X86)
            mingw_parts += [ "'arch':['{}:{}']".format(TAG_ARCH_X86, win32_api_level) ]
            conflicts = ['mingw-multiarch']
            models_per_arch[TAG_ARCH_X86] = GCC_MODEL_MINGW32

        elif TAG_ARCH_X86_64 in mingw_arch_list:
            toolset_id = 'mingw-{}'.format(TAG_ARCH_X86_64)
            mingw_parts += [ "'arch':['{}:{}']".format(TAG_ARCH_X86_64, win64_api_level) ]
            conflicts = ['mingw-multiarch']
            models_per_arch[TAG_ARCH_X86_64] = GCC_MODEL_MINGW64

        config_parts += ["'mingw':{{{}}}".format(','.join(mingw_parts))]

    elif 'xtools' in kwargs:
        xtools_parts = []
        xtools = kwargs['xtools']
        required = xtools.get('required', 0)
        xtools_package = xtools.get('package')
        xtools_prefix = xtools.get('prefix')
        if not xtools_package:
            raise BuildSystemException("Can't process makefile: '{}', line: {}, crosstools 'package' directory is not given.".format(config_proto, pragma_line))
        if not os.path.isdir(os.path.expanduser(xtools_package)):
            if not required:
                print("BUILDSYS: makefile: '{}', line: {}\n  crosstools 'package' directory not found: '{}'".format(config_proto, pragma_line, xtools_package))
                return None, None, None, None
            raise BuildSystemException("Can't process makefile: '{}', line: {}, crosstools 'package' directory not found: '{}'.".format(config_proto, pragma_line, xtools_package))
        xtools_parts += ["'package_path':'{}'".format(escape_string(xtools_package))]
        if xtools_prefix:
            xtools_parts += ["'prefix':'{}'".format(xtools_prefix)]
        xtools_arch = xtools.get('arch')
        if not xtools_arch:
            raise BuildSystemException("Can't process makefile: '{}', line: {}, crosstools 'arch' list is not given or empty.".format(config_proto, pragma_line))
        xtools_arch_list, _ = parse_arch_specific_tokens(xtools_arch, arch_supported=TAG_ALL_KNOWN_ARCH_LIST, allow_empty_tokens=True)
        if not xtools_arch_list:
            raise BuildSystemException("Can't process makefile: '{}', line: {}, token 'arch' is malformed: '{}'".format(config_proto, pragma_line, xtools_arch))
        xtools_parts += ["'arch':['{}']".format("','".join(xtools_arch_list))]

        toolset_id = 'xtools-{}'.format('-'.join(sorted(xtools_arch_list)))
        config_parts += ["'x-tools':{{{}}}".format(','.join(xtools_parts))]

        for arch in xtools_arch_list:
            models_per_arch[arch] = CROSSTOOL_MODEL_NAMES[arch]

    else:
        toolset_id = '{}-native'.format(native_id)
        if sys_platform == TAG_PLATFORM_LINUX:
            if native_id == 'gcc':
                models_per_arch[sys_arch] = LINUX_GCC_MODEL_NAMES[sys_arch]
                if sys_arch == TAG_ARCH_X86_64:
                    models_per_arch[TAG_ARCH_X86] = LINUX_GCC_MODEL_NAMES[TAG_ARCH_X86]

        elif sys_platform == TAG_PLATFORM_MACOSX:
            if native_id == 'clang' and sys_arch == TAG_ARCH_X86_64:
                models_per_arch[TAG_ARCH_X86_64] = CLANG_MODEL_MACOSX_X86_64

    if nasm_executable:
        config_parts += ["'nasm_executable':'{0}'".format(escape_string(nasm_executable))]

    description_lines = [
        "[{}]".format(toolset_id),
        "{} = {}".format(TAG_INI_TOOLSET_MODULE, native_id),
    ]

    if config_parts:
        description_lines += [ "{} = {{{}}}".format(TAG_INI_TOOLSET_CONFIG, ','.join(config_parts)) ]

    return toolset_id, description_lines, conflicts, models_per_arch


def describe_toolset(config_proto, pragma_line, sys_platform, sys_arch, **kwargs):
    return _describe_toolset_imp('gcc', config_proto, pragma_line, sys_platform, sys_arch, **kwargs)


def _describe_clang_toolset(config_proto, pragma_line, sys_platform, sys_arch, **kwargs):
    return _describe_toolset_imp('clang', config_proto, pragma_line, sys_platform, sys_arch, **kwargs)


def _create_clang_toolset(sysinfo, loader, **kwargs):
    nasm_executable = kwargs.get('nasm_executable')
    clang_tools = ToolsInfoGCC(is_clang=True, nasm=nasm_executable)
    return ToolsetGCC('clang', clang_tools, sysinfo, loader)
