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
import logging
import time

import unittest

from common.XcalLogger import XcalLogger
from scanTaskService.Config import SCANNER_WORKER_COUNT
from scanTaskService.XcalExpirationWatch import ExpireHookType
from scanTaskService.components.JobInitiator import JobInitiator, JobListener, JobTimeoutManager
from scanTaskService.components.ScanServiceWorker import ExpiredTaskRemover, ScanServiceJobListener
from scanTaskService.scanApp import app

class TestJobInitiater(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger("TestJobInitiater", "main")
        logging.getLogger().setLevel(logging.INFO)

        # ScannerWorker().start_workers(SCANNER_WORKER_COUNT)
        # ExpiredTaskRemover().start()

    def test_create_job_and_expire(self):
        lst = JobListener(self.logger).poll_job_task("testjob", 100)
        print("Previously, we had %d jobs" % len(lst))
        JobInitiator(self.logger).initiate_job_flow("testjob", {"a": "1"}, ExpireHookType.EXPIRE_NOW)

    def test_create_job_agent(self):
        lst = JobListener(self.logger).poll_job_task("testjob", 100)
        print("Previously, we had %d jobs" % len(lst))
        print("Now adding a new Job")
        # Then, initiate the flow
        JobInitiator(self.logger).initiate_job_flow("testjob", {"a": "3"}, ExpireHookType.EXPIRE_CONNECT_AGENT)
        lst = JobListener(self.logger).poll_job_task("testjob", 1)
        self.assertEqual(1, len(lst))
        self.assertEqual("3", lst[0].get("a"))

    def test_create_job_scan_engine(self):
        lst = JobListener(self.logger).poll_job_task("testjob", 100)
        print("Previously, we had %d jobs" % len(lst))
        JobInitiator(self.logger).initiate_job_flow("testjob", {"a": "1"}, ExpireHookType.EXPIRE_IGNORE)
        lst = JobListener(self.logger).poll_job_task("testjob", 1)
        self.assertEqual(1, len(lst))
        self.assertEqual("1", lst[0].get("a"))

class TestJobTimeoutManager(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger("TestJobInitiater", "main")
        logging.getLogger().setLevel(logging.INFO)

        # ScannerWorker().start_workers(SCANNER_WORKER_COUNT)
        # ExpiredTaskRemover().start()

    def test_create_and_expire(self):
        man = JobTimeoutManager(self.logger)
        local_conf = {}
        job_id = man.start_timeout("test", local_conf, timeout_seconds=-1)
        logging.info("Previously, created job = %s, is expired ? = %d" % (job_id, int(man.is_expired(local_conf))))
        logging.info("Changed Config Object = %s" % str(local_conf))
