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
from .parse_deffile import load_export_list_from_def_file
from .string_utils import escape_string, argv_to_rsp
from .toolset_base import ToolsetBase, ToolsetModel, ToolsetActionBase, ToolsetActionResult
from .osxapi_level import *
from .ssp_stub import SSP_STUB_SOURCE
from .winapi_level import *
from .winrc_manifest import WINRC_MANIFEST


GCC_MODEL_LINUX_X86 = 'gcc-linux-x86'
GCC_MODEL_LINUX_X86_64 = 'gcc-linux-x86_64'
GCC_MODEL_LINUX_ARM = 'gcc-linux-arm'
GCC_MODEL_LINUX_ARM64 = 'gcc-linux-arm64'

CLANG_MODEL_MACOSX_X86_64 = 'clang-macosx-x86_64'
CLANG_CROSSTOOL_MODEL_MACOSX_X86_64 = 'clang-xt-macosx-x86_64'
CLANG_CROSSTOOL_CUSTOM_MODEL_FORMAT_MACOSX_X86_64 = 'clang-{}-macosx-x86_64'

GCC_CROSSTOOL_MODEL_LINUX_X86 = 'gcc-xt-linux-x86'
GCC_CROSSTOOL_MODEL_LINUX_X86_64 = 'gcc-xt-linux-x86_64'
GCC_CROSSTOOL_MODEL_LINUX_ARM = 'gcc-xt-linux-arm'
GCC_CROSSTOOL_MODEL_LINUX_ARM64 = 'gcc-xt-linux-arm64'

GCC_CROSSTOOL_CUSTOM_MODEL_FORMAT_LINUX_X86 = 'gcc-{}-linux-x86'
GCC_CROSSTOOL_CUSTOM_MODEL_FORMAT_LINUX_X86_64 = 'gcc-{}-linux-x86_64'
GCC_CROSSTOOL_CUSTOM_MODEL_FORMAT_LINUX_ARM = 'gcc-{}-linux-arm'
GCC_CROSSTOOL_CUSTOM_MODEL_FORMAT_LINUX_ARM64 = 'gcc-{}-linux-arm64'

GCC_MODEL_MINGW32 = 'mingw-win32'
GCC_MODEL_MINGW64 = 'mingw-win64'
GCC_CUSTOM_MODEL_FORMAT_MINGW32 = '{}-win32'
GCC_CUSTOM_MODEL_FORMAT_MINGW64 = '{}-win64'

CROSSTOOL_MODEL_NAMES = {
    TAG_ARCH_X86: GCC_CROSSTOOL_MODEL_LINUX_X86,
    TAG_ARCH_X86_64: GCC_CROSSTOOL_MODEL_LINUX_X86_64,
    TAG_ARCH_ARM: GCC_CROSSTOOL_MODEL_LINUX_ARM,
    TAG_ARCH_ARM64: GCC_CROSSTOOL_MODEL_LINUX_ARM64,
}

CROSSTOOL_CUSTOM_MODELS_FORMAT = {
    TAG_ARCH_X86: GCC_CROSSTOOL_CUSTOM_MODEL_FORMAT_LINUX_X86,
    TAG_ARCH_X86_64: GCC_CROSSTOOL_CUSTOM_MODEL_FORMAT_LINUX_X86_64,
    TAG_ARCH_ARM: GCC_CROSSTOOL_CUSTOM_MODEL_FORMAT_LINUX_ARM,
    TAG_ARCH_ARM64: GCC_CROSSTOOL_CUSTOM_MODEL_FORMAT_LINUX_ARM64,
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

        argv = [self.tools.gpp, '-Werror-implicit-function-declaration', '-ffunction-sections', '-fdata-sections', '-fno-omit-frame-pointer' ]

        argv += self.arch_flags
        if self.tools.sysroot:
            argv += ['-isysroot', self.tools.sysroot]

        if self.source_type == BUILD_TYPE_CPP:
            argv += ['-x', 'c++', '-std=c++11']
        elif self.source_type == BUILD_TYPE_C:
            argv += ['-x', 'c']
        elif self.source_type == BUILD_TYPE_ASM:
            argv += ['-x', 'assembler-with-cpp']
        else:
            raise BuildSystemException("Unsupported build type is given for file: '{}'".format(self.source_path))

        if not self.tools.is_mingw:
            argv += ['-fpic']
            if self.tools.is_clang:
                argv += ['-fstack-protector']
            else:
                argv += ['-fstack-protector-strong']
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

        if not self.tools.is_clang and not self.tools.is_mingw:
            argv += [ '-D_GNU_SOURCE' ]

        argv += [ '-c', '-o', self.obj_path, self.source_path ]

        ctx.subprocess_communicate(output, argv, issuer=self.source_path, title=os.path.basename(self.source_path), env=self.tools.env)

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
        self.obj_directory = obj_directory
        self.rsp_fname = self.module_name + '.rsplnk'
        self.outlib_path = os.path.join(lib_directory, 'lib' + self.module_name + '.a')
        self.obj_fnames = []
        self.primary_deps = []

        for obj_name in obj_names:
            obj_fname = obj_name + sysinfo[TAG_CFG_OBJ_SUFFIX]
            self.obj_fnames.append(obj_fname)
            self.primary_deps.append(os.path.join(obj_directory, obj_fname))

        self.extra_deps = description.self_file_parts[:]

    def execute(self, output, ctx):
        build_result = [BuildArtifact(BUILD_RET_TYPE_LIB, self.outlib_path, BUILD_RET_ATTR_DEFAULT)]
        target_is_ready = False
        if not ctx.force:
            target_is_ready, _ = is_target_up_to_date(self.outlib_path, self.primary_deps, self.extra_deps, ctx.verbose)
        if target_is_ready:
            output.report_message("BUILDSYS: up-to-date: '{}', lib: {}".format(self.module_name, self.outlib_path))
            return ToolsetActionResult(rebuilt=False, artifacts=build_result)

        output.report_message("BUILDSYS: create LIB module '{}' ...".format(self.module_name))

        with open(os.path.join(self.obj_directory, self.rsp_fname), mode='wt') as rsp_fh:
            for rsp_entry in self.obj_fnames:
                rsp_fh.writelines([rsp_entry, '\n'])
        if self.tools.is_clang and not self.tools.is_crosstool:
            argv = [self.tools.ar, '-static', '-filelist', self.rsp_fname, '-o', self.outlib_path]
        else:
            argv = [self.tools.ar, 'rcs', self.outlib_path, '@' + self.rsp_fname ]
        ctx.subprocess_communicate(output, argv, issuer=self.outlib_path, env=self.tools.env, cwd=self.obj_directory)
        return ToolsetActionResult(rebuilt=True, artifacts=build_result)


class LinkActionGCC(ToolsetActionBase):
    def __init__(self, tools, sysinfo, loader, description, exe_directory, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config):
        self.tools = tools
        self.sharedlib_directory = sharedlib_directory
        self.is_dll = True if exe_directory is None else False
        self.obj_directory = obj_directory
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
        self.ssp_stub_fname_src = 'ssp_stub.c'
        self.ssp_stub_fname_obj = 'ssp_stub' + sysinfo[TAG_CFG_OBJ_SUFFIX]

        self.with_default_ssp = False
        if not self.tools.is_mingw and not self.tools.is_clang:
            if description.with_default_ssp:
                self.with_default_ssp = True

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
            self.windres_arch_flags = []
            if build_model.architecture_abi_name == TAG_ARCH_X86_64:
                self.windres_arch_flags += [ '--target', 'pe-x86-64']
            elif build_model.architecture_abi_name == TAG_ARCH_X86:
                self.windres_arch_flags += [ '--target', 'pe-i386']

        self.rsp_file = os.path.join(self.link_private_dir, self.module_name_private + '.rsplnk')
        self.obj_fnames = []
        self.arch_compile_flags = []
        self.arch_compile_flags += build_model.get_arch_compile_flags()
        self.arch_link_flags = []
        self.arch_link_flags += build_model.get_arch_link_flags(description)
        self.build_config = build_config

        for obj_name in obj_names:
            obj_fname = obj_name + sysinfo[TAG_CFG_OBJ_SUFFIX]
            self.obj_fnames.append(obj_fname)
            self.primary_deps.append(os.path.join(obj_directory, obj_fname))
        if self.with_default_ssp:
            ssp_stub_fpath_obj = os.path.join(self.link_private_dir, self.ssp_stub_fname_obj)
            self.primary_deps.append(ssp_stub_fpath_obj)
            self.obj_fnames.append(ssp_stub_fpath_obj)

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
        touch_file(link_stamp_file_tmp)

        if self.tools.is_mingw:
            if self.winrc_file is not None:
                argv = [self.tools.windres]
                argv += self.windres_arch_flags
                argv += [self.winrc_file, self.res_file]
                for incd in self.include_dirs:
                    argv += [ '-I{}'.format(incd) ]
                for defrc in self.winrc_definitions:
                    argv += [ '-D{}'.format(defrc) ]
                ctx.subprocess_communicate(output, argv, issuer=self.winrc_file, title=os.path.basename(self.winrc_file), env=self.tools.env)

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
                argv = [self.tools.windres]
                argv += self.windres_arch_flags
                argv += [manifest_rc, self.manifest_res_file]
                ctx.subprocess_communicate(output, argv, issuer=manifest_rc, title=os.path.basename(manifest_rc), env=self.tools.env)

        if self.with_default_ssp:
            with open(os.path.join(self.link_private_dir, self.ssp_stub_fname_src), mode='wt') as fh_ssp:
                fh_ssp.writelines([SSP_STUB_SOURCE])
            argv = [ self.tools.gpp ]
            argv += self.arch_link_flags
            if self.tools.sysroot:
                argv += ['-isysroot', self.tools.sysroot]
            argv += ['-x', 'c', '-fpic', '-fvisibility=hidden', '-Wall', '-O3', '-c', '-o', self.ssp_stub_fname_obj, self.ssp_stub_fname_src]
            ctx.subprocess_communicate(output, argv, issuer=self.ssp_stub_fname_src, title=self.ssp_stub_fname_src, env=self.tools.env, cwd=self.link_private_dir)

        argv = [ self.tools.gpp ]
        argv += self.arch_link_flags

        if self.tools.is_mingw:
            argv += ['-Wl,--enable-stdcall-fixup']

        if self.is_dll:
            argv += ['-shared']
            if not self.tools.is_clang:
                argv += ['-Wl,--no-undefined' ]

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

            if self.export_map_file is not None:
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

            with open(os.path.join(self.link_private_dir, 'symbols.json'), 'wt') as fh:
                print("[", file=fh)
                exp_idx = 0
                for export_entry in sorted(actual_export_list):
                    exp_idx += 1
                    exp_tail = ',' if exp_idx < len(actual_export_list) else ''
                    print('    "{}"{}'.format(export_entry, exp_tail), file=fh)
                print("]", file=fh)

        else:
            if self.tools.is_mingw:
                if self.use_wmain:
                    argv += ['-municode']
                if self.win_stack_size:
                    argv += ['-Wl,--stack,{}'.format(self.win_stack_size)]
            else:
                if not self.tools.is_clang:
                    argv += ['-pie']

        if self.tools.is_clang:
            argv += ['-Wl,-dead_strip', '-Wl,-dead_strip_dylibs', '-Wl,-no_dead_strip_inits_and_terms' ]
        else:
            argv += ['-Wl,--gc-sections']
            if self.tools.is_mingw:
                argv += ['-Wl,-strip-all']

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

        argv += self.obj_fnames

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
        ctx.subprocess_communicate(output, argv, issuer=self.bin_path_private, env=self.tools.env, cwd=self.obj_directory)

        if self.macosx_install_name_options:
            install_name_tool = 'install_name_tool'
            if self.tools.bin_prefix:
                install_name_tool = self.tools.bin_prefix + install_name_tool
            if sys.platform == 'win32':
                install_name_tool = install_name_tool + '.exe'
            if self.tools.dir_prefix:
                install_name_tool = os.path.join(self.tools.dir_prefix, install_name_tool)
            argv = [install_name_tool]
            argv += self.macosx_install_name_options
            argv += [ self.bin_path_private ]
            ctx.subprocess_communicate(output, argv, issuer=self.bin_path_private, env=self.tools.env)

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
    def __init__(self, name, tools, sysinfo, loader, toolset_custom_models):
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

                mingw_x86_model_name = GCC_MODEL_MINGW32 if toolset_custom_models is None else toolset_custom_models[TAG_ARCH_X86]

                model_win32 = GccModel(
                    model_name=mingw_x86_model_name, toolset_version=toolset_version, is_native=is_windows_32bit(),
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

                mingw_x86_64_model_name = GCC_MODEL_MINGW64 if toolset_custom_models is None else toolset_custom_models[TAG_ARCH_X86_64]

                model_win64 = GccModel(
                    model_name=mingw_x86_64_model_name, toolset_version=toolset_version, is_native=is_windows_64bit(),
                    target_os=TAG_PLATFORM_WINDOWS, target_os_alias=None, arch_name=TAG_ARCH_X86_64,
                    arch_flags=mingw_x86_64_compile_flags, arch_link_flags=mingw_x86_64_link_flags, os_version=os_version_x86_64)

                models.append(model_win64)

        elif self._tools.is_crosstool:
            if self._tools.crosstool_target_platform == TAG_PLATFORM_LINUX:
                self._platform_name = TAG_PLATFORM_LINUX

                for x_arch in self._tools.arch_list:
                    x_model_name = CROSSTOOL_MODEL_NAMES[x_arch] if toolset_custom_models is None else toolset_custom_models[x_arch]
                    x_is_native = CROSSTOOL_NATIVE_STATUS[x_arch]

                    x_model = GccModel(
                        model_name=x_model_name, toolset_version=toolset_version, is_native=x_is_native,
                        target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=x_arch,
                        arch_flags=[], arch_link_flags=[], crosstool=True)

                    models.append(x_model)

            elif self._tools.crosstool_target_platform == TAG_PLATFORM_MACOSX and self._tools.is_clang and self._tools.arch_list == [TAG_ARCH_X86_64]:
                self._platform_name = TAG_PLATFORM_MACOSX

                x_model_name = CLANG_CROSSTOOL_MODEL_MACOSX_X86_64 if toolset_custom_models is None else toolset_custom_models[TAG_ARCH_X86_64]
                x_is_native = is_macosx_x86_64()
                sdk_path = self._tools.sysroot
                osxapi_level_x86_64 = self._tools.api_levels[TAG_ARCH_X86_64]
                if not osxapi_level_x86_64:
                    osxapi_level_x86_64 = MACOSX_API_DEFAULT_LEVEL[TAG_ARCH_X86_64]

                x_arch_flags = [
                    '-target', 'x86_64-apple-darwin',
                    '-mmacosx-version-min=' + osxapi_level_x86_64,
                ]

                x_arch_link_flags = [
                    '-target', 'x86_64-apple-darwin',
                    '-mmacosx-version-min=' + osxapi_level_x86_64,
                    '-Wl,-syslibroot,' + sdk_path,
                    '-L' + os.path.normpath(os.path.join(sdk_path, 'usr/lib/system')),
                    '-F' + os.path.normpath(os.path.join(sdk_path, 'System/Library/Frameworks')),
                ]

                x_model = GccModel(
                    model_name=x_model_name, toolset_version=toolset_version, is_native=x_is_native,
                    target_os=TAG_PLATFORM_MACOSX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_X86_64,
                    arch_flags=x_arch_flags, arch_link_flags=x_arch_link_flags, crosstool=True)

                models.append(x_model)

        else:
            if is_linux_x86_64():
                self._platform_name = TAG_PLATFORM_LINUX
                model_name_native_x86 = GCC_MODEL_LINUX_X86 if toolset_custom_models is None else toolset_custom_models[TAG_ARCH_X86]
                model_name_native_x86_64 = GCC_MODEL_LINUX_X86_64 if toolset_custom_models is None else toolset_custom_models[TAG_ARCH_X86_64]

                model_linux_x86 = GccModel(
                    model_name=model_name_native_x86, toolset_version=toolset_version, is_native=False,
                    target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_X86,
                    arch_flags=['-m32'], arch_link_flags=['-m32'])

                model_linux_x86_64 = GccModel(
                    model_name=model_name_native_x86_64, toolset_version=toolset_version, is_native=True,
                    target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_X86_64,
                    arch_flags=[], arch_link_flags=[])

                models.extend([model_linux_x86, model_linux_x86_64])

            elif is_linux_x86():
                self._platform_name = TAG_PLATFORM_LINUX
                model_name_native = GCC_MODEL_LINUX_X86 if toolset_custom_models is None else toolset_custom_models[TAG_ARCH_X86]

                model_linux_x86 = GccModel(
                    model_name=model_name_native, toolset_version=toolset_version, is_native=True,
                    target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_X86,
                    arch_flags=[], arch_link_flags=[])

                models.append(model_linux_x86)

            elif is_linux_arm():
                self._platform_name = TAG_PLATFORM_LINUX
                model_name_native = GCC_MODEL_LINUX_ARM if toolset_custom_models is None else toolset_custom_models[TAG_ARCH_ARM]

                model_linux_arm = GccModel(
                    model_name=model_name_native, toolset_version=toolset_version, is_native=True,
                    target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_ARM,
                    arch_flags=[], arch_link_flags=[])

                models.append(model_linux_arm)

            elif is_linux_arm64():
                self._platform_name = TAG_PLATFORM_LINUX
                model_name_native = GCC_MODEL_LINUX_ARM64 if toolset_custom_models is None else toolset_custom_models[TAG_ARCH_ARM64]

                model_linux_arm = GccModel(
                    model_name=model_name_native, toolset_version=toolset_version, is_native=True,
                    target_os=TAG_PLATFORM_LINUX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_ARM64,
                    arch_flags=[], arch_link_flags=[])

                models.append(model_linux_arm)

            elif is_macosx_x86_64():
                if self._name == 'clang':
                    self._platform_name = TAG_PLATFORM_MACOSX
                    model_name_native = CLANG_MODEL_MACOSX_X86_64 if toolset_custom_models is None else toolset_custom_models[TAG_ARCH_X86_64]

                    osxapi_level_x86_64 = self._tools.api_levels[TAG_ARCH_X86_64]
                    osx_arch_flags = []
                    osx_arch_link_flags = []
                    if osxapi_level_x86_64:
                        osx_arch_flags += [
                            '-mmacosx-version-min=' + osxapi_level_x86_64,
                        ]
                        osx_arch_link_flags += [
                            '-mmacosx-version-min=' + osxapi_level_x86_64,
                        ]

                    model_macosx_x86_64 = GccModel(
                        model_name=model_name_native, toolset_version=toolset_version, is_native=True,
                        target_os=TAG_PLATFORM_MACOSX, target_os_alias=TAG_PLATFORM_ALIAS_POSIX, arch_name=TAG_ARCH_X86_64,
                        arch_flags=osx_arch_flags, arch_link_flags=osx_arch_link_flags)

                    models.append(model_macosx_x86_64)

            if self._platform_name is None:
                platform = sys.platform
                if platform.startswith('linux'):
                    platform = 'linux'
                if hasattr(os, 'uname'):
                    platform = platform + ',' + os.uname()[4]
                raise BuildSystemException("Unsupported platform: '{}'".format(platform))

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
    def __init__(self, dir_prefix=None, sysroot=None, bin_prefix=None, is_mingw=None, is_clang=None, is_crosstool=None, arch_list=None, nasm=None, api_levels=None, toolset_version=None, crosstool_target_platform=None, env=None):
        tool_gcc = 'clang' if is_clang else 'gcc'
        tool_gpp = 'clang' if is_clang else 'g++'
        tool_ar  = 'libtool' if is_clang and not is_crosstool else 'ar'
        tool_windres = 'windres' if is_mingw else None

        if is_crosstool:
            if crosstool_target_platform not in [TAG_PLATFORM_LINUX, TAG_PLATFORM_MACOSX]:
                raise BuildSystemException("Got unsupported target platform '{}' for cross build.".format(crosstool_target_platform))

        if sys.platform == 'win32':
            tool_gcc = tool_gcc + '.exe'
            tool_gpp = tool_gpp + '.exe'
            tool_ar  = tool_ar  + '.exe'
            if tool_windres is not None:
                tool_windres = tool_windres + '.exe'

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

        self.bin_prefix = bin_prefix
        self.dir_prefix = dir_prefix
        self.env = env
        self.is_mingw = is_mingw
        self.is_clang = is_clang
        self.is_crosstool = is_crosstool
        self.crosstool_target_platform = crosstool_target_platform
        self.sysroot = sysroot
        self.arch_list = arch_list
        self.api_levels = api_levels

        self.gcc = tool_gcc
        self.gpp = tool_gpp
        self.ar  = tool_ar
        self.windres = tool_windres
        self.nasm_executable = nasm if nasm else 'nasm'
        self.nasm_enabled = False
        self.toolset_version = toolset_version

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
        p = None
        errmsg = None
        try:
            p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        except Exception as ex:
            errmsg = str(ex)
        if p is None:
            errmsg = 'Subprocess communication failed\n  ' + ' '.join(argv) + '\n    ' + errmsg
            raise BuildSystemException(errmsg)
        if self.toolset_version:
            return self.toolset_version
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


def init_cross_tools(crosstools_title, sysinfo, toolset_name, target_platform, xtools_cfg, nasm, arch_list_enabled, api_levels_enabled, api_levels_default=None):
    package_path = xtools_cfg.get('package_path')
    sysroot_path = xtools_cfg.get('sysroot')
    toolset_version = xtools_cfg.get('version')

    if package_path is None:
        raise BuildSystemException("Malformed {} config: 'package_path' is not given in project config file.".format(crosstools_title))
    package_path = os.path.normpath(os.path.expanduser(package_path))
    if not os.path.isabs(package_path):
        package_path = os.path.join(sysinfo[TAG_CFG_DIR_PROJECT_ROOT], package_path)
    if not os.path.isdir(package_path):
        raise BuildSystemException("Malformed {} config: 'package_path' resolved as '{}' is not a directory.".format(crosstools_title, package_path))
    package_path_bin = os.path.join(package_path, 'bin')
    if not os.path.isdir(package_path_bin):
        raise BuildSystemException("Malformed {} config: '{}' is not a directory.".format(crosstools_title, package_path_bin))

    if sysroot_path:
        sysroot_path = os.path.normpath(os.path.expanduser(sysroot_path))
        if not os.path.isdir(sysroot_path):
            raise BuildSystemException("Malformed {} config: '{}' is not a directory.".format(crosstools_title, sysroot_path))

    cross_arch_list = xtools_cfg.get('arch')
    if not isinstance(cross_arch_list, list) or not cross_arch_list:
        raise BuildSystemException("Malformed {} config: 'arch' list is not given or empty in project config file.".format(crosstools_title))

    arch_parsed = []
    api_levels = {}
    for arch in cross_arch_list:
        api_level = None
        if ':' in arch:
            arch_value, api_level = arch.split(':', 1)
            api_level = api_level.strip()
        else:
            arch_value = arch
            api_level = None
        if arch_value not in arch_list_enabled:
            raise BuildSystemException("Malformed {} config: unknown arch value '{}' is given. Only the following values are supported: {}.".format(crosstools_title, arch_value, ', '.join(arch_list_enabled)))
        if api_levels_enabled is not None:
            if not api_level:
                api_level = api_levels_default[arch_value]
            elif api_level not in api_levels_enabled:
                raise BuildSystemException("Malformed {} config: unknown API level '{}' is given. Only the following values are supported: {}.".format(crosstools_title, api_level, ', '.join(api_levels_enabled)))
        else:
            if not api_level:
                api_level = None
        arch_parsed.append(arch_value)
        api_levels[arch_value] = api_level

    bin_prefix = xtools_cfg.get('prefix')
    is_clang = True if toolset_name == 'clang' else False
    if target_platform == TAG_PLATFORM_WINDOWS:
        is_crosstool = False
        is_mingw = True
    else:
        is_crosstool = True
        is_mingw = False

    custom_env = None
    if is_clang:
        custom_env = {}
        custom_env.update(os.environ)
        custom_env['COMPILER_PATH'] = package_path_bin

    tools = ToolsInfoGCC(dir_prefix=package_path_bin, sysroot=sysroot_path, bin_prefix=bin_prefix, is_crosstool=is_crosstool, is_mingw=is_mingw, crosstool_target_platform=target_platform,
                        is_clang=is_clang, arch_list=arch_parsed, api_levels=api_levels, toolset_version=toolset_version, nasm=nasm, env=custom_env)
    return tools


def _create_clang_toolset(sysinfo, loader, sys_platform, sys_arch, toolset_custom_models, **kwargs):
    nasm_executable = kwargs.get('nasm_executable')
    if 'macosx-xtools' in kwargs:
        xtools_cfg = kwargs['macosx-xtools']
        cross_tools = init_cross_tools('MacOSX cross-tools', sysinfo, 'clang', TAG_PLATFORM_MACOSX, xtools_cfg, nasm_executable,
                                     arch_list_enabled=[TAG_ARCH_X86_64], api_levels_enabled=None)
        return ToolsetGCC('clang', cross_tools, sysinfo, loader, toolset_custom_models)

    arch_list = kwargs.get('arch')
    api_levels = {}
    if arch_list:
        for arch in arch_list:
            api_level = None
            if ':' in arch:
                arch_value, api_level = arch.split(':', 1)
                api_level = api_level.strip()
            else:
                arch_value = arch
            if arch_value not in TAG_ALL_KNOWN_ARCH_LIST:
                raise BuildSystemException("Malformed clang config: unknown arch value '{}' is given. Only the following values are supported: {}.".format(arch_value, ', '.join(TAG_ALL_KNOWN_ARCH_LIST)))
            if api_level:
                api_levels[arch_value] = api_level
    api_level_sys = {sys_arch: api_levels.get(sys_arch)}
    clang_tools = ToolsInfoGCC(is_clang=True, nasm=nasm_executable, api_levels=api_level_sys)
    return ToolsetGCC('clang', clang_tools, sysinfo, loader, toolset_custom_models)


def create_toolset(sysinfo, loader, sys_platform, sys_arch, toolset_custom_models, **kwargs):
    nasm_executable = kwargs.get('nasm_executable')
    if 'mingw' in kwargs:
        mingw = kwargs['mingw']
        mingw_tools = init_cross_tools('MinGW', sysinfo, 'gcc', TAG_PLATFORM_WINDOWS, mingw, nasm_executable,
                                     arch_list_enabled=TAG_ALL_KNOWN_MINGW_ARCH_LIST, api_levels_enabled=WINDOWS_API_LEVELS, api_levels_default=WINDOWS_API_DEFAULT_LEVEL)

        return ToolsetGCC('gcc', mingw_tools, sysinfo, loader, toolset_custom_models)

    if 'xtools' in kwargs:
        xtools_cfg = kwargs['xtools']
        cross_tools = init_cross_tools('cross-tools', sysinfo, 'gcc', TAG_PLATFORM_LINUX, xtools_cfg, nasm_executable,
                                     arch_list_enabled=TAG_ALL_KNOWN_ARCH_LIST, api_levels_enabled=None)
        return ToolsetGCC('gcc', cross_tools, sysinfo, loader, toolset_custom_models)

    gcc_tools = ToolsInfoGCC(nasm=nasm_executable)
    return ToolsetGCC('gcc', gcc_tools, sysinfo, loader, toolset_custom_models)


def _describe_toolset_imp(native_id, config_proto, pragma_line, sys_platform, sys_arch, toolset_label, **kwargs):
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
            if toolset_label:
                models_per_arch[TAG_ARCH_X86] = GCC_CUSTOM_MODEL_FORMAT_MINGW32.format(toolset_label)
                models_per_arch[TAG_ARCH_X86_64] = GCC_CUSTOM_MODEL_FORMAT_MINGW64.format(toolset_label)
            else:
                conflicts = ['mingw-{}'.format(TAG_ARCH_X86), 'mingw-{}'.format(TAG_ARCH_X86_64)]
                models_per_arch[TAG_ARCH_X86] = GCC_MODEL_MINGW32
                models_per_arch[TAG_ARCH_X86_64] = GCC_MODEL_MINGW64

        elif TAG_ARCH_X86 in mingw_arch_list:
            toolset_id = 'mingw-{}'.format(TAG_ARCH_X86)
            mingw_parts += [ "'arch':['{}:{}']".format(TAG_ARCH_X86, win32_api_level) ]
            if toolset_label:
                models_per_arch[TAG_ARCH_X86] = GCC_CUSTOM_MODEL_FORMAT_MINGW32.format(toolset_label)
            else:
                conflicts = ['mingw-multiarch']
                models_per_arch[TAG_ARCH_X86] = GCC_MODEL_MINGW32

        elif TAG_ARCH_X86_64 in mingw_arch_list:
            toolset_id = 'mingw-{}'.format(TAG_ARCH_X86_64)
            mingw_parts += [ "'arch':['{}:{}']".format(TAG_ARCH_X86_64, win64_api_level) ]
            if toolset_label:
                models_per_arch[TAG_ARCH_X86_64] = GCC_CUSTOM_MODEL_FORMAT_MINGW64.format(toolset_label)
            else:
                conflicts = ['mingw-multiarch']
                models_per_arch[TAG_ARCH_X86_64] = GCC_MODEL_MINGW64

        config_parts += ["'mingw':{{{}}}".format(','.join(mingw_parts))]

    elif 'xtools' in kwargs:
        xtools_parts = []
        xtools = kwargs['xtools']
        required = xtools.get('required', 0)
        xtools_package = xtools.get('package')
        xtools_prefix = xtools.get('prefix')
        xtools_version = xtools.get('version')
        xtools_sysroot = xtools.get('sysroot')
        if not xtools_package:
            raise BuildSystemException("Can't process makefile: '{}', line: {}, crosstools 'package' directory is not given.".format(config_proto, pragma_line))
        if not os.path.isdir(os.path.expanduser(xtools_package)):
            if not required:
                print("BUILDSYS: makefile: '{}', line: {}\n  crosstools 'package' directory not found: '{}'".format(config_proto, pragma_line, xtools_package))
                return None, None, None, None
            raise BuildSystemException("Can't process makefile: '{}', line: {}, crosstools 'package' directory not found: '{}'.".format(config_proto, pragma_line, xtools_package))
        if xtools_sysroot is not None:
            if not os.path.isdir(os.path.expanduser(xtools_sysroot)):
                raise BuildSystemException("Can't process makefile: '{}', line: {}, crosstools 'sysroot' directory not found: '{}'.".format(config_proto, pragma_line, xtools_sysroot))
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
        if xtools_sysroot:
            xtools_parts += ["'sysroot':'{}'".format(escape_string(xtools_sysroot))]
        if xtools_version:
            xtools_parts += ["'version':'{}'".format(xtools_version)]

        toolset_id = 'xtools-{}'.format('-'.join(sorted(xtools_arch_list)))
        config_parts += ["'xtools':{{{}}}".format(','.join(xtools_parts))]

        for arch in xtools_arch_list:
            if toolset_label:
                mod_fmt = CROSSTOOL_CUSTOM_MODELS_FORMAT[arch]
                models_per_arch[arch] = mod_fmt.format(toolset_label)
            else:
                models_per_arch[arch] = CROSSTOOL_MODEL_NAMES[arch]

    elif 'macosx-xtools' in kwargs:
        xtools_parts = []
        xtools = kwargs['macosx-xtools']
        required = xtools.get('required', 0)
        xtools_package = xtools.get('package')
        xtools_prefix = xtools.get('prefix')
        xtools_version = xtools.get('version')
        xtools_sysroot = xtools.get('sysroot')
        xtools_arch = xtools.get('arch')

        if not xtools_package:
            raise BuildSystemException("Can't process makefile: '{}', line: {}, crosstools 'package' directory is not given.".format(config_proto, pragma_line))
        if not os.path.isdir(os.path.expanduser(xtools_package)):
            if not required:
                print("BUILDSYS: makefile: '{}', line: {}\n  crosstools 'package' directory not found: '{}'".format(config_proto, pragma_line, xtools_package))
                return None, None, None, None
            raise BuildSystemException("Can't process makefile: '{}', line: {}, crosstools 'package' directory not found: '{}'.".format(config_proto, pragma_line, xtools_package))

        if xtools_sysroot is not None:
            if not os.path.isdir(os.path.expanduser(xtools_sysroot)):
                raise BuildSystemException("Can't process makefile: '{}', line: {}, crosstools 'sysroot' directory not found: '{}'.".format(config_proto, pragma_line, xtools_sysroot))
        else:
            raise BuildSystemException("Can't process makefile: '{}', line: {}, crosstools 'sysroot' directory is not given.".format(config_proto, pragma_line))

        xtools_arch_list = []
        if xtools_arch:
            xtools_arch_list, xtools_api_levels = parse_arch_specific_tokens(xtools_arch, arch_supported=[TAG_ARCH_X86_64], allow_empty_tokens=True)
            if not xtools_arch_list:
                raise BuildSystemException("Can't process makefile: '{}', line: {}, token 'arch' is malformed: '{}'".format(config_proto, pragma_line, xtools_arch))
            if xtools_api_levels[TAG_ARCH_X86_64]:
                xtools_arch_list = [ '{}:{}'.format(TAG_ARCH_X86_64, xtools_api_levels[TAG_ARCH_X86_64]) ]
        if not xtools_arch_list:
            xtools_arch_list = [ TAG_ARCH_X86_64 ]

        xtools_parts += ["'package_path':'{}'".format(escape_string(xtools_package))]
        if xtools_prefix:
            xtools_parts += ["'prefix':'{}'".format(xtools_prefix)]
        xtools_parts += ["'arch':['{}']".format(xtools_arch_list[0])]
        if xtools_sysroot:
            xtools_parts += ["'sysroot':'{}'".format(escape_string(xtools_sysroot))]
        if xtools_version:
            xtools_parts += ["'version':'{}'".format(xtools_version)]

        toolset_id = 'macosx-xtools'
        config_parts += ["'macosx-xtools':{{{}}}".format(','.join(xtools_parts))]
        if toolset_label:
            models_per_arch[TAG_ARCH_X86_64] = CLANG_CROSSTOOL_CUSTOM_MODEL_FORMAT_MACOSX_X86_64.format(toolset_label)
        else:
            models_per_arch[TAG_ARCH_X86_64] = CLANG_CROSSTOOL_MODEL_MACOSX_X86_64

    else:
        if toolset_label:
            toolset_id = native_id
        else:
            toolset_id = '{}-native'.format(native_id)

        if sys_platform == TAG_PLATFORM_LINUX:
            if native_id == 'gcc':
                models_per_arch[sys_arch] = LINUX_GCC_MODEL_NAMES[sys_arch]
                if sys_arch == TAG_ARCH_X86_64:
                    models_per_arch[TAG_ARCH_X86] = LINUX_GCC_MODEL_NAMES[TAG_ARCH_X86]

        elif sys_platform == TAG_PLATFORM_MACOSX:
            if native_id == 'clang' and sys_arch == TAG_ARCH_X86_64:
                if toolset_label:
                    models_per_arch[TAG_ARCH_X86_64] = CLANG_CROSSTOOL_CUSTOM_MODEL_FORMAT_MACOSX_X86_64.format(toolset_label)
                else:
                    models_per_arch[TAG_ARCH_X86_64] = CLANG_MODEL_MACOSX_X86_64
                osx_arch = kwargs.get('arch')
                if osx_arch:
                    osx_arch_list, osx_api_levels = parse_arch_specific_tokens(osx_arch, arch_supported=[TAG_ARCH_X86_64], allow_empty_tokens=True)
                    if not osx_arch_list:
                        raise BuildSystemException("Can't process makefile: '{}', line: {}, token 'arch' is malformed: '{}'".format(config_proto, pragma_line, osx_arch))
                    if osx_api_levels[TAG_ARCH_X86_64]:
                        osx_arch_list = [ '{}:{}'.format(TAG_ARCH_X86_64, osx_api_levels[TAG_ARCH_X86_64]) ]
                        config_parts += ["'arch':['{}']".format(osx_arch_list[0])]

    if nasm_executable:
        config_parts += ["'nasm_executable':'{0}'".format(escape_string(nasm_executable))]

    if toolset_label:
        toolset_id = '{}/{}'.format(toolset_id, toolset_label)

    description_lines = [
        "[{}]".format(toolset_id),
        "{} = {}".format(TAG_INI_TOOLSET_MODULE, native_id),
    ]

    if toolset_label:
        custom_models_parts = []
        for arch in sorted(models_per_arch):
            custom_models_parts.append("'{}':'{}'".format(arch, models_per_arch[arch]))
        description_lines += [
            "{} = {{{}}}".format(TAG_INI_TOOLSET_MODELS, ','.join(custom_models_parts)),
        ]

    if config_parts:
        description_lines += [ "{} = {{{}}}".format(TAG_INI_TOOLSET_CONFIG, ','.join(config_parts)) ]

    return toolset_id, description_lines, conflicts, models_per_arch


def describe_toolset(config_proto, pragma_line, sys_platform, sys_arch, toolset_label, **kwargs):
    return _describe_toolset_imp('gcc', config_proto, pragma_line, sys_platform, sys_arch, toolset_label, **kwargs)


def _describe_clang_toolset(config_proto, pragma_line, sys_platform, sys_arch, toolset_label, **kwargs):
    return _describe_toolset_imp('clang', config_proto, pragma_line, sys_platform, sys_arch, toolset_label, **kwargs)
