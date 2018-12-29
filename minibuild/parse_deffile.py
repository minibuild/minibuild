from .error_utils import BuildSystemException


def load_export_list_from_def_file(def_file, winapi_only, for_winapi):
    export_section_found = False
    export_list = []
    lines = [line.rstrip('\r\n') for line in open(def_file)]
    line_number = 0
    inside_export = False
    for line in lines:
        line_number += 1
        text = line.lstrip()
        if not text or text[0] == ';':
            continue
        tokens = text.split()
        line_is_keyword = False
        if len(line) == len(text):
            line_is_keyword = True
        if line_is_keyword:
            if inside_export:
                inside_export = False
            elif len(tokens) == 1 and tokens[0] == 'EXPORTS':
                if export_section_found:
                    raise BuildSystemException("'EXPORTS' section found more then once inside DEF file: '{}'".format(def_file))
                export_section_found = True
                inside_export = True
            continue
        if inside_export:
            if tokens and not tokens[0].startswith('@'):
                symbol = tokens[0]
                symbol_enabled = True
                if winapi_only and not for_winapi:
                    if symbol in winapi_only:
                        symbol_enabled = False
                if symbol_enabled:
                    export_list.append(symbol)
    if not export_section_found:
        raise BuildSystemException("'EXPORTS' section not found inside DEF file: '{}'".format(def_file))
    if not export_list:
        raise BuildSystemException("Cannot load symbols information from 'EXPORTS' section inside DEF file: '{}'".format(def_file))
    return export_list
