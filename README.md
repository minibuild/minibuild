# MiniBuild build system
## Overview
_MiniBuild_ build system is a pure Python package aimed to build executables, static and shared libraries from C, C++ and ASM source files. Build process can be launched from any directory containing a `minibuild.mk` makefile. This file describes what type of binary is going to be built and its dependencies on other modules inside a directory tree of your project.
  
## Supported toolchains and platforms:
* Windows (i686, x86_64):
  - Microsoft Visual Studio 2005, 2008, 2010, 2012, 2013, 2015, 2017
  - MinGW
* Linux (i686, x86_64, arm-eabi, aarch64):
  - GCC
  - A range of gcc cross-toolchains generated by crosstool-ng: https://crosstool-ng.github.io
* MacOSX (x86_64):
  - clang
  
## Assembly language support
By default ASM source files are supposed to be written in toolchain default assembly dialect (which is usually MASM or GAS depending on toolchain being used for build). However threre is case, when your ASM source files are written in NASM assembly language dialect. To prescribe this fact a corresponding option just has to be turned on in related makefile.

## Documentation
Documentation is available at https://minibuild.github.io/minibuild/
