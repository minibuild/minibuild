import datetime
import decimal
import os.path
import sys

from .build_art import BuildArtifact
from .constants import *
from .error_utils import BuildSystemException
from .os_utils import load_py_object, normalize_path_optional

_MTIME_PRECISION = decimal.Decimal('0.001') # 0.001 second
_MTIME_FORMAT = '%Y-%m-%dT%H:%M:%S.%f'


def prerequisite_newer_then_target(mt_target, mt_pre, fname_target, fname_pre, verbose):
    mtd_target = decimal.Decimal(mt_target).quantize(_MTIME_PRECISION)
    mtd_pre = decimal.Decimal(mt_pre).quantize(_MTIME_PRECISION)
    newer = mtd_pre > mtd_target
    if verbose and newer:
        mtdf_pre = datetime.datetime.fromtimestamp(mtd_pre).strftime(_MTIME_FORMAT)
        mtdf_pre = mtdf_pre[:-3]
        mtdf_target = datetime.datetime.fromtimestamp(mtd_target).strftime(_MTIME_FORMAT)
        mtdf_target = mtdf_target[:-3]
        print("BUILDSYS: prerequisite is newer than target:\n    {}, i.e. {} - prerequisite: {}\n    {}, i.e. {} - target: {}".format(mtd_pre, mtdf_pre, fname_pre, mtd_target, mtdf_target, fname_target))
    return newer


def is_target_up_to_date(target_file_path, obj_files, required_depends, verbose):
    if not os.path.isfile(target_file_path):
        return False, None

    if obj_files:
        for obj_file_path in obj_files:
            if not os.path.isfile(obj_file_path):
                return False, (obj_file_path, None)

    target_mtime = os.path.getmtime(target_file_path)

    if required_depends:
        for dep in required_depends:
            if isinstance(dep, BuildArtifact):
                dep_path = dep.path
            else:
                dep_path = dep
            dep_mtime = os.path.getmtime(dep_path)
            if prerequisite_newer_then_target(target_mtime, dep_mtime, target_file_path, dep_path, verbose):
                return False, (dep_path, dep_mtime)

    if obj_files:
        for obj_file_path in obj_files:
            obj_mtime = os.path.getmtime(obj_file_path)
            if prerequisite_newer_then_target(target_mtime, obj_mtime, target_file_path, obj_file_path, verbose):
                return False, (obj_file_path, obj_mtime)

    return True, None


def is_target_with_deps_up_to_date(project_root, source_file_path, target_file_path, depends_file_path, extra_depends, verbose):
    if not os.path.isfile(source_file_path):
        return False
    if not os.path.isfile(target_file_path):
        return False
    if not os.path.isfile(depends_file_path):
        return False
    source_mtime = os.path.getmtime(source_file_path)
    target_mtime = os.path.getmtime(target_file_path)

    if prerequisite_newer_then_target(target_mtime, source_mtime, target_file_path, source_file_path, verbose):
        return False

    for ext_dep in extra_depends:
        ext_dep_mtime = os.path.getmtime(ext_dep)
        if prerequisite_newer_then_target(target_mtime, ext_dep_mtime, target_file_path, ext_dep, verbose):
            return False

    depends = load_py_object(depends_file_path)
    for dep_item in depends:
        dep_item_path = os.path.join(project_root, dep_item)
        if not os.path.isfile(dep_item_path):
            return False
        dep_item_mtime = os.path.getmtime(dep_item_path)
        if prerequisite_newer_then_target(target_mtime, dep_item_mtime, target_file_path, dep_item_path, verbose):
            return False
    return True


def eval_include_dirs_in_description(description, project_root, source_type):
    include_dirs = []
    if source_type == BUILD_TYPE_ASM:
        if description.asm_include_dir_list:
            for incdir in description.asm_include_dir_list:
                incd = normalize_path_optional(incdir, description.self_dirname)
                if not os.path.isdir(incd):
                    raise BuildSystemException("Include directory '{}' not found, required in '{}'".format(incd, description.self_file_parts[0]))
                include_dirs.append(incd)
    else:
        if description.include_dir_list:
            for incdir in description.include_dir_list:
                incd = normalize_path_optional(incdir, description.self_dirname)
                if not os.path.isdir(incd):
                    raise BuildSystemException("Include directory '{}' not found, required in '{}'".format(incd, description.self_file_parts[0]))
                include_dirs.append(incd)
    return include_dirs


def eval_explicit_depends_in_description(loader, description, model, xpl_depends):
    for depref in description.explicit_depends:
        depdir = normalize_path_optional(depref, description.self_dirname)
        depdesc = loader.load_build_description(depdir, model, required_by=description.self_file_parts[0])
        xpl_depends.append(depdesc)


def eval_libs_in_description(loader, description, model, static_libs, shared_libs):
    if not description.lib_list:
        return
    for libref in description.lib_list:
        libdir = normalize_path_optional(libref, description.self_dirname)
        libdesc = loader.load_build_description(libdir, model, required_by=description.self_file_parts[0])
        if libdesc.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_LIB_STATIC:
            static_libs.append(libdesc)
        elif libdesc.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_LIB_SHARED:
            shared_libs.append(libdesc)
        else:
            raise BuildSystemException("Not a description of a shared/static library: '{}'".format(description.self_file_parts[0]))


def eval_libnames_in_description(loader, description, model, libstatic_names, libshared_names):
    static_libs = []
    shared_libs = []
    eval_libs_in_description(loader, description, model, static_libs, shared_libs)
    for desc in static_libs:
        libstatic_names.append(desc.module_name)
    for desc in shared_libs:
        libshared_names.append(desc.module_name)


def eval_prebuilt_lib_list_in_description(description, current_model):
    platform_alias = current_model.platform_alias
    all_attr = [TAG_GRAMMAR_KEY_PREBULT_LIB_LIST]
    all_attr += ['_'.join([TAG_GRAMMAR_KEY_PREBULT_LIB_LIST, current_model.platform_name])]
    if platform_alias is not None:
        all_attr += ['_'.join([TAG_GRAMMAR_KEY_PREBULT_LIB_LIST, platform_alias])]
    full_prebuilt_lib_list = []
    for attr_name in all_attr:
        prebuilt_lib_list = getattr(description, attr_name)
        full_prebuilt_lib_list += prebuilt_lib_list
    return full_prebuilt_lib_list


def eval_definitions_list_in_description(description, current_model, source_type):
    tag = TAG_GRAMMAR_KEY_ASM_DEFINITIONS_LIST if source_type == BUILD_TYPE_ASM else TAG_GRAMMAR_KEY_DEFINITIONS_LIST
    platform_alias = current_model.platform_alias
    all_attr = [tag]
    all_attr += ['_'.join([tag, current_model.platform_name])]
    all_attr += ['_'.join([tag, current_model.platform_name, current_model.architecture_abi_name])]
    if platform_alias is not None:
        all_attr += ['_'.join([tag, platform_alias])]
        all_attr += ['_'.join([tag, platform_alias, current_model.architecture_abi_name])]
    full_definitions_list = []
    for attr_name in all_attr:
        definitions_list = getattr(description, attr_name)
        full_definitions_list += definitions_list
    return full_definitions_list


def verify_exports_def_file(description):
    if description.export_def_file is None:
        return None
    exports_fname = normalize_path_optional(description.export_def_file, description.self_dirname)
    if not os.path.isfile(exports_fname):
        raise BuildSystemException("Exports definition file '{}' not found, required in '{}'".format(exports_fname, description.self_file_parts[0]))
    return exports_fname


def verify_winrc_file(description):
    if description.winrc_file is None:
        return None
    winrc_fname = normalize_path_optional(description.winrc_file, description.self_dirname)
    if not os.path.isfile(winrc_fname):
        raise BuildSystemException("RC file '{}' not found, required in '{}'".format(winrc_fname, description.self_file_parts[0]))
    return winrc_fname


def parse_gnu_makefile_depends(common_prefix, src_path, dep_path, obj_path):
    depends = []
    common_prefix_len = len(common_prefix)
    norm_src_path = os.path.normcase(src_path)
    with open(dep_path, mode='rt') as gcc_depinfo:
        target_catched = False
        end = False
        for raw_line in gcc_depinfo.readlines():
            ln = raw_line.strip('\r\n').strip()
            if not ln:
                raise BuildSystemException("Can't parse - {}".format(dep_path))
            if not target_catched:
                if ':' not in ln:
                    raise BuildSystemException("Can't parse - {}".format(dep_path))
                if sys.platform == 'win32':
                    bits = ln.split(':', 3)
                    if len(bits) < 3:
                        raise BuildSystemException("Can't parse - {}".format(dep_path))
                    target = ':'.join((bits[0], bits[1])).strip()
                    tail = bits[2].strip()
                else:
                    bits = ln.split(':', 2)
                    target = bits[0].strip()
                    tail = bits[1].strip()
                if target != obj_path:
                    raise BuildSystemException("Can't parse - {}\n    '{}' != '{}'".format(dep_path, target, obj_path))
                target_catched = True
            else:
                tail = ln
            end = True
            if tail.endswith('\\'):
                end = False
                tail = tail[0:len(tail)-1]
            for dep_item in tail.split():
                dep_item_abs = dep_item
                if not os.path.isabs(dep_item):
                    dep_item_abs = os.path.normpath(os.path.join(os.path.dirname(norm_src_path), dep_item))
                norm_dep = os.path.normcase(dep_item_abs)
                if norm_dep.startswith(common_prefix):
                    if norm_dep != norm_src_path:
                        dep_to_use = norm_dep[common_prefix_len:]
                        depends.append(dep_to_use)
            if end:
                break
    return depends
