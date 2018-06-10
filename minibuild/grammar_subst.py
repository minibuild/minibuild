import re

from .error_utils import BuildSystemException
from .string_utils import is_string_instance

_RE_PRPROCESS = re.compile(r'\$\{@(\w+)\}')
_PREPROCESSOR_RAW_TYPES = (bool, float, int)


def _preprocess_grammar_string_value(subst_map, fname, var_name, var_value):
    result = var_value
    used_subst = None
    processed = False
    while True:
        if not '${@' in result:
            break
        if used_subst is None:
            used_subst = _RE_PRPROCESS.findall(var_value)
        if processed or not used_subst:
            raise BuildSystemException("Invalid makefile syntax, can't preprocess '{}' variable, got from '{}'."
                "\n  Input: '{}', aborted at line: '{}'."
                .format(var_name, fname, var_value, result))
        for subst in used_subst:
            if subst not in subst_map:
                raise BuildSystemException("Invalid makefile syntax, can't preprocess '{}' variable, got from '{}'."
                    "\n  Input: '{}', aborted at unknown substitution: '{}'."
                    .format(var_name, fname, var_value, subst))
            subst_token = '${@' + subst + '}'
            subst_value = subst_map[subst]
            result = result.replace(subst_token, subst_value)
        processed = True
    return result


def preprocess_grammar_value(subst, fname, expected_var_type, var_name, var_value):
    if expected_var_type is not None:
        if not isinstance(var_value, expected_var_type):
            raise BuildSystemException("Invalid makefile syntax, type of '{}' variable is '{}', but type '{}' is expected, got from '{}'.".format(
                var_name, type(var_value).__name__, expected_var_type.__name__, fname))

    if var_value is None:
        return None

    if isinstance(var_value, _PREPROCESSOR_RAW_TYPES):
        return var_value

    if is_string_instance(var_value):
        return _preprocess_grammar_string_value(subst, fname, var_name, var_value)

    if isinstance(var_value, list):
        lst_result = []
        for lst_item in var_value:
            processed_item = preprocess_grammar_value(subst, fname, None, var_name, lst_item)
            lst_result.append(processed_item)
        return lst_result

    if isinstance(var_value, dict):
        dict_result = {}
        for k in var_value:
            processed_item = preprocess_grammar_value(subst, fname, None, var_name, var_value[k])
            dict_result[k] = processed_item
        return dict_result

    raise BuildSystemException("Invalid makefile syntax, '{}' variable has a content with unknown preprocessor type '{}', got from '{}'.".format(
        var_name, type(var_value).__name__, fname))

    return var_value
