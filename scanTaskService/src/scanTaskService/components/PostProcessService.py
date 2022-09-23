#  Copyright (C) 2019-2022 Xcalibyte (Shenzhen) Limited.
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import json
import os
import tarfile

from common.CommonGlobals import BASE_SCAN_PATH
from common.ConfigObject import ConfigObject
from common.FileUtility import FileUtility
from common.XcalLogger import XcalLogger
from scanTaskService.Config import JAVA_SCAN_OBJECT_FILE_DIR, RUNTIME_STORAGE_FILE_CACHE_SETTING_NAME
from scanTaskService.components.CachedFileStorage import CachedFileStorage
from scanTaskService.components.InternalCommunicator import XcalInternalCommunicator
from scanTaskService.util.SettingStorageUtil import SettingStorageUtil


class PostProcessService(object):
    def __init__(self, logger: XcalLogger, task_config: ConfigObject):
        self.task_config = task_config
        self.scan_id = task_config.get("scanTaskId")
        self.scan_path = os.path.join(BASE_SCAN_PATH, self.scan_id)
        self.logger = XcalLogger("PostProcessService", "__init__", parent=logger)

    def find_file(self, file_name, path):
        for root, dirs, files in os.walk(path):
            if file_name in files:
                return os.path.join(root, file_name)

    def post_process(self):
        cache = CachedFileStorage(self.logger, self.task_config)
        checksum = self.task_config.get("runtimeLibraryChecksum")
        runtime_cache_setting_value = cache.check_storage_exists(checksum)
        if runtime_cache_setting_value is None:
            self.logger.warn("post_process", "no caching file related to checksum %s found" % checksum)
        elif runtime_cache_setting_value.get("artifactFileId") is None:
            communicator = XcalInternalCommunicator(self.logger, self.task_config)

            extra_path = os.path.join(self.scan_path, JAVA_SCAN_OBJECT_FILE_DIR)
            runtime_library = 'rt.o'

            utility = FileUtility(self.logger)
            utility.goto_dir(self.scan_path)
            file_path = self.find_file(runtime_library, extra_path)
            self.logger.trace("post_process", "file_path: %s" % file_path)
            if file_path is not None:
                with tarfile.open('rt_o.tgz', 'w:gz') as archive:
                    archive.add(os.path.relpath(file_path, self.scan_path))

                file_id = communicator.upload_file(os.path.join(self.scan_path, "rt_o.tgz"))
                runtime_cache_setting_value["artifactFileId"] = file_id

                # remove old value, load list from settings and add new value
                cache.remove_file_storage(checksum)
                file_list = cache.load_list_from_settings()
                file_list.append(runtime_cache_setting_value)
                savable_dict = {"list": file_list}
                setting_util = SettingStorageUtil(self.logger, self.task_config)
                setting_util.set_file_cache_by_name(RUNTIME_STORAGE_FILE_CACHE_SETTING_NAME, json.dumps(savable_dict))
            utility.goback_dir()
