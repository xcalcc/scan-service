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



import shlex
import unittest

from common.XcalLogger import XcalLogger
from scanTaskService.util.SshUtility import SshUtility
from tests.TestConfig import TEST_AGENT_USER, TEST_AGENT_ADDR
from scanTaskService.scanApp import app


class TestSshUtility(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger("Test_SshUtility", "main")

    @unittest.skip("Deprecated feature")
    def test_ssh_test_ok(self):
        """
        SSH should return 0 when executing correct command
        :param logger:
        :return:
        """
        rc = SshUtility.ssh_execute("echo " + shlex.quote("ok"), TEST_AGENT_USER, TEST_AGENT_ADDR, 10, self.logger)
        self.assertEqual(rc, 0, "ssh should return 0 in echoing")

    @unittest.skip("Deprecated feature")
    def test_ssh_test_fail(self):
        """
        SSH should return non-zero in testing with wrong command
        :param logger:
        :return:
        """
        rc = SshUtility.ssh_execute("which " + shlex.quote("unknown_command_me"), TEST_AGENT_USER, TEST_AGENT_ADDR, 10, self.logger)
        self.assertNotEqual(rc, 0, "ssh should fail in given wrong command")

if __name__ == '__main__':
    unittest.main()
