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

from common.ConfigObject import ConfigObject
from common.XcalException import XcalException
from common.XcalLogger import XcalLogger
from scanTaskService.Config import TaskErrorNo
from scanTaskService.components.InternalCommunicator import XcalInternalCommunicator


class SettingStorageUtil(object):

    def __init__(self, logger: XcalLogger, task_config: ConfigObject):
        self.logger = XcalLogger('SettingStorageUtil', '__init__', parent=logger)
        self.task_config = task_config

    def get_file_cache_raw_object_by_name(self, name: str):
        file_cache_list = XcalInternalCommunicator(self.logger, self.task_config).list_file_cache()
        self.logger.debug('get_file_cache_raw_object_by_name', json.dumps(file_cache_list))
        for file_cache in file_cache_list:
            if file_cache.get('cacheKey', 'unknown') == name:
                return file_cache
        return None

    def get_file_cache_by_name(self, name: str):
        file_cache = self.get_file_cache_raw_object_by_name(name)
        if file_cache is not None:
            return file_cache.get('cacheValue')
        return None

    def set_file_cache_by_name(self, name: str, value: str):
        if name is None or value is None:
            raise XcalException('SettingStorageUtil', 'set_file_cache_by_name', 'name or value is None',
                                TaskErrorNo.E_SETTING_SET_PARM_ERROR)
        file_cache = self.get_file_cache_raw_object_by_name(name)
        if file_cache is None:
            file_cache = {'cacheKey': name, 'cacheValue': value}
            XcalInternalCommunicator(self.logger, self.task_config).create_file_cache(file_cache)
        else:
            file_cache = {'cacheKey': name, 'cacheValue': value}
            XcalInternalCommunicator(self.logger, self.task_config).update_file_cache(file_cache)
