import os.path

from .constants import *
from .error_utils import BuildSystemException
from .grammar_subst import preprocess_grammar_value
from .os_utils import load_py_object, normalize_path_optional


def _pass_exclusion_constraints(arcpath, arcname, excl_rules):
    rule_arcname_equals         = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCNAME_EQUALS)
    rule_arcname_startswith     = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCNAME_STARTSWITH)
    rule_arcname_endswith       = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCNAME_ENDSWITH)
    rule_arcpath_equals         = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCPATH_EQUALS)
    rule_arcpath_startswith     = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCPATH_STARTSWITH)
    rule_arcpath_endswith       = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCPATH_STARTSWITH)
    rule_arcname_not_equals     = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCNAME_EQUALS)
    rule_arcname_not_startswith = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCNAME_STARTSWITH)
    rule_arcname_not_endswith   = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCNAME_ENDSWITH)
    rule_arcpath_not_equals     = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCPATH_EQUALS)
    rule_arcpath_not_startswith = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCPATH_STARTSWITH)
    rule_arcpath_not_endswith   = excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCPATH_ENDSWITH)

    if rule_arcname_equals:
        for r in rule_arcname_equals:
            if r == arcname:
                return False
    if rule_arcname_startswith:
        for r in rule_arcname_startswith:
            if arcname.startswith(r):
                return False
    if rule_arcname_endswith:
        for r in rule_arcname_endswith:
            if arcname.endswith(r):
                return False
    if rule_arcname_not_equals:
        for r in rule_arcname_not_equals:
            if r != arcname:
                return False
    if rule_arcname_not_startswith:
        for r in rule_arcname_not_startswith:
            if not arcname.startswith(r):
                return False
    if rule_arcname_not_endswith:
        for r in rule_arcname_not_endswith:
            if not arcname.endswith(r):
                return False
    if rule_arcpath_equals:
        for r in rule_arcpath_equals:
            if r == arcpath:
                return False
    if rule_arcpath_startswith:
        for r in rule_arcpath_startswith:
            if arcpath.startswith(r):
                return False
    if rule_arcpath_endswith:
        for r in rule_arcpath_endswith:
            if arcpath.endswith(r):
                return False
    if rule_arcpath_not_equals:
        for r in rule_arcpath_not_equals:
            if r != arcpath:
                return False
    if rule_arcpath_not_startswith:
        for r in rule_arcpath_not_startswith:
            if not arcpath.startswith(r):
                return False
    if rule_arcpath_not_endswith:
        for r in rule_arcpath_not_endswith:
            if not arcpath.endswith(r):
                return False
    return True


def _collect_files_in_spec(dir_path, dir_arcname, excl_dirs, excl_files, catalog):
    for item in sorted(os.listdir(dir_path)):
        item_path = os.path.join(dir_path, item)
        if dir_arcname:
            item_arcname = '/'.join([dir_arcname, item])
        else:
            item_arcname = item
        if os.path.isdir(item_path):
            if _pass_exclusion_constraints(item_arcname, item, excl_dirs):
                _collect_files_in_spec(item_path, item_arcname, excl_dirs, excl_files, catalog)
        else:
            if _pass_exclusion_constraints(item_arcname, item, excl_files):
                catalog.append((item_path, item_arcname))


def parse_spec_file(fname, grammar_substitutions):
    spec_fname = os.path.normpath(fname)
    if not os.path.isabs(spec_fname):
         raise BuildSystemException("Can't parse spec-file, given path '{}' is not an absolute pathname".format(fname))
    if not os.path.exists(spec_fname):
        raise BuildSystemException("Can't parse spec-file, file not found '{}'.".format(spec_fname))
    catalog_spec_object = load_py_object(spec_fname)
    catalog_spec = preprocess_grammar_value(grammar_substitutions, fname, list, '<spec>', catalog_spec_object)
    landmark_dir = os.path.dirname(spec_fname)

    if not isinstance(catalog_spec, list) or not catalog_spec:
        raise BuildSystemException("Can't parse spec-file '{}', content of file is not a non-empty list.".format(spec_fname))
    catalog = []
    for catalog_entry in catalog_spec:
        if not isinstance(catalog_entry, dict):
            raise BuildSystemException("Can't parse spec-file '{}', list entry is not a dict.".format(spec_fname))
        home_dir_ref = catalog_entry.get(TAG_GRAMMAR_SPEC_ATTR_DIRNANE, landmark_dir)
        home_dir = normalize_path_optional(home_dir_ref, landmark_dir)
        if not os.path.isdir(home_dir):
            raise BuildSystemException("Can't parse spec-file '{}', directory given in spec '{}' not found.".format(spec_fname, home_dir))
        prefix = catalog_entry.get(TAG_GRAMMAR_SPEC_ATTR_PREFIX, '')
        explicit_files_list = catalog_entry.get(TAG_GRAMMAR_SPEC_ATTR_CATALOG)
        if explicit_files_list is None:
            excl_dirs = catalog_entry.get(TAG_GRAMMAR_SPEC_ATTR_EXCLUDE_DIR, {})
            excl_files = catalog_entry.get(TAG_GRAMMAR_SPEC_ATTR_EXCLUDE_FILE, {})
            _collect_files_in_spec(home_dir, prefix, excl_dirs, excl_files, catalog)
        else:
            if not isinstance(explicit_files_list, list):
                raise BuildSystemException("Can't parse spec-file '{}', got malformed spec entry.".format(spec_fname))
            for entry in explicit_files_list:
                xpl_entry_path = normalize_path_optional(entry, home_dir)
                if not os.path.isfile(xpl_entry_path):
                    raise BuildSystemException("Can't parse spec-file '{}', final file '{}' in catalog not found.".format(spec_fname, xpl_entry_path))
                if prefix:
                    item_arcname = '/'.join([prefix, entry])
                else:
                    item_arcname = entry
                catalog.append((xpl_entry_path, item_arcname))
    if not catalog:
        raise BuildSystemException("Can't parse spec-file '{}', final catalog is empty.".format(spec_fname))
    return catalog
