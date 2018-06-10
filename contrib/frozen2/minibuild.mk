#import "@/cpython2/build/pyfreeze"

module_type = 'executable'
module_name = 'minibuild'
build_list = ['main.c', 'minibuild_frozen.c', 'minibuild_frozen_impl.c']
win_console = 1
win_stack_size = 2000000

spec_file = 'freeze.spec'
spec_post_build = ['pyfreeze']
spec_file_entails = {'pyfreeze_export': '_PyImport_FrozenMiniBuild', 'pyfreeze_file_prefix': 'minibuild'}

include_dir_list = [
  '${@project_root}/cpython2/vendor/Include',
]

lib_list = [
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
  '${@project_root}/pyffi',
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
prebuilt_lib_list_linux = ['dl', 'pthread', 'util']
macosx_framework_list = ['CoreFoundation', 'SystemConfiguration']
