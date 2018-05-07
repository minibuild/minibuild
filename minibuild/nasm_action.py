from __future__ import print_function
import os.path
import subprocess

from .constants import *
from .depends_check import *
from .error_utils import BuildSystemException
from .string_utils import escape_string


NASM_OUTPUT_FORMATS = {
    TAG_PLATFORM_WINDOWS: {TAG_ARCH_X86: 'win32', TAG_ARCH_X86_64: 'win64'},
    TAG_PLATFORM_LINUX: {TAG_ARCH_X86: 'elf32', TAG_ARCH_X86_64: 'elf64'},
}

class NasmSourceBuildAction:
    def __init__(self, nasm_executable, sysinfo, description, asm_file_path, obj_directory, obj_name, build_model, build_config):
        self.nasm = nasm_executable
        self.asm_path = asm_file_path
        self.obj_path = os.path.join(obj_directory, ''.join([obj_name, sysinfo[TAG_CFG_OBJ_SUFFIX]]))
        self.dep_path = os.path.join(obj_directory, ''.join([obj_name, sysinfo[TAG_CFG_DEP_SUFFIX]]))
        self.deptmp_path = self.dep_path + 'tmp'
        self.project_root = sysinfo[TAG_CFG_DIR_PROJECT_ROOT]
        self.common_prefix = sysinfo[TAG_CFG_PROJECT_ROOT_COMMON_PREFIX]
        self.include_dirs = eval_include_dirs_in_description(description, self.project_root, BUILD_TYPE_ASM)
        self.definitions = eval_definitions_list_in_description(description, build_model, BUILD_TYPE_ASM)
        self.extra_deps = []
        self.extra_deps.extend(description.self_file_parts)
        self.arch = build_model.architecture_abi_name
        self.platform_name = build_model.platform_name
        self.build_config = build_config

    def __call__(self, force, verbose):
        target_is_ready = False
        if not force:
            target_is_ready = is_target_with_deps_up_to_date(
                self.project_root, self.asm_path, self.obj_path, self.dep_path, self.extra_deps, verbose)
        if target_is_ready:
            if verbose:
                print("BUILDSYS: up-to-date: {}".format(self.asm_path))
            return False

        if verbose:
            print("BUILDSYS: ASM: {}".format(self.asm_path))

        out_format = NASM_OUTPUT_FORMATS.get(self.platform_name, {}).get(self.arch)
        if not out_format:
            raise BuildSystemException("NASM: Got unsupported platform '{}' or arch '{}'.".format(self.platform_name, self.arch))

        argv = [self.nasm, '-f', out_format]

        if self.build_config == BUILD_CONFIG_DEBUG:
            argv += ['-g']
            if self.platform_name == TAG_PLATFORM_LINUX:
                argv += ['-F', 'dwarf']

        for incd in self.include_dirs:
            argv += [ '-I{}{}'.format(incd, os.sep) ]

        for _def in self.definitions:
            argv += [ '-D{}'.format(_def) ]

        argv += ['-o', self.obj_path, '-MD', self.deptmp_path, self.asm_path]

        if verbose:
            print("BUILDSYS: EXEC: {}".format(' '.join(argv)))

        print(os.path.basename(self.asm_path))
        p = subprocess.Popen(argv)
        p.communicate()
        if p.returncode != 0:
            raise BuildSystemException(self.asm_path, exit_code=p.returncode)
        depends = parse_gnu_makefile_depends(self.common_prefix, self.asm_path, self.deptmp_path, self.obj_path)
        with open(self.dep_path, mode='wt') as dep_content:
            dep_content.writelines(['[\n'])
            for dep_item in depends:
                dep_content.writelines(['    "', escape_string(dep_item), '",\n'])
            dep_content.writelines([']\n'])
        os.remove(self.deptmp_path)
        return True
