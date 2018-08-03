from __future__ import print_function
import subprocess
import sys

from .error_utils import *


class ToolsetActionResult(object):
    def __init__(self, rebuilt, artifacts):
        self.rebuilt = rebuilt
        self.artifacts = artifacts
        self.error_text = None
        self.exit_code = None


class ToolsetActionOutput(object):
    def report_message(self, msg):
        raise BuildSystemPureVirtualCall(self)


class ToolsetActionOutputDirect(ToolsetActionOutput):
    def report_message(self, msg):
        print(msg)


class ToolsetActionContext(object):
    def __init__(self, force, verbose, trace):
        self.force = force
        self.verbose = verbose
        self.trace = trace

    def subprocess_communicate(self, output, argv, issuer, env=None, cwd=None, output_filter=None, title=None):
        ret = None
        if self.verbose:
            output.report_message("BUILDSYS: EXEC: {}".format(' '.join(argv)))
        elif self.trace:
            output.report_message(' '.join(argv))
        if title is not None:
            output.report_message(title)
        p = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, cwd=cwd)
        stdout_data, _ = p.communicate()
        stdout_data = stdout_data.rstrip('\r\n').strip()
        if output_filter is not None:
            ret, stdout_data = output_filter(stdout_data, p.returncode)
        if stdout_data:
            output.report_message(stdout_data)
        if p.returncode != 0:
            raise BuildSystemException(issuer, exit_code=p.returncode)
        return ret


class ToolsetActionBase(object):
    def safe_execute(self, ctx, output=None):
        if output is None:
            output = ToolsetActionOutputDirect()
        ret = None
        try:
            ret = self.execute(output, ctx)
        except BuildSystemException as exc:
            ret = ToolsetActionResult(rebuilt=None, artifacts=None)
            ret.error_text = buildsys_error_to_string(exc)
            ret.exit_code = exc.to_exit_code()
        except Exception as err:
            etype, value, tb = sys.exc_info()
            ret = ToolsetActionResult(rebuilt=None, artifacts=None)
            ret.error_text = traceback_to_string(etype, value, tb)
            ret.exit_code = 126
        return ret

    def execute(self, output, ctx):
        raise BuildSystemPureVirtualCall(self)


class ToolsetModel(object):
    @property
    def model_name(self):
        raise BuildSystemPureVirtualCall(self)

    @property
    def platform_name(self):
        raise BuildSystemPureVirtualCall(self)

    @property
    def platform_alias(self):
        raise BuildSystemPureVirtualCall(self)

    @property
    def architecture_abi_name(self):
        raise BuildSystemPureVirtualCall(self)

    def is_native(self):
        raise BuildSystemPureVirtualCall(self)

    @property
    def toolset_version(self):
        raise BuildSystemPureVirtualCall(self)

    def is_crosstool(self):
        return False


class ToolsetBase(object):
    @property
    def toolset_name(self):
        raise BuildSystemPureVirtualCall(self)

    @property
    def platform_name(self):
        raise BuildSystemPureVirtualCall(self)

    @property
    def supported_models(self):
        raise BuildSystemPureVirtualCall(self)

    def create_cpp_build_action(self, description, cpp_source, obj_directory, obj_name, build_model, build_config):
        raise BuildSystemPureVirtualCall(self)

    def create_c_build_action(self, description, c_source, obj_directory, obj_name, build_model, build_config):
        raise BuildSystemPureVirtualCall(self)

    def create_asm_build_action(self, description, asm_source, obj_directory, obj_name, build_model, build_config):
        raise BuildSystemPureVirtualCall(self)

    def create_lib_static_link_action(self, description, lib_directory, obj_directory, obj_names, build_model, build_config):
        raise BuildSystemPureVirtualCall(self)

    def create_exe_link_action(self, description, exe_directory, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config):
        raise BuildSystemPureVirtualCall(self)

    def create_lib_shared_link_action(self, description, sharedlib_directory, lib_directory, obj_directory, obj_names, build_model, build_config):
        raise BuildSystemPureVirtualCall(self)
