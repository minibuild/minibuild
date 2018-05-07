import sys
if sys.version_info.major < 3:
    import ConfigParser as configparser
else:
    import configparser

def load_ini_config(path):
    config = configparser.RawConfigParser()
    config.read(path)
    return config


def get_ini_conf_boolean0(config, section, option, default=None):
    if not config.has_option(section, option):
        return default
    return config.getboolean(section, option)


def get_ini_conf_string1(config, section, option):
    return config.get(section, option).strip()


def get_ini_conf_string0(config, section, option, default=None):
    if not config.has_option(section, option):
        return default
    return get_ini_conf_string1(config, section, option)


def get_ini_conf_strings(config, section, option):
    return config.get(section, option).split()


def get_ini_conf_strings_optional(config, section, option):
    if not config.has_option(section, option):
        return []
    return get_ini_conf_strings(config, section, option)
