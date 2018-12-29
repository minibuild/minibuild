from __future__ import print_function

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile

from .actions_pool import ActionsPool
from .build_art import BuildArtifact
from .constants import *
from .depends_check import *
from .error_utils import BuildSystemException, BuildSystemSysExit
from .os_utils import cleanup_dir, mkdir_safe, normalize_path_optional, load_py_object, touch_file
from .spec_file import parse_spec_file
from .string_utils import is_string_instance
from .toolset_base import ToolsetActionContext


_BUILD_TYPE_MAPPING = {
  '.cpp': BUILD_TYPE_CPP,
  '.c': BUILD_TYPE_C,
  '.asm': BUILD_TYPE_ASM,
  '.S': BUILD_TYPE_ASM,
  '.s': BUILD_TYPE_ASM,
}


def resolve_build_list(description, current_model):
    platform_alias = current_model.platform_alias

    all_attr = [TAG_GRAMMAR_KEY_BUILD_LIST]
    all_attr += ['_'.join([TAG_GRAMMAR_KEY_BUILD_LIST, current_model.platform_name])]
    if platform_alias is not None:
        all_attr += ['_'.join([TAG_GRAMMAR_KEY_BUILD_LIST, platform_alias])]
    all_attr += ['_'.join([TAG_GRAMMAR_KEY_BUILD_LIST, current_model.platform_name, current_model.architecture_abi_name])]
    if platform_alias is not None:
        all_attr += ['_'.join([TAG_GRAMMAR_KEY_BUILD_LIST, platform_alias, current_model.architecture_abi_name])]

    full_build_list = []
    for attr_name in all_attr:
        build_list = getattr(description, attr_name)
        if build_list is not None:
            full_build_list += build_list

    all_attr_dir_search = [TAG_GRAMMAR_KEY_SRC_SEARCH_DIR_LIST]
    all_attr_dir_search += ['_'.join([TAG_GRAMMAR_KEY_SRC_SEARCH_DIR_LIST, current_model.platform_name])]
    if platform_alias is not None:
        all_attr_dir_search += ['_'.join([TAG_GRAMMAR_KEY_SRC_SEARCH_DIR_LIST, platform_alias])]
    all_attr_dir_search += ['_'.join([TAG_GRAMMAR_KEY_SRC_SEARCH_DIR_LIST, current_model.platform_name, current_model.architecture_abi_name])]
    if platform_alias is not None:
        all_attr_dir_search += ['_'.join([TAG_GRAMMAR_KEY_SRC_SEARCH_DIR_LIST, platform_alias, current_model.architecture_abi_name])]

    all_attr_dir_search_asm = [TAG_GRAMMAR_KEY_ASM_SEARCH_DIR_LIST]
    all_attr_dir_search_asm += ['_'.join([TAG_GRAMMAR_KEY_ASM_SEARCH_DIR_LIST, current_model.platform_name])]
    if platform_alias is not None:
        all_attr_dir_search_asm += ['_'.join([TAG_GRAMMAR_KEY_ASM_SEARCH_DIR_LIST, platform_alias])]
    all_attr_dir_search_asm += ['_'.join([TAG_GRAMMAR_KEY_ASM_SEARCH_DIR_LIST, current_model.platform_name, current_model.architecture_abi_name])]
    if platform_alias is not None:
        all_attr_dir_search_asm += ['_'.join([TAG_GRAMMAR_KEY_ASM_SEARCH_DIR_LIST, platform_alias, current_model.architecture_abi_name])]

    full_search_list = [ description.self_dirname ]
    for attr_dir_search in all_attr_dir_search:
        search_list = getattr(description, attr_dir_search)
        if search_list:
            for search_dname in search_list:
                norm_dname = normalize_path_optional(search_dname, description.self_dirname)
                if not os.path.isdir(norm_dname):
                    raise BuildSystemException("Search directory '{}' not found, got from '{}'.".format(norm_dname, description.self_file_parts[0]))
                full_search_list.append(norm_dname)

    full_search_list_asm = [ description.self_dirname ]
    for attr_dir_search in all_attr_dir_search_asm:
        search_list = getattr(description, attr_dir_search)
        if search_list:
            for search_dname in search_list:
                norm_dname = normalize_path_optional(search_dname, description.self_dirname)
                if not os.path.isdir(norm_dname):
                    raise BuildSystemException("Search directory '{}' not found, got from '{}'.".format(norm_dname, description.self_file_parts[0]))
                full_search_list_asm.append(norm_dname)

    result = []
    for item in full_build_list:
        obj_name, ext = os.path.splitext(os.path.basename(item))
        build_type = _BUILD_TYPE_MAPPING.get(ext, BUILD_TYPE_UNKNOWN)
        search_list_to_try = full_search_list_asm if build_type == BUILD_TYPE_ASM else full_search_list
        attempts = []
        source_full_path = None
        for try_dir in search_list_to_try:
            try_file = os.path.normpath(os.path.join(try_dir, item))
            if os.path.isfile(try_file):
                source_full_path = try_file
                break
            attempts.append(try_file)
        if source_full_path is None:
            raise BuildSystemException("Can't find file '{}' got from '{}'. Tried:\n  {}"
                .format(item, description.self_file_parts[0], '\n  '.join(attempts)))
        result.append((build_type, source_full_path, obj_name))
    return result


class BuildCache:
    def __init__(self):
        self._state = {}
        self._state_noarch = {}

    def cache_build_result(self, description, used_model_name, result):
        if description.module_type in TAG_ALL_MODULE_TYPES_NOARCH:
            self._state_noarch[description.self_dirname] = result
        else:
            if used_model_name not in self._state:
                self._state[used_model_name] = {}
            self._state[used_model_name][description.self_dirname] = result

    def get_cached_build_result(self, description, used_model_name):
        if description.module_type in TAG_ALL_MODULE_TYPES_NOARCH:
            return self._state_noarch.get(description.self_dirname)
        if used_model_name in self._state:
            return self._state[used_model_name].get(description.self_dirname)
        return None

class ActiveExtState:
    def __init__(self):
        self._state = {}

    def inc_ref(self, description, used_model_name):
        if used_model_name not in self._state:
            self._state[used_model_name] = {}
        if description.self_dirname in self._state[used_model_name]:
            self._state[used_model_name][description.self_dirname] += 1
        else:
            self._state[used_model_name][description.self_dirname] = 1
        return self._state[used_model_name][description.self_dirname]

    def dec_ref(self, description, used_model_name):
        r = -1
        if used_model_name in self._state and description.self_dirname in self._state[used_model_name]:
            self._state[used_model_name][description.self_dirname] -= 1
            r = self._state[used_model_name][description.self_dirname]
        return r

    def ref_count(self, description, used_model_name):
        return self._state.get(used_model_name, {}).get(description.self_dirname, 0)


def zip_module_rebuild_required(zip_obj_dir, zippath, catalog, description, verbose):
    post_build_stamp_file = None
    if description.post_build:
        post_build_stamp_file = os.path.join(zip_obj_dir, POST_BUILD_OBJ_STAMP_FILE)
    if not os.path.exists(zippath):
        return True
    if post_build_stamp_file is not None:
        if not os.path.exists(post_build_stamp_file):
            return True
    zip_mtime = os.path.getmtime(zippath)
    for desc_file_part in description.self_file_parts:
        desc_part_mtime = os.path.getmtime(desc_file_part)
        if prerequisite_newer_then_target(zip_mtime, desc_part_mtime, zippath, desc_part_mtime, verbose):
            return True
    for fpath, _ in catalog:
        if not os.path.isfile(fpath):
            return True
        mt = os.path.getmtime(fpath)
        if prerequisite_newer_then_target(zip_mtime, mt, zippath, fpath, verbose):
            return True
    return False


def download_link(url, target_file):
    context = None
    if url.startswith('https:'):
        if (sys.version_info.major, sys.version_info.minor, sys.version_info.micro) >= (2,7,9):
            import ssl
            context = ssl._create_unverified_context()
    if sys.version_info.major < 3:
        import urllib2
        urlopen = urllib2.urlopen
    else:
        import urllib.request
        urlopen = urllib.request.urlopen
    if context is not None:
        response = urlopen(url, context=context)
    else:
        response = urlopen(url)
    payload = response.read()
    with open(target_file, mode='wb') as file_object:
        file_object.write(payload)


def download_files(sysinfo, description, force_download, verbose):
    if not description.download_list:
        raise BuildSystemException("Mandatory token '{}' is missed or empty list, required in '{}'.".format(TAG_GRAMMAR_KEY_DOWNLOAD_LIST, description.self_file_parts[0]))

    download_obj_dir = os.path.join(sysinfo[TAG_CFG_DIR_OBJ], description.module_name, TAG_DIR_NOARCH)
    mkdir_safe(download_obj_dir)
    have_new_downloads = False

    catalog = []
    result = []
    idx = 0
    for catalog_entry in description.download_list:
        idx += 1
        if not isinstance(catalog_entry, list) or len(catalog_entry) < 2 or not is_string_instance(catalog_entry[0]) or not is_string_instance(catalog_entry[1]) or not catalog_entry[0] or not catalog_entry[1]:
            raise BuildSystemException("Can't parse download entry #{}, provided in: '{}'.".format(idx, description.self_file_parts[0]))
        download_url = catalog_entry[0]
        target_fname = catalog_entry[1]
        target_file_path = os.path.join(download_obj_dir, target_fname)
        catalog.append([download_url, target_file_path])
        result.append(BuildArtifact(BUILD_RET_TYPE_RESOURCE, target_file_path, BUILD_RET_ATTR_DEFAULT))

    for catalog_entry in catalog:
        download_url = catalog_entry[0]
        target_fname = catalog_entry[1]
        do_download = force_download
        if not do_download:
            target_ready, _ = is_target_up_to_date(target_fname, None, description.self_file_parts, verbose)
            if not target_ready:
                do_download = True
        if do_download:
            if os.path.isfile(target_fname):
                os.remove(target_fname)
            target_fname_tmp = target_fname + '.part'
            print("BUILDSYS: downloading '{}' ...".format(download_url))
            download_link(download_url, target_fname_tmp)
            os.rename(target_fname_tmp, target_fname)
            have_new_downloads = True
        else:
            print("BUILDSYS: up-to-date: '{}', URL: '{}'".format(description.module_name, download_url))

    return (have_new_downloads, result)


def make_posix_permissions(is_exe):
    permissions = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
    if is_exe:
        permissions = permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    return permissions


class ExtAction:
    def __init__(self, ext_type, ext_name, module_name, verbose, argv):
        self._ext_type = ext_type
        self._ext_name = ext_name
        self._module_name = module_name
        self._verbose = verbose
        self._argv = argv

    def __call__(self):
        print("BUILDSYS: run {} action '{}' for module '{}'".format(self._ext_type, self._ext_name, self._module_name))
        if self._verbose:
            print("BUILDSYS: EXEC: {}".format(self._argv))
        p = subprocess.Popen(self._argv)
        p.communicate()
        if p.returncode != 0:
            raise BuildSystemException("Failed to run {} action '{}' for module '{}'".format(
                self._ext_type, self._ext_name, self._module_name), exit_code=p.returncode)


class BuildExtensionEntry:
    def __init__(self, dir_loaded_from, description):
        self.dir_loaded_from = dir_loaded_from
        self.description = description


class BuildWorkflow:
    def __init__(self, sysinfo, toolset_models_mapping, native_model_remap, grammar_substitutions, verbose, trace, parallelism, faccess, faccess_prefixes):
        self._sysinfo = sysinfo
        self._toolset_models_mapping = toolset_models_mapping
        self._native_model_remap = native_model_remap
        self._extensions_mapping = {}
        self._imported_extensions = {}
        self._grammar_substitutions = grammar_substitutions
        self._build_cache = BuildCache()
        self._ext_protector = ActiveExtState()
        self._verbose = verbose
        self._trace = trace
        self._faccess = faccess
        self._faccess_prefixes = faccess_prefixes
        self._actions_pool = ActionsPool(jobs_count=parallelism, verbose=verbose)

    def import_extension(self, loader, dname_import, required_by):
        dname_import_id = os.path.normcase(dname_import)
        if dname_import_id in self._extensions_mapping:
            return self._imported_extensions[self._extensions_mapping[dname_import_id]].description
        ext_description = loader.load_build_extension(dname_import, required_by)
        if ext_description.ext_name in self._imported_extensions:
            prev_dname_import = self._imported_extensions[ext_description.ext_name].dir_loaded_from
            raise BuildSystemException("Can't import build extension '{}' from '{}', extension with same name is already imported from '{}'.".format(ext_description.ext_name, dname_import, prev_dname_import))
        self._extensions_mapping[dname_import_id] = ext_description.ext_name
        self._imported_extensions[ext_description.ext_name] = BuildExtensionEntry(dname_import, ext_description)
        return ext_description

    def run(self, build_directory, used_model_name, build_config, public, public_format, public_layout, rebuild_level):
        toolset, loader = self._toolset_models_mapping[used_model_name]
        current_model = toolset.supported_models[used_model_name]
        description = loader.load_build_description(build_directory, current_model)
        try:
            self._actions_pool.init()
            build_result = self._perform_build(description, used_model_name, build_config, rebuild_level)
        finally:
            self._actions_pool.shutdown()

        if public:
            self._publish_module_artifacts(build_result, description, used_model_name, build_config, public_format, public_layout, rebuild_level)

    def _publish_module_artifacts(self, build_result, description, used_model_name, build_config, public_format, public_layout, rebuild_level):
        being_built, artifacts = build_result[0], build_result[1]
        obj_dir_prefix = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, used_model_name, build_config) + os.sep
        obj_dir_prefix_length = len(obj_dir_prefix)
        if public_layout == TAG_PUBLIC_LAYAOUT_FLAT:
            public_dir = self._sysinfo[TAG_CFG_DIR_PUBLIC]
        else:
            public_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_PUBLIC], used_model_name, build_config)
        public_name = description.public_name if description.public_name else description.module_name
        toolset, _ = self._toolset_models_mapping[used_model_name]
        current_model = toolset.supported_models[used_model_name]
        if public_format is not None:
            publish_in_tgz_format = True if public_format == TAG_PUBLIC_FORMAT_TGZ else False
        else:
            publish_in_tgz_format = True if current_model.platform_alias == TAG_PLATFORM_ALIAS_POSIX else False
        if publish_in_tgz_format:
            current_format = TAG_PUBLIC_FORMAT_TGZ
            publication = os.path.join(public_dir, public_name + '.tgz')
        else:
            current_format = TAG_PUBLIC_FORMAT_ZIP
            publication = os.path.join(public_dir, public_name + '.zip')
        print("BUILDSYS: publishing: {}: {}".format(current_format, publication))
        catalog = []
        for art in artifacts:
            if description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_COMPOSITE:
                if not art.path.startswith(obj_dir_prefix):
                    raise BuildSystemException("Got out of tree artifact location: '{}', it is not in: '{}*'.".format(art.path, obj_dir_prefix))
                arcname = art.path[obj_dir_prefix_length:].replace('\\', '/')
            else:
                arcname = os.path.basename(art.path)
            catalog.append((art, arcname))
        do_publish = rebuild_level > 0
        if not do_publish:
            do_publish = being_built
        if not do_publish:
            up_to_date, _ = is_target_up_to_date(publication, None, artifacts, self._verbose)
            if not up_to_date:
                do_publish = True
        if not do_publish:
            print("BUILDSYS: up-to-date: '{}', PUBLIC".format(description.module_name))
            return

        mkdir_safe(public_dir)
        if publish_in_tgz_format:
            with tarfile.open(publication, mode='w:gz') as z:
                for node in catalog:
                    art, arcname = node[0], node[1]
                    print(arcname)
                    is_exe = True if art.attributes & BUILD_RET_ATTR_FLAG_EXECUTABLE else False
                    permissions = make_posix_permissions(is_exe)
                    with open(art.path, mode='rb') as fobj:
                        info = os.fstat(fobj.fileno())
                        ti = tarfile.TarInfo()
                        ti.type = tarfile.REGTYPE
                        ti.name = arcname
                        ti.mode = permissions
                        ti.size = info.st_size
                        ti.mtime = info.st_mtime
                        z.addfile(ti, fobj)
        else:
            with zipfile.ZipFile(publication, "w", zipfile.ZIP_DEFLATED) as z:
                for node in catalog:
                    art, arcname = node[0], node[1]
                    print(arcname)
                    z.write(art.path, arcname)
        print("BUILDSYS: '{}' published as {}".format(description.module_name, publication))

    def _follow_faccess_for_file(self, source):
        faccess_stamps = []
        norm_src_path = os.path.normcase(source)
        faccess_in_interest = False
        for faccess_prefix in self._faccess_prefixes:
            if norm_src_path.startswith(self._sysinfo[TAG_CFG_PROJECT_OUTPUT_COMMON_PREFIX]):
                break
            if norm_src_path.startswith(faccess_prefix):
                faccess_in_interest = True
                break
        if not faccess_in_interest:
            return
        norm_src_relpath = source[len(self._sysinfo[TAG_CFG_PROJECT_ROOT_COMMON_PREFIX]):]
        faccess_stamp_file = os.path.join(self._sysinfo[TAG_CFG_DIR_FACCESS], norm_src_relpath)
        faccess_stamps += [ (norm_src_relpath.replace('\\', '/'), faccess_stamp_file) ]
        for faccess_relpath, faccess_stamp_file in faccess_stamps:
            if self._verbose:
                print("BUILDSYS: FACCESS: {}".format(faccess_relpath))
            mkdir_safe(os.path.dirname(faccess_stamp_file))
            touch_file(faccess_stamp_file)

    def _follow_faccess_in_spec_file(self, catalog):
        for source, _ in catalog:
            self._follow_faccess_for_file(source)

    def _build_zip_module(self, description, current_model, force):
        if not description.spec_file:
            raise BuildSystemException("Mandatory token '{}' is missed, required in '{}'.".format(TAG_GRAMMAR_KEY_SPEC_FILE, description.self_file_parts[0]))
        if not description.zip_file:
            raise BuildSystemException("Mandatory token '{}' is missed, required in '{}'.".format(TAG_GRAMMAR_KEY_ZIP_FILE, description.self_file_parts[0]))

        zip_obj_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, TAG_DIR_NOARCH)
        mkdir_safe(zip_obj_dir)

        spec_fname = normalize_path_optional(description.spec_file, description.self_dirname)
        catalog = parse_spec_file(spec_fname, self._grammar_substitutions, current_model)

        zippath = os.path.join(zip_obj_dir, description.zip_file)
        if force:
            need_rebuild = True
        else:
            need_rebuild = zip_module_rebuild_required(zip_obj_dir, zippath, catalog, description, self._verbose)
        zipspec_catalog = []
        if need_rebuild:
            print("BUILDSYS: Zipping '{}' ...".format(description.module_name))
            if os.path.exists(zippath):
                os.remove(zippath)
            with zipfile.ZipFile(zippath, "w", zipfile.ZIP_DEFLATED) as z:
                for source, arcname in catalog:
                    z.write(source, arcname)
                    zipspec_catalog.append([source, arcname])
            if self._faccess:
                self._follow_faccess_in_spec_file(catalog)
        else:
            print("BUILDSYS: up-to-date: '{}', ZIP: {}".format(description.module_name, zippath))

        return (need_rebuild, [BuildArtifact(BUILD_RET_TYPE_ZIP, zippath, BUILD_RET_ATTR_DEFAULT)])

    def _perform_build(self, description, used_model_name, build_config, rebuild_level):
        toolset, loader = self._toolset_models_mapping[used_model_name]
        current_model = toolset.supported_models[used_model_name]

        mod_build_result = None
        if rebuild_level <= 0:
            cached_prebuilt_result = self._build_cache.get_cached_build_result(description, used_model_name)
            if cached_prebuilt_result is not None:
                print("BUILDSYS: up-to-date(cached): '{}', {}".format(description.module_name, description.module_type))
                return (False, cached_prebuilt_result)

        print("BUILDSYS: start build '{}', {},{} ...".format(description.module_name, description.module_type, used_model_name))

        if description.explicit_depends and rebuild_level >= 0:
            xpl_depends_desc = []
            eval_explicit_depends_in_description(loader, description, current_model, xpl_depends_desc)
            for xpl_dep_desc in xpl_depends_desc:
                xpl_dep_cached_result = self._build_cache.get_cached_build_result(xpl_dep_desc, used_model_name)
                if xpl_dep_cached_result is not None:
                    continue
                xpl_rebuild_level = 2 if rebuild_level == 2 else 0
                self._perform_build(xpl_dep_desc, used_model_name, build_config, xpl_rebuild_level)

        if description.pre_build_noarch:
            self._perform_pre_build(description, used_model_name, build_config, rebuild_level, noarch=True)

        if description.pre_build:
            self._perform_pre_build(description, used_model_name, build_config, rebuild_level, noarch=False)

        if description.spec_file:
            noarch_obj_mod_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, TAG_DIR_NOARCH)
            mkdir_safe(noarch_obj_mod_dir)
            spec_fname_output = os.path.join(noarch_obj_mod_dir, 'spec-output.json')
            spec_fname_stamp = os.path.join(noarch_obj_mod_dir, 'spec-output.stamp')
            spec_fname_input = normalize_path_optional(description.spec_file, description.self_dirname)
            up_to_date = None
            if rebuild_level <= 0:
                up_to_date, _ = is_target_up_to_date(spec_fname_stamp, [spec_fname_input], description.self_file_parts, self._verbose)
                if up_to_date and not os.path.isfile(spec_fname_output):
                    up_to_date = False
                if up_to_date:
                    with open(spec_fname_output) as fh:
                        files_in_spec = [ x[0] for x in json.load(fh)[TAG_GRAMMAR_KEY_SPEC_FILE] ]
                    up_to_date, _ = is_target_up_to_date(spec_fname_stamp, files_in_spec, None, self._verbose)
            if rebuild_level <= 0 and up_to_date:
                print("BUILDSYS: up-to-date: spec-file for module '{}'".format(description.module_name))
            else:
                print("BUILDSYS: processing spec-file for module '{}'".format(description.module_name))
                mod_spec_catalog = parse_spec_file(spec_fname_input, self._grammar_substitutions, current_model)
                with open(spec_fname_output, 'wt') as spec_fh:
                    spec_data = {}
                    spec_data[TAG_GRAMMAR_KEY_SPEC_FILE] = []
                    for source, arcname in mod_spec_catalog:
                        spec_data[TAG_GRAMMAR_KEY_SPEC_FILE].append([source, arcname])
                    for entail_attr in TAG_GRAMMAR_SPEC_FILE_ENTAILS:
                        entail_value = getattr(description, entail_attr)
                        if entail_value is not None:
                            spec_data[entail_attr] = entail_value
                    if description.spec_file_entails:
                        for entail_attr in description.spec_file_entails:
                            entail_value = description.spec_file_entails[entail_attr]
                            spec_data[entail_attr] = entail_value
                    json.dump(spec_data, spec_fh, sort_keys=True, indent=4, ensure_ascii=False)
                if description.spec_post_build:
                    self._perform_spec_post_build(description, used_model_name, build_config, rebuild_level)
                touch_file(spec_fname_stamp)
                if self._faccess:
                    self._follow_faccess_in_spec_file(mod_spec_catalog)


        if description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_ZIP_FILE:
            mod_build_result = self._build_zip_module(description, current_model, rebuild_level > 0)

        elif description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_DOWNLOAD:
            force_download = rebuild_level > 0
            noarch_obj_mod_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, TAG_DIR_NOARCH)
            if description.pre_build or description.pre_build_noarch:
                mod_download_pre_build_stamp_file = os.path.join(noarch_obj_mod_dir, PRE_BUILD_OBJ_STAMP_FILE)
                if not os.path.isfile(mod_download_pre_build_stamp_file):
                    force_download = True
            if description.post_build:
                mod_download_post_build_stamp_file = os.path.join(noarch_obj_mod_dir, POST_BUILD_OBJ_STAMP_FILE)
                if not os.path.isfile(mod_download_post_build_stamp_file):
                    force_download = True
            mod_build_result = download_files(self._sysinfo, description, force_download, self._verbose)

        elif description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_COMPOSITE:
            mod_composite_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, current_model.model_name, build_config)
            mod_composite_dir_noarch = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, TAG_DIR_NOARCH)
            mkdir_safe(mod_composite_dir)
            if not isinstance(description.composite_spec, list):
                raise BuildSystemException("Spec of composite not a list, provided in: '{}'.".format(description.self_file_parts[0]))
            composite_entries = []
            for spec_entry in description.composite_spec:
                if isinstance(spec_entry, str):
                    composite_entries.append((spec_entry, {}))
                elif isinstance(spec_entry, list):
                    if len(spec_entry) < 2:
                        composite_entries.append((spec_entry[0], {}))
                    else:
                        if not isinstance(spec_entry[1], dict):
                            raise BuildSystemException("Entry properties in composite spec is not a dict, provided in: '{}'.".format(description.self_file_parts[0]))
                        target_properties = {}
                        for prop_name in spec_entry[1].keys():
                            prop_value = spec_entry[1][prop_name]
                            if prop_name in TAG_GRAMMAR_COMPOSITE_ITEM_STR_PROPERTIES:
                                if not isinstance(prop_value, str):
                                    raise BuildSystemException("Got malformed (not a str) property '{}' in composite spec, provided in: '{}'.".format(prop_name, description.self_file_parts[0]))
                            target_properties[prop_name] = prop_value
                        composite_entries.append((spec_entry[0], target_properties))
                else:
                    raise BuildSystemException("Entry in composite spec is not a str or list, provided in: '{}'.".format(description.self_file_parts[0]))

            composite_need_rebuild = False
            composite_subdirs_required = []
            composite_copy_files_info = []
            composite_output_files = []
            for desc_ref, target_properties in composite_entries:
                if target_properties.get(TAG_GRAMMAR_COMPOSITE_ITEM_IS_FILE):
                    file_ref = normalize_path_optional(desc_ref, description.self_dirname)
                    if not os.path.isfile(file_ref):
                        raise BuildSystemException("File '{}' not found, required in '{}'".format(file_ref, description.self_file_parts[0]))
                    if target_properties.get(TAG_GRAMMAR_COMPOSITE_ITEM_IS_SPEC_FILE):
                        composite_injection = parse_spec_file(file_ref, self._grammar_substitutions, current_model)
                        being_built, artifacts = False, []
                        for composite_injection_entry_path, composite_injection_arcname in composite_injection:
                            artifacts.append((BuildArtifact(BUILD_RET_TYPE_RESOURCE, composite_injection_entry_path, BUILD_RET_ATTR_DEFAULT), composite_injection_arcname))
                    else:
                        file_ref_is_executable = True if target_properties.get(TAG_GRAMMAR_COMPOSITE_ITEM_IS_EXECUTABLE) else False
                        file_ref_attr = BUILD_RET_ATTR_DEFAULT
                        if file_ref_is_executable:
                            file_ref_attr = file_ref_attr | BUILD_RET_ATTR_FLAG_EXECUTABLE
                        being_built, artifacts = False, [(BuildArtifact(BUILD_RET_TYPE_RESOURCE, file_ref, file_ref_attr), None)]
                else:
                    desc_dir = normalize_path_optional(desc_ref, description.self_dirname)
                    if not os.path.exists(desc_dir):
                        raise BuildSystemException("Directory '{}' not found, required in '{}'".format(desc_dir, description.self_file_parts[0]))
                    if not os.path.isdir(desc_dir):
                        raise BuildSystemException("Not a directory '{}', required to be a directory in '{}'".format(desc_dir, description.self_file_parts[0]))
                    sub_description = loader.load_build_description(desc_dir, current_model)
                    if sub_description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_COMPOSITE:
                        raise BuildSystemException("Build of recursive composites is not supported, provided in '{}'".format(description.self_file_parts[0]))
                    artifacts = []
                    being_built, _artifacts = self._perform_build(sub_description, used_model_name, build_config, rebuild_level)
                    for art in _artifacts:
                        artifacts.append((art, None))

                if being_built:
                    composite_need_rebuild = True
                for artifact_entry in artifacts:
                    art_type = artifact_entry[0].object_type
                    art_build_path = artifact_entry[0].path
                    art_build_attr = artifact_entry[0].attributes
                    art_alternative_name = artifact_entry[1]
                    art_alternative_subdir = None
                    art_primary = True
                    if art_type in (BUILD_RET_TYPE_LIB, BUILD_RET_TYPE_PDB):
                        art_primary = False
                    if art_type == BUILD_RET_TYPE_LIB:
                        continue
                    if art_type == BUILD_RET_TYPE_PDB:
                        if build_config != BUILD_CONFIG_DEBUG:
                            continue
                    art_target_dir = mod_composite_dir
                    if art_alternative_name is None:
                        art_target_fname = os.path.basename(art_build_path)
                    elif '/' in art_alternative_name:
                        art_alternative_bits = art_alternative_name.split('/')
                        art_target_fname = art_alternative_bits[-1]
                        art_alternative_subdir = '/'.join(art_alternative_bits[0:-1])
                    else:
                        art_target_fname = art_alternative_name
                    if TAG_GRAMMAR_COMPOSITE_ITEM_SUBDIR in target_properties:
                        target_subdir = target_properties[TAG_GRAMMAR_COMPOSITE_ITEM_SUBDIR]
                        art_target_dir = os.path.normpath(os.path.join(art_target_dir, target_subdir))
                        if art_alternative_subdir is not None:
                            art_target_dir = os.path.normpath(os.path.join(art_target_dir, art_alternative_subdir))
                        if art_target_dir not in composite_subdirs_required:
                            composite_subdirs_required.append(art_target_dir)
                    if art_primary:
                        if TAG_GRAMMAR_COMPOSITE_ITEM_REPLACE_EXT in target_properties:
                            art_target_fname = os.path.splitext(art_target_fname)[0]
                            art_target_fname = art_target_fname + target_properties[TAG_GRAMMAR_COMPOSITE_ITEM_REPLACE_EXT]
                        if TAG_GRAMMAR_COMPOSITE_ITEM_STRIP_FNANE_PREFIX in target_properties:
                            art_prefix_to_strip = target_properties[TAG_GRAMMAR_COMPOSITE_ITEM_STRIP_FNANE_PREFIX]
                            if art_target_fname.startswith(art_prefix_to_strip):
                                art_target_fname = art_target_fname[len(art_prefix_to_strip):]
                    art_target_path = os.path.join(art_target_dir, art_target_fname)
                    composite_copy_files_info.append((art_build_path, art_target_path, art_build_attr))
                    composite_output_files.append(BuildArtifact(art_type, art_target_path, art_build_attr))

            if description.pre_build_noarch:
                mod_composite_pre_build_noarch_stamp_file = os.path.join(mod_composite_dir_noarch, PRE_BUILD_OBJ_STAMP_FILE)
                if not os.path.exists(mod_composite_pre_build_noarch_stamp_file):
                    composite_need_rebuild = True

            if description.pre_build:
                mod_composite_pre_build_stamp_file = os.path.join(mod_composite_dir, PRE_BUILD_OBJ_STAMP_FILE)
                if not os.path.exists(mod_composite_pre_build_stamp_file):
                    composite_need_rebuild = True

            if description.post_build:
                mod_composite_post_build_stamp_file = os.path.join(mod_composite_dir, POST_BUILD_OBJ_STAMP_FILE)
                if not os.path.exists(mod_composite_post_build_stamp_file):
                    composite_need_rebuild = True

            if not composite_need_rebuild:
                for art_build_path, art_target_path, art_build_attr in composite_copy_files_info:
                    if not os.path.isfile(art_target_path):
                        composite_need_rebuild = True
                        break
                    mt_src = os.path.getmtime(art_build_path)
                    mt_dst = os.path.getmtime(art_target_path)
                    if prerequisite_newer_then_target(mt_dst, mt_src, art_target_path, art_build_path, self._verbose):
                        composite_need_rebuild = True
                        break

            if composite_need_rebuild:
                cleanup_dir(mod_composite_dir)
                for composite_subdir in composite_subdirs_required:
                    mkdir_safe(composite_subdir)
                for art_build_path, art_target_path, art_build_attr in composite_copy_files_info:
                    print("BUILDSYS: copy file: '{}' >>> '{}'".format(art_build_path, art_target_path))
                    art_is_exe = True if art_build_attr & BUILD_RET_ATTR_FLAG_EXECUTABLE else False
                    art_permissions = make_posix_permissions(art_is_exe)
                    shutil.copyfile(art_build_path, art_target_path)
                    shutil.copystat(art_build_path, art_target_path)
                    if sys.platform != 'win32':
                        print("BUILDSYS: chmod: '{:04o}' >>> '{}'".format(art_permissions, art_target_path))
                        os.chmod(art_target_path, art_permissions)
                    if self._faccess:
                        self._follow_faccess_for_file(art_build_path)
            else:
                print("BUILDSYS: up-to-date: '{}', COMPOSITE".format(description.module_name))

            mod_build_result = (composite_need_rebuild, composite_output_files)

        else:
            mod_obj_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, current_model.model_name, build_config)
            mkdir_safe(mod_obj_dir)

            is_exe_or_dll = False
            exe_or_dll_deps_changed = False
            if (description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_EXE) or (description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_LIB_SHARED):
                is_exe_or_dll = True

            if is_exe_or_dll and rebuild_level >= 0:
                static_libs_deps = []
                shared_libs_deps = []
                eval_libs_in_description(loader, description, current_model, static_libs_deps, shared_libs_deps)
                submod_rebuild_level = 2 if rebuild_level == 2 else 0

                for libstatic_desc in static_libs_deps:
                    libstatic_cached_result = self._build_cache.get_cached_build_result(libstatic_desc, used_model_name)
                    if libstatic_cached_result is not None:
                        continue
                    exe_or_dll_build_dep = self._perform_build(libstatic_desc, used_model_name, build_config, submod_rebuild_level)
                    if exe_or_dll_build_dep[0]:
                        exe_or_dll_deps_changed = True

                for libshared_desc in shared_libs_deps:
                    libshared_cached_result = self._build_cache.get_cached_build_result(libshared_desc, used_model_name)
                    if libshared_cached_result is not None:
                        continue
                    exe_or_dll_build_dep = self._perform_build(libshared_desc, used_model_name, build_config, submod_rebuild_level)
                    if exe_or_dll_build_dep[0]:
                        exe_or_dll_deps_changed = True

            actions = []
            obj_names = []
            parsed_build_list = resolve_build_list(description, current_model)
            if len(parsed_build_list) == 0 and description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_LIB_STATIC:
                raise BuildSystemException("Empty build list provided in: '{}'.".format(description.self_file_parts[0]))

            for build_type, source_path, obj_name in parsed_build_list:
                action = None
                obj_names.append(obj_name)
                if build_type == BUILD_TYPE_CPP:
                    action = toolset.create_cpp_build_action(description=description, cpp_source=source_path,
                        obj_directory=mod_obj_dir, obj_name=obj_name, build_model=current_model, build_config=build_config)
                elif build_type == BUILD_TYPE_C:
                    action = toolset.create_c_build_action(description=description, c_source=source_path,
                        obj_directory=mod_obj_dir, obj_name=obj_name, build_model=current_model, build_config=build_config)
                elif build_type == BUILD_TYPE_ASM:
                    action = toolset.create_asm_build_action(description=description, asm_source=source_path,
                        obj_directory=mod_obj_dir, obj_name=obj_name, build_model=current_model, build_config=build_config)
                if action is None:
                    raise BuildSystemException("Can't create build action for: '{}'.".format(source_path))
                actions.append(action)

            force_mod_rebuild = rebuild_level > 0
            force_src_rebuild = rebuild_level > 0

            src_ctx = ToolsetActionContext(force=force_src_rebuild, verbose=self._verbose, trace=self._trace)
            for action in actions:
                self._actions_pool.put(action, src_ctx)
            src_rebuilt = self._actions_pool.join()
            if src_rebuilt:
                force_mod_rebuild = True

            if not force_mod_rebuild:
                if is_exe_or_dll:
                    force_mod_rebuild = exe_or_dll_deps_changed

            model_lib_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_LIB], current_model.model_name, build_config)
            model_sharedlib_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_SHARED], current_model.model_name, build_config)
            model_exe_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_EXE], current_model.model_name, build_config)
            mod_action = None

            if description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_LIB_STATIC:
                mkdir_safe(model_lib_dir)
                mod_action = toolset.create_lib_static_link_action(description=description,
                    lib_directory=model_lib_dir,
                    obj_directory=mod_obj_dir,
                    obj_names=obj_names, build_model=current_model, build_config=build_config)

            elif description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_LIB_SHARED:
                mkdir_safe(model_sharedlib_dir)
                mod_action = toolset.create_lib_shared_link_action(description=description,
                    sharedlib_directory=model_sharedlib_dir,
                    lib_directory=model_lib_dir,
                    obj_directory=mod_obj_dir,
                    obj_names=obj_names, build_model=current_model, build_config=build_config)

            elif description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_EXE:
                mkdir_safe(model_exe_dir)
                mod_action = toolset.create_exe_link_action(description=description,
                    sharedlib_directory=model_sharedlib_dir,
                    exe_directory=model_exe_dir,
                    lib_directory=model_lib_dir,
                    obj_directory=mod_obj_dir,
                    obj_names=obj_names, build_model=current_model, build_config=build_config)

            if mod_action is None:
                raise BuildSystemException("Can't create build action for module of type: '{}', provided in: '{}'.".format(description.module_type, description.self_file_parts[0]))

            mod_ctx = ToolsetActionContext(force=force_mod_rebuild, verbose=self._verbose, trace=self._trace)
            mod_action_result = mod_action.safe_execute(mod_ctx)
            if mod_action_result.exit_code is not None:
                print(mod_action_result.error_text)
                raise BuildSystemSysExit(mod_action_result.exit_code)

            mod_build_result = (mod_action_result.rebuilt, mod_action_result.artifacts)

            if self._faccess:
                faccess_stamps = []
                faccess_mod_header_refs = set()
                for build_type, source_path, obj_name in parsed_build_list:
                    norm_src_path = os.path.normcase(source_path)
                    faccess_in_interest = False
                    for faccess_prefix in self._faccess_prefixes:
                        if norm_src_path.startswith(self._sysinfo[TAG_CFG_PROJECT_OUTPUT_COMMON_PREFIX]):
                            break
                        if norm_src_path.startswith(faccess_prefix):
                            faccess_in_interest = True
                            break
                    if not faccess_in_interest:
                        continue
                    norm_src_path = source_path[len(self._sysinfo[TAG_CFG_PROJECT_ROOT_COMMON_PREFIX]):]
                    faccess_stamp_file = os.path.join(self._sysinfo[TAG_CFG_DIR_FACCESS], norm_src_path)
                    faccess_stamps += [ (norm_src_path.replace('\\', '/'), faccess_stamp_file) ]
                    facccess_dep_file = os.path.join(mod_obj_dir, obj_name + self._sysinfo[TAG_CFG_DEP_SUFFIX])
                    headers_refs = load_py_object(facccess_dep_file)
                    for header_ref in headers_refs:
                        header_ref_norm = os.path.normcase(os.path.normpath(header_ref))
                        if header_ref_norm in faccess_mod_header_refs:
                            continue
                        faccess_mod_header_refs.add(header_ref_norm)
                        faccess_header_in_interest = False
                        for faccess_prefix in self._faccess_prefixes:
                            norm_header_path = self._sysinfo[TAG_CFG_PROJECT_ROOT_COMMON_PREFIX] + header_ref_norm
                            if norm_header_path.startswith(self._sysinfo[TAG_CFG_PROJECT_OUTPUT_COMMON_PREFIX]):
                                break
                            if norm_header_path.startswith(faccess_prefix):
                                faccess_header_in_interest = True
                                break
                        if not faccess_header_in_interest:
                            continue
                        header_relpath = os.path.normpath(header_ref)
                        faccess_stamp_file = os.path.join(self._sysinfo[TAG_CFG_DIR_FACCESS], header_relpath)
                        faccess_stamps += [ (header_relpath.replace('\\', '/'), faccess_stamp_file) ]
                if current_model.platform_name == TAG_PLATFORM_WINDOWS:
                    if description.module_type in [TAG_GRAMMAR_VALUE_MODULE_TYPE_EXE, TAG_GRAMMAR_VALUE_MODULE_TYPE_LIB_SHARED]:
                        faccess_rc_file = verify_winrc_file(description)
                        if faccess_rc_file:
                            self._follow_faccess_for_file(faccess_rc_file)
                if description.module_type == TAG_GRAMMAR_VALUE_MODULE_TYPE_LIB_SHARED:
                    faccess_def_file = verify_exports_def_file(description)
                    if faccess_def_file:
                        self._follow_faccess_for_file(faccess_def_file)
                for faccess_relpath, faccess_stamp_file in faccess_stamps:
                    if self._verbose:
                        print("BUILDSYS: FACCESS: {}".format(faccess_relpath))
                    mkdir_safe(os.path.dirname(faccess_stamp_file))
                    touch_file(faccess_stamp_file)

        if mod_build_result[0]:
            if description.post_build:
                self._perform_post_build(description, used_model_name, build_config, rebuild_level)

        self._build_cache.cache_build_result(description, used_model_name, mod_build_result[1])
        print("BUILDSYS: finish build '{}', {},{}".format(description.module_name, description.module_type, used_model_name))
        return mod_build_result

    def _create_ext_action(self, expected_ext_type, ext_name, description, used_model_name, build_config, rebuild_level):
        if not ext_name in self._imported_extensions or not description._buildsys_import_list or not ext_name in description._buildsys_import_list:
            raise BuildSystemException("Build extension '{}' is unknown (or not imported), got from '{}'.".format(ext_name, description.self_file_parts[0]))
        ext_description = self._imported_extensions[ext_name].description
        if ext_description.ext_type != expected_ext_type:
            raise BuildSystemException("Type info mismatched in build extension '{}': got '{}', but expected '{}'.".format(ext_name, ext_description.ext_type, expected_ext_type))
        action = None
        try:
            self._ext_protector.inc_ref(ext_description, used_model_name)
            action = self._create_ext_action_imp(ext_description, description, used_model_name, build_config, rebuild_level)
        finally:
            self._ext_protector.dec_ref(ext_description, used_model_name)
        return action

    def _create_ext_action_imp(self, ext_description, description, used_model_name, build_config, rebuild_level):
        ext_ref_count = self._ext_protector.ref_count(ext_description, used_model_name)
        if ext_ref_count > 2:
            raise BuildSystemException("Got unexpected recursive call from '{}'.".format(ext_description.self_file_parts[0]))

        native_toolset = None
        native_loader = None
        native_model = None
        if (ext_description.ext_native_depends is not None or
                ext_description.ext_obj_dir_native_as_var is not None or
                ext_description.ext_exe_path_native_as_var is not None):
            if self._native_model_remap is None:
                raise BuildSystemException("Native model is not defined, required by '{}'.".format(ext_description.self_file_parts[0]))
            native_toolset, native_loader = self._toolset_models_mapping[self._native_model_remap]
            native_model = native_toolset.supported_models[self._native_model_remap]

        if ext_description.ext_native_depends is not None:
            ext_private_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_EXT], ext_description.ext_name)
            mkdir_safe(ext_private_dir)
            stamp_fname = 'depends-{}-{}.stamp'.format(self._native_model_remap, build_config)
            stamp_path = os.path.join(ext_private_dir, stamp_fname)
            up_to_date, _ = is_target_up_to_date(stamp_path, None, ext_description.self_file_parts, self._verbose)
            if rebuild_level > 1 or (not up_to_date and rebuild_level >= 0):
                submod_rebuild_level = 2 if rebuild_level == 2 and ext_ref_count < 2 else 0
                for dep_ref in ext_description.ext_native_depends:
                    dep_dir = normalize_path_optional(dep_ref, ext_description.self_dirname)
                    dep_desc = native_loader.load_build_description(dep_dir, native_model, required_by=ext_description.self_file_parts[0])
                    self._perform_build(dep_desc, self._native_model_remap, build_config, submod_rebuild_level)
                touch_file(stamp_path)

        local_vars = {}
        if ext_description.ext_obj_dir_native_as_var is not None:
            for local_var_name, module_ref in ext_description.ext_obj_dir_native_as_var:
                module_dir = normalize_path_optional(module_ref, ext_description.self_dirname)
                module_desc = native_loader.load_build_description(module_dir, native_model, required_by=ext_description.self_file_parts[0])
                module_obj_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], module_desc.module_name, self._native_model_remap, build_config)
                local_vars[local_var_name] = module_obj_dir

        if ext_description.ext_exe_path_native_as_var is not None:
            for local_var_name, module_ref in ext_description.ext_exe_path_native_as_var:
                module_dir = normalize_path_optional(module_ref, ext_description.self_dirname)
                module_desc = native_loader.load_build_description(module_dir, native_model, required_by=ext_description.self_file_parts[0])
                if module_desc.module_type != TAG_GRAMMAR_VALUE_MODULE_TYPE_EXE:
                    raise BuildSystemException("Module '{}' is not an executable, required by '{}'.".format(module_desc.module_name, ext_description.self_file_parts[0]))
                module_exe_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_EXE], self._native_model_remap, build_config)
                module_exe_name = module_desc.module_name
                if module_desc.exe_name:
                    module_exe_name = module_desc.exe_name
                if sys.platform == 'win32':
                   module_exe_name = module_exe_name + '.exe'
                local_vars[local_var_name] = os.path.join(module_exe_dir, module_exe_name)

        subst_vars = {}
        if ext_description.ext_vars_required is not None:
            for subst_var_name in ext_description.ext_vars_required:
                if subst_var_name == TAG_GRAMMAR_VALUE_EXT_VAR_DIR_HERE:
                    subst_vars[TAG_GRAMMAR_VALUE_EXT_VAR_DIR_HERE] = ext_description.self_dirname
                elif subst_var_name == TAG_GRAMMAR_VALUE_EXT_VAR_BUILDSYS_TARGET_OBJ_DIR:
                    mod_obj_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, used_model_name, build_config)
                    mkdir_safe(mod_obj_dir)
                    subst_vars[TAG_GRAMMAR_VALUE_EXT_VAR_BUILDSYS_TARGET_OBJ_DIR] = mod_obj_dir
                elif subst_var_name == TAG_GRAMMAR_VALUE_EXT_VAR_BUILDSYS_TARGET_OBJ_NOARCH_DIR:
                    mod_obj_noarch_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, TAG_DIR_NOARCH)
                    mkdir_safe(mod_obj_noarch_dir)
                    subst_vars[TAG_GRAMMAR_VALUE_EXT_VAR_BUILDSYS_TARGET_OBJ_NOARCH_DIR] = mod_obj_noarch_dir
                elif subst_var_name == TAG_GRAMMAR_VALUE_EXT_VAR_BUILDSYS_TARGET_SRC_DIR:
                    subst_vars[TAG_GRAMMAR_VALUE_EXT_VAR_BUILDSYS_TARGET_SRC_DIR] = description.self_dirname
                elif subst_var_name == TAG_GRAMMAR_VALUE_EXT_VAR_EXE_SUFFIX:
                    if sys.platform == 'win32':
                        subst_vars[TAG_GRAMMAR_VALUE_EXT_VAR_EXE_SUFFIX] = '.exe'
                    else:
                        subst_vars[TAG_GRAMMAR_VALUE_EXT_VAR_EXE_SUFFIX] = ''
                elif subst_var_name == TAG_GRAMMAR_VALUE_EXT_VAR_OS_SEP:
                    subst_vars[TAG_GRAMMAR_VALUE_EXT_VAR_OS_SEP] = os.sep
                else:
                    raise BuildSystemException("Unsupported extension variable '{}', got from '{}'.".format(subst_var_name, ext_description.self_file_parts[0]))

        if ext_description.ext_local_vars_required is not None:
            for local_var_name in ext_description.ext_local_vars_required:
                if local_var_name not in local_vars:
                    raise BuildSystemException("Undefined local variable '{}' required, got from '{}'.".format(local_var_name, ext_description.self_file_parts[0]))
                subst_vars[local_var_name] = local_vars[local_var_name]

        cmdline_value = ext_description.ext_call_cmdline if ext_description.ext_call_cmdline else ''
        if subst_vars:
            try:
                cmdline = cmdline_value.format(**subst_vars)
            except Exception as fmtexc:
                raise BuildSystemException("Malformed value '{}' in extension token '{}' - {}: {}, got from '{}'.".format(
                    cmdline_value, TAG_GRAMMAR_KEY_EXT_CALL_CMDLINE, type(fmtexc).__name__, fmtexc, ext_description.self_file_parts[0]))
        else:
            cmdline = cmdline_value

        posix = False if sys.platform == 'win32' else True
        argv = shlex.split(cmdline, comments=False, posix=posix)
        if ext_description.ext_call_type == TAG_GRAMMAR_VALUE_EXT_CALL_TYPE_INTERPRETER:
            if self._sysinfo[TAG_CFG_FROZEN]:
                argv.insert(0, '--interpreter')
            argv.insert(0, sys.executable)

        if not argv:
            raise BuildSystemException("Malformed value '{}' in extension token '{}', command-line is empty, got from '{}'.".format(
                cmdline_value, TAG_GRAMMAR_KEY_EXT_CALL_CMDLINE, ext_description.self_file_parts[0]))
        ext_action = ExtAction(ext_description.ext_type, ext_description.ext_name, description.module_name, self._verbose, argv)
        return ext_action

    def _perform_pre_build(self, description, used_model_name, build_config, rebuild_level, noarch):
        if noarch or description.module_type in (TAG_GRAMMAR_VALUE_MODULE_TYPE_ZIP_FILE, TAG_GRAMMAR_VALUE_MODULE_TYPE_DOWNLOAD):
            mod_obj_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, TAG_DIR_NOARCH)
        else:
            mod_obj_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, used_model_name, build_config)
        mkdir_safe(mod_obj_dir)
        mod_pre_build_stamp_file = os.path.join(mod_obj_dir, PRE_BUILD_OBJ_STAMP_FILE)
        if os.path.isfile(mod_pre_build_stamp_file):
            if rebuild_level < 1:
                return
            else:
                os.remove(mod_pre_build_stamp_file)
        if noarch:
            ext_type = TAG_GRAMMAR_VALUE_EXT_TYPE_PRE_BUILD_NOARCH
            ext_list = description.pre_build_noarch
        else:
            ext_type = TAG_GRAMMAR_VALUE_EXT_TYPE_PRE_BUILD
            ext_list = description.pre_build
        for ext_name in ext_list:
            ext_action = self._create_ext_action(ext_type, ext_name, description, used_model_name, build_config, rebuild_level)
            ext_action()
        touch_file(mod_pre_build_stamp_file)

    def _perform_post_build(self, description, used_model_name, build_config, rebuild_level):
        for ext_name in description.post_build:
            ext_action = self._create_ext_action(TAG_GRAMMAR_VALUE_EXT_TYPE_POST_BUILD, ext_name,
                description, used_model_name, build_config, rebuild_level)
            ext_action()
        if description.module_type in (TAG_GRAMMAR_VALUE_MODULE_TYPE_ZIP_FILE, TAG_GRAMMAR_VALUE_MODULE_TYPE_DOWNLOAD):
            mod_obj_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, TAG_DIR_NOARCH)
        else:
            mod_obj_dir = os.path.join(self._sysinfo[TAG_CFG_DIR_OBJ], description.module_name, used_model_name, build_config)
        mod_post_build_stamp_file = os.path.join(mod_obj_dir, POST_BUILD_OBJ_STAMP_FILE)
        touch_file(mod_post_build_stamp_file)

    def _perform_spec_post_build(self, description, used_model_name, build_config, rebuild_level):
        for ext_name in description.spec_post_build:
            ext_action = self._create_ext_action(TAG_GRAMMAR_VALUE_EXT_TYPE_SPEC_POST_BUILD, ext_name,
                description, used_model_name, build_config, rebuild_level)
            ext_action()
