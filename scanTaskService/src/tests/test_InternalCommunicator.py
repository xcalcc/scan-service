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
from unittest import mock

from common.CommonGlobals import Stage, Status, Percentage, TaskErrorNo
from common.XcalLogger import XcalLogger
from scanTaskService.components.InternalCommunicator import XcalInternalCommunicator


class ResponseClass(object):
    def __init__(self, status_code):
        self.status_code = status_code


class InternlCommunicatorTests(unittest.TestCase):

    def setUp(self):
        self.logger = XcalLogger("InternlCommunicatorTests", "setUp")
        self.task_config = dict()
        self.communicator = XcalInternalCommunicator(self.logger, self.task_config)

    def test_upload_progress_without_message_argument(self):
        scan_task_id = "12345"
        stage = Stage.SCANNING
        status = Status.PROCESSING
        percentage = Percentage.START
        error_code = TaskErrorNo.E_NO_SCAN_RESULT

        response = ResponseClass(200)
        send_http_request = mock.Mock(return_value=response)
        self.communicator._send_http_request = send_http_request

        result = self.communicator.upload_progress(scan_task_id, stage, status, percentage, error_code = error_code)
        self.assertEqual(None, result)

    def test_upload_progress_with_empty_message_as_keyword_argument(self):
        scan_task_id = "12345"
        stage = Stage.SCANNING
        status = Status.PROCESSING
        percentage = Percentage.START
        error_code = TaskErrorNo.E_NO_SCAN_RESULT
        message = None

        response = ResponseClass(200)
        send_http_request = mock.Mock(return_value=response)
        self.communicator._send_http_request = send_http_request

        result = self.communicator.upload_progress(scan_task_id, stage, status, percentage, message = message, error_code = error_code)
        self.assertEqual(None, result)


if __name__ == '__main__':
    unittest.main()