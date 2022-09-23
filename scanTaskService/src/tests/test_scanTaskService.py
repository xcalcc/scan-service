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



import unittest
import uuid

from scanTaskService.Config import app
from scanTaskService import scanApp
from unittest import mock
import json

from tests.TestConfig import TEST_AGENT_ADDR, TEST_AGENT_USER, TEST_TOKEN, TEST_SCANDATA_DIR
from common.TokenExtractor import TOKEN_FIELD_NAME

TEST_DEMO_PROJ_DIR = TEST_SCANDATA_DIR + "/1234"

class TestScanTaskService(unittest.TestCase):
    """
    test scanTaskService in scanTaskService.py
    """

    def setUp(self):
        self.app = app.test_client()
        self.scan_api = '/api/scan_task_service/v2'
        self.get_agent_task_api = '/api/scan_task_service/v2/agent/get_task'
        self.get_cache_api = '/api/scan_task_service/v2/agent/check_file_cache'
        self.save_cache_api = '/api/scan_task_service/v2/agent/save_file_cache'

    def test_scan_task_start_ok(self):
        scanApp.SCAN_controller = mock.Mock()
        config_content = json.dumps({'agentUser': TEST_AGENT_USER, 'agentAddress': TEST_AGENT_ADDR})
        co = {'scanTaskId': '1234', 'scanFilePath': TEST_DEMO_PROJ_DIR,
              'preprocessPath': TEST_DEMO_PROJ_DIR,
         'configContent': config_content, TOKEN_FIELD_NAME: TEST_TOKEN}
        resp_info = self.app.post(self.scan_api, json = co)
        self.assertEqual(resp_info.status_code, 200)
        data = json.loads(resp_info.get_data().decode())
        self.assertEqual(data, 'scan_task_service pipeline started')

    def test_scan_task_start_without_token(self):
        config_content = json.dumps({'language': 'C'})
        resp_info = self.app.post(self.scan_api, json = {'scanTaskId': '1234',
                                                         'preprocessPath': TEST_DEMO_PROJ_DIR,
                                                         'scanFilePath': TEST_DEMO_PROJ_DIR,
                                                           'configContent': config_content})
        self.assertEqual(500, resp_info.status_code)
        data = resp_info.get_data().decode()
        self.assertIn("authentication token is missing", data)

    def test_scan_task_start_without_preprocess_path(self):
        config_content = json.dumps({'language': 'C'})
        resp_info = self.app.post(self.scan_api, json = {'scanTaskId': '1234',
                                                         TOKEN_FIELD_NAME: TEST_TOKEN,
                                                         'scanFilePath': TEST_DEMO_PROJ_DIR,
                                                           'configContent': config_content})
        self.assertEqual(500, resp_info.status_code)
        data = resp_info.get_data().decode()
        self.assertIn("preprocessPath is missing", data)


    def test_scan_task_start_without_scan_id(self):
        config_content = json.dumps({'language': 'C'})
        resp_info = self.app.post(self.scan_api, json={'scanFilePath': TEST_DEMO_PROJ_DIR,
                                                       TOKEN_FIELD_NAME: TEST_TOKEN,
                                                       'preprocessPath': TEST_DEMO_PROJ_DIR,
                                                       'configContent': config_content})
        self.assertEqual(500, resp_info.status_code)
        data = resp_info.get_data().decode()
        self.assertIn("scanTaskId is missing", data)


    def test_scan_task_start_without_scan_path(self):
        config_content = json.dumps({'language': 'C'})
        resp_info = self.app.post(self.scan_api, json={'scanTaskId': '1234',
                                                       TOKEN_FIELD_NAME: TEST_TOKEN,
                                                       'preprocessPath': TEST_DEMO_PROJ_DIR,
                                                       'configContent': config_content})
        self.assertEqual(500, resp_info.status_code)
        data = resp_info.get_data().decode()
        self.assertIn("scanFilePath is missing", data)

    def test_get_file_cache_api(self):
        resp_info = self.app.post(self.get_cache_api, json={
            "agentName": "random-agent",
            "checksum": "abc",
            "token": TEST_TOKEN,
        })
        self.assertEqual("existing", resp_info.json.get("status"))

    def test_save_file_cache_api(self):
        resp_info = self.app.post(self.save_cache_api, json={
            "agentName": "random-agent",
            "checksum": "a123",
            "fileId": str(uuid.uuid1()),
            "token": TEST_TOKEN,
        })
        self.assertEqual("ok", resp_info.json.get("status"))

    def test_save_and_read_api(self):
        random_file_id = str(uuid.uuid1())
        resp_info = self.app.post(self.save_cache_api, json={
            "agentName": "random-agent",
            "checksum": "m1234",
            "fileId": random_file_id,
            "token": TEST_TOKEN,
        })
        self.assertEqual("ok", resp_info.json.get("status"), msg="The save should return okay")

        resp_info = self.app.post(self.get_cache_api, json={
            "agentName": "random-agent",
            "checksum": "m1234",
            "token": TEST_TOKEN,
        })
        self.assertEqual("existing", resp_info.json.get("status"), msg="The checksum should be present because we've just saved")
        self.assertEqual(random_file_id, resp_info.json.get("fileId"), msg="The saved fileId should be what we have saved just before")

    def test_get_agent_task(self):
        resp_info = self.app.post(self.get_agent_task_api, json={
            "agentName": "random-agent"
        })


if __name__ == '__main__':
    unittest.main()