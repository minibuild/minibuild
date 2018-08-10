# MiniBuild tutorial
[Vitaly Murashev](https://www.linkedin.com/in/vitaly-murashev/)
## Introduction
**MiniBuild** build system is a pure Python package aimed to build executables, static and shared libraries from C, C++ and ASM source files. Build process can be launched from any directory containing a `minibuild.mk` file. This file describes what type of binary is going to be built and its dependencies on other modules inside a directory tree of your project.
## Glossary
### minibuild.ini
A file used to configure the build system for your project. It prescribes what compiler toolchain is used for each target platform. A directory where this file located is treated as `project-root` directory.
### project-root directory
A directory being treated as `project-root`. Build system expects that all source files held somewhere inside it. Moreover `minibuild.ini` file is supposed to be placed there.
### output directory
A directory holding the output of the build system. The build system attempts to isolate all file modifications to this directory. Its path is `<project-root>/output`.
## minibuild.mk - Grammar reference
Build-system treats `minibuild.mk` file as a generic description of a module being built. While this file remains a module  written in the Python programming language, it is supposed to have some predefined global variables which are picked up and interpreted directly by the build system framework. These variables are also mentioned below as _grammar tokens_.  

Some _grammar tokens_ are **_ISA_ (instruction set architecture) extendable**. So if for example grammar token **var** marked as **_ISA extendable_**, than the following grammar tokens are supported as well: **var_linux, var_linux_arm, var_linux_arm64, var_linux_x86, var_linux_x86_64, var_macosx, var_macosx_arm, var_macosx_arm64, var_macosx_x86, var_macosx_x86_64, var_posix, var_posix_arm, var_posix_arm64, var_posix_x86, var_posix_x86_64, var_windows, var_windows_arm, var_windows_arm64, var_windows_x86, var_windows_x86_64**

Some other _grammar tokens_ are **platform extendable**. So if for example grammar token **var** marked as **platform extendable**, than the following grammar tokens are supported as well: **var_linux, var_macosx, var_posix, var_windows**

* **module_type**
  _string_, possible values: `executable`, `lib-static`, `lib-shared`,  `composite`, `zip-file`, `download`.  
  
* **module_name**
  _string_  
  The name of module being built.  
  
* **exe_name**
  _string_, effective when _module_type='executable'_  
  The file name of executable binary being built. When this option is not given, then value of the option `module_name` is used instead.  
  
*  **public_name**
  The name of zip-archive for publishing, when given it is used instead of `module_name`.  
  
* **build_list**
  _list of strings_  
  The list of file names (not paths) of which describing module consists of.  
  ISA extensions: **build_list_linux, build_list_linux_arm, build_list_linux_arm64, build_list_linux_x86, build_list_linux_x86_64, build_list_macosx, build_list_macosx_arm, build_list_macosx_arm64, build_list_macosx_x86, build_list_macosx_x86_64, build_list_posix, build_list_posix_arm, build_list_posix_arm64, build_list_posix_x86, build_list_posix_x86_64, build_list_windows, build_list_windows_arm, build_list_windows_arm64, build_list_windows_x86, build_list_windows_x86_64**
  
* **symbol_visibility_default**
  _boolean (integer)_, GCC/MinGW specific  
  When set to _True_, source files are compiled _without_ GCC command line argument `‑fvisibility=hidden`, otherwise the argument `‑fvisibility=hidden` is always being used.  
  
* **win_console**
  _boolean (integer)_, Windows specific, effective when _module_type='executable'_  
  When set to _True_, target executable is compiled for subsystem `console`.  
  When this grammar token is not given, its default value: `win_console = 1`
  
* **with_default_manifest**
  _boolean (integer)_, Windows specific, effective when _module_type_ is _'executable'_ or _'lib-shared'_  
  When set to _True_, target binary is built with manifest file predefined in _MiniBuild_ build system.  
  When this grammar token is not given, its default value: `with_default_manifest = 1`
  
* **win_stack_size**
  _integer_, Windows specific, effective when _module_type='executable'_  
  This option defines explicit value in bytes of stack size to be used when executable binary is compiled for _Windows_ platform.  
  
* **wmain**
  _boolean (integer)_, Windows specific, effective when _module_type='executable'_  
  This option has to be set to _True_, when executable entry point is `wmain`.  
  
* **winrc_file**
  _string_, Windows specific, effective when _module_type_ is _'executable'_ or _'lib-shared'_  
  Path to a resource-definition script (.rc file) that describes the resources used by binary being built.  
  
* **winrc_definitions**
  _list of strings_, Windows specific, effective when _module_type_ is _'executable'_ or _'lib-shared'_  
  The list of extra definitions to be used during compilation of a resource-definition script (.rc file) specified by option `winrc_file`.  
  
* **with_default_ssp**
  _boolean (integer)_, Linux specific, effective when _module_type_ is _'executable'_ or _'lib-shared'_  
  When set to _True_, target binary is built with SSP (Stack Smashing Protector) stubs predefined in _MiniBuild_ build system, it helps to avoid explicit link with `libssp` for certain toolchains.  
  When this grammar token is not given, its default value: `with_default_ssp = 1`
  
* **nasm**
  _boolean (integer)_, _i686_, _x86_64_ specific  
  This option has to be set to _True_, when your assembler sources are written in [NASM](https://www.nasm.us) assembler language, rather then in toolchain default assembler dialect (which is usually MASM or GAS depending on toolchain being used for build).
  
* **include_dir_list**
  _list of strings_  
  The list of directories from which C and C++ header files are included. Directory entries in the list should be provided relative to the current `minibuild.mk` script.  
  
* **asm_include_dir_list**
  _list of strings_  
  The list of directories from which ASM files are included. Directory entries in the list should be provided relative to the current `minibuild.mk` script.  
  
* **src_search_dir_list**
  _list of strings_  
  The list of directories where C and C++ sources mentioned in `build_list` option are resided. Directory entries in the list should be provided relative to the current `minibuild.mk` script.  
  ISA extensions: **src_search_dir_list_linux, src_search_dir_list_linux_arm, src_search_dir_list_linux_arm64, src_search_dir_list_linux_x86, src_search_dir_list_linux_x86_64, src_search_dir_list_macosx, src_search_dir_list_macosx_arm, src_search_dir_list_macosx_arm64, src_search_dir_list_macosx_x86, src_search_dir_list_macosx_x86_64, src_search_dir_list_posix, src_search_dir_list_posix_arm, src_search_dir_list_posix_arm64, src_search_dir_list_posix_x86, src_search_dir_list_posix_x86_64, src_search_dir_list_windows, src_search_dir_list_windows_arm, src_search_dir_list_windows_arm64, src_search_dir_list_windows_x86, src_search_dir_list_windows_x86_64**
  
* **asm_search_dir_list**
  _list of strings_  
  The list of directories where ASM sources mentioned in `build_list` option are resided. Directory entries in the list should be provided relative to the current `minibuild.mk` script.  
  ISA extensions: **asm_search_dir_list_linux, asm_search_dir_list_linux_arm, asm_search_dir_list_linux_arm64, asm_search_dir_list_linux_x86, asm_search_dir_list_linux_x86_64, asm_search_dir_list_macosx, asm_search_dir_list_macosx_arm, asm_search_dir_list_macosx_arm64, asm_search_dir_list_macosx_x86, asm_search_dir_list_macosx_x86_64, asm_search_dir_list_posix, asm_search_dir_list_posix_arm, asm_search_dir_list_posix_arm64, asm_search_dir_list_posix_x86, asm_search_dir_list_posix_x86_64, asm_search_dir_list_windows, asm_search_dir_list_windows_arm, asm_search_dir_list_windows_arm64, asm_search_dir_list_windows_x86, asm_search_dir_list_windows_x86_64**
  
* **lib_list**
  _list of strings_, effective when _module_type='executable'_ or _module_type='lib-shared'_  
  The list of directories to the locations of static or shared libraries on which current module is dependent on, i.e. each entry in this list has to be a path of a directory where `minibuild.mk` of dependent library resides. Directory entries in the list should be provided relative to the current `minibuild.mk` script.  
  
* **prebuilt_lib_list**
  _list of strings_, effective when _module_type='executable'_ or _module_type='lib-shared'_  
  The list of names of prebuilt libraries supported by toolchain to link against.  
  Platform extensions: **prebuilt_lib_list_linux, prebuilt_lib_list_macosx, prebuilt_lib_list_posix, prebuilt_lib_list_windows**  
  Example of usage:
```
prebuilt_lib_list_linux = ['dl','pthread']
prebuilt_lib_list_windows = ['advapi32', 'user32']
```

* **macosx_framework_list**
  _list of strings_, effective when compiling for _MacOSX_ platform and  _module_type='executable'_ or _module_type='lib-shared'_  
  The list of MacOSX frameworks to link against.  
  Example of usage:
```
macosx_framework_list = ['CoreFoundation', 'SystemConfiguration']
```

* **macosx_install_name_options**
  _string_, effective when compiling for _MacOSX_ platform and  _module_type='executable'_ or _module_type='lib-shared'_  
  This option may be used to prescribe that invocation of [install_name_tool](https://www.unix.com/man-page/osx/1/INSTALL_NAME_TOOL/) is required when linking shared library or executable binary described by current `minibuild.mk` script.  
  Example of usage:
```
macosx_install_name_options = '-change libmytest.so @loader_path/libmytest.so'
```

* **definitions**
  _list of strings_  
  The list of definitions to be used during compilation of C or C++ sources.  
  ISA extensions: **definitions_linux, definitions_linux_arm, definitions_linux_arm64, definitions_linux_x86, definitions_linux_x86_64, definitions_macosx, definitions_macosx_arm, definitions_macosx_arm64, definitions_macosx_x86, definitions_macosx_x86_64, definitions_posix, definitions_posix_arm, definitions_posix_arm64, definitions_posix_x86, definitions_posix_x86_64, definitions_windows, definitions_windows_arm, definitions_windows_arm64, definitions_windows_x86, definitions_windows_x86_64**  
  
* **asm_definitions**
  _list of strings_  
  The list of definitions to be used during compilation of ASM sources.  
  ISA extensions: **asm_definitions_linux, asm_definitions_linux_arm, asm_definitions_linux_arm64, asm_definitions_linux_x86, asm_definitions_linux_x86_64, asm_definitions_macosx, asm_definitions_macosx_arm, asm_definitions_macosx_arm64, asm_definitions_macosx_x86, asm_definitions_macosx_x86_64, asm_definitions_posix, asm_definitions_posix_arm, asm_definitions_posix_arm64, asm_definitions_posix_x86, asm_definitions_posix_x86_64, asm_definitions_windows, asm_definitions_windows_arm, asm_definitions_windows_arm64, asm_definitions_windows_x86, asm_definitions_windows_x86_64**  
  
* **export**
  _list of strings_, effective when _module_type='lib-shared'_  
  Explicit list of symbols to be exported from shared library being build.  
  
* **export_def_file**
  string, effective when _module_type='lib-shared'_  
  Path to a module-definition (.def) file. Path should be provided relative to the current `minibuild.mk` script. _This option supported for all platforms._ The build system framework has its own logic for parsing def-files in case when toolchain being used for build doesn't have native support for it.  
  
* **export_winapi_only**
  _list of strings_, effective when _module_type='lib-shared'_  
  The list of symbols to be exported from shared library when it is being built for _Windows_ platform, but have to be excluded from the set of exported symbols, when the the same library is being built for any other platform. This option may be convenient in conjunction with or **export_def_file** option.  
  
* **disabled_warnings**
  _list of strings_  
  The list of warnings to be disabled during source files compilation.  
  Example of usage:
```
if BUILDSYS_TOOLSET_NAME == 'msvs':
    disabled_warnings = ['4090']
else:
    disabled_warnings = ['unused-function']
```

* **composite_spec**
  _list of objects_ in predefined format, effective and required when _module_type='composite'_  
  See _composite_spec_ grammar reference for details.  
  
* **spec_file**
  _string_, supported for all module types  
  Path to _spec-file_ file. Path should be provided relative to the current `minibuild.mk` script.  
  The idea of _spec-file_ here is completely custom to the current build system framework. In a couple words, spec-file provides patterns how to enumerate files in an arbitrary directory tree and emit results of enumeration in related json file inside `output directory`. When this option is given correspondent spec-file is always processed before any other build actions.
  For more details see spec-file grammar reference.  
  
* **zip_file**
  _string_, effective and required when _module_type='zip-file'_  
  Name of this zip-file to be generated during the build according to given _spec-file_ when _module_type='zip-file'_.  
  
* **post_build**
  _list of strings_  
  The list of names of custom actions to be executed right after build actions. For more details about custom actions supported by build system see related description.  
  
* **spec_post_build**
  _list of strings_, effective when _spec_file_ option is given as well  
  The list of names of custom actions to be executed right after processing spec-file and before any build action. For more details about custom actions supported by build system see related description.  
  
* **spec_file_entails**
  _dictionary of objects_, effective when _spec_file_ option is given as well  
  When this option is given, its value is used to extend result of spec-file processing. This option may be useful to pass extra information into a custom action oriented on processing spec-files.
  
* **download_list**
  _list of pairs [URL, local.file]_, effective and required when _module_type='download'_  
  When build of a module of type _'download'_ is done, all downloaded files are supposed to be located in directory: `<project-root>/output/obj/<module-name>/noarch/`.  
  Example of usage:
```
download_list = [
    ['https://mkcert.org/generate/', 'certdata.pem']
]
```

* **explicit_depends**
  _list of strings_  
  The list of directories where `minibuild.mk` files of other modules reside. Paths should be provided relative to the current `minibuild.mk` script.  
  In some twisted cases module may have dependencies on other modules, which are not deducible by the essential logic of the build system. In this case related dependencies should be provided via this option.  
  
* **zip_section**
  _string_, effective when _module_type='executable'_ or _module_type='lib-shared'_  
  Path to a zip-file to be shipped into a binary being build. Path should be provided relative to the current `minibuild.mk` script.  
  