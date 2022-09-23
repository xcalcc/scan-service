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
import os
import shutil
import time
import unittest

from common.XcalLogger import XcalLogger
from common.ConfigObject import ConfigObject
from tests.TestConfig import TEST_AGENT_USER, TEST_CPP_AGENT_ADDR, TEST_TOKEN, TEST_SCANDATA_DIR
from common.TokenExtractor import TOKEN_FIELD_NAME
from common.XcalException import XcalException
from scanTaskService.scanApp import app
from scanTaskService.components.XcalServices import ScanController, PrescanService, XvsaEngineRunnerService, \
    ScanReporterService, ControllerType, FlattenResultService, ScanStageObject


class TestPrescanService(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.viable_co = ConfigObject({
            "scanTaskId": "7890",
            "preprocessPath": TEST_SCANDATA_DIR + "/7890",
            "scanFilePath": TEST_SCANDATA_DIR + "/7890",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": ConfigObject({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_CPP_AGENT_ADDR,
            })
        })

        self.mismatch_path = ConfigObject({
            "scanTaskId": "8890",
            "preprocessPath": TEST_SCANDATA_DIR + "/7890",
            "scanFilePath": TEST_SCANDATA_DIR + "/7890",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": ConfigObject({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": "non-exist.xc5.io",
            })
        })

        self.logger = XcalLogger("TestPrescanService", "main")

    def test_prescan_service_ok(self):
        """
        Prescan Service Should Return Successfully without throwing exception
        :param logger:
        :return:
        """
        # Should emit no exception -------------------------
        co = ConfigObject(self.viable_co)
        ps = PrescanService(self.logger, co, {"type":"prescan", "startRatio":10, "completeRatio":100})
        ps.execute()

    def test_retrieve_object(self):
        """
        Prescan Service Should Return Successfully without throwing exception
        :param logger:
        :return:
        """
        # Should emit no exception -------------------------
        co = ConfigObject(self.viable_co)
        co.set("prescan", {
            "scanTaskId" : self.viable_co.get("scanTaskId"),
            "preprocessPath": self.viable_co.get("preprocessPath"),
            "scanFilePath": self.viable_co.get("scanFilePath"),
            "jobConfig": {
                "taskConfig": self.viable_co.convert_to_dict()
            }
        })
        co.get("configContent")
        ps = PrescanService(self.logger, co, {"type":"prescan", "startRatio":10, "completeRatio":100})
        ps.execute()


    def test_prescan_service_fail_no_client(self):
        co = ConfigObject(self.viable_co)
        co.get("configContent").set("agentUser", "nonExist")

        # Should emit exception -------------------------
        try:
            ps = PrescanService(self.logger, co, {"type":"prescan", "startRatio":10, "completeRatio":100})
            ps.execute()
        except XcalException as err:
            logging.exception(err)
            self.assertIn("failure in ssh -> agent", str(err), "should emit error when no viable client user is given")


    def test_prescan_service_fail_no_client_hostname(self):
        co = ConfigObject(self.viable_co)
        co.get("configContent").set("agentAddress", "nonExist")

        # Should emit exception -------------------------
        try:
            ps = PrescanService(self.logger, co, {"type":"prescan", "startRatio":10, "completeRatio":100})
            ps.execute()
        except XcalException as err:
            logging.exception(err)
            self.assertIn("failure in ssh -> agent", str(err), "should emit error when no viable client user is given")

class TestScanRunnerService(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger("TestScanRunnerService", "main")
        self.execution = {"type": ControllerType.DEFAULT_ASYNC}

    @unittest.skipIf(not(os.path.exists(TEST_SCANDATA_DIR + "/xvsa_test.sample")),
                     "xvsa_test.sample does not exist")
    def test_scan_runner_service_ok(self):
        """
        ScanRunnerService Should Return Successfully without throwing exception
        :param logger:
        :return:
        """
        # Should emit no exception -------------------------
        co = ConfigObject({
            "scanTaskId": "xvsa_test",
            "scanFilePath": TEST_SCANDATA_DIR + "/xvsa_test",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": ConfigObject({
                "agentUser": "non-exist-user",
                "agentAddress": "non-exist.xc5.io"
            })
        })
        shutil.rmtree(TEST_SCANDATA_DIR + "/xvsa_test", ignore_errors=True)
        shutil.copytree(TEST_SCANDATA_DIR + "/xvsa_test.sample", TEST_SCANDATA_DIR + "/xvsa_test")
        XvsaEngineRunnerService(self.logger, co, {"type":"xvsa", "startRatio":10, "completeRatio":100},
                                execution=self.execution).execute()

    @unittest.skipUnless(os.path.exists(TEST_SCANDATA_DIR + "/xvsa_test.sample"), "Testcase not ready")
    def test_scan_runner_service_fail_no_decompress(self):
        co = ConfigObject({
            "scanTaskId": "xvsa_test",
            "scanFilePath": TEST_SCANDATA_DIR + "/xvsa_test",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": ConfigObject({
                "agentUser": "non-exist-user",
                "agentAddress": "non-exist.xc5.io",
            })
        })
        shutil.rmtree(TEST_SCANDATA_DIR + "/xvsa_test", ignore_errors=True)
        shutil.copytree(TEST_SCANDATA_DIR + "/xvsa_test.sample", TEST_SCANDATA_DIR + "/xvsa_test")
        shutil.rmtree(TEST_SCANDATA_DIR + "/xvsa_test/xvsa_test.preprocess", ignore_errors=True)

        # Should emit exception -------------------------
        try:
            XvsaEngineRunnerService(self.logger, co, {"type":"xvsa", "startRatio":10, "completeRatio":100},
                                    execution=self.execution).execute()
        except XcalException as err:
            logging.exception(err)
            self.assertIn("XvsaScan Exception, find scan.log", str(err), "should emit error when no preprocess dir is present")
        except Exception as err:
            logging.exception(err)
            self.assertFalse(True, "control flow should not reach here")


    def test_scan_runner_service_pass_no_preprocess_tar(self):
        co = ConfigObject({
            "scanTaskId": "xvsa_test",
            "scanFilePath": TEST_SCANDATA_DIR + "/xvsa_test",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": ConfigObject({
                "agentUser": "non-exist-user",
                "agentAddress": "non-exist.xc5.io",
            })
        })
        shutil.rmtree(TEST_SCANDATA_DIR + "/xvsa_test", ignore_errors=True)
        shutil.copytree(TEST_SCANDATA_DIR + "/xvsa_test.sample", TEST_SCANDATA_DIR + "/xvsa_test")
        shutil.rmtree(TEST_SCANDATA_DIR + "/xvsa_test/preprocess.tar.gz", ignore_errors=True)

        # Should emit exception -------------------------
        try:
            XvsaEngineRunnerService(self.logger, co, {"type":"xvsa", "startRatio":10, "completeRatio":100},
                                    execution=self.execution).execute()
        except XcalException as err:
            logging.exception(err)
            self.assertFalse(True, "No exception is acceptable here")

class TestScanReporterService(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger(TestScanReporterService.__name__, "main")

    @unittest.skipIf(not(os.path.exists(TEST_SCANDATA_DIR + "/upload_test.sample")),
                     "skipped becasue upload_test.sample dir does not exist")
    def test_result_uploader_service_ok(self):
        """
        ScanRunnerService Should Return Successfully without throwing exception
        :param logger:
        :return:
        """
        # Should emit no exception -------------------------
        co = {
            "scanTaskId": "upload_test",
            "scanFilePath": TEST_SCANDATA_DIR + "/upload_test",
            "preprocessPath": TEST_SCANDATA_DIR + "/upload_test",
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": ConfigObject({
                "agentUser": "non-exist-user",
                "agentAddress": "non-exist.xc5.io",
            })
        }
        shutil.rmtree(TEST_SCANDATA_DIR + "/upload_test", ignore_errors=True)
        shutil.copytree(TEST_SCANDATA_DIR + "/upload_test.sample", TEST_SCANDATA_DIR + "/upload_test")
        ScanReporterService(self.logger, co, {"type":"uploadResult", "startRatio":10, "completeRatio":100}).execute()

class TestScanController(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger(TestScanReporterService.__name__, "main")

    @unittest.skipUnless(os.path.exists(TEST_SCANDATA_DIR + "/xvsa_test.sample"), "Testcase not ready")
    def test_xvsa_scan_ok(self):

        co = {
            "scanTaskId": "xvsa_test",
            "scanFilePath": TEST_SCANDATA_DIR + "/xvsa_test",
            "preprocessPath": TEST_SCANDATA_DIR + "/xvsa_test",
            "pipeline": [{"type": "prescan", "startRatio": 0, "completeRatio": 100},
                         {"type": "getPrescanObject", "startRatio": 0, "completeRatio": 100},
                         {"type": "xvsa", "startRatio": 0, "completeRatio": 80}],
            "pipelineOffset": 2,
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": json.dumps({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_CPP_AGENT_ADDR,
            })
        }
        shutil.rmtree(TEST_SCANDATA_DIR + "/xvsa_test", ignore_errors=True)
        shutil.copytree(TEST_SCANDATA_DIR + "/xvsa_test.sample", TEST_SCANDATA_DIR + "/xvsa_test")
        # shutil.rmtree(TEST_SCANDATA_DIR + "/xvsa_test/preprocess.tar.gz", ignore_errors=True)

        #  Should not emit error ------------------------
        sc = ScanController(self.logger)
        sc.process_internal_job(co)

    @unittest.skipIf(not(os.path.exists(TEST_SCANDATA_DIR + "/full_scan_test.sample")),
                     "skipped because the required files not exist")
    def test_full_scan_ok(self):
        co = {
            "scanTaskId": "full_scan_test",
            "scanFilePath": TEST_SCANDATA_DIR + "/full_scan_test",
            "preprocessPath": TEST_SCANDATA_DIR + "/full_scan_test",
            "pipeline": [{"type":"prescan", "startRatio": 0, "completeRatio":100},
                         {"type":"getPrescanObject", "startRatio": 0, "completeRatio":100},
                         {"type":"xvsa", "startRatio": 0, "completeRatio":100}],
            "pipelineOffset": 0,
            "configContent": json.dumps({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_CPP_AGENT_ADDR
            }),
            TOKEN_FIELD_NAME: TEST_TOKEN
        }

        shutil.rmtree(TEST_SCANDATA_DIR + "/full_scan_test", ignore_errors=True)
        shutil.copytree(TEST_SCANDATA_DIR + "/full_scan_test.sample", TEST_SCANDATA_DIR + "/full_scan_test")

        #  Should not emit error ------------------------
        sc = ScanController(self.logger)
        sc.process_internal_job(co)

        co["pipelineOffset"] = 1
        co["prescan"] = {"jobConfig": {"uploadResults": [
            {"fileId": "1234-4444-5555", "step": {"name":"preprocessResult"}}
        ]}}
        sc.process_internal_job(co)

        co["pipelineOffset"] = 2
        sc.process_internal_job(co)

    def test_full_scan_fail_no_file_id(self):
        a = {
            "scanTaskId": "full_scan_test",
            "scanFilePath": TEST_SCANDATA_DIR + "/full_scan_test",
            "preprocessPath": TEST_SCANDATA_DIR + "/full_scan_test",
            "configContent": json.dumps({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_CPP_AGENT_ADDR,
            }),
            TOKEN_FIELD_NAME:TEST_TOKEN
        }
        shutil.rmtree(TEST_SCANDATA_DIR + "/full_scan_test", ignore_errors=True)

        #  Should emit no-src exception -----------------
        try:
            sc = ScanController(self.logger)
            sc.process_internal_job(a)
        except AssertionError as err:
            self.assertIn("Assertion", str(err), "should report error in making tarball")



class TestFlattenResultService(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.logger = XcalLogger(TestScanReporterService.__name__, "main")

    def test_two_v_files(self):
        co = {
            "scanTaskId": "multiple_v_test",
            "scanFilePath": TEST_SCANDATA_DIR + "/multiple_v_test",
            "preprocessPath": TEST_SCANDATA_DIR + "/multiple_v_test",
            "pipeline": [{"type": "flattenResult", "startRatio": 0, "completeRatio": 80}],
            "pipelineOffset": 2,
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": json.dumps({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_CPP_AGENT_ADDR,
            })
        }
        shutil.rmtree(TEST_SCANDATA_DIR + "/multiple_v_test", ignore_errors=True)
        shutil.copytree(TEST_SCANDATA_DIR + "/multiple_v_test.sample", TEST_SCANDATA_DIR + "/multiple_v_test")
        # shutil.rmtree(TEST_SCANDATA_DIR + "/xvsa_test/preprocess.tar.gz", ignore_errors=True)

        start = time.time()
        #  Should not emit error ------------------------
        sc = FlattenResultService(self.logger, ConfigObject(co),
                                  ScanStageObject(stage_type="flattenResult",    start=85, complete=100, sync=1, timeout=15,  info={}).as_dict())
        sc.flatten_scan_result()
        end = time.time()

        self.logger.info("EXECUTION SUCCESS", "")
        self.logger.info("Total time: ", str(end - start))

        self.assertTrue(os.path.exists(TEST_SCANDATA_DIR + "/multiple_v_test/multiple_v_test.v"))
        with open(TEST_SCANDATA_DIR + "/multiple_v_test/multiple_v_test.v") as f:
            f.seek(0, 2)
            file_size = f.tell()
            self.assertGreater(file_size, 0)


    @unittest.skip
    def test_two_v_files_indent_1(self):
        """
        By default skipped due to this takes too much time to execute, roughly 60x than above.
        :return:
        """
        TEST_CASE_SAMPLE_DIR = TEST_SCANDATA_DIR + "/multiple_v_test.sample"
        TEST_CASE_DIR = TEST_SCANDATA_DIR + "/multiple_v_test"
        TEST_RESULT_FILE = TEST_CASE_DIR + "/multiple_v_test.v"
        co = {
            "scanTaskId": "multiple_v_test",
            "scanFilePath": TEST_CASE_DIR,
            "preprocessPath": TEST_CASE_DIR,
            "pipeline": [{"type": "flattenResult", "startRatio": 0, "completeRatio": 80}],
            "pipelineOffset": 2,
            TOKEN_FIELD_NAME: TEST_TOKEN,
            "configContent": json.dumps({
                "agentUser": TEST_AGENT_USER,
                "agentAddress": TEST_CPP_AGENT_ADDR,
                "flattenIndent": "1",
            })
        }

        # Remove the test case dir and re-copy from sample dir.
        if (os.path.exists(TEST_CASE_DIR)):
            shutil.rmtree(TEST_CASE_DIR)

        shutil.copytree(TEST_CASE_SAMPLE_DIR, TEST_CASE_DIR)

        start = time.time()
        #  Should not emit error ------------------------
        sc = FlattenResultService(self.logger, ConfigObject(co),
                                  ScanStageObject(stage_type="flattenResult",    start=85, complete=100, sync=1, timeout=15,  info={}).as_dict())
        sc.flatten_scan_result()
        end = time.time()

        self.logger.info("EXECUTION SUCCESS", "")
        self.logger.info("Total time: ", str(end - start))

        self.assertTrue(os.path.exists(TEST_RESULT_FILE))
        with open(TEST_RESULT_FILE) as f:
            f.seek(0, 2)
            file_size = f.tell()
            self.assertGreater(file_size, 0)

if __name__ == '__main__':
    unittest.main()
