BUILD_CONFIG_RELEASE = 'release'
BUILD_CONFIG_DEBUG = 'debug'
BUILD_CONFIG_ALL = [BUILD_CONFIG_RELEASE, BUILD_CONFIG_DEBUG]

BUILD_CONFIG_DEFAULT_BOOTSTRAP_DIR = 'output/bootstrap'
BUILD_CONFIG_DEFAULT_OBJ_DIR       = 'output/obj'
BUILD_CONFIG_DEFAULT_EXE_DIR       = 'output/exe'
BUILD_CONFIG_DEFAULT_EXT_DIR       = 'output/ext'
BUILD_CONFIG_DEFAULT_LIB_DIR       = 'output/lib'
BUILD_CONFIG_DEFAULT_SHARED_DIR    = 'output/shared'
BUILD_CONFIG_DEFAULT_PUBLIC_DIR    = 'output/public'


BUILD_TYPE_UNKNOWN = 0
BUILD_TYPE_C       = 1
BUILD_TYPE_CPP     = 2
BUILD_TYPE_ASM     = 3

BUILD_RET_TYPE_LIB      = 1
BUILD_RET_TYPE_PDB      = 2
BUILD_RET_TYPE_EXE      = 3
BUILD_RET_TYPE_DLL      = 4
BUILD_RET_TYPE_ZIP      = 5
BUILD_RET_TYPE_RESOURCE = 6

BUILD_RET_ATTR_DEFAULT          = 0x00000000
BUILD_RET_ATTR_FLAG_EXECUTABLE  = 0x00000001

TAG_SUBST_PROJECT_ROOT = 'project_root'

BUILD_SYSTEM_CONFIG_FILE = 'minibuild.ini'
BUILD_MODULE_DESCRIPTION_FILE = 'minibuild.mk'
BUILD_MODULE_EXTENSION_FILE = 'minibuild.ext'
POST_BUILD_OBJ_STAMP_FILE = 'postbuild.stamp'

TAG_INI_CONF_MAIN = 'MINIBUILD'
TAG_INI_CONF_MAIN_NATIVE = 'MINIBUILD-NATIVE'
TAG_INI_TOOLSET_MODULE = 'module'
TAG_INI_TOOLSET_CONFIG = 'config'
TAG_INI_NATIVE_MODELS_DETECTION_MODE = 'native-models'

TAG_NATIVE_MODELS_DETECTION_DISABLED = 'disabled'
TAG_NATIVE_MODELS_DETECTION_OPTIONAL = 'optional'
TAG_NATIVE_MODELS_DETECTION_AUTO = 'auto'
TAG_NATIVE_MODELS_DETECTION_CONFIG = 'config'

TAG_NATIVE_MODELS_DETECTION_ALL_MODES = [
    TAG_NATIVE_MODELS_DETECTION_DISABLED,
    TAG_NATIVE_MODELS_DETECTION_OPTIONAL,
    TAG_NATIVE_MODELS_DETECTION_AUTO,
    TAG_NATIVE_MODELS_DETECTION_CONFIG,
]

TAG_CFG_DIR_PROJECT_ROOT = 'dir-project-root'
TAG_CFG_PROJECT_ROOT_COMMON_PREFIX = 'dir-project-common-prefix'
TAG_CFG_DIR_BOOTSTRAP = 'dir-bootstrap'
TAG_CFG_DIR_OBJ = 'dir-obj'
TAG_CFG_DIR_EXE = 'dir-exe'
TAG_CFG_DIR_EXT = 'dir-ext'
TAG_CFG_DIR_LIB = 'dir-lib'
TAG_CFG_DIR_PUBLIC = 'dir-public'
TAG_CFG_DIR_SHARED = 'dir-shared'
TAG_CFG_OBJ_SUFFIX = 'obj-suffix'
TAG_CFG_PDB_SUFFIX = 'pdb-suffix'
TAG_CFG_DEP_SUFFIX = 'dep-suffix'

TAG_DIR_NOARCH = 'noarch'

TAG_ARCH_X86     = 'x86'
TAG_ARCH_X86_64  = 'x86_64'
TAG_ARCH_ARM     = 'arm'
TAG_ARCH_ARM64   = 'arm64'

TAG_ALL_KNOWN_ARCH_LIST = [
    TAG_ARCH_X86,
    TAG_ARCH_X86_64,
    TAG_ARCH_ARM,
    TAG_ARCH_ARM64,
]

TAG_ALL_KNOWN_MINGW_ARCH_LIST = [
    TAG_ARCH_X86,
    TAG_ARCH_X86_64,
]

TAG_PLATFORM_WINDOWS     = 'windows'
TAG_PLATFORM_LINUX       = 'linux'
TAG_PLATFORM_MACOSX      = 'macosx'
TAG_PLATFORM_ALIAS_POSIX = 'posix'

TAG_BUILDSYS_TARGET_PLATFORM = 'BUILDSYS_TARGET_PLATFORM'
TAG_BUILDSYS_TOOLSET_NAME = 'BUILDSYS_TOOLSET_NAME'

TAG_GRAMMAR_VALUE_MODULE_TYPE_EXE        = 'executable'
TAG_GRAMMAR_VALUE_MODULE_TYPE_LIB_STATIC = 'lib-static'
TAG_GRAMMAR_VALUE_MODULE_TYPE_LIB_SHARED = 'lib-shared'
TAG_GRAMMAR_VALUE_MODULE_TYPE_COMPOSITE  = 'composite'
TAG_GRAMMAR_VALUE_MODULE_TYPE_ZIP_FILE   = 'zip-file'
TAG_GRAMMAR_VALUE_MODULE_TYPE_DOWNLOAD   = 'download'

TAG_ALL_MODULE_TYPES_NOARCH = [
    TAG_GRAMMAR_VALUE_MODULE_TYPE_ZIP_FILE,
    TAG_GRAMMAR_VALUE_MODULE_TYPE_DOWNLOAD,
]

TAG_GRAMMAR_SPEC_ATTR_DIRNANE                     = 'dirname'
TAG_GRAMMAR_SPEC_ATTR_CATALOG                     = 'catalog'
TAG_GRAMMAR_SPEC_ATTR_PREFIX                      = 'prefix'
TAG_GRAMMAR_SPEC_ATTR_EXCLUDE_DIR                 = 'exclude-dir'
TAG_GRAMMAR_SPEC_ATTR_EXCLUDE_FILE                = 'exclude-file'
TAG_GRAMMAR_SPEC_ATTR_IF_ARCNAME_EQUALS           = 'if-arcname-equals'
TAG_GRAMMAR_SPEC_ATTR_IF_ARCNAME_STARTSWITH       = 'if-arcname-startswith'
TAG_GRAMMAR_SPEC_ATTR_IF_ARCNAME_ENDSWITH         = 'if-arcname-endswith'
TAG_GRAMMAR_SPEC_ATTR_IF_ARCPATH_EQUALS           = 'if-arcpath-equals'
TAG_GRAMMAR_SPEC_ATTR_IF_ARCPATH_STARTSWITH       = 'if-arcpath-startswith'
TAG_GRAMMAR_SPEC_ATTR_IF_ARCPATH_STARTSWITH       = 'if-arcpath-endswith'
TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCNAME_EQUALS       = 'if-not-arcname-equals'
TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCNAME_STARTSWITH   = 'if-not-arcname-startswith'
TAG_GRAMMAR_SPEC_ATTR_IF_NOT_NOT_ARCNAME_ENDSWITH = 'if-not-arcname-endswith'
TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCPATH_EQUALS       = 'if-not-arcpath-equals'
TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCPATH_STARTSWITH   = 'if-not-arcpath-startswith'
TAG_GRAMMAR_SPEC_ATTR_IF_NOT_ARCPATH_ENDSWITH     = 'if-not-arcpath-endswith'

TAG_GRAMMAR_COMPOSITE_ITEM_SUBDIR = 'subdir'
TAG_GRAMMAR_COMPOSITE_ITEM_REPLACE_EXT = 'replace-ext'
TAG_GRAMMAR_COMPOSITE_ITEM_STRIP_FNANE_PREFIX = 'strip-filename-prefix'
TAG_GRAMMAR_COMPOSITE_ITEM_IS_SPEC_FILE = 'spec_file'
TAG_GRAMMAR_COMPOSITE_ITEM_IS_FILE = 'file'
TAG_GRAMMAR_COMPOSITE_ITEM_IS_EXECUTABLE = 'executable'

TAG_GRAMMAR_COMPOSITE_ITEM_STR_PROPERTIES = [
    TAG_GRAMMAR_COMPOSITE_ITEM_SUBDIR,
    TAG_GRAMMAR_COMPOSITE_ITEM_REPLACE_EXT,
    TAG_GRAMMAR_COMPOSITE_ITEM_STRIP_FNANE_PREFIX,
]

TAG_GRAMMAR_BUILTIN_SELF_FILE_PARTS        = 'self_file_parts'
TAG_GRAMMAR_BUILTIN_SELF_DIRNAME           = 'self_dirname'

TAG_GRAMMAR_KEY_MODULE_TYPE                  = 'module_type'
TAG_GRAMMAR_KEY_MODULE_NAME                  = 'module_name'
TAG_GRAMMAR_KEY_EXE_NAME                     = 'exe_name'
TAG_GRAMMAR_KEY_BUILD_LIST                   = 'build_list'
TAG_GRAMMAR_KEY_SYMBOL_VISIBILITY_DEFAULT    = 'symbol_visibility_default'
TAG_GRAMMAR_KEY_WIN_CONSOLE                  = 'win_console'
TAG_GRAMMAR_KEY_WIN_STACK_SIZE               = 'win_stack_size'
TAG_GRAMMAR_KEY_WMAIN                        = 'wmain'
TAG_GRAMMAR_KEY_ASM_IS_NASM                  = 'nasm'
TAG_GRAMMAR_KEY_INC_DIR_LIST                 = 'include_dir_list'
TAG_GRAMMAR_KEY_ASM_INC_DIR_LIST             = 'asm_include_dir_list'
TAG_GRAMMAR_KEY_SRC_SEARCH_DIR_LIST          = 'src_search_dir_list'
TAG_GRAMMAR_KEY_ASM_SEARCH_DIR_LIST          = 'asm_search_dir_list'
TAG_GRAMMAR_KEY_LINK_DIR_LIST                = 'lib_list'
TAG_GRAMMAR_KEY_PREBULT_LIB_LIST             = 'prebuilt_lib_list'
TAG_GRAMMAR_KEY_MACOSX_FRAMEWORK_LIST        = 'macosx_framework_list'
TAG_GRAMMAR_KEY_MACOSX_INSTALL_NAME_OPTIONS  = 'macosx_install_name_options'
TAG_GRAMMAR_KEY_DEFINITIONS_LIST             = 'definitions'
TAG_GRAMMAR_KEY_ASM_DEFINITIONS_LIST         = 'asm_definitions'
TAG_GRAMMAR_KEY_EXPORT_LIST                  = 'export'
TAG_GRAMMAR_KEY_EXPORT_DEF_FILE              = 'export_def_file'
TAG_GRAMMAR_KEY_EXPORT_WINAPI_ONLY           = 'export_winapi_only'
TAG_GRAMMAR_KEY_DISABLED_WARNINGS            = 'disabled_warnings'
TAG_GRAMMAR_KEY_COMPOSITE_SPEC               = 'composite_spec'
TAG_GRAMMAR_KEY_SPEC_FILE                    = 'spec_file'
TAG_GRAMMAR_KEY_ZIP_FILE                     = 'zip_file'
TAG_GRAMMAR_KEY_POST_BUILD                   = 'post_build'
TAG_GRAMMAR_KEY_SPEC_POST_BUILD              = 'spec_post_build'
TAG_GRAMMAR_KEY_SPEC_FILE_ENTAILS            = 'spec_file_entails'
TAG_GRAMMAR_KEY_DOWNLOAD_LIST                = 'download_list'
TAG_GRAMMAR_KEY_EXPLICIT_DEPENDS             = 'explicit_depends'
TAG_GRAMMAR_KEY_ZIP_SECTION                  = 'zip_section'


TAG_GRAMMAR_SPEC_FILE_ENTAILS = [
    TAG_GRAMMAR_KEY_ZIP_FILE,
]

GRAMMAR_PREPROCESS_ENABLED  = True
GRAMMAR_PREPROCESS_DISABLED = False

TAG_GRAMMAR_KEYS_COMMON = {
    TAG_GRAMMAR_KEY_MODULE_TYPE                  : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_MODULE_NAME                  : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_EXE_NAME                     : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_BUILD_LIST                   : (list, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_EXPORT_WINAPI_ONLY           : (list, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_SYMBOL_VISIBILITY_DEFAULT    : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_WIN_CONSOLE                  : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_WIN_STACK_SIZE               : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_WMAIN                        : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_ASM_IS_NASM                  : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_INC_DIR_LIST                 : (list, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_ASM_INC_DIR_LIST             : (list, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_SRC_SEARCH_DIR_LIST          : (list, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_ASM_SEARCH_DIR_LIST          : (list, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_LINK_DIR_LIST                : (list, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_PREBULT_LIB_LIST             : (list, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_MACOSX_FRAMEWORK_LIST        : (list, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_MACOSX_INSTALL_NAME_OPTIONS  : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_DEFINITIONS_LIST             : (list, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_ASM_DEFINITIONS_LIST         : (list, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_EXPORT_DEF_FILE              : (None, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_EXPORT_LIST                  : (list, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_DISABLED_WARNINGS            : (list, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_COMPOSITE_SPEC               : (list, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_SPEC_FILE                    : (None, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_ZIP_FILE                     : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_POST_BUILD                   : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_SPEC_POST_BUILD              : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_SPEC_FILE_ENTAILS            : (dict, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_DOWNLOAD_LIST                : (list, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_EXPLICIT_DEPENDS             : (list, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_ZIP_SECTION                  : (None, GRAMMAR_PREPROCESS_ENABLED),
}


TAG_GRAMMAR_KEY_EXT_TYPE                   = 'ext_type'
TAG_GRAMMAR_KEY_EXT_NAME                   = 'ext_name'
TAG_GRAMMAR_KEY_EXT_NATIVE_DEPENDS         = 'ext_native_depends'
TAG_GRAMMAR_KEY_EXT_OBJ_DIR_NATIVE_AS_VAR  = 'ext_obj_dir_native_as_var'
TAG_GRAMMAR_KEY_EXT_VARS_REQUIRED          = 'ext_vars_required'
TAG_GRAMMAR_KEY_EXT_LOCAL_VARS_REQUIRED    = 'ext_local_vars_required'
TAG_GRAMMAR_KEY_EXT_CALL_CMDLINE           = 'ext_call_cmdline'

TAG_GRAMMAR_KEYS_EXT_ALL = {
    TAG_GRAMMAR_KEY_EXT_TYPE                     : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_EXT_NAME                     : (None, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_EXT_NATIVE_DEPENDS           : (list, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_EXT_OBJ_DIR_NATIVE_AS_VAR    : (list, GRAMMAR_PREPROCESS_ENABLED),
    TAG_GRAMMAR_KEY_EXT_VARS_REQUIRED            : (list, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_EXT_LOCAL_VARS_REQUIRED      : (list, GRAMMAR_PREPROCESS_DISABLED),
    TAG_GRAMMAR_KEY_EXT_CALL_CMDLINE             : (None, GRAMMAR_PREPROCESS_DISABLED),
}

TAG_GRAMMAR_KEYS_EXT_FORCE_NATIVE_MODEL_SUPPORT = [
    TAG_GRAMMAR_KEY_EXT_NATIVE_DEPENDS,
    TAG_GRAMMAR_KEY_EXT_OBJ_DIR_NATIVE_AS_VAR,
]

TAG_GRAMMAR_VALUE_EXT_TYPE_POST_BUILD             = 'post-build'
TAG_GRAMMAR_VALUE_EXT_TYPE_SPEC_POST_BUILD        = 'spec-post-build'

TAG_GRAMMAR_VALUE_EXT_VAR_DIR_HERE                       = 'DIR_HERE'
TAG_GRAMMAR_VALUE_EXT_VAR_EXE_SUFFIX                     = 'EXE_SUFFIX'
TAG_GRAMMAR_VALUE_EXT_VAR_OS_SEP                         = 'OS_SEP'
TAG_GRAMMAR_VALUE_EXT_VAR_BUILDSYS_TARGET_OBJ_DIR        = 'BUILDSYS_TARGET_OBJ_DIR'
TAG_GRAMMAR_VALUE_EXT_VAR_BUILDSYS_TARGET_OBJ_NOARCH_DIR = 'BUILDSYS_TARGET_OBJ_NOARCH_DIR'
TAG_GRAMMAR_VALUE_EXT_VAR_BUILDSYS_TARGET_SRC_DIR        = 'BUILDSYS_TARGET_SRC_DIR'


def _extend_build_list_grammar_keys():
    result = {}
    defaults = TAG_GRAMMAR_KEYS_COMMON[TAG_GRAMMAR_KEY_BUILD_LIST]
    for platform in (
            TAG_PLATFORM_WINDOWS,
            TAG_PLATFORM_LINUX,
            TAG_PLATFORM_MACOSX,
            TAG_PLATFORM_ALIAS_POSIX,
            ):
        key = '_'.join([TAG_GRAMMAR_KEY_BUILD_LIST, platform])
        result[key] = defaults
        for arch in TAG_ALL_KNOWN_ARCH_LIST:
            subkey = '_'.join([key, arch])
            result[subkey] = defaults
    return result


def _extend_src_search_dir_list_grammar_keys():
    result = {}
    for tag in [TAG_GRAMMAR_KEY_SRC_SEARCH_DIR_LIST, TAG_GRAMMAR_KEY_ASM_SEARCH_DIR_LIST]:
        defaults = TAG_GRAMMAR_KEYS_COMMON[tag]
        for platform in (
                TAG_PLATFORM_WINDOWS,
                TAG_PLATFORM_LINUX,
                TAG_PLATFORM_MACOSX,
                TAG_PLATFORM_ALIAS_POSIX,
                ):
            key = '_'.join([tag, platform])
            result[key] = defaults
            for arch in TAG_ALL_KNOWN_ARCH_LIST:
                subkey = '_'.join([key, arch])
                result[subkey] = defaults
    return result


def _extend_prebuilt_lib_list_grammar_keys():
    result = {}
    defaults = TAG_GRAMMAR_KEYS_COMMON[TAG_GRAMMAR_KEY_PREBULT_LIB_LIST]
    for platform in (
            TAG_PLATFORM_WINDOWS,
            TAG_PLATFORM_LINUX,
            TAG_PLATFORM_MACOSX,
            TAG_PLATFORM_ALIAS_POSIX,
            ):
        key = '_'.join([TAG_GRAMMAR_KEY_PREBULT_LIB_LIST, platform])
        result[key] = defaults
    return result


def _extend_definitions_grammar_keys():
    result = {}
    for tag in [TAG_GRAMMAR_KEY_DEFINITIONS_LIST, TAG_GRAMMAR_KEY_ASM_DEFINITIONS_LIST]:
        defaults = TAG_GRAMMAR_KEYS_COMMON[tag]
        for platform in (
                TAG_PLATFORM_WINDOWS,
                TAG_PLATFORM_LINUX,
                TAG_PLATFORM_MACOSX,
                TAG_PLATFORM_ALIAS_POSIX,
                ):
            key = '_'.join([tag, platform])
            result[key] = defaults
            for arch in TAG_ALL_KNOWN_ARCH_LIST:
                subkey = '_'.join([key, arch])
                result[subkey] = defaults
    return result


def _extend_grammar_keys():
    result = {}
    result.update(TAG_GRAMMAR_KEYS_COMMON)
    result.update(_extend_build_list_grammar_keys())
    result.update(_extend_src_search_dir_list_grammar_keys())
    result.update(_extend_prebuilt_lib_list_grammar_keys())
    result.update(_extend_definitions_grammar_keys())
    return result

TAG_GRAMMAR_KEYS_ALL = _extend_grammar_keys()
