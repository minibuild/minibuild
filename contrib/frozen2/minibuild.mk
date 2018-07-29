#pragma os:linux pass   cmdline='--model gcc-xt-linux-x86_64 --public --public-format zip --public-layout flat'
#pragma os:macosx pass  cmdline='--model clang-macosx-x86_64 --public --public-format zip --public-layout flat'
#pragma os:windows pass cmdline='--model mingw-win64         --public --public-format zip --public-layout flat'

#import "@/cpython2/build/pyfreeze"

import os.path

if BUILDSYS_TARGET_PLATFORM == 'macosx':
    public_name = 'minibuild-macosx'
elif BUILDSYS_TARGET_PLATFORM == 'windows':
    if BUILDSYS_TOOLSET_NAME == 'gcc':
        public_name = 'minibuild-mingw-{}'.format(BUILDSYS_TARGET_ARCH)
    elif BUILDSYS_TOOLSET_NAME == 'msvs':
        public_name = 'minibuild-msvs{}-{}'.format(BUILDSYS_TOOLSET_VERSION, BUILDSYS_TARGET_ARCH)
if not public_name:
    public_name = 'minibuild-{}-{}'.format(BUILDSYS_TARGET_PLATFORM, BUILDSYS_TARGET_ARCH)

module_type = 'executable'
module_name = 'minibuild'
build_list = ['main.c', 'minibuild_frozen.c', 'minibuild_frozen_impl.c']
win_stack_size = 2000000

spec_file = 'freeze.spec'
spec_post_build = ['pyfreeze']
spec_file_entails = {'pyfreeze_export': '_PyImport_FrozenMiniBuild', 'pyfreeze_file_prefix': 'minibuild'}

if os.path.isdir(os.path.join(BUILDSYS_PROJECT_ROOT_DIRNAME, 'cpython2/config')):
    include_dir_list += [
      '${@project_root}/cpython2/config',
    ]


include_dir_list += [
  '${@project_root}/cpython2/vendor/Include',
]


if os.path.isdir(os.path.join(BUILDSYS_PROJECT_ROOT_DIRNAME, 'pyffi')):
    lib_list += ['${@project_root}/pyffi']
elif os.path.isdir(os.path.join(BUILDSYS_PROJECT_ROOT_DIRNAME, 'libffi')):
    lib_list += ['${@project_root}/libffi']

lib_list += [
  '${@project_root}/cpython2/build/core/static',
  '${@project_root}/cpython2/build/stdlib/static',
  '${@project_root}/cpython2/build/modules/ctypes/static',
  '${@project_root}/cpython2/build/modules/elementtree/static',
  '${@project_root}/cpython2/build/modules/hashlib/static',
  '${@project_root}/cpython2/build/modules/multiprocessing/static',
  '${@project_root}/cpython2/build/modules/socket/static',
  '${@project_root}/cpython2/build/modules/ssl/static',
  '${@project_root}/cpython2/build/modules/sqlite/static',
  '${@project_root}/cpython2/build/modules/pyexpat/static',
  '${@project_root}/cpython2/build/modules/select/static',
  '${@project_root}/cpython2/build/modules/unicodedata/static',
  '${@project_root}/cpython2/build/modules/bz2/static',
  '${@project_root}/cpython2/build/modules/crypt/static',
  '${@project_root}/zlib',
  '${@project_root}/openssl/build/crypto_static',
  '${@project_root}/openssl/build/ssl_static',
  '${@project_root}/openssl_posix_crypt/contrib/static',
  '${@project_root}/sqlcipher/src',
  '${@project_root}/bzip2',
]

explicit_depends = ['resource']
zip_section = '${@project_output}/obj/minibuild_zrc/noarch/zsection.zip'

definitions_windows = ['Py_NO_ENABLE_SHARED']
prebuilt_lib_list_windows = ['advapi32', 'user32', 'shell32', 'ole32', 'oleaut32', 'crypt32', 'ws2_32']
prebuilt_lib_list_linux = ['dl', 'pthread', 'util', 'nsl']
macosx_framework_list = ['CoreFoundation', 'SystemConfiguration']
