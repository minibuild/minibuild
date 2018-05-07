from __future__ import print_function
import argparse
import importlib
import os
import os.path
import platform
import sys

from .build_description import BuildDescriptionLoader
from .build_workflow import BuildWorkflow
from .config_ini import *
from .constants import *
from .error_utils import BuildSystemException
from .os_utils import *


SUPPORTED_PLATFORMS_PROBE = [
    (is_linux_x86_64,       TAG_PLATFORM_LINUX,         TAG_ARCH_X86_64),
    (is_linux_x86,          TAG_PLATFORM_LINUX,         TAG_ARCH_X86),
    (is_linux_arm64,        TAG_PLATFORM_LINUX,         TAG_ARCH_ARM64),
    (is_linux_arm,          TAG_PLATFORM_LINUX,         TAG_ARCH_ARM),
    (is_macosx_x86_64,      TAG_PLATFORM_MACOSX,        TAG_ARCH_X86_64),
    (is_windows_64bit,      TAG_PLATFORM_WINDOWS,       TAG_ARCH_X86_64),
    (is_windows_32bit,      TAG_PLATFORM_WINDOWS,       TAG_ARCH_X86),
]

def resolve_project_landmark(build_directory):
    root_variant = None
    lookup_sequence = []
    while True:
        if root_variant is None:
            root_variant = build_directory
        else:
            last_root_variant = root_variant
            root_variant = os.path.normpath(os.path.join(last_root_variant, os.pardir))
            if last_root_variant == root_variant:
                raise BuildSystemException("Can't resolve project root while trying the following lookup sequence:\n  {}"
                    .format('\n  '.join(lookup_sequence)))
        config_variant = os.path.normpath(os.path.join(root_variant, BUILD_SYSTEM_CONFIG_FILE))
        lookup_sequence.append(config_variant)
        if os.path.isfile(config_variant):
            return root_variant


def auto_eval_native_model(used_model_name, toolset_models_mapping, required, verbose):
    native_model_remap = None
    used_toolset, _ = toolset_models_mapping[used_model_name]
    used_model = used_toolset.supported_models[used_model_name]
    if used_model.is_native():
        if verbose:
            print("BUILDSYS: Current model '{}' resolved as native".format(used_model_name))
        native_model_remap = used_model_name
    elif is_windows_64bit():
        if used_model.platform_name == TAG_PLATFORM_WINDOWS and used_model.architecture_abi_name == TAG_ARCH_X86:
            if verbose:
                print("BUILDSYS: Current model '{}' resolved as native due to Windows specific.".format(used_model_name))
            native_model_remap = used_model_name

    if native_model_remap is None:
        for model_name in used_toolset.supported_models:
            if used_toolset.supported_models[model_name].is_native():
                native_model_remap = model_name
                if verbose:
                    print("BUILDSYS: Model '{}' resolved as native, taken directly from used toolset '{}'.".format(used_model_name, used_toolset.toolset_name))
                break

    if native_model_remap is None:
        native_models_all = []
        native_models_from_same_toolset = []
        if native_model_remap is None:
            for model_name in toolset_models_mapping:
                toolset, _ = toolset_models_mapping[model_name]
                model = toolset.supported_models[model_name]
                if model.is_native():
                    native_models_all.append(model_name)
                    if toolset.toolset_name == used_toolset.toolset_name:
                        native_models_from_same_toolset.append(model_name)

        native_models_variants = native_models_from_same_toolset if native_models_from_same_toolset else native_models_all

        if not native_models_variants:
            if required:
                raise BuildSystemException("Cannot detect any build model to be treated as native for this platform.")
        elif len(native_models_variants) > 1:
            msg = ','.join(native_models_variants)
            if required:
                raise BuildSystemException("Malformed project config file: got clash of native models, possible variants: '{}'.".format(msg))
            if verbose:
                print("BUILDSYS: Disable native model support due to clash of possible variants: '{}'.".format(msg))
        else:
            native_model_remap = native_models_variants[0]
            if verbose:
                print("BUILDSYS: Model '{}' resolved as native.".format(native_model_remap))

    return native_model_remap


def eval_native_model_from_config(used_model_name, toolset_models_mapping, config, sys_platform, sys_arch, verbose):
    platform_ini_tag = '{}-{}'.format(sys_platform, sys_arch)
    native_model_remap = get_ini_conf_string0(config, TAG_INI_CONF_MAIN_NATIVE, platform_ini_tag)
    if not native_model_remap:
        raise BuildSystemException("Malformed project config file: option not found at '{}/{}'.".format(TAG_INI_CONF_MAIN_NATIVE, platform_ini_tag))
    if not native_model_remap or native_model_remap in [TAG_NATIVE_MODELS_DETECTION_DISABLED, TAG_NATIVE_MODELS_DETECTION_OPTIONAL, TAG_NATIVE_MODELS_DETECTION_AUTO]:
        if native_model_remap == TAG_NATIVE_MODELS_DETECTION_DISABLED:
            if verbose:
                print("BUILDSYS: Got project configuration with disabled native model support.")
            return None
        required = True if native_model_remap == TAG_NATIVE_MODELS_DETECTION_AUTO else False
        return auto_eval_native_model(used_model_name, toolset_models_mapping, required, verbose)
    if native_model_remap not in toolset_models_mapping:
        raise BuildSystemException(
            "Malformed project config file: got unknown model '{}' at '{}/{}'."
                .format(native_model_remap, TAG_INI_CONF_MAIN_NATIVE, platform_ini_tag))
    if verbose:
        print("BUILDSYS: Model '{}' configured as native.".format(native_model_remap))
    return native_model_remap


def eval_native_model(used_model_name, toolset_models_mapping, config, sys_platform, sys_arch, verbose):
    eval_mode = get_ini_conf_string0(config, TAG_INI_CONF_MAIN, TAG_INI_NATIVE_MODELS_DETECTION_MODE)
    if eval_mode:
        if eval_mode not in TAG_NATIVE_MODELS_DETECTION_ALL_MODES:
            raise BuildSystemException(
                "Malformed project config file: got unknown value '{}' at '{}/{}', possible variants: '{}'."
                    .format(eval_mode, TAG_INI_CONF_MAIN, TAG_INI_NATIVE_MODELS_DETECTION_MODE, ','.join(TAG_NATIVE_MODELS_DETECTION_ALL_MODES)))
    else:
        eval_mode = TAG_NATIVE_MODELS_DETECTION_OPTIONAL

    if eval_mode == TAG_NATIVE_MODELS_DETECTION_DISABLED:
        if verbose:
            print("BUILDSYS: Got project configuration with disabled native model support.")
        native_model_remap = None

    elif eval_mode == TAG_NATIVE_MODELS_DETECTION_CONFIG:
        native_model_remap = eval_native_model_from_config(used_model_name, toolset_models_mapping, config, sys_platform, sys_arch, verbose)

    else:
        native_model_required = True if eval_mode in [TAG_NATIVE_MODELS_DETECTION_AUTO, TAG_NATIVE_MODELS_DETECTION_CONFIG] else False
        native_model_remap = auto_eval_native_model(used_model_name, toolset_models_mapping, native_model_required, verbose)

    if native_model_remap is None and verbose:
        if eval_mode != TAG_NATIVE_MODELS_DETECTION_DISABLED:
            print("BUILDSYS: Got project configuration without native model support.")
    return native_model_remap


def create_build_workflow(build_directory, argv):
    project_root = resolve_project_landmark(build_directory)
    config_file = os.path.normpath(os.path.join(project_root, BUILD_SYSTEM_CONFIG_FILE))
    if not os.path.isfile(config_file):
        raise BuildSystemException("Project config file is not found by path: '{}'.".format(config_file))

    current_platform = platform.system()
    if not current_platform:
        current_platform = sys.platform

    for os_probe, sys_platform, sys_arch in SUPPORTED_PLATFORMS_PROBE:
        if os_probe():
            break
    else:
        raise BuildSystemException("Current platform '{}' is not supported.".format(current_platform))

    config = load_ini_config(path=config_file)

    platform_cfg_option = 'toolset-{}'.format(sys_platform)
    toolset_sections_names = get_ini_conf_strings_optional(config, TAG_INI_CONF_MAIN, platform_cfg_option)
    if not toolset_sections_names:
        raise BuildSystemException("Malformed project config file: got empty value at '{}/{}'.".format(TAG_INI_CONF_MAIN, platform_cfg_option))

    toolset_init_requests = []
    for toolset_section in toolset_sections_names:
        toolset_module_title = get_ini_conf_string0(config, toolset_section, TAG_INI_TOOLSET_MODULE)
        if toolset_module_title is None:
            raise BuildSystemException("Malformed project config file: option not found at '{}/{}'.".format(toolset_section, TAG_INI_TOOLSET_MODULE))
        if not toolset_module_title:
            raise BuildSystemException("Malformed project config file: got empty value at '{}/{}'.".format(toolset_section, TAG_INI_TOOLSET_MODULE))
        toolset_serialized_config = get_ini_conf_string0(config, toolset_section, TAG_INI_TOOLSET_CONFIG)
        if toolset_serialized_config:
            ast = compile(toolset_serialized_config, '<toolset-config>', 'eval')
            toolset_init_args = eval(ast, {"__builtins__": None}, {})
        else:
            toolset_init_args = {}
        toolset_init_requests += [ (toolset_module_title, toolset_init_args) ]

    bootstrap_dir = os.path.normpath(os.path.join(project_root, BUILD_CONFIG_DEFAULT_BOOTSTRAP_DIR))
    obj_dir = os.path.normpath(os.path.join(project_root, BUILD_CONFIG_DEFAULT_OBJ_DIR))
    exe_dir = os.path.normpath(os.path.join(project_root, BUILD_CONFIG_DEFAULT_EXE_DIR))
    ext_dir = os.path.normpath(os.path.join(project_root, BUILD_CONFIG_DEFAULT_EXT_DIR))
    static_lib_dir = os.path.normpath(os.path.join(project_root, BUILD_CONFIG_DEFAULT_LIB_DIR))
    shared_lib_dir = os.path.normpath(os.path.join(project_root, BUILD_CONFIG_DEFAULT_SHARED_DIR))
    public_dir = os.path.normpath(os.path.join(project_root, BUILD_CONFIG_DEFAULT_PUBLIC_DIR))

    build_description_fname = os.path.join(os.getcwd(), BUILD_MODULE_DESCRIPTION_FILE)

    mkdir_safe(bootstrap_dir)
    mkdir_safe(obj_dir)
    mkdir_safe(exe_dir)
    mkdir_safe(static_lib_dir)
    mkdir_safe(shared_lib_dir)

    sysinfo = {
        TAG_CFG_DIR_PROJECT_ROOT: project_root,
        TAG_CFG_PROJECT_ROOT_COMMON_PREFIX: ''.join([os.path.normcase(project_root), os.path.sep]),
        TAG_CFG_DIR_BOOTSTRAP: bootstrap_dir,
        TAG_CFG_DIR_OBJ: obj_dir,
        TAG_CFG_DIR_EXE: exe_dir,
        TAG_CFG_DIR_EXT: ext_dir,
        TAG_CFG_DIR_LIB: static_lib_dir,
        TAG_CFG_DIR_SHARED: shared_lib_dir,
        TAG_CFG_DIR_PUBLIC: public_dir,
        TAG_CFG_OBJ_SUFFIX : '.obj',
        TAG_CFG_PDB_SUFFIX : '.pdb',
        TAG_CFG_DEP_SUFFIX : '.dep',
    }

    subst_info = {
        TAG_SUBST_PROJECT_ROOT: project_root,
    }

    toolset_models_mapping = {}
    toolset_choices = []
    imported_toolset_modules = {}
    for toolset_module_title, toolset_init_args in toolset_init_requests:
        mod_toolset = imported_toolset_modules.get(toolset_module_title)
        if mod_toolset is None:
            toolset_module_name = '{}.toolset_{}'.format(__package__, toolset_module_title)
            mod_toolset = importlib.import_module(toolset_module_name)
            imported_toolset_modules[toolset_module_title] = mod_toolset

        desc_loader = BuildDescriptionLoader()
        toolset = mod_toolset.create_toolset(sysinfo, desc_loader, **toolset_init_args)
        desc_loader.set_toolset_name(toolset.toolset_name)
        desc_loader.set_target_platform(toolset.platform_name)
        desc_loader.set_substitutions(subst_info)

        toolset_models = toolset.supported_models
        for model_name in toolset_models:
            if model_name in toolset_models_mapping:
                raise BuildSystemException("Malformed project config file: got clash of model names for '{}'.".format(model_name))
            model = toolset_models[model_name]
            toolset_models_mapping[model_name] = (toolset, desc_loader)
            toolset_choices.append(model_name)

    parser = argparse.ArgumentParser()
    parser.add_argument('--model', nargs=1, choices=toolset_choices, required=True)
    parser.add_argument('--config', nargs=1, choices=BUILD_CONFIG_ALL, required=True)
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--public', action='store_true')
    args = parser.parse_args(argv)

    native_model_remap = eval_native_model(args.model[0], toolset_models_mapping, config, sys_platform, sys_arch, args.verbose)

    logic = BuildWorkflow(sysinfo=sysinfo, toolset_models_mapping=toolset_models_mapping, native_model_remap=native_model_remap,
        grammar_substitutions=subst_info)

    for model_name in toolset_models_mapping:
        _, desc_loader = toolset_models_mapping[model_name]
        desc_loader.set_import_hook(lambda x, y: logic.import_extension(desc_loader, x, y))

    build_args = {}
    build_args['build_directory'] = build_directory
    build_args['used_model_name'] = args.model[0]
    build_args['build_config'] = args.config[0]
    build_args['public'] = args.public
    build_args['force_rebuild'] = args.force
    build_args['verbose'] = args.verbose

    return logic, build_args


def preload_argv():
    argv = []
    arg_dir = None
    next_arg_is_dir = False
    for arg in sys.argv[1:]:
        if arg_dir is None:
            if next_arg_is_dir:
                arg_dir = arg
                continue
            if arg == '--directory':
                next_arg_is_dir = True
                continue
        argv.append(arg)
    if arg_dir is not None:
        build_directory = os.path.abspath(os.path.normpath(arg_dir))
        if not os.path.isdir(build_directory):
            raise BuildSystemException("Invalid build directoty '{}' is given in command line, directory '{}' is not found.".format(arg_dir, build_directory))
    else:
        build_directory = os.getcwd()
    return build_directory, argv



def script_main():
    try:
        build_directory, argv = preload_argv()
        logic, args = create_build_workflow(build_directory, argv)
        logic.run(**args)

    except BuildSystemException as exc:
        print("BUILDSYS: ERROR: {}".format(exc))
        return exc.to_exit_code()
