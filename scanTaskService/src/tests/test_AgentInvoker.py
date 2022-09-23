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

import os
import unittest
import uuid

from common.XcalLogger import XcalLogger
from scanTaskService.components.AgentInvoker import AgentInvoker
from common.ConfigObject import ConfigObject
from tests.TestConfig import TEST_TOKEN, TEST_SCANDATA_DIR
from common.TokenExtractor import TOKEN_FIELD_NAME
from scanTaskService.scanApp import app

TEST_FILE_SERVICE_LOCAL_FILE = TEST_SCANDATA_DIR + "/5678"


class TestAgentInvoker(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.scan_task_id = str(uuid.uuid4())
        self.logger = XcalLogger("Test_FileService", "main")

    def stest_agent_kafka_publish(self):
        co = ConfigObject({
            "scanTaskId": self.scan_task_id,
            "preprocessPath": TEST_SCANDATA_DIR + "/0000",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": ConfigObject({
                "a": "a001"
            })
        })
        AgentInvoker(self.logger).invoke_agent_via_queue([], co)

    def test_http_agent_run_real_proj(self):
        co = ConfigObject({
            "scanTaskId": self.scan_task_id,
            "preprocessPath": TEST_SCANDATA_DIR + "/real_proj",
            # TODO: Auto gen this....
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": ConfigObject({
                "build": "make",
                "workdir": os.path.dirname(os.path.abspath(__file__))
            })
        })
        AgentInvoker(self.logger).invoke_agent_via_queue([], co)

    def test_with_agent_name(self):
        co = ConfigObject({
            "scanTaskId": self.scan_task_id,
            "preprocessPath": TEST_SCANDATA_DIR + "/real_proj",
            # TODO: Auto gen this....
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": ConfigObject({
                "agentName": "abc",
                "build": "make",
                "workdir": os.path.dirname(os.path.abspath(__file__))
            })
        })
        AgentInvoker(self.logger).invoke_agent_via_queue([], co)

    def test_prepare_steps_without_commit_id_should_return_steps_without_diff_step(self):
        task_info = ConfigObject({
            "scanTaskId": self.scan_task_id,
            "preprocessPath": TEST_SCANDATA_DIR + "/real_proj",
            "commitId": "e8bba8b87cdc36d51e0be03e6834282e207dfc92",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "agentName": "abc",
            "build": "make",
            "workdir": "/home/test/basic"
        })
        steps = AgentInvoker(self.logger).prepare_steps(None, task_info)
        for step in steps:
            self.assertNotEqual(step.get("type"), "diff")

    def test_prepare_steps_source_storage_name_and_source_storage_value_should_keep_using_original_value(self):
        source_storage_name = "XX_xx"
        source_storage_type = "GITLAB"
        task_info = ConfigObject({
            "sourceStorageName": source_storage_name,
            "sourceStorageType": source_storage_type,
            "sourceCodeAddress": "https://xxx.com",
            "scanTaskId": self.scan_task_id,
            "preprocessPath": TEST_SCANDATA_DIR + "/real_proj",
            "commitId": "e8bba8b87cdc36d51e0be03e6834282e207dfc92",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "agentName": "abc",
            "build": "make",
            "workdir": "/home/test/basic"
        })
        steps = AgentInvoker(self.logger).prepare_steps(None, task_info)
        for step in steps:
            if step.get("type") == "prepareFileInfo":
                self.assertEqual(step.get("sourceStorageName"), source_storage_name)
                self.assertEqual(step.get("sourceStorageType"), source_storage_type)

    def test_prepare_steps_with_commit_id_and_baseline_commit_id_should_return_steps_with_diff_step(self):
        task_info = ConfigObject({
            "scanTaskId": self.scan_task_id,
            "preprocessPath": TEST_SCANDATA_DIR + "/real_proj",
            "commitId": "e8bba8b87cdc36d51e0be03e6834282e207dfc92",
            "baselineCommitId": "e8bba8b87cdc36d51e0be03e6834282e207dfa80",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "agentName": "abc",
            "build": "make",
            "workdir": "/home/test/basic"
        })
        steps = AgentInvoker(self.logger).prepare_steps(None, task_info)
        diff_relate_step_num = 0
        for step in steps:
            if (step.get("type") == "diff") or (step.get("type") == "upload" and step.get("name") == "diffResult"):
                diff_relate_step_num += 1
        self.assertEqual(2, diff_relate_step_num)


if __name__ == '__main__':
    unittest.main()
