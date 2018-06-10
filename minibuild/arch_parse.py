def parse_arch_specific_tokens(value, arch_supported, allow_empty_tokens, supported_tokens=None, arch_substitutions=None):
    arch_result = []
    arch_tokens = {}
    bits = value.split(',')
    for bit in bits:
        arch_token = ''
        arch_parsed = None
        if ':' in bit:
            arch_value, arch_token = bit.split(':', 1)
            arch_token = arch_token.strip()
            arch_parsed = arch_value
        else:
            arch_parsed = bit
        if arch_substitutions and arch_parsed in arch_substitutions:
            arch_parsed = arch_substitutions[arch_parsed]
        if arch_parsed not in arch_supported:
            return None, None
        if not arch_token and not allow_empty_tokens:
            return None, None
        if arch_token and supported_tokens:
            if arch_token not in supported_tokens:
                return None, None
        if arch_parsed not in arch_result:
            arch_result.append(arch_parsed)
        arch_tokens[arch_parsed] = arch_token
    return arch_result, arch_tokens
