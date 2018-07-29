from __future__ import print_function
import json
import os
import os.path

from .constants import *
from .error_utils import BuildSystemException


def perform_faccess_emerge(sysinfo):
    catalog = []
    faccess_dir = sysinfo[TAG_CFG_DIR_FACCESS]
    if not os.path.isdir(faccess_dir):
        raise BuildSystemException("Directory not found: '{}'.".format(faccess_dir))
    subdirs = [(faccess_dir, '')]
    while subdirs:
        subdir_path, subdir_archname = subdirs[0]
        del subdirs[0]
        for item in sorted(os.listdir(subdir_path)):
            item_path = os.path.join(subdir_path, item)
            if subdir_archname:
                item_arcname = '/'.join([subdir_archname, item])
            else:
                item_arcname = item
            if os.path.isdir(item_path):
                subdirs.append((item_path, item_arcname))
            else:
                catalog.append(item_arcname)
    result = os.path.join(sysinfo[TAG_CFG_DIR_PROJECT_OUTPUT], BUILD_CONFIG_DEFAULT_FACCESS_EMERGE_FILE)
    try:
        with open(result, 'wt') as fh:
            json.dump(catalog, fh, sort_keys=True, indent=4, ensure_ascii=False)
    except:
        if os.path.isfile(result):
            os.remove(result)
        raise
    print("BUILDSYS: File generated: '{}'\n          Entries count: {}".format(result, len(catalog)))
