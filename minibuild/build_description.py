import linecache
import os.path
import re
import sys
import traceback

from .constants import *
from .error_utils import BuildSystemException
from .grammar_subst import preprocess_grammar_value
from .os_utils import normalize_path_optional
from .string_utils import is_string_instance


_RE_INC = re.compile(r'^#include\s+"([\S]+)"\s*$')
_RE_IMP = re.compile(r'^#import\s+"([\S]+)"\s*$')

_RE_PRAGMA_BUILD = re.compile(r'^#pragma\s+build\b(.*)$')

if sys.version_info.major < 3:
    _CO_FUTURE_DIVISION         = 0x02000  # division
    _CO_FUTURE_ABSOLUTE_IMPORT  = 0x04000  # perform absolute imports by default
    _CO_FUTURE_WITH_STATEMENT   = 0x08000  # with statement
    _CO_FUTURE_PRINT_FUNCTION   = 0x10000  # print function

    _COMPILE_FLAGS = _CO_FUTURE_DIVISION | _CO_FUTURE_ABSOLUTE_IMPORT | _CO_FUTURE_WITH_STATEMENT | _CO_FUTURE_PRINT_FUNCTION
else:
    _COMPILE_FLAGS = 0


def _parse_traceback_of_file(etype, value, tb, issuer_fname, issuer_output, issuer_traceback):
    lines = []
    parsed = True if tb is None else False
    while tb is not None:
        file_info = None
        line = None
        f = tb.tb_frame
        lineno = tb.tb_lineno
        co = f.f_code
        filename = co.co_filename
        if filename == issuer_fname:
            parsed = True
        if filename == issuer_fname and issuer_output and issuer_traceback:
            file_info = '  File "{}", line {}'.format(issuer_traceback[lineno-1][0], issuer_traceback[lineno-1][1])
            line = issuer_output[lineno-1]
        elif parsed:
            file_info = '  File "{}", line {}, in {}'.format(filename, lineno, co.co_name)
            linecache.checkcache(filename)
            line = linecache.getline(filename, lineno, f.f_globals)
        if file_info:
            lines.append(file_info)
        if line:
            lines.append('    ' + line.strip())
        tb = tb.tb_next
    if parsed:
        lines.insert(0, 'Traceback (most recent call last):')
        exc_lines = traceback.format_exception_only(etype, value)
        for xln in exc_lines:
            exc_line = xln.rstrip('\r\n')
            if exc_line:
                lines.append(exc_line)
    return parsed, lines


def _format_exception(etype, value):
    return _parse_traceback_of_file(etype, value, None, None, None, None)


def _exec_compile(source, fname):
        return compile(source, fname, 'exec', _COMPILE_FLAGS, 1)


def _parse_pragmas(fname):
    tb_parsed, tb_lines = None, None
    with open(fname, mode='rt') as fh:
        try:
            source = fh.read()
            ast = _exec_compile(source, fname)
        except SyntaxError:
            etype, value, _ = sys.exc_info()
            tb_parsed, tb_lines = _format_exception(etype, value)
            if not tb_parsed:
                raise
    if tb_parsed:
        tb_lines.insert(0, "Can't load makefile: '{}'".format(fname))
        raise BuildSystemException('\n'.join(tb_lines))
    with open(fname, mode='rt') as fh:
        lines = [ ln.rstrip('\r\n') for ln in fh.readlines() ]
    pragma_lines = []
    stop_reparse = False
    idx = 0
    for ln in lines:
        if stop_reparse:
            break
        idx += 1
        if not stop_reparse:
            ln_stripped = ln.strip()
            if ln_stripped and not ln_stripped.startswith('#'):
                stop_reparse = True
            if not stop_reparse and ln_stripped.startswith('#pragma'):
                pragma_lines += [(idx, ln)]
    return pragma_lines


def makefile_is_project_landmark(fname):
    pragma_lines = _parse_pragmas(fname)
    pragma_line = 0
    for _, line in pragma_lines:
        pragma_line += 1
        m = _RE_PRAGMA_BUILD.match(line)
        if m:
            details = m.group(1)
            if details:
                return True, details.strip(), pragma_line
            return True, None, pragma_line
    return False, None, -1


def load_buildconf_pragmas(fname):
    buildconf_lines = []
    pragma_lines = _parse_pragmas(fname)
    for idx, line in pragma_lines:
        if _RE_PRAGMA_BUILD.match(line):
            continue
        ln = line.replace('#pragma', '').strip()
        buildconf_lines += [(idx, ln)]
    return buildconf_lines


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


def _parse_make_file(project_root, working_dir, file_to_parse, required_by, output, output_traceback, file_parts, imports_table):
    fname = normalize_path_optional(file_to_parse, working_dir)
    if fname in required_by:
       raise BuildSystemException("Got recursive instruction #include: file: '{}'.".format(fname))

    dir_of_file = os.path.dirname(fname)

    if not os.path.isfile(fname):
        if not required_by:
            raise BuildSystemException("Makefile not found: '{}'".format(fname))
        elif len(required_by) == 1:
            raise BuildSystemException("Makefile not found: '{}', required by: '{}'.".format(fname, required_by[0]))
        else:
            raise BuildSystemException("Makefile not found: '{}', required by:\n  {}"
                .format(fname, ' <= '.join(required_by)))

    tb_parsed, tb_lines = None, None
    with open(fname, mode='rt') as fh:
        try:
            source = fh.read()
            ast = _exec_compile(source, fname)
        except SyntaxError:
            etype, value, _ = sys.exc_info()
            tb_parsed, tb_lines = _format_exception(etype, value)
    if tb_parsed:
        tb_origin = fname if not file_parts else file_parts[0]
        tb_lines.insert(0, "Can't load makefile: '{}'".format(tb_origin))
        raise BuildSystemException('\n'.join(tb_lines))

    file_parts.append(fname)
    stop_reparse = False
    with open(fname, mode='rt') as fh:
        lines = [ ln.rstrip('\r\n') for ln in fh.readlines() ]
    idx = 0
    for ln in lines:
        idx += 1
        if not stop_reparse:
            ln_stripped = ln.strip()
            if ln_stripped and not ln_stripped.startswith('#'):
                stop_reparse = True
            if not stop_reparse and ln_stripped.startswith('#include'):
                fname_inc = _parse_makefile_injection(ln, _RE_INC, project_root, dir_of_file)
                if fname_inc is None:
                    raise BuildSystemException("Invalid #include syntax: file: '{}', line: {}".format(fname, idx))
                required_by.insert(0, fname)
                _parse_make_file(project_root, dir_of_file, fname_inc, required_by, output, output_traceback, file_parts, imports_table)
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
        output_traceback.append((fname, idx))


def _load_make_file(project_root, working_dir, fname, grammar_map, subst, buildsys_builtins, required_by, import_enabled):
    origin = []
    output = []
    output_traceback = []
    file_parts = []
    imports_table = {} if import_enabled else None
    if required_by is not None:
        origin.insert(0, required_by)
    _parse_make_file(project_root, working_dir, fname, origin, output, output_traceback, file_parts, imports_table)
    local_vars = {}
    for var_name in grammar_map:
        var_type = grammar_map[var_name][0]
        var_value = None if var_type is None else var_type()
        local_vars[var_name] = var_value
    if buildsys_builtins is not None:
        local_vars.update(buildsys_builtins)
    tb_parsed, tb_lines = None, None
    try:
        text = '\n'.join(output)
        text_ast = _exec_compile(text, file_parts[0])
        exec(text_ast, {}, local_vars)
    except:
        etype, value, tb = sys.exc_info()
        tb_parsed, tb_lines = _parse_traceback_of_file(etype, value, tb, file_parts[0], output, output_traceback)
        if not tb_parsed:
            raise
    if tb_parsed:
        tb_lines.insert(0, "Can't load makefile: '{}'".format(file_parts[0]))
        raise BuildSystemException('\n'.join(tb_lines))
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

    def set_build_config(self, value):
        self.buildsys_builtins[TAG_BUILDSYS_CONFIG] = value

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
        if not desc.module_type:
            raise BuildSystemException("Can't load makefile: '{}', grammar token '{}' is missed or empty.".format(desc.self_file_parts[0], TAG_GRAMMAR_KEY_MODULE_TYPE))
        if desc.module_type not in TAG_ALL_SUPPORTED_MODULE_TYPES:
            raise BuildSystemException("Can't load makefile: '{}', given value '{}' of grammar token '{}' is not in list of supported values: '{}'".format(
                desc.self_file_parts[0], desc.module_type, TAG_GRAMMAR_KEY_MODULE_TYPE, "', '".join(TAG_ALL_SUPPORTED_MODULE_TYPES)))
        if not desc.module_name:
            raise BuildSystemException("Can't load makefile: '{}', grammar token '{}' is missed or empty.".format(desc.self_file_parts[0], TAG_GRAMMAR_KEY_MODULE_NAME))

        return desc

    def load_build_extension(self, working_dir, required_by):
        project_root = self.subst[TAG_SUBST_PROJECT_ROOT]
        buildsys_builtins = None
        import_enabled = False
        grammar_tokens, _ = _load_make_file(project_root, working_dir, BUILD_MODULE_EXTENSION_FILE, TAG_GRAMMAR_KEYS_EXT_ALL,
            self.subst, buildsys_builtins, required_by, import_enabled)
        desc = BuildDescription(grammar_tokens)
        if not desc.ext_type:
            raise BuildSystemException("Can't load makefile: '{}', grammar token '{}' is missed or empty.".format(desc.self_file_parts[0], TAG_GRAMMAR_KEY_EXT_TYPE))
        if desc.ext_type not in TAG_ALL_SUPPORTED_EXTENTION_TYPES:
            raise BuildSystemException("Can't load makefile: '{}', given value '{}' of grammar token '{}' is not in list of supported values: '{}'".format(
                desc.self_file_parts[0], desc.ext_type, TAG_GRAMMAR_KEY_EXT_TYPE, "', '".join(TAG_ALL_SUPPORTED_EXTENTION_TYPES)))
        if not desc.ext_call_type:
            raise BuildSystemException("Can't load makefile: '{}', grammar token '{}' is missed or empty.".format(desc.self_file_parts[0], TAG_GRAMMAR_KEY_EXT_CALL_TYPE))
        if desc.ext_call_type not in TAG_ALL_SUPPORTED_EXTENTION_CALL_TYPES:
            raise BuildSystemException("Can't load makefile: '{}', given value '{}' of grammar token '{}' is not in list of supported values: '{}'".format(
                desc.self_file_parts[0], desc.ext_call_type, TAG_GRAMMAR_KEY_EXT_CALL_TYPE, "', '".join(TAG_ALL_SUPPORTED_EXTENTION_CALL_TYPES)))
        if not desc.ext_name:
            raise BuildSystemException("Can't load makefile: '{}', grammar token '{}' is missed or empty.".format(desc.self_file_parts[0], TAG_GRAMMAR_KEY_EXT_NAME))
        return desc
