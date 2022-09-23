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



# Run app
import json
import logging
import os

import requests

TEST_PORT = 6600


class ScanTaskServiceAPIData(object):
    def __init__(self):
        self.hostname = os.getenv("API_SERVER_HOSTNAME", "api")
        self.issue_api_version = os.getenv("ISSUE_API_VERSION", "v3")
        self.update_api_version = os.getenv("UPDATE_API_VERSION", "v2")
        self.issues_url = {"URL": ["http://%s/api/%s/issue_service/scan_task" % (self.hostname, self.issue_api_version), "issues"]}
        self.update_url = {"URL": "http://%s/api/%s/scan_service/scan_task" % (self.hostname, self.update_api_version)}


APIData = ScanTaskServiceAPIData()

#      ------------------------------------------
#        Test Specific Config
#      ------------------------------------------
TEST_AGENT_USER = os.getenv("TEST_AGENT_USER", "xc5")
TEST_AGENT_ADDR = os.getenv("TEST_AGENT_ADDR", "127.0.0.1")
TEST_CPP_AGENT_ADDR = os.getenv("TEST_CPP_AGENT_ADDR", "127.0.0.1")
TEST_API_GATEWAY=os.getenv("API_SERVER_HOSTNAME", "127.0.0.1")
TEST_API_GATEWAY_PREFIX="http://%s" % TEST_API_GATEWAY
TEST_SCANDATA_DIR=os.getenv("TEST_SCANDATA_DIR", "/private/share/scan")


class TestingUtility(object):
    """
    Testing Utility
    """

    @staticmethod
    def get_token():
        url = TEST_API_GATEWAY_PREFIX + "/api/auth_service/v2/login?locale=en"
        # use real username/password
        res = requests.post(url, json={"username":"xx","password":"xx"})
        login_result = res.json()
        if res is not None and res.status_code == 200:
            logging.warning("login result : %s", json.dumps(login_result))
            return login_result.get("accessToken")
        else:
            logging.error("login fail : %s", json.dumps(login_result))
        return "TOKEN LOADING FAILED"


TEST_TOKEN = os.getenv("TEST_TOKEN", TestingUtility.get_token())
