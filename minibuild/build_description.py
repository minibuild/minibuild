import os.path
import re

from .constants import *
from .error_utils import BuildSystemException
from .grammar_subst import preprocess_grammar_value
from .os_utils import normalize_path_optional
from .string_utils import is_string_instance


_RE_INC = re.compile(r'^#include\s+"([\S]+)"\s*$')
_RE_IMP = re.compile(r'^#import\s+"([\S]+)"\s*$')


def _parse_makefile_injection(line, regexp, project_root, working_dir):
    result = None
    m = regexp.match(line)
    if m:
        result = m.group(1)
    if result:
        result = result.strip()
    if result and result.startswith('@'):
        result = result.replace('@', project_root, 1)
    if result:
        result = normalize_path_optional(result, working_dir)
    return result


class _ExtensionImportOrigin:
    def __init__(self, dname_import, src_file, src_line):
        self.dname_import = dname_import
        self.src_file = src_file
        self.src_line = src_line


def _parse_make_file(project_root, working_dir, file_to_parse, required_by, output, file_parts, imports_table):
    fname = normalize_path_optional(file_to_parse, working_dir)
    if fname in required_by:
       raise BuildSystemException("Got recursive instruction #include: file: '{}'.".format(fname))

    dir_of_file = os.path.dirname(fname)

    if not os.path.isfile(fname):
        if not required_by:
            raise BuildSystemException("No such description: '{}'".format(fname))
        elif len(required_by) == 1:
            raise BuildSystemException("No such description: '{}', required by: '{}'.".format(fname, required_by[0]))
        else:
            raise BuildSystemException("No such description: '{}', required by:\n  {}"
                .format(fname, ' <= '.join(required_by)))

    with open(fname, mode='rt') as fh:
        try:
            source = fh.read()
            ast = compile(source, fname, 'exec')
        except SyntaxError as syntax:
            raise BuildSystemException("Invalid syntax: file: '{}', line: {}, offset: {}.".format(fname, syntax.lineno, syntax.offset))

    file_parts.append(fname)
    stop_reparse = False
    with open(fname, mode='rt') as fh:
        lines = [ ln.rstrip('\r\n') for ln in fh.readlines() ]
    idx = 0
    for ln in lines:
        if not stop_reparse:
            idx += 1
            ln_stripped = ln.strip()
            if ln_stripped and not ln_stripped.startswith('#'):
                stop_reparse = True
            if not stop_reparse and ln_stripped.startswith('#include'):
                fname_inc = _parse_makefile_injection(ln, _RE_INC, project_root, dir_of_file)
                if fname_inc is None:
                    raise BuildSystemException("Invalid #include syntax: file: '{}', line: {}".format(fname, idx))
                required_by.insert(0, fname)
                _parse_make_file(project_root, dir_of_file, fname_inc, required_by, output, file_parts, imports_table)
                required_by.pop(0)
            if not stop_reparse and ln_stripped.startswith('#import'):
                if imports_table is None:
                    raise BuildSystemException("Unexpected #import syntax: file: '{}', line: {}".format(fname, idx))
                dname_import = _parse_makefile_injection(ln, _RE_IMP, project_root, dir_of_file)
                if dname_import is None:
                    raise BuildSystemException("Invalid #import syntax: file: '{}', line: {}".format(fname, idx))
                if not os.path.isdir(dname_import):
                    raise BuildSystemException("Directory for #import not found: '{}', required by: '{}' at line: {}".format(dname_import, fname, idx))
                dname_import_id = os.path.normcase(dname_import)
                imports_table[dname_import_id] = _ExtensionImportOrigin(dname_import, fname, idx)

        output.append(ln)


def _load_make_file(project_root, working_dir, fname, grammar_map, subst, buildsys_builtins, required_by, import_enabled):
    origin = []
    output = []
    file_parts = []
    imports_table = {} if import_enabled else None
    if required_by is not None:
        origin.insert(0, required_by)
    _parse_make_file(project_root, working_dir, fname, origin, output, file_parts, imports_table)
    local_vars = {}
    for var_name in grammar_map:
        var_type = grammar_map[var_name][0]
        var_value = None if var_type is None else var_type()
        local_vars[var_name] = var_value
    if buildsys_builtins is not None:
        local_vars.update(buildsys_builtins)
    try:
        text = '\n'.join(output)
        text_ast = compile(text, file_parts[0], 'exec')
        exec(text_ast, {}, local_vars)
    except SyntaxError as syntax:
        raise BuildSystemException("Invalid syntax: file: '{}', line: {}, offset: {}.".format(file_parts[0], syntax.lineno, syntax.offset))
    grammar_tokens = {}
    for var_name in local_vars.keys():
        if var_name in grammar_map:
            need_preprocess = grammar_map[var_name][1]
            if need_preprocess:
                expected_var_type = grammar_map[var_name][0]
                grammar_tokens[var_name] = preprocess_grammar_value(subst, file_parts[0], expected_var_type, var_name, local_vars[var_name])
            else:
                grammar_tokens[var_name] = local_vars[var_name]
    grammar_tokens[TAG_GRAMMAR_BUILTIN_SELF_FILE_PARTS] = file_parts
    grammar_tokens[TAG_GRAMMAR_BUILTIN_SELF_DIRNAME] = os.path.dirname(file_parts[0])
    return grammar_tokens, imports_table


class BuildDescription:
    def __init__(self, tokens):
        self._tokens = tokens
        self._buildsys_import_list = None

    def __getattr__(self, attr):
        if attr in self._tokens:
            return self._tokens[attr]
        title = None
        if TAG_GRAMMAR_BUILTIN_SELF_FILE_PARTS and self._tokens[TAG_GRAMMAR_BUILTIN_SELF_FILE_PARTS]:
            title = self._tokens[TAG_GRAMMAR_BUILTIN_SELF_FILE_PARTS][0]
        raise AttributeError("'{}[{}]' object has no attribute '{}'".format(self.__class__.__name__, title, attr))


class BuildDescriptionLoader:
    def __init__(self):
        self.buildsys_builtins = {}
        self.subst = {}
        self.import_hook = None

    def set_target_platform(self, value):
        self.buildsys_builtins[TAG_BUILDSYS_TARGET_PLATFORM] = value

    def set_toolset_name(self, value):
        self.buildsys_builtins[TAG_BUILDSYS_TOOLSET_NAME] = value

    def set_substitutions(self, subst_info):
        self.subst = subst_info

    def set_import_hook(self, import_hook):
        self.import_hook = import_hook

    def load_build_description(self, working_dir, required_by=None):
        project_root = self.subst[TAG_SUBST_PROJECT_ROOT]
        import_enabled = callable(self.import_hook)
        grammar_tokens, imports = _load_make_file(project_root, working_dir, BUILD_MODULE_DESCRIPTION_FILE, TAG_GRAMMAR_KEYS_ALL,
            self.subst, self.buildsys_builtins, required_by, import_enabled)
        desc = BuildDescription(grammar_tokens)
        if imports:
            for dname_import_idx in imports:
                import_origin = imports[dname_import_idx]
                ext = self.import_hook(import_origin.dname_import, import_origin.src_file)
                ext_name = ext.ext_name
                if desc._buildsys_import_list is None:
                    desc._buildsys_import_list = [ ext_name ]
                else:
                    desc._buildsys_import_list.append(ext_name)
                desc._tokens[TAG_GRAMMAR_BUILTIN_SELF_FILE_PARTS].extend(ext._tokens[TAG_GRAMMAR_BUILTIN_SELF_FILE_PARTS])
        return desc

    def load_build_extension(self, working_dir, required_by):
        project_root = self.subst[TAG_SUBST_PROJECT_ROOT]
        buildsys_builtins = None
        import_enabled = False
        grammar_tokens, _ = _load_make_file(project_root, working_dir, BUILD_MODULE_EXTENSION_FILE, TAG_GRAMMAR_KEYS_EXT_ALL,
            self.subst, buildsys_builtins, required_by, import_enabled)
        return BuildDescription(grammar_tokens)
