from __future__ import print_function
import importlib
import os.path
import shlex
import sys

from .arch_parse import parse_arch_specific_tokens
from .constants import *
from .depends_check import prerequisite_newer_then_target
from .error_utils import BuildSystemException
from .os_utils import touch_file
from .pragma_tokens import load_buildconf_pragmas


class _ToolsetPragmaConfig:
    def __init__(self, label, toolset_name, pragma_line, pragma_options, subtype, model_aliases):
        self.label = label
        self.toolset_name = toolset_name
        self.pragma_line = pragma_line
        self.pragma_options = pragma_options
        self.subtype = subtype
        self.model_aliases = model_aliases

    def title(self):
        if self.subtype:
            return '{}/{}'.format(self.subtype, self.toolset_name)
        else:
            return self.toolset_name

    def dump_options(self):
        bits = []
        for key in sorted(self.pragma_options):
            bits.append('{}={}'.format(key, self.pragma_options[key]))
        for arch in sorted(self.model_aliases):
            bits.append('{} alias: {}'.format(arch, self.model_aliases[arch]))
        return ', '.join(bits)

    def eval_model_aliases(self, models_per_arch):
        aliases = {}
        for arch in sorted(self.model_aliases):
            if arch in models_per_arch:
                alias = self.model_aliases[arch]
                model_name = models_per_arch[arch]
                aliases[alias] = model_name
        return aliases


def _generate_build_config_imp(config_proto, dest_config, sys_platform, sys_arch, verbose):
    nasm_executable = None
    imported_toolset_modules = {}
    toolset_init_requests = []
    native_model_mode = TAG_NATIVE_MODELS_DETECTION_OPTIONAL
    native_model_value = None
    arch_list_with_default_models = None
    default_models_per_arch = None
    aliases_mapping = {}
    arch_substitutions = {'sys': sys_arch}

    pragmas = load_buildconf_pragmas(config_proto, sys_platform)

    for pragma in pragmas:
        if pragma.pragma_id == TAG_PRAGMA_NASM:
            if TAG_PRAGMA_TOKEN_KEY_EXECUTABLE in pragma.options:
                nasm_executable = pragma.options[TAG_PRAGMA_TOKEN_KEY_EXECUTABLE]
                if verbose:
                    print("BUILDSYS: #pragma # nasm # executable: '{}'".format(nasm_executable))

        elif pragma.pragma_id == TAG_PRAGMA_NATIVE:
            if TAG_PRAGMA_TOKEN_KEY_MODEL not in pragma.options or not pragma.options[TAG_PRAGMA_TOKEN_KEY_MODEL]:
                raise BuildSystemException("Can't load makefile: '{}', instruction #pragma at line: {}, token: '{}' not given.".format(config_proto, pragma.lineno, TAG_PRAGMA_TOKEN_KEY_MODEL))
            native_model = pragma.options[TAG_PRAGMA_TOKEN_KEY_MODEL]
            if native_model in [TAG_NATIVE_MODELS_DETECTION_DISABLED, TAG_NATIVE_MODELS_DETECTION_OPTIONAL, TAG_NATIVE_MODELS_DETECTION_AUTO]:
                native_model_mode = native_model
            else:
                native_model_mode = TAG_NATIVE_MODELS_DETECTION_CONFIG
                native_model_value = native_model

        elif pragma.pragma_id == TAG_PRAGMA_TOOLSET:
            if TAG_PRAGMA_TOKEN_KEY_MODULE not in pragma.options or not pragma.options[TAG_PRAGMA_TOKEN_KEY_MODULE]:
                raise BuildSystemException("Can't load makefile: '{}', instruction #pragma at line: {}, token: '{}' not given.".format(config_proto, pragma.lineno, TAG_PRAGMA_TOKEN_KEY_MODULE))
            toolset_path = pragma.options[TAG_PRAGMA_TOKEN_KEY_MODULE]
            toolset_label = None
            if '/' in toolset_path:
                toolset_name, toolset_label = toolset_path.split('/', 1)
                if not toolset_label or '/' in toolset_label:
                    raise BuildSystemException("Can't load makefile: '{}', instruction #pragma at line: {}, got malformed toolset label: '{}'.".format(config_proto, pragma.lineno, toolset_label))
            else:
                toolset_name = toolset_path
            toolset_subtype = None
            if toolset_name == 'mingw':
                toolset_subtype = 'mingw'
                toolset_name = 'gcc'
            elif toolset_name == 'xtools':
                toolset_subtype = 'xtools'
                toolset_name = 'gcc'
            elif toolset_name == 'macosx-xtools':
                toolset_subtype = 'macosx-xtools'
                toolset_name = 'clang'
            mod_toolset = imported_toolset_modules.get(toolset_name)
            if mod_toolset is None:
                toolset_module_name = '{}.toolset_{}'.format(__package__, toolset_name)
                try:
                    mod_toolset = importlib.import_module(toolset_module_name)
                    imported_toolset_modules[toolset_name] = mod_toolset
                except ImportError:
                    raise BuildSystemException("Can't load makefile: '{}', instruction #pragma at line: {}, got unknown toolset module: '{}'.".format(config_proto, pragma.lineno, toolset_name))
            del pragma.options[TAG_PRAGMA_TOKEN_KEY_MODULE]

            toolset_model_aliases = {}
            if TAG_PRAGMA_TOKEN_KEY_ALIAS in pragma.options and pragma.options[TAG_PRAGMA_TOKEN_KEY_ALIAS]:
                model_aliases = pragma.options[TAG_PRAGMA_TOKEN_KEY_ALIAS]
                del pragma.options[TAG_PRAGMA_TOKEN_KEY_ALIAS]
                aliases_arch_list, toolset_model_aliases = parse_arch_specific_tokens(model_aliases, TAG_ALL_KNOWN_ARCH_LIST, allow_empty_tokens=False, arch_substitutions=arch_substitutions)
                if not aliases_arch_list:
                    raise BuildSystemException("Can't process makefile: '{}', instruction #pragma at line: {}, token '{}' is malformed: '{}'".format(config_proto, pragma.lineno, TAG_PRAGMA_TOKEN_KEY_ALIAS, model_aliases))

            conf = _ToolsetPragmaConfig(toolset_label, toolset_name, pragma.lineno, pragma.options, toolset_subtype, toolset_model_aliases)
            toolset_init_requests.append(conf)

        elif pragma.pragma_id == TAG_PRAGMA_DEFAULT_MODELS:
            if pragma.os_name == TAG_PRAGMA_OS_VALUE_ALL:
                raise BuildSystemException("Can't process makefile: '{}', instruction #pragma at line: {}, token '{}' must be OS specific.".format(config_proto, pragma.lineno, TAG_PRAGMA_TOKEN_KEY_MODEL))
            if TAG_PRAGMA_TOKEN_KEY_MODEL not in pragma.options or not pragma.options[TAG_PRAGMA_TOKEN_KEY_MODEL]:
                raise BuildSystemException("Can't load makefile: '{}', instruction #pragma at line: {}, token: '{}' not given.".format(config_proto, pragma.lineno, TAG_PRAGMA_TOKEN_KEY_MODEL))
            pragma_default_models = pragma.options[TAG_PRAGMA_TOKEN_KEY_MODEL]
            arch_list_with_default_models, default_models_per_arch = parse_arch_specific_tokens(pragma_default_models, TAG_ALL_KNOWN_ARCH_LIST, allow_empty_tokens=False, arch_substitutions=arch_substitutions)
            if not arch_list_with_default_models:
                raise BuildSystemException("Can't process makefile: '{}', instruction #pragma at line: {}, token '{}' is malformed: '{}'".format(config_proto, pragma.lineno, TAG_PRAGMA_TOKEN_KEY_MODEL, pragma_default_models))
            if verbose:
                print("BUILDSYS: #pragma line: {:2} # {} # {}".format(pragma.lineno, 'default models', pragma_default_models))

    if not toolset_init_requests:
        raise BuildSystemException("Can't load makefile: '{}', no #pragma instructions are given for any toolset configuration on current platform: {}.".format(config_proto, sys_platform))

    for conf in toolset_init_requests:
        if verbose:
            print("BUILDSYS: #pragma line: {:2} # {} # {}".format(conf.pragma_line, conf.title(), conf.dump_options()))

    toolset_ids = []
    conf_parts_tail = []
    skipped_toolset_count = 0
    for conf in toolset_init_requests:
        mod_toolset = imported_toolset_modules[conf.toolset_name]
        pragma_options = {}
        if conf.subtype:
            pragma_options[conf.subtype] = dict(conf.pragma_options)
        else:
            pragma_options = dict(conf.pragma_options)
        if nasm_executable:
            pragma_options['nasm_executable'] = nasm_executable
        toolset_id, description_lines, conflicts, models_per_arch = mod_toolset.describe_toolset(config_proto, conf.pragma_line, sys_platform, sys_arch, conf.label, **pragma_options)
        if toolset_id is None:
            skipped_toolset_count += 1
            continue
        if not isinstance(conflicts, list):
            conflicts = []
        conflicts.append(toolset_id)
        for processed_id, processed_conf in toolset_ids:
            if processed_id in conflicts:
                raise BuildSystemException("Can't load makefile: '{}', instruction #pragma at line {}, i.e. toolset: '{}', conflicts with already registered toolset '{}' at line {}."
                    .format(config_proto, conf.pragma_line, toolset_id, processed_id, processed_conf.pragma_line))

        aliases_mapping_for_toolset = conf.eval_model_aliases(models_per_arch)
        aliases_mapping.update(aliases_mapping_for_toolset)

        toolset_ids += [(toolset_id, conf)]
        conf_parts_tail.append("")
        conf_parts_tail.extend(description_lines)

    if not toolset_ids:
        raise BuildSystemException("Can't find any build toolset on this machine, tried toolsets count: {}".format(skipped_toolset_count))

    all_toolset = []
    for processed_id, _ in toolset_ids:
        all_toolset.append(processed_id)

    conf_parts = [
        "[{}]".format(TAG_INI_CONF_MAIN),
        "toolset-{} = {}".format(sys_platform, ' '.join(all_toolset)),
        "{} = {}".format(TAG_INI_NATIVE_MODELS_DETECTION_MODE, native_model_mode),
    ]

    if native_model_mode == TAG_NATIVE_MODELS_DETECTION_CONFIG:
        conf_parts += [
            "",
            "[{}]".format(TAG_INI_CONF_MAIN_NATIVE),
            "{}-{} = {}".format(sys_platform, sys_arch, native_model_value),
        ]

    if aliases_mapping:
        conf_parts += [
            "",
            "[{}]".format(TAG_INI_CONF_MAIN_ALIAS),
        ]
        for alias in sorted(aliases_mapping):
            model_name = aliases_mapping[alias]
            conf_parts.append("{} = {}".format(alias, model_name))

    if arch_list_with_default_models:
        conf_parts += [
            "",
            "[{}]".format(TAG_INI_CONF_MAIN_DEFAULT),
        ]
        for arch in arch_list_with_default_models:
            conf_parts.append("{}-{} = {}".format(sys_platform, arch, default_models_per_arch[arch]))

    conf_parts.extend(conf_parts_tail)

    with open(dest_config, mode='wt') as fh:
        for line in conf_parts:
            fh.writelines([line, '\n'])
    if verbose:
        print("BUILDSYS: File generated: {}".format(dest_config))


def generate_build_config(config_proto, config_file, sys_platform, sys_arch, verbose):
    gen_stamp_file = os.path.splitext(config_file)[0] + '.stamp'
    if os.path.isfile(config_proto) and os.path.isfile(gen_stamp_file) and os.path.isfile(config_file):
        mt_proto = os.path.getmtime(config_proto)
        mt_target = os.path.getmtime(gen_stamp_file)
        if not prerequisite_newer_then_target(mt_target, mt_proto, gen_stamp_file, config_proto, verbose):
            return
    _generate_build_config_imp(config_proto, config_file, sys_platform, sys_arch, verbose)
    touch_file(gen_stamp_file)
