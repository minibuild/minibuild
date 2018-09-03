import os.path

from .constants import *
from .error_utils import BuildSystemException
from .grammar_subst import preprocess_grammar_value
from .os_utils import load_py_object, normalize_path_optional
from .string_utils import is_string_instance


def _target_os_equal(value, toolset_model):
    if toolset_model.platform_name == value:
        return True
    return False


def _target_os_not_equal(value, toolset_model):
    return not _target_os_equal(value, toolset_model)


def _target_os_alias_equal(value, toolset_model):
    if not toolset_model.platform_alias:
        return False
    if toolset_model.platform_alias == value:
        return True
    return False


def _target_os_alias_not_equal(value, toolset_model):
    return not _target_os_alias_equal(value, toolset_model)


_SPEC_CONDITION_MATCH = {
    TAG_GRAMMAR_SPEC_ATTR_IF_OS : _target_os_equal,
    TAG_GRAMMAR_SPEC_ATTR_IF_NOT_OS : _target_os_not_equal,
    TAG_GRAMMAR_SPEC_ATTR_IF_OS_ALIAS: _target_os_alias_equal,
    TAG_GRAMMAR_SPEC_ATTR_IF_NOT_OS_ALIAS: _target_os_alias_not_equal,
}

def _apply_rule_filter(spec_fname, rules, current_model):
    if not rules:
        return rules
    filtered_rules = []
    for idx in range(len(rules)):
        if is_string_instance(rules[idx]):
            continue
        if isinstance(rules[idx], list) and len(rules[idx]) == 2 and is_string_instance(rules[idx][0]) and isinstance(rules[idx][1], dict):
            passed = True
            for cond_key in rules[idx][1]:
                cond_value = rules[idx][1][cond_key]
                match = _SPEC_CONDITION_MATCH.get(cond_key)
                if not callable(match):
                    raise BuildSystemException("Can't parse spec-file '{}', got malformed condition key '{}' in spec entry:\n    {}".format(spec_fname, cond_key, rules[idx]))
                if passed:
                    passed = match(cond_value, current_model)
            filtered_rules.insert(0, (idx, passed))
        else:
            raise BuildSystemException("Can't parse spec-file '{}', got malformed spec entry:\n    {}".format(spec_fname, rules[idx]))

    for idx, passed in filtered_rules:
        if passed:
            rules[idx] = rules[idx][0]
        else:
            del rules[idx]

    return rules


def _pass_exclusion_constraints(spec_fname, arcpath, arcname, excl_rules, current_model):
    rule_arcname_equals         = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCNAME_EQUALS), current_model)
    rule_arcname_startswith     = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCNAME_STARTSWITH), current_model)
    rule_arcname_endswith       = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCNAME_ENDSWITH), current_model)
    rule_arcpath_equals         = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCPATH_EQUALS), current_model)
    rule_arcpath_startswith     = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCPATH_STARTSWITH), current_model)
    rule_arcpath_endswith       = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_ARCPATH_STARTSWITH), current_model)
    rule_arcname_not_equals     = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCNAME_EQUALS), current_model)
    rule_arcname_not_startswith = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCNAME_STARTSWITH), current_model)
    rule_arcname_not_endswith   = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCNAME_ENDSWITH), current_model)
    rule_arcpath_not_equals     = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCPATH_EQUALS), current_model)
    rule_arcpath_not_startswith = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCPATH_STARTSWITH), current_model)
    rule_arcpath_not_endswith   = _apply_rule_filter(spec_fname, excl_rules.get(TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCPATH_ENDSWITH), current_model)

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


def _collect_files_in_spec(spec_fname, dir_path, dir_arcname, excl_dirs, excl_files, current_model, catalog):
    for item in sorted(os.listdir(dir_path)):
        item_path = os.path.join(dir_path, item)
        if dir_arcname:
            item_arcname = '/'.join([dir_arcname, item])
        else:
            item_arcname = item
        if os.path.isdir(item_path):
            if _pass_exclusion_constraints(spec_fname, item_arcname, item, excl_dirs, current_model):
                _collect_files_in_spec(spec_fname, item_path, item_arcname, excl_dirs, excl_files, current_model, catalog)
        else:
            if _pass_exclusion_constraints(spec_fname, item_arcname, item, excl_files, current_model):
                catalog.append((item_path, item_arcname))


def parse_spec_file(fname, grammar_substitutions, current_model):
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
            _collect_files_in_spec(spec_fname, home_dir, prefix, excl_dirs, excl_files, current_model, catalog)
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
