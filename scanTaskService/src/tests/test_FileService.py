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



import tempfile
import unittest
import uuid

import requests

from common.XcalLogger import XcalLogger
from scanTaskService.Config import app
from common.ConfigObject import ConfigObject
from scanTaskService.components.FileService import FileServiceImpl, RemoteFileService
from tests.TestConfig import TEST_AGENT_USER, TEST_AGENT_ADDR, TEST_TOKEN, TEST_SCANDATA_DIR
from common.TokenExtractor import TOKEN_FIELD_NAME
from common.XcalException import XcalException

TEST_FILE_SERVICE_LOCAL_FILE = TEST_SCANDATA_DIR + "/5678"

class TestFileService(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger("Test_FileService", "main")

    @unittest.skip("Deprecated feature")
    def test_send_file_ok(self):
        """
        Scp should return {"status":"ok", ....} when file is successfully sent to remote
        :param logger:
        :return:
        """
        co = ConfigObject({
            "configContent": ConfigObject({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_AGENT_ADDR,
            })
        })
        fc = FileServiceImpl(co, self.logger)
        fresult = fc.send_file(TEST_FILE_SERVICE_LOCAL_FILE, TEST_SCANDATA_DIR + "")
        self.assertEqual(fresult.get("status"), "ok", "file service should pass when file is existing")

    def test_send_file_fail(self):
        """
        Scp should fail when file to be sent is non existing
        :return:
        """
        co = ConfigObject({
            "configContent": ConfigObject({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_AGENT_ADDR,
            })
        })
        fs = FileServiceImpl(co, self.logger)
        try:
            fresult = fs.send_file("/non-existing-file", TEST_SCANDATA_DIR + "")
        except XcalException as err:
            self.assertIn("due to scp fail 1", str(err), "file service should fail when file is non existing")
        else:
            self.assertFalse(True, "control flow should not reach here")

    @unittest.skip("Deprecated feature")
    def test_fetch_file_ok(self):
        co = ConfigObject({
            "configContent": ConfigObject({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_AGENT_ADDR,
            })
        })
        fs = FileServiceImpl(co, self.logger)
        fresult = fs.fetch_file(TEST_SCANDATA_DIR + "/5678", TEST_SCANDATA_DIR + "/")
        self.assertEqual(fresult.get("status"), "ok", "file service should pass when file is existing")

    def test_fetch_file_fail(self):
        co = ConfigObject({
            "configContent": ConfigObject({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_AGENT_ADDR,
            })
        })
        fs = FileServiceImpl(co, self.logger)
        try:
            fresult = fs.fetch_file(TEST_SCANDATA_DIR + "/non-existing--file", TEST_SCANDATA_DIR + "/")
        except XcalException as err:
            self.assertIn("due to scp fail 1", str(err), "file service should fail when file is non existing")
        else:
            self.assertFalse(True, "control flow should not reach here")

class TestRemoteFileService(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger("Test_FileService", "main")

    def test_remote_download_id_error(self):
        co = ConfigObject({
            TOKEN_FIELD_NAME: TEST_TOKEN
        })
        try:
            with tempfile.NamedTemporaryFile("w+b") as f:
                RemoteFileService(co, self.logger).fetch_file_with_token(str(uuid.uuid1()), f.name, co)
        except requests.exceptions.HTTPError as err:
            pass
        except Exception:
            self.assertFalse(True, "Remote download should fail due to id error")


if __name__ == '__main__':
    unittest.main()
