from __future__ import print_function
import argparse
import importlib
import multiprocessing
import os
import os.path
import platform
import shlex
import subprocess
import sys

from .build_description import BuildDescriptionLoader
from .build_workflow import BuildWorkflow
from .config_ini import *
from .constants import *
from .error_utils import BuildSystemException, BuildSystemSysExit, buildsys_error_to_string
from .faccess_emerge import perform_faccess_emerge
from .gen_bconf import generate_build_config
from .os_utils import *
from .pragma_tokens import load_buildconf_pragmas, makefile_is_project_landmark
from .__version__ import __version__


SUPPORTED_PLATFORMS_PROBE = [
    (is_linux_x86_64,       TAG_PLATFORM_LINUX,         TAG_ARCH_X86_64),
    (is_linux_x86,          TAG_PLATFORM_LINUX,         TAG_ARCH_X86),
    (is_linux_arm64,        TAG_PLATFORM_LINUX,         TAG_ARCH_ARM64),
    (is_linux_arm,          TAG_PLATFORM_LINUX,         TAG_ARCH_ARM),
    (is_macosx_x86_64,      TAG_PLATFORM_MACOSX,        TAG_ARCH_X86_64),
    (is_windows_64bit,      TAG_PLATFORM_WINDOWS,       TAG_ARCH_X86_64),
    (is_windows_32bit,      TAG_PLATFORM_WINDOWS,       TAG_ARCH_X86),
]


def parse_landmark_details(value, config_proto, pragma_line):
    landmark_options = {}
    args = []
    if value:
        args = shlex.split(value)
    for arg in args:
        if '=' not in arg:
            raise BuildSystemException("Can't load makefile: '{}', instruction #pragma at line: {}, malformed token: '{}'.".format(config_proto, pragma_line, arg))
        k, v = arg.split('=', 1)
        landmark_options[k] = v
    return landmark_options


def resolve_project_landmark(build_directory, verbose):
    dname = None
    dir_sequence = []
    while True:
        if dname is None:
            dname = build_directory
            dir_sequence.append(dname)
        else:
            last_root_variant = dname
            dname = os.path.normpath(os.path.join(last_root_variant, os.pardir))
            if dname == last_root_variant:
                break
            dir_sequence.append(dname)

    lookup_sequence1 = []
    for dname in dir_sequence:
        config_variant = os.path.normpath(os.path.join(dname, BUILD_SYSTEM_CONFIG_FILE))
        lookup_sequence1.append(config_variant)
        if os.path.isfile(config_variant):
            return dname, None, None

    any_makefile = False
    lookup_sequence2 = []
    for dname in reversed(dir_sequence):
        config_variant = os.path.normpath(os.path.join(dname, BUILD_MODULE_DESCRIPTION_FILE))
        if os.path.isfile(config_variant):
            any_makefile = True
            lookup_sequence2.append(config_variant)
            is_landmark, landmark_details, pragma_line = makefile_is_project_landmark(config_variant)
            if is_landmark:
                landmark_options = parse_landmark_details(landmark_details, config_variant, pragma_line)
                if verbose:
                    if landmark_options:
                        print("BUILDSYS: Landmark: '{}', configuration: {}".format(config_variant, landmark_details))
                    else:
                        print("BUILDSYS: Landmark: '{}', configuration: <default>".format(config_variant))
                project_root = dname
                if TAG_PRAGMA_BUILD_PROJECT_ROOT in landmark_options and landmark_options[TAG_PRAGMA_BUILD_PROJECT_ROOT]:
                    project_root = normalize_path_optional(landmark_options[TAG_PRAGMA_BUILD_PROJECT_ROOT], dname)
                    if verbose:
                        print("BUILDSYS: Landmark: redirect project-root from '{}' to '{}' due to option '{}'".format(dname, project_root, landmark_options[TAG_PRAGMA_BUILD_PROJECT_ROOT]))

                return project_root, config_variant, landmark_options

    if not any_makefile:
        raise BuildSystemException("Not a MiniBuild project (or any of the parent directories)")

    if lookup_sequence1 and lookup_sequence2:
        raise BuildSystemException("Can't resolve project root while trying the following lookup sequences:\n1)  {}\n----\n2)  {}".format('\n    '.join(lookup_sequence1), '\n    '.join(lookup_sequence2)))

    raise BuildSystemException("Can't resolve project root while trying the following lookup sequence:\n  {}".format('\n  '.join(lookup_sequence1)))


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

        if len(native_models_variants) > 1:
            native_models_cross = []
            for model_name in native_models_variants:
                toolset, _ = toolset_models_mapping[model_name]
                model = toolset.supported_models[model_name]
                if model.is_crosstool():
                    native_models_cross.append(model_name)
            if len(native_models_cross) == 1:
                native_models_variants = native_models_cross

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


def eval_native_model_from_config(used_model_name, toolset_models_mapping, model_aliases, config, sys_platform, sys_arch, verbose):
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
    if native_model_remap in model_aliases:
        native_model_remap = model_aliases[native_model_remap]
    if native_model_remap not in toolset_models_mapping:
        raise BuildSystemException(
            "Malformed project config file: got unknown model '{}' at '{}/{}'."
                .format(native_model_remap, TAG_INI_CONF_MAIN_NATIVE, platform_ini_tag))
    if verbose:
        print("BUILDSYS: Model '{}' configured as native.".format(native_model_remap))
    return native_model_remap


def eval_native_model(used_model_name, toolset_models_mapping, model_aliases, config, sys_platform, sys_arch, verbose):
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
        native_model_remap = eval_native_model_from_config(used_model_name, toolset_models_mapping, model_aliases, config, sys_platform, sys_arch, verbose)

    else:
        native_model_required = True if eval_mode in [TAG_NATIVE_MODELS_DETECTION_AUTO, TAG_NATIVE_MODELS_DETECTION_CONFIG] else False
        native_model_remap = auto_eval_native_model(used_model_name, toolset_models_mapping, native_model_required, verbose)

    if native_model_remap is None and verbose:
        if eval_mode != TAG_NATIVE_MODELS_DETECTION_DISABLED:
            print("BUILDSYS: Got project configuration without native model support.")
    return native_model_remap


def read_model_aliases(config):
    model_aliases = {}
    if config.has_section(TAG_INI_CONF_MAIN_ALIAS):
        aliases = config.options(TAG_INI_CONF_MAIN_ALIAS)
        for alias in aliases:
            model_name = get_ini_conf_string1(config, TAG_INI_CONF_MAIN_ALIAS, alias)
            model_aliases[alias] = model_name
    return model_aliases


def eval_default_model(config, sys_platform, sys_arch):
    return get_ini_conf_string0(config, TAG_INI_CONF_MAIN_DEFAULT, '{}-{}'.format(sys_platform, sys_arch))


class ArgumentParserExit(Exception):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def __init__(*args, **kwargs):
        argparse.ArgumentParser.__init__(*args, **kwargs)

    def exit(self, status=0, message=None):
        if status == 0:
            if message:
                self._print_message(message, sys.stdout)
            raise ArgumentParserExit()
        else:
            msg = message.rstrip('\r\n')
            strip = ['minibuild:', 'error:']
            while True:
                retry = False
                for s in strip:
                    if msg.startswith(s):
                        msg = msg[len(s):].strip()
                        retry = True
                        break
                if not retry:
                    break
            raise BuildSystemException(msg, exit_code=status)


class ArgumentParserFormat(argparse.HelpFormatter):
    def _split_lines(self, text, width):
        if text.startswith('R|'):
            return text[2:].splitlines()
        return argparse.HelpFormatter._split_lines(self, text, width)


def format_version_string(frozen):
    ext_bits = []
    if frozen:
        ext_bits.append('frozen')
    ext_bits.append('on python {}.{}.{}'.format(sys.version_info[0], sys.version_info[1], sys.version_info[2]))
    return "minibuild {} [{}]".format(__version__, ' '.join(ext_bits))


class PassThroughCommand:
    def __init__(self, fname, lineno, argv, pass_with_interpreter):
        self.fname = fname
        self.lineno = lineno
        self.argv = argv
        self.pass_with_interpreter = pass_with_interpreter


class PassThroughCommandList:
    def __init__(self):
        self.items = []

    def append(self, item):
        self.items.append(item)


def guess_parallelism():
    processors_count = multiprocessing.cpu_count()
    if processors_count in [0, 1]:
        return 2
    elif processors_count == 2:
        return 3
    return processors_count + 2


def create_build_workflow(frozen, build_directory, verbose, argv):
    buildsys_error = None
    sysinfo = None
    toolset_choices = []
    model_aliases = {}
    try:
        current_platform = platform.system()
        if not current_platform:
            current_platform = sys.platform

        for os_probe, sys_platform, sys_arch in SUPPORTED_PLATFORMS_PROBE:
            if os_probe():
                break
        else:
            raise BuildSystemException("Current platform '{}' is not supported.".format(current_platform))

        is_wsl = False
        if sys_platform == TAG_PLATFORM_LINUX:
            if os.access('/proc/version', os.R_OK):
                with open('/proc/version', 'rt') as fp:
                    proc_version = fp.read()
                if 'Microsoft' in proc_version:
                    is_wsl = True

        project_root, conf_mk, conf_options = resolve_project_landmark(build_directory, verbose)

        if verbose:
            if is_wsl:
                print("BUILDSYS: Landmark: project-root: '{}', on WSL/{} {}".format(project_root, sys_platform, sys_arch))
            else:
                print("BUILDSYS: Landmark: project-root: '{}', on {} {}".format(project_root, sys_platform, sys_arch))

        pragma_token_output_dir = TAG_PRAGMA_BUILD_DIR_OUTPUT
        if is_wsl:
            if conf_options and TAG_PRAGMA_BUILD_DIR_OUTPUT_WSL in conf_options and conf_options[TAG_PRAGMA_BUILD_DIR_OUTPUT_WSL]:
                pragma_token_output_dir = TAG_PRAGMA_BUILD_DIR_OUTPUT_WSL

        if conf_options and pragma_token_output_dir in conf_options and conf_options[pragma_token_output_dir]:
            custom_output_dname = conf_options[pragma_token_output_dir]
            if custom_output_dname.startswith('@'):
                custom_output_dname = custom_output_dname.replace('@', project_root, 1)

            output_dname = normalize_path_optional(custom_output_dname, os.path.dirname(conf_mk))
        else:
            output_dname = os.path.join(project_root, BUILD_CONFIG_DEFAULT_OUTPUT_DIR)

        if verbose:
            print("BUILDSYS: Landmark: output directory: '{}'".format(output_dname))

        bootstrap_dir  = os.path.normpath(os.path.join(output_dname, BUILD_CONFIG_DEFAULT_BOOTSTRAP_DIR))
        obj_dir        = os.path.normpath(os.path.join(output_dname, BUILD_CONFIG_DEFAULT_OBJ_DIR))
        exe_dir        = os.path.normpath(os.path.join(output_dname, BUILD_CONFIG_DEFAULT_EXE_DIR))
        ext_dir        = os.path.normpath(os.path.join(output_dname, BUILD_CONFIG_DEFAULT_EXT_DIR))
        static_lib_dir = os.path.normpath(os.path.join(output_dname, BUILD_CONFIG_DEFAULT_LIB_DIR))
        shared_lib_dir = os.path.normpath(os.path.join(output_dname, BUILD_CONFIG_DEFAULT_SHARED_DIR))
        public_dir     = os.path.normpath(os.path.join(output_dname, BUILD_CONFIG_DEFAULT_PUBLIC_DIR))
        faccess_dir    = os.path.normpath(os.path.join(output_dname, BUILD_CONFIG_DEFAULT_FACCESS_DIR))

        sysinfo = {
            TAG_CFG_FROZEN: frozen,
            TAG_CFG_DIR_PROJECT_ROOT: project_root,
            TAG_CFG_DIR_PROJECT_OUTPUT: output_dname,
            TAG_CFG_PROJECT_ROOT_COMMON_PREFIX: os.path.normcase(project_root) + os.path.sep,
            TAG_CFG_PROJECT_OUTPUT_COMMON_PREFIX : os.path.normcase(output_dname) + os.path.sep,
            TAG_CFG_DIR_BOOTSTRAP: bootstrap_dir,
            TAG_CFG_DIR_OBJ: obj_dir,
            TAG_CFG_DIR_EXE: exe_dir,
            TAG_CFG_DIR_EXT: ext_dir,
            TAG_CFG_DIR_LIB: static_lib_dir,
            TAG_CFG_DIR_SHARED: shared_lib_dir,
            TAG_CFG_DIR_PUBLIC: public_dir,
            TAG_CFG_DIR_FACCESS: faccess_dir,
            TAG_CFG_OBJ_SUFFIX : '.obj',
            TAG_CFG_PDB_SUFFIX : '.pdb',
            TAG_CFG_DEP_SUFFIX : '.dep',
        }

        if conf_mk:
            config_file = os.path.normpath(os.path.join(bootstrap_dir, '{}-{}'.format(sys_platform, BUILD_SYSTEM_CONFIG_FILE)))
            mkdir_safe(bootstrap_dir)
            generate_build_config(conf_mk, config_file, sys_platform, sys_arch, verbose)
        else:
            config_file = os.path.normpath(os.path.join(project_root, BUILD_SYSTEM_CONFIG_FILE))
        if not os.path.isfile(config_file):
            raise BuildSystemException("Project config file is not found by path: '{}'.".format(config_file))

        config = load_ini_config(path=config_file)
        model_aliases = read_model_aliases(config)

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
            toolset_serialized_custom_models = get_ini_conf_string0(config, toolset_section, TAG_INI_TOOLSET_MODELS)
            if toolset_serialized_custom_models:
                ast = compile(toolset_serialized_custom_models, '<toolset-models>', 'eval')
                toolset_custom_models = eval(ast, {"__builtins__": None}, {})
            else:
                toolset_custom_models = None

            toolset_init_requests += [ (toolset_module_title, toolset_custom_models, toolset_init_args) ]

        subst_info = {
            TAG_SUBST_PROJECT_ROOT: project_root,
            TAG_SUBST_PROJECT_OUTPUT: output_dname,
        }

        toolset_models_mapping = {}
        imported_toolset_modules = {}
        for toolset_module_title, toolset_custom_models, toolset_init_args in toolset_init_requests:
            mod_toolset = imported_toolset_modules.get(toolset_module_title)
            if mod_toolset is None:
                try:
                    toolset_module_name = '{}.toolset_{}'.format(__package__, toolset_module_title)
                    mod_toolset = importlib.import_module(toolset_module_name)
                    imported_toolset_modules[toolset_module_title] = mod_toolset
                except ImportError:
                    raise BuildSystemException("Malformed project config file: got unknown toolset module: '{}'.".format(toolset_module_title))

            desc_loader = BuildDescriptionLoader(sys_platform, sys_arch)
            toolset = mod_toolset.create_toolset(sysinfo, desc_loader, sys_platform, sys_arch, toolset_custom_models, **toolset_init_args)
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

    except BuildSystemException as ex:
        buildsys_error = ex

    if buildsys_error is None:
        models_help_prefix = '1) primary ' if model_aliases else ''
        models_help = 'R|{}choices:\n    {}'.format(models_help_prefix, '\n    '.join(toolset_choices))
        alias_choises = []
        for alias in sorted(model_aliases):
            alias_choises.append(alias)
        if alias_choises:
            models_help = "{}\n2) aliases:\n    {}".format(models_help, '\n    '.join(alias_choises))
    else:
        models_help = 'build model'

    parallelism = guess_parallelism()

    parser = ArgumentParser(prog='minibuild', formatter_class=ArgumentParserFormat)
    parser.add_argument('--model',     nargs='?', help=models_help)
    parser.add_argument('--config',    nargs='?', choices=BUILD_CONFIG_ALL, default=BUILD_CONFIG_RELEASE, help='build configuration')
    parser.add_argument('--directory', nargs='?', help='startup directory for build')
    parser.add_argument('-j', '--parallel', nargs='?', default=parallelism, metavar='N', type=int, help='R|run N jobs in parallel\n    default={}, derived from CPUs available'.format(parallelism))
    parser.add_argument('--pass',      action='store_true', dest='pass_through', help='proceed with command-lines from makefile')
    parser.add_argument('--force',     choices=[-1,0,1,2],  default=0, type=int,
        help='R|implied rebuild level (default is 0)\n   -1: skip build of dependent targets\n    0: as needed\n    1: force rebuild of current module only\n    2: force rebuild of all targets')
    parser.add_argument('--public',    action='store_true', help='when building composite target, publish it as zip/tgz')
    parser.add_argument('--public-format', nargs='?', choices=['auto'] + TAG_PUBLIC_FORMAT_ALL[:], default='auto',
        help="public format, default is 'auto', i.e. 'zip' when target is built for Windows and 'tgz' otherwise")
    parser.add_argument('--public-layout', nargs='?', choices=['default', TAG_PUBLIC_LAYAOUT_FLAT], default='default',
        help="public layout, 'flat' means to avoid any subdirectories creation when publishing")
    parser.add_argument('--trace',     action='store_true', help='show all command lines while building')
    parser.add_argument('--verbose',   action='store_true', help='verbose output while building')
    parser.add_argument('--faccess',   action='store_true', help="R|track all files being accessed while building,\nas result stamps of accessed files are saved\nin '<project-output>/{}' directory".format(BUILD_CONFIG_DEFAULT_FACCESS_DIR))
    parser.add_argument('--faccess-directory', nargs='*', metavar='dirname', help="R|Directory name relative to <project-root> where to\ntrack files being accessed, default is <project-root>")
    parser.add_argument('--faccess-emerge', action='store_true', help="R|Emerge content of '<project-output>/{}' directory\nin '<project-output>/{}' file".format(BUILD_CONFIG_DEFAULT_FACCESS_DIR, BUILD_CONFIG_DEFAULT_FACCESS_EMERGE_FILE))
    parser.add_argument('--version',   action='store_true', help='print version number and exit')
    if frozen:
        parser.add_argument('--interpreter', action='store_true', help='launch this executable as python interpreter')

    try:
        args = parser.parse_args(argv)
    except ArgumentParserExit:
        return None, None

    if args.version:
        print(format_version_string(frozen))
        return None, None

    if args.faccess_emerge and sysinfo is not None:
        perform_faccess_emerge(sysinfo)
        return None, None

    if buildsys_error is not None:
        raise buildsys_error

    public_format = None
    if args.public_format in TAG_PUBLIC_FORMAT_ALL:
        public_format = args.public_format

    public_layout = TAG_PUBLIC_LAYAOUT_FLAT if args.public_layout == TAG_PUBLIC_LAYAOUT_FLAT else None

    faccess_prefixes = []
    if args.faccess:
        if args.faccess_directory:
            for faccess_dir_arg in args.faccess_directory:
                faccess_dirname_abs = normalize_path_optional(faccess_dir_arg, project_root)
                if not os.path.isdir(faccess_dirname_abs):
                    raise BuildSystemException("Directory requested for faccess track not found: '{}'.".format(faccess_dir_arg))
                faccess_dirname_norm_prefix = os.path.normcase(faccess_dirname_abs) + os.sep
                if not faccess_dirname_norm_prefix.startswith(sysinfo[TAG_CFG_PROJECT_ROOT_COMMON_PREFIX]):
                    raise BuildSystemException("Directory requested for faccess track '{}' (resolved as '{}') is out of <project-root> source tree.".format(faccess_dir_arg, faccess_dirname_abs))
                faccess_prefixes.append(faccess_dirname_norm_prefix)
        if not faccess_prefixes:
            faccess_prefixes = [ sysinfo[TAG_CFG_PROJECT_ROOT_COMMON_PREFIX] ]

    if args.pass_through:
        pass_through_commands = PassThroughCommandList()
        build_description_fname = os.path.join(build_directory, BUILD_MODULE_DESCRIPTION_FILE)
        if not os.path.isfile(build_description_fname):
            raise BuildSystemException("Makefile not found: '{}'".format(build_description_fname))
        pragmas = load_buildconf_pragmas(build_description_fname, sys_platform)
        for pragma in pragmas:
            if pragma.pragma_id != TAG_PRAGMA_TOKEN_KEY_PASS:
                continue
            if TAG_PRAGMA_TOKEN_KEY_CMDLINE not in pragma.options or not pragma.options[TAG_PRAGMA_TOKEN_KEY_CMDLINE]:
                raise BuildSystemException("Can't load makefile: '{}', instruction #pragma at line: {}, token: '{}' not given.".format(build_description_fname, pragma.lineno, TAG_PRAGMA_TOKEN_KEY_CMDLINE))
            pass_err = None
            try:
                posix = False if sys.platform == 'win32' else True
                pass_argv = shlex.split(pragma.options[TAG_PRAGMA_TOKEN_KEY_CMDLINE], comments=False, posix=posix)
            except ValueError as ex:
                pass_err = str(ex)
            if pass_err is not None:
                raise BuildSystemException("Can't load makefile: '{}', instruction #pragma at line: {}, value of token '{}' is malformed: {}".format(build_description_fname, pragma.lineno, TAG_PRAGMA_TOKEN_KEY_CMDLINE, pass_err))
            pass_with_interpreter = True if pragma.options.get('interpreter') else False
            pass_through_commands.append(PassThroughCommand(build_description_fname, pragma.lineno, pass_argv, pass_with_interpreter))
            if verbose:
                print("BUILDSYS: #pragma # pass # cmdline: {}".format(pragma.options[TAG_PRAGMA_TOKEN_KEY_CMDLINE]))
        return None, pass_through_commands

    if not args.model:
        arg_model = eval_default_model(config, sys_platform, sys_arch)
        if not arg_model:
            raise BuildSystemException("Build model is not given in command-line.")
        else:
            if verbose:
                print("BUILDSYS: Using default build model '{}'.".format(arg_model))
    else:
        arg_model = args.model

    if arg_model not in toolset_choices and arg_model not in model_aliases:
        raise BuildSystemException("Got unknown build model '{}' from command-line, try '--help' for more information.".format(arg_model))

    if arg_model in model_aliases:
        primary_model = model_aliases[arg_model]
        if verbose:
            print("BUILDSYS: Build model alias '{}' resolved as '{}'.".format(arg_model, primary_model))
        arg_model = primary_model

    native_model_remap = eval_native_model(arg_model, toolset_models_mapping, model_aliases, config, sys_platform, sys_arch, verbose)

    parallelism = args.parallel
    if parallelism <= 0:
        parallelism = 1

    if os.environ.get('MINIBUILD_TRACE'):
        cmd_trace = True
    else:
        cmd_trace = args.trace
    logic = BuildWorkflow(sysinfo=sysinfo, toolset_models_mapping=toolset_models_mapping, native_model_remap=native_model_remap,
        grammar_substitutions=subst_info, verbose=verbose, trace=cmd_trace, parallelism=parallelism, faccess=args.faccess, faccess_prefixes=faccess_prefixes)

    for model_name in toolset_models_mapping:
        _, desc_loader = toolset_models_mapping[model_name]
        desc_loader.set_import_hook(lambda x, y: logic.import_extension(desc_loader, x, y))
        desc_loader.set_build_config(args.config)

    build_args = {}
    build_args['build_directory'] = build_directory
    build_args['used_model_name'] = arg_model
    build_args['build_config'] = args.config
    build_args['public'] = args.public
    build_args['public_format'] = public_format
    build_args['public_layout'] = public_layout
    build_args['rebuild_level'] = args.force

    return logic, build_args


def preload_argv(args, dir_redirect):
    argv = []
    verbose = False
    arg_dir = None
    next_arg_is_dir = False
    for arg in args:
        if arg == '--verbose':
            verbose = True
            continue
        if arg_dir is None:
            if next_arg_is_dir:
                arg_dir = arg
                continue
            if arg == '--directory':
                next_arg_is_dir = True
                continue
        argv.append(arg)
    if arg_dir is not None:
        build_directory = normalize_path_optional(arg_dir, dir_redirect)
        if not os.path.isdir(build_directory):
            raise BuildSystemException("Invalid build directoty '{}' is given in command line, directory '{}' is not found.".format(arg_dir, build_directory))
    else:
        build_directory = dir_redirect
    return build_directory, verbose, argv


def invoke_interpreter(argv, cwd, frozen, verbose):
    argv = argv[:]
    if frozen:
        argv.insert(0, '--interpreter')
    argv.insert(0, sys.executable)
    if verbose:
        print("BUILDSYS: EXEC: ['{}'], CWD: '{}'".format("','".join(argv), cwd))
    p = subprocess.Popen(argv, cwd=cwd)
    p.communicate()
    if p.returncode != 0:
        raise BuildSystemException("Pass-through command completed with non-zero exit code.")


def script_main_perform(argv_in, frozen, dir_redirect, walks, level, verbose=None):
    pass_with_interpreter = False
    if isinstance(argv_in, PassThroughCommand):
        argv = argv_in.argv
        pass_with_interpreter = argv_in.pass_with_interpreter
    else:
        argv = argv_in

    if pass_with_interpreter:
        invoke_interpreter(argv, dir_redirect, frozen, verbose)
        return

    build_directory, _verbose, argv = preload_argv(argv, dir_redirect)
    if verbose is None:
        if os.environ.get('MINIBUILD_VERBOSE'):
            verbose = True
        else:
            verbose = _verbose
    if verbose:
        print("BUILDSYS: CWD: {}".format(build_directory))
        print("BUILDSYS: RUN: {}".format(' '.join(argv)))
    if build_directory in walks:
        raise BuildSystemException("Maximum recursion depth exceeded, see #pragma in '{}', line: {}".format(argv_in.fname, argv_in.lineno))
    walks.add(build_directory)
    logic, args = create_build_workflow(frozen, build_directory, verbose, argv)
    if logic is not None:
        logic.run(**args)
    elif isinstance(args, PassThroughCommandList):
        for cmd in args.items:
            if level == 0:
                walks.clear()
            script_main_perform(cmd, frozen, build_directory, walks, level+1, verbose)


def script_main(argv=None):
    try:
        frozen = True if __file__ == '<frozen>' else False
        if argv is None:
            argv = sys.argv[1:]
        if len(argv) == 1 and argv[0] == '--version':
            print(format_version_string(frozen))
            return 0
        walks = set()
        script_main_perform(argv, frozen, os.getcwd(), walks, 0)
        return 0
    except BuildSystemSysExit as exc:
        return exc.to_exit_code()
    except BuildSystemException as exc:
        print(buildsys_error_to_string(exc))
        return exc.to_exit_code()
