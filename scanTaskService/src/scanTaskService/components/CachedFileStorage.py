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
import logging

from scanTaskService.Config import RUNTIME_STORAGE_FILE_CACHE_SETTING_NAME, TaskErrorNo, CLEAR_ALL_FILE_CACHE
from common.ConfigObject import ConfigObject
from scanTaskService.util.SettingStorageUtil import SettingStorageUtil
from scanTaskService.util.TimeUtility import TimeUtility
from common.XcalException import XcalException
from common.XcalLogger import XcalLogger


class CachedFileStorage(object):
    def __init__(self, logger:XcalLogger, task_config:ConfigObject):
        self.logger = XcalLogger("CachedFileStorage", "__init__", parent=logger)
        self.task_config = task_config
        pass

    def check_storage_exists(self, key:str, topic:str = None):
        """
        Check & Get FileId from Cached File Storage
        :param key: the key to search (e.g. file hash)
        :param topic: the category of the storage (storageName)
        :return: None is no such item was found.
        """
        if key is None:
            raise XcalException("CachedFileStorage", "check_storage_exists", "provided None in key",
                                TaskErrorNo.E_UTIL_CACHE_NONE_PARAM)

        self.logger.trace("check_storage_exists", "Searching for storage matching key = %s" % key)

        file_list = self.load_list_from_settings(topic)
        for one_file_info in file_list:
            file_id = one_file_info.get("fileId")
            self.logger.info("check_storage_exists", "Found one fileId = %s, with key = %s" % (file_id, one_file_info.get("key")))
            if (one_file_info.get("key") is not None and key is not None) and (one_file_info.get("key") == key):
                return one_file_info

        return None

    def save_to_storage(self, key:str, file_id:str, topic:str = None):
        if topic is None:
            topic = RUNTIME_STORAGE_FILE_CACHE_SETTING_NAME

        if key is None or file_id is None or len(file_id) < 1:
            raise XcalException("CachedFileStorage", "save_to_storage", "provided None in key or file_id", TaskErrorNo.E_UTIL_CACHE_NONE_PARAM)

        savable_file_info = {"fileId": file_id, "key": key, "updateTime": TimeUtility().get_utc_timestamp()}
        file_list = self.load_list_from_settings(topic)
        new_item = True

        for one_file_info in file_list:
            saved_key = one_file_info.get("key")
            saved_file_id = one_file_info.get("fileId")
            self.logger.trace("Located one existing key = %s, fileId = %s" % (saved_key, saved_file_id), "")
            if saved_key == key:
                new_item = False
                one_file_info["fileId"] = file_id
                self.logger.trace("File key = %s, fileId = %s already exists, updating ... " % (key, file_id), "")

        self.logger.trace("File key = %s, not existing, saving new fileIdd = %s, skipping ... " % (key, file_id), "")

        if new_item:
            file_list.append(savable_file_info)

        # Support or debug purpose only, for deleting all files stored in the server
        if CLEAR_ALL_FILE_CACHE:
            file_list = []

        savable_dict = {"list": file_list}
        setting_util = SettingStorageUtil(self.logger, self.task_config)
        setting_util.set_file_cache_by_name(topic, json.dumps(savable_dict))

    def load_list_from_settings(self, topic=None):
        if topic is None:
            topic = RUNTIME_STORAGE_FILE_CACHE_SETTING_NAME

        setting_util = SettingStorageUtil(self.logger, self.task_config)
        object_list_str = setting_util.get_file_cache_by_name(topic)

        if object_list_str is not None and len(object_list_str) > 0:
            try:
                saved_dict = json.loads(object_list_str)
            except json.decoder.JSONDecodeError as err:
                logging.exception(err)
                self.logger.error("CachedFileStorage", "load_list_from_settings", "")
                raise XcalException("CachedFileStorage", "load_list_from_settings",
                                    "Cannot load saved storage json from settings = %s" % str(object_list_str),
                                    TaskErrorNo.E_UTIL_CACHE_JSON_INVALID)
        else:
            saved_dict = {"list": []}

        file_list = saved_dict.get("list")
        return file_list

    def remove_file_storage(self, key:str, topic:str = None):
        if topic is None:
            topic = RUNTIME_STORAGE_FILE_CACHE_SETTING_NAME
        if key is None:
            raise XcalException("CachedFileStorage", "save_to_storage", "provided None in key",
                                TaskErrorNo.E_UTIL_CACHE_NONE_PARAM)
        file_list = self.load_list_from_settings(topic)
        new_list = []
        removed_count = 0
        for one_file_info in file_list:
            saved_key = one_file_info.get("key")
            saved_file_id = one_file_info.get("fileId")
            self.logger.trace("Located one existing key = %s, fileId = %s" % (saved_key, saved_file_id), "")
            if saved_key == key:
                self.logger.trace("Found the one to remove, not adding it to result list", "")
                removed_count += 1
            else:
                new_list.append(one_file_info)

        savable_dict = {"list": new_list}
        setting_util = SettingStorageUtil(self.logger, self.task_config)
        setting_util.set_file_cache_by_name(topic, json.dumps(savable_dict))

        return removed_count

    def remove_all_file_storage(self, topic:str = None):
        if topic is None:
            topic = RUNTIME_STORAGE_FILE_CACHE_SETTING_NAME
        new_list = []
        savable_dict = {"list": new_list}
        setting_util = SettingStorageUtil(self.logger, self.task_config)
        setting_util.set_file_cache_by_name(topic, json.dumps(savable_dict))