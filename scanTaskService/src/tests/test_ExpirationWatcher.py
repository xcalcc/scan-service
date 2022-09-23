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

from common.CommonGlobals import TaskErrorNo
from common.XcalException import XcalException
from common.XcalLogger import XcalLogger
import scanTaskService.Config
from scanTaskService.Config import app
from tests.TestConfig import TEST_AGENT_USER, TEST_AGENT_ADDR
from scanTaskService.XcalExpirationWatch import ExpirationWatcher, ExpireHookType
from common.ConfigObject import ConfigObject


class TestExpirationWatcher(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger("Test_ExpirationWatcher", "main")
        self.common_co = ConfigObject({
            "scanTaskId": "abcd",
            "configContent": ConfigObject({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_AGENT_ADDR,
            })
        })

    def test_expire_hook_add(self):
        co = ConfigObject({
            "scanTaskId": "abcd",
            "configContent": ConfigObject({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_AGENT_ADDR,
            })
        })
        ExpirationWatcher.expire_list = []
        scanTaskService.Config.AGENT_CONNECT_EXPIRE_DURATION = 0
        scanTaskService.Config.AGENT_PRESCAN_TIMEOUT_DURATION = 0
        ExpirationWatcher(self.logger).add_expiration_hook("abcd", "", co.convert_to_dict(), hook_type=ExpireHookType.EXPIRE_CONNECT_AGENT)
        self.assertGreaterEqual(len(ExpirationWatcher.expire_list), 0)

    def test_expire_hook_remove(self):
        co = ConfigObject({
            "scanTaskId": "abcd",
            "configContent": ConfigObject({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_AGENT_ADDR,
            })
        })
        ExpirationWatcher.expire_list = []
        scanTaskService.Config.AGENT_PRESCAN_TIMEOUT_DURATION = 0
        scanTaskService.Config.AGENT_CONNECT_EXPIRE_DURATION = 0
        ExpirationWatcher(self.logger).add_expiration_hook("abc1", "", co.convert_to_dict(), hook_type=ExpireHookType.EXPIRE_NOW)
        ExpirationWatcher(self.logger).remove_by_id("abc1")
        time.sleep(1)
        self.assertEqual(0, len(ExpirationWatcher.expire_list))
        lst = ExpirationWatcher(self.logger).pop_expired_list()
        self.assertLessEqual(0, len(lst))

    def test_expire_pop_expire_list(self):
        ExpirationWatcher.expire_list = []
        scanTaskService.Config.AGENT_PRESCAN_TIMEOUT_DURATION = 0
        scanTaskService.Config.AGENT_CONNECT_EXPIRE_DURATION = 0
        ExpirationWatcher(self.logger).add_expiration_hook("aegz", "", self.common_co.convert_to_dict(), hook_type=ExpireHookType.EXPIRE_NOW)
        self.assertEqual(1, len(ExpirationWatcher.expire_list))
        time.sleep(1)
        lst = ExpirationWatcher(self.logger).pop_expired_list()
        self.assertEqual(1, len(lst))

    def test_get_ignore_interval(self):
        ExpirationWatcher.expire_list = []
        try:
            ExpirationWatcher(self.logger).get_timeout_interval(self.common_co, exp_type=ExpireHookType.EXPIRE_IGNORE)
        except Exception as err:
            self.assertIsInstance(err, XcalException)
            self.assertEqual(err.err_code, TaskErrorNo.E_UTIL_EXPIRE_IGNORE_DURATION)
        else:
            self.assertFalse(True)
if __name__ == '__main__':
    unittest.main()
