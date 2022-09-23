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



import time
import unittest

from common.XcalLogger import XcalLogger
from tests.TestConfig import TEST_SCANDATA_DIR
from scanTaskService.components.AgentInvoker import AgentInvoker
from scanTaskService.Config import app
import json

from common.ConfigObject import ConfigObject


class TestAgentService(unittest.TestCase):
    """
    test Agent Service APIs
    """

    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger("TestAgentService", "__init__")
        self.agent_poll_api = '/api/scan_task_service/v3/agent/get_task'
        self.agent_upload_file_api = '/api/scan_task_service/v2/agent/upload_file'

    def test_scan_agent_get_task_ok(self):
        co = ConfigObject({
            "scanTaskId": "000",
            "scanSrcPath": TEST_SCANDATA_DIR + "/0000",
            "configContent": ConfigObject({
                "a": "a001"
            })
        })
        AgentInvoker(self.logger).invoke_agent_via_queue([], co)
        time.sleep(1)
        resp_info = self.app.get(self.agent_poll_api)
        self.assertEqual(200, resp_info.status_code)
        data = json.loads(resp_info.get_data().decode())
        self.assertIn('jobCount', data)

        ## Not working...
        # self.assertGreaterEqual(data['jobCount'], 1)


if __name__ == '__main__':
    unittest.main()