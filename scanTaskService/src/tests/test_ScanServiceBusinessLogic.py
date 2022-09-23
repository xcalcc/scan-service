#
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
import shutil
import unittest

from common.XcalLogger import XcalLogger
from common.ConfigObject import ConfigObject
from tests.TestConfig import TEST_AGENT_USER, TEST_CPP_AGENT_ADDR, TEST_TOKEN, TEST_SCANDATA_DIR
from common.TokenExtractor import TOKEN_FIELD_NAME
from scanTaskService.scanApp import app
from scanTaskService.components.XcalServices import ScanServiceBusinessLogic


class TestScanServiceBusinessLogic(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger(TestScanServiceBusinessLogic.__name__, "main")

    def test_whole_start(self):

        co = ConfigObject({
            "scanTaskId": "xvsa_test",
            "scanFilePath": TEST_SCANDATA_DIR + "/xvsa_test",
            "preprocessPath": TEST_SCANDATA_DIR + "/xvsa_test",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": json.dumps({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_CPP_AGENT_ADDR,
            })
        })
        shutil.rmtree(TEST_SCANDATA_DIR + "/xvsa_test", ignore_errors=True)
        shutil.copytree(TEST_SCANDATA_DIR + "/xvsa_test.sample", TEST_SCANDATA_DIR + "/xvsa_test")
        # shutil.rmtree(TEST_SCANDATA_DIR + "/xvsa_test/preprocess.tar.gz", ignore_errors=True)

        #  Should not emit error ------------------------
        sc = ScanServiceBusinessLogic(self.logger)
        sc.initiate_scan_pipeline(co)
