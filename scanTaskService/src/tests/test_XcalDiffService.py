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
from unittest.mock import patch

from common.ConfigObject import ConfigObject
from common.XcalLogger import XcalLogger
from scanTaskService.components.XcalServices import ScanStageObject, XcalDiffService


class TestXcalDiffService(unittest.TestCase):
    def setUp(self):
        self.logger = XcalLogger(TestXcalDiffService.__name__, "main")

    def test_pass(self):
        pass

    @patch('scanTaskService.components.InternalCommunicator.XcalInternalCommunicator.upload_progress')
    def test_do_diff_when_import_result_failed_should_return_None(self, mock_upload_progress):
        config = {
            "scanTaskId": str(uuid.uuid4()),
            "uploadResultSuccessNumber": 0,
            "commitId": "b92ee88b1d43e697aec1dc18ad92a2d8a121afd2",
            "baselineCommitId": "b92ee88b1d43e697aec1dc18ad92a2d8a121afd2"
        }

        mock_upload_progress.return_value = True

        stage = ScanStageObject(stage_type = "diff", start = 5, complete = 100, sync = 1, timeout = 15, info = {})
        diff_service = XcalDiffService(self.logger, ConfigObject(config), stage = stage)
        diff_result_path = diff_service.do_diff()
        self.assertIsNone(diff_result_path)

    @patch('scanTaskService.components.InternalCommunicator.XcalInternalCommunicator.upload_progress')
    def test_do_diff_when_baseline_commit_id_is_not_provide_should_return_None(self, mock_upload_progress):
        config = {
            "scanTaskId": str(uuid.uuid4()),
            "uploadResultSuccessNumber": 1,
            "commitId": "b92ee88b1d43e697aec1dc18ad92a2d8a121afd2"
        }

        mock_upload_progress.return_value = True

        stage = ScanStageObject(stage_type = "diff", start = 5, complete = 100, sync = 1, timeout = 15, info = {})
        diff_service = XcalDiffService(self.logger, ConfigObject(config), stage = stage)
        diff_result_path = diff_service.do_diff()
        self.assertIsNone(diff_result_path)

    @patch('scanTaskService.components.InternalCommunicator.XcalInternalCommunicator.upload_progress')
    def test_do_diff_when_commit_id_is_not_provide_should_return_None(self, mock_upload_progress):
        config = {
            "scanTaskId": str(uuid.uuid4()),
            "uploadResultSuccessNumber": 1,
            "baselineCommitId": "b92ee88b1d43e697aec1dc18ad92a2d8a121afd2"
        }

        mock_upload_progress.return_value = True

        stage = ScanStageObject(stage_type = "diff", start = 5, complete = 100, sync = 1, timeout = 15, info = {})
        diff_service = XcalDiffService(self.logger, ConfigObject(config), stage = stage)
        diff_result_path = diff_service.do_diff()
        self.assertIsNone(diff_result_path)