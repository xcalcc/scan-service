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



import logging
import unittest
import uuid

from common.XcalLogger import XcalLogger
from scanTaskService.Config import app
from tests.TestConfig import TEST_TOKEN, TEST_AGENT_USER, TEST_CPP_AGENT_ADDR, TEST_SCANDATA_DIR
from scanTaskService.components.CachedFileStorage import CachedFileStorage
from common.ConfigObject import ConfigObject
from common.TokenExtractor import TOKEN_FIELD_NAME
from common.XcalException import XcalException


class TestCachedFileStorage(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(format='%(asctime)s   [%(levelname)12s]    [%(module)16s]   %(message)s',
                            level=logging.DEBUG)
        self.app = app.test_client()
        self.viable_co = ConfigObject({
            "scanTaskId": "7890",
            "preprocessPath": TEST_SCANDATA_DIR + "/7890",
            "scanFilePath": TEST_SCANDATA_DIR + "/7890",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": ConfigObject({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_CPP_AGENT_ADDR,
            })
        })
        self.logger = XcalLogger("Test_DockerUtility", "main")

    def test_get_with_key(self):
        cache = CachedFileStorage(self.logger, self.viable_co)
        res = cache.check_storage_exists("abc")
        self.assertIsNotNone(res)
        self.assertIn("fileId", res)
        self.assertIn("key", res)

    def test_get_with_none_key(self):
        cache = CachedFileStorage(self.logger, self.viable_co)
        try:
            cache.check_storage_exists(None)
        except XcalException as err:
            self.assertIn("provided None in key", err.message)
        else:
            self.assertTrue(False, msg="There should be exceptions popped up, yet given None")
        pass

    def test_save_file_with_valid_topic(self):
        cache = CachedFileStorage(self.logger, self.viable_co)
        cache.save_to_storage("abc", "file-xxxx-yyyy-zzzzzzzz")

    def test_save_file_with_new_value_old_key(self):
        cache = CachedFileStorage(self.logger, self.viable_co)
        cache.save_to_storage("abc", str(uuid.uuid1()))

    def test_save_file_with_new_key_new_value(self):
        cache = CachedFileStorage(self.logger, self.viable_co)
        cache.save_to_storage(str(uuid.uuid1()), str(uuid.uuid1()))


    def test_save_file_with_none_topic(self):
        cache = CachedFileStorage(self.logger, self.viable_co)
        try:
            cache.save_to_storage("abc", None)
        except XcalException as err:
            self.assertIn("provided None in key", err.message)
        else:
            self.assertTrue(False, msg="There should be exceptions popped up, yet given None")


    def test_save_file_with_key_and_incorrect_id(self):
        cache = CachedFileStorage(self.logger, self.viable_co)
        try:
            cache.save_to_storage("abc", "")
        except XcalException as err:
            self.assertIn("provided None in key", err.message)
        else:
            self.assertTrue(False, msg="There should be exceptions popped up, yet given None")

    def test_save_file_with_none_key(self):
        cache = CachedFileStorage(self.logger, self.viable_co)
        try:
            cache.save_to_storage(None, "file-id-xxxx-xxxx")
        except XcalException as err:
            self.assertIn("provided None in key", err.message)
        else:
            self.assertTrue(False, msg="There should be exceptions popped up, yet given None")

    def test_save_file_with_none_file_id(self):
        cache = CachedFileStorage(self.logger, self.viable_co)
        try:
            cache.save_to_storage("abc", None)
        except XcalException as err:
            self.assertIn("provided None in key", err.message)
        else:
            self.assertTrue(False, msg="There should be exceptions popped up, yet given None")