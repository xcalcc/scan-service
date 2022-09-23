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

from common.XcalException import XcalException
from common.XcalLogger import XcalLogger
from scanTaskService.Config import app
from scanTaskService.util.DockerUtility import DockerUtility


class TestDockerUtility(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger("Test_DockerUtility", "main")

    def test_start_scan_container_with_incorrect_image_should_throw_exception(self):
        container_name = "test_container"
        image_name = "xxxxx123:latest"
        scan_command = "ls"
        docker_utility = DockerUtility(self.logger, container_name, image_name, scan_command)
        task_config = None
        try:
            docker_utility.start_scan_container(task_config)
        except XcalException:
            pass







