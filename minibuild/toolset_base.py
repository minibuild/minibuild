from .error_utils import BuildSystemPureVirtualCall

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
