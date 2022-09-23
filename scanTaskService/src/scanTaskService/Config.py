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

import logging
import os
import time
from enum import Enum

from flask import Flask
from prometheus_client import CollectorRegistry, Gauge, Counter

from common import CommonGlobals
from common.XcalLogger import XcalLogger
from common.CommonGlobals import TaskErrorNo


ROOT_DIR = os.path.dirname(os.path.abspath(__file__)) # This is your Project Root
DEFAULT_LOG_LEVEL = 25
DESTINATION_DIR_SUFFIX = ".preprocess"      # extract preprocess.tar.gz to xxx.preprocess directory -----
PREPROCESS_FILE_SUFFIX = [".i", ".ii"]      # TODO: Verify to be replaced by file info collection(bear) --
SCAN_RESULT_COMPARATER = os.path.join(os.path.dirname(__file__), 'bin/vtxt_diff')
SCAN_RESULT_CONVERTER = os.path.join(os.path.dirname(__file__), 'bin/v2csf')
INITIAL_TIMESTAMP = int(time.mktime(time.strptime('2021-02-12 00:00:00', '%Y-%m-%d %H:%M:%S')))
SCAN_RESULT_DIFF_FILE_NAME = "scan_result.vdiff"    # scan result diff file
SCAN_SERVICE_DIAGNOSTIC_INFO_FILE_NAME = "scan_service_diagnostic_info.tar.gz"
KAFKA_HOST = os.getenv("KAFKA_SERVER_HOST", "kafka")
AGENT_TOPIC_PREFIX = "agent-tasks-"
AGENT_NAME_DEFAULT = "default-agent"
JOB_QUEUE_NAME = "public_default"           # starts with public_ is a public job queue name
TOPIC_PREFIX = "job-"
KAFKA_DEFAULT_GROUP_ID = "scan-group"
SCAN_RUNNER_JOB_TOPIC = "scan-engine-runner"
SCAN_ENGINE_TOPIC = "scan-engine-tasks"     # only for xvsa only
JAVA_SCAN_OBJECT_FILE_DIR = "extra-object"  # rt.tgz will be extracted to here, and added to the xvsa options
SCANNER_WORKER_TIMEOUT_LIST = "scanner-worker-execute"
JAVA_SCAN_RUNTIME_LOCAL_TEMP_FILE_NAME = "extra.tar.gz"
JAVA_RUNTIME_OBJECT_FILE_NAME = "rt.tgz"
REMOTE_RESULT_V_FILE_TEMP_NAME = "remote.v"
SPOTBUGS_RESULT_V_FILE_TEMP_NAME = "connector.v"
RUNTIME_STORAGE_FILE_CACHE_SETTING_NAME = "runtimeObjectCache"
UPLOAD_VOLUME_PATH = "/share/upload/"
FILE_SERVICE_URL = os.getenv("FILE_SERVICE_URL", "http://127.0.0.1:9000")
PREPROCESS_DATA_BUCKET_NAME = os.getenv("PREPROCESS_DATA_BUCKET_NAME", "preprocess-data")
SCAN_SERVICE_LOG_PATH=os.getenv("SCAN_SERVICE_LOG_PATH", os.path.join(os.curdir, "xcalscan.run.log"))
LOGSTASH_HOST = os.getenv('LOGSTASH_HOST', 'logstash')
LOGSTASH_PORT = os.getenv('LOGSTASH_PORT', 5000)
AGENT_CONNECT_EXPIRE_DURATION = 86400  # seconds, Report err if no agent fetches from Job Queue in this period
AGENT_TIMEOUT = 600                    # remove the agent info when it is not modified than AGENT_TIMEOUT seconds
SCAN_CONTROLLER_STAGE_INTERVAL = 60    # seconds, Report err if the next stage starts later
                                       # than this duration after the current stage
SCANNER_WORKER_COUNT = 1
KAFKA_POLL_TIMEOUT_MS = 10000
# KAFKA_CONSUMER_EXPIRE_PERIOD = 86400 * 365    # In seconds, a year
AGENT_MAX_ENTRIES_PER_POLL = 1       # Per poll
TIMEOUT_DEFAULT_STAGE_SECONDS = 1800 # The default time limit per stage in the pipeline
NAME_LEN_MAX = 64
KAFKA_PUBLISH_TIMEOUT = 1.0
COMPLETE_RATIO_FULL = 100       # Complete Ratio that should be marked as complete
SKIP_API_CALL_ERRORS = True     # Skip all Api call errors.
CLEAR_ALL_FILE_CACHE = False    # Clear all existing runtime object file caches
VERSION_INFO_STR = "0.0.16"      # Version string
SCAN_SERVICE_API_VER = "v2"     # In version/info
FLATTEN_V_FILE_BUFFERING = 10 * 1024 * 1024   # V file Dump Write Buffering,
                                              # perform disk write each time this many bytes are generated
MAXIMUM_SINGLE_V_FILE_SIZE = 499 * 1024 * 1024
UPLOAD_FILE_MAX_SIZE = int(os.getenv("MAX_FILE_SIZE", 1024 * 1024 * 1024))
ENABLE_SPOTBUGS = False

# http client config
HTTP_CLIENT_RETRY_TOTAL = int(os.getenv('HTTP_CLIENT_RETRY_TOTAL', 3))
HTTP_CLIENT_RETRY_BACKOFF_FACTOR = int(os.getenv('HTTP_CLIENT_RETRY_BACKOFF_FACTOR', 10))
HTTP_CLIENT_RETRY_BACKOFF_MAX = int(os.getenv('HTTP_CLIENT_RETRY_BACKOFF_MAX', 10))
HTTP_CLIENT_RETRY_STATUS_LIST = [int(status_code_string) for status_code_string in os.getenv('HTTP_CLIENT_RETRY_STATUS_LIST', "400,401,402,403,500,502,504").split(",")]
# set connect timeout to slightly larger than a multiple of 3, which is the default TCP packet retransmission window.
HTTP_CONNECT_TIMEOUT = int(os.getenv('HTTP_CONNECT_TIMEOUT', 3.05))
# temporarily set read timeout to 7200 seconds since currently insert fileinfo.json to db may consume much time.
# will set this to a reasonable value when server side improve the file service process.
HTTP_READ_TIMEOUT = int(os.getenv('HTTP_READ_TIMEOUT', 7200))

# scan docker setting
SCAN_DOCKER_MEM_LIMIT = "16g"

FILE_SERVICE_CONFIG = {
    "schema": "%s://" % os.getenv("API_SCHEMA", "http"),
    "serverAddress": os.getenv("API_SERVER_HOSTNAME", "api"),
    "downloadApi": "/api/file_service/v2/file_info/{id}/file",
    "downloadFieldName": "{id}",
    "extraParam": "?token={token}"
}

# Initializing the app context (Flask)-----------
app = Flask(__name__)

# Prometheus ------------------------------------
registry = CollectorRegistry()
scanTaskServiceCounter = Counter('xcal_scan_service_count', 'scanTaskService', ['method', 'endpoint'], registry=registry)
scanTaskServiceDuration = Gauge('xcal_scan_service_duration', 'scanTaskService', registry=registry)
scanFileSize = Gauge('xcal_scan_file_size', 'scanTaskService', registry=registry)
scanFileLines = Gauge('xcal_scan_file_lines', 'scanTaskService', registry=registry)
scanFileCount = Gauge('xcal_scan_file_count', 'scanTaskService', registry=registry)
scanSourceFileSize = Gauge('xcal_scan_source_file_size', 'scanTaskService', registry=registry)
scanSourceFileLines = Gauge('xcal_scan_source_file_lines', 'scanTaskService', registry=registry)
scanSourceFileCount = Gauge('xcal_scan_source_file_count', 'scanTaskService', registry=registry)
push_gateway_url = os.getenv("PUSH_GATEWAY_URL", "")

# Global Expired Tasks List


class ScanTaskServiceAPIData(object):
    def __init__(self):
        self.hostname = os.getenv("API_SERVER_HOSTNAME", "api")
        self.xvsa_hostname = os.getenv("XVSA_SERVER_HOSTNAME", "api@80")
        self.web_api_version = os.getenv("WEB_API_VERSION", "v2")
        self.issue_api_version = os.getenv("ISSUE_API_VERSION", "v2")
        self.current_user_api_version = os.getenv("CURRENT_USER_API_VERSION", "v2")
        self.update_api_version = os.getenv("UPDATE_API_VERSION", "v2")
        self.schema = os.getenv("API_SCHEMA", "http")

        self.issues_url = "%s://%s/api/issue_service/%s/scan_task/{id}/issues" % (self.schema, self.hostname, self.issue_api_version)
        self.fileinfo_url = "%s://%s/api/file_service/%s/scan_task/{id}/file_info" % (self.schema, self.hostname, self.web_api_version)
        self.upload_file = "%s://%s/api/file_service/%s/file/file_info" % (self.schema, self.hostname, self.web_api_version)
        self.issue_diff_url = "%s://%s/api/issue_service/%s/scan_task/{id}/{baseline_id}/issue_diff" % (self.schema, self.hostname, self.web_api_version)
        self.current_user_url = "%s://%s/api/user_service/%s/current" % (self.schema, self.hostname, self.current_user_api_version)
        self.search_scan_task_url = "%s://%s/api/scan_service/%s/scan_task/search" % (self.schema, self.hostname, self.web_api_version)
        self.get_scan_task_summary_url = "%s://%s/api/scan_service/%s/scan_task/{id}/scan_summary" % (self.schema, self.hostname, self.web_api_version)
        self.update_url = "%s://%s/api/scan_service/%s/scan_task/{id}" % (self.schema, self.hostname, self.update_api_version)
        self.file_cache_list_url = "%s://%s/api/file_service/%s/file_cache_list" % (self.schema, self.hostname, self.web_api_version)
        self.file_cache_manage_url = "%s://%s/api/file_service/%s/file_cache" % (self.schema, self.hostname, self.web_api_version)
        self.file_cache_file_info_url = "%s://%s/api/file_service/%s/file_info" % (self.schema, self.hostname, self.web_api_version)
        self.gateway_version_api = "%s://%s/api/gateway/version/info" % (self.schema, self.hostname)
        self.web_service_version_api = "%s://%s/api/actuator/info" % (self.schema, self.hostname)
        self.scan_service_version_api = "%s://%s/api/scan_task_service/version/info" % (self.schema, self.hostname)
        self.diagnostic_log_upload_url = "%s://%s/api/scan_service/%s/scan_task/{id}/diagnostic_info" % (self.schema, self.hostname, self.web_api_version)
        self.async_issues_url = "%s://%s/api/issue_service/%s/scan_task/{id}/issues_async" % (self.schema, self.hostname, self.issue_api_version)
        self.async_issue_diff_url = "%s://%s/api/issue_service/%s/scan_task/{id}/{baseline_id}/issue_diff_async" % (self.schema, self.hostname, self.web_api_version)
        self.async_update_url = "%s://%s/api/scan_service/%s/scan_task/{id}/async" % (self.schema, self.hostname, self.update_api_version)


APIData = ScanTaskServiceAPIData()

CommonGlobals.jaeger_service_name = os.getenv("JAEGER_SERVICE_NAME", "scan-service")
CommonGlobals.jaeger_agent_host = os.getenv("JAEGER_AGENT_HOST", 'jaeger-agent')
CommonGlobals.jaeger_agent_port = os.getenv("JAEGER_AGENT_PORT", 6831)
if CommonGlobals.jaeger_agent_host is None or CommonGlobals.jaeger_agent_port is None:
    CommonGlobals.use_jaeger = False


class ScanStep(Enum):
    PRESCAN = 1,
    SCAN_ENGINE = 2
