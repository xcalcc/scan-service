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
import tarfile
import requests

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util import Retry
from requests import Session

from common.CommonGlobals import Stage, Status, Percentage, ERROR_CODE_VISIBLE, FILE_INFO_FILE_NAME
from common.HashUtility import HashUtility

from common.XcalLogger import XcalLogger, XcalLoggerExternalLinker
from common.TokenExtractor import TokenExtractor
from scanTaskService.Config import APIData, TaskErrorNo, SKIP_API_CALL_ERRORS, UPLOAD_FILE_MAX_SIZE, SCAN_SERVICE_DIAGNOSTIC_INFO_FILE_NAME, HTTP_CLIENT_RETRY_TOTAL, HTTP_CLIENT_RETRY_BACKOFF_FACTOR, HTTP_CLIENT_RETRY_BACKOFF_MAX, HTTP_CLIENT_RETRY_STATUS_LIST, HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT
from common.XcalException import XcalException


class XcalInternalCommunicator(object):
    def __init__(self, logger: XcalLogger, task_config):
        self.logger = logger
        self.task_config = task_config
        self.token_string = TokenExtractor(task_config).get_token_str()

    def get_current_user_info(self):
        local_log = None
        try:
            with XcalLogger("XcalInternalCommunicator", "get_current_user_info", parent = self.logger) as local_log:
                authen_header = {"Content-Type": "application/json", "Authorization": self.token_string}
                response = self._send_http_request(local_log, APIData.current_user_url, {},
                                                  authen_header, method = "GET")

                response.raise_for_status()
                return response
        except requests.exceptions.RequestException as e:
            logging.exception(e)
            if local_log is not None:
                local_log.error("XcalInternalCommunicator", "get_current_user_info",
                                ("failed, but continuing : %s" % str(e)))
            raise XcalException("XcalInternalCommunicator", "get_current_user_info", e, TaskErrorNo.E_GET_CURRENT_USER_INFO_FAILED)

    def search_scan_task(self):
        local_log = None
        try:
            with XcalLogger("XcalInternalCommunicator", "search_scan_task", parent = self.logger) as local_log:
                authen_header = {"Content-Type": "application/json", "Authorization": self.token_string}

                data = {
                    "projectId": self.task_config.get("projectUUID"),
                    "status": ["COMPLETED"],
                    "equalAttributes": [{
                        "type": "SCAN",
                        "name": "commitId",
                        "value": self.task_config.get("baselineCommitId")
                    }]
                }
                api_with_params = "%s?%s" % (APIData.search_scan_task_url, "page=0&size=1&sort=modifiedOn,DESC")
                response = self._send_http_request(local_log, api_with_params, json.dumps(data),
                                                  authen_header, method = "POST")

                response.raise_for_status()
                return response
        except requests.exceptions.RequestException as e:
            logging.exception(e)
            if local_log is not None:
                local_log.error("XcalInternalCommunicator", "search_scan_task", "failed, but continuing : %s" % str(e))
            return None

    def get_scan_summary(self, scan_task_id):
        local_log = None
        try:
            with XcalLogger("XcalInternalCommunicator", "get_scan_summary", parent = self.logger) as local_log:
                authen_header = {"Content-Type": "application/json", "Authorization": self.token_string}

                api_url = APIData.get_scan_task_summary_url.replace("{id}", scan_task_id)
                response = self._send_http_request(local_log, api_url, {}, authen_header, method = "GET")

                response.raise_for_status()
                return response
        except requests.exceptions.RequestException as e:
            logging.exception(e)
            if local_log is not None:
                local_log.error("XcalInternalCommunicator", "get_scan_summary", "failed, but continuing : %s" % str(e))
            return None

    def upload_diff_result(self, baseline_scan_task_id, scan_task_id, fix_issues_file_path, new_issues_file_path):
        local_log = None
        try:
            with XcalLogger("XcalInternalCommunicator", "upload_diff_result", parent = self.logger) as local_log:
                api_url = APIData.async_issue_diff_url.replace("{id}", scan_task_id).replace("{baseline_id}", baseline_scan_task_id)

                post_data = {'id': scan_task_id, 'baselineId': baseline_scan_task_id}
                post_headers = {"Authorization": self.token_string}
                post_files = {}

                fix_issues_file = None
                new_issues_file = None

                try:
                    if (os.path.exists(fix_issues_file_path)):
                        fix_issues_file = open(fix_issues_file_path, "rb")
                        post_files["fixed_issue_file"] = fix_issues_file
                    if (os.path.exists(new_issues_file_path)):
                        new_issues_file = open(new_issues_file_path, "rb")
                        post_files["new_issue_file"] = new_issues_file

                    response = self._send_http_request(local_log, api_url, data=post_data, header=post_headers, files=post_files, method="POST")
                    local_log.info("upload diff result response info", response.content)

                    response.raise_for_status()
                    return response
                finally:
                    if fix_issues_file:
                        fix_issues_file.close()
                    if new_issues_file:
                        new_issues_file.close()
        except requests.exceptions.RequestException as e:
            logging.exception(e)
            if local_log is not None:
                local_log.error("XcalInternalCommunicator", "upload_diff_result", "failed, but continuing : %s" % str(e))
            return None

    def save_to_json_file(self, file_path, content):
        try:
            with open(file_path, 'w') as outfile:
                json.dump(content, outfile, indent = 1)
        except Exception as e:
            logging.exception(e)
            self.logger.error("XcalInternalCommunicator", "upload_scan_result",
                              ("save import result response to file failed, but continuing : %s" % str(e)))

    def get_upload_scan_result_params(self, scan_task_id: str, scan_path: str, scan_result: str = None, file_info_id: str = None):
        params=[]
        params.append(["POST"])
        
        server_api_url = APIData.issues_url.replace("{id}", scan_task_id)
        params.append(["server_api_url",server_api_url])

        scan_result = '%s/scan_result/xvsa-xfa-dummy.csf' % scan_path
        params.append(["scan_result",scan_result])
        
        params.append(["Authorization",self.token_string])

        return params

    def upload_scan_result(self, scan_task_id: str, scan_path: str, scan_result: str = None):
        """
        Upload issues/file info to Web-Main-Api
        scan result can be v file or v file archive
        :param scan_result: File name of the scan result to be uploaded
        :param scan_task_id:
        :param scan_path:
        :return: upload scan result success return 1, failed return 0
        """
        try:
            with XcalLogger("XcalInternalCommunicator", "upload_scan_result", parent=self.logger) as local_log:

                # Prepare Data to Upload -----------------------
                if scan_result is None:
                    scan_result = '%s/scan_result/xvsa-xfa-dummy.csf' % scan_path

                if not os.path.exists(scan_result):
                    raise XcalException("XcalInternalCommunicator", "upload_scan_result",
                                        ("scan result file does not exist, scan result: %s" % scan_result),
                                        TaskErrorNo.E_SRV_UPLOAD_NO_V_FILE)

                size = os.path.getsize(scan_result)
                if size > UPLOAD_FILE_MAX_SIZE:
                    local_log.error("XcalInternalCommunicator", "upload_scan_result",
                                    "scan result % is too large" % scan_result)
                    self.upload_progress(scan_task_id, Stage.IMPORT_RESULT, Status.PROCESSING,
                                         Percentage.MIDDLE, "scan result % is too large" % scan_result)
                    raise XcalException("XcalInternalCommunicator", "upload_scan_result",
                                        ("scan result is too large: %s, size = %d " % (scan_result, size)),
                                        TaskErrorNo.E_SRV_UPLOAD_V_FILE_OVERSIZE)

                with open(scan_result, 'rb') as binaryfile:
                    files = {'upload_file': binaryfile}
                    post_headers = {"Authorization": self.token_string}
                    server_api_url = APIData.issues_url.replace("{id}", scan_task_id)
                    response = self._send_http_request(local_log, server_api_url,
                                           data={'id': scan_task_id},
                                           header=post_headers,
                                           files=files, method="POST")
                    local_log.info("upload scan result response info", response.content)

                    if response.status_code >= 300:
                        logging.error(response.content)
                        local_log.error("XcalInternalCommunicator", "upload_scan_result",
                                        "upload scan result %s failed = %s" % (scan_result, str(response.status_code)))
                        self.upload_progress(scan_task_id, Stage.IMPORT_RESULT, Status.PROCESSING,
                                             Percentage.MIDDLE, "import scan result %s failed, response info: %s" % (scan_result, response.content))

                        raise XcalException("XcalInternalCommunicator", "upload_scan_result",
                                        "unexpected http status code %s" % response.status_code,
                                        -1)
                    else:
                        local_log.trace("upload scan result %s success " + scan_result, "")
                        # save import result response content to file which will be used for diff later
                        # view_result_file = "%s/%s.view" % (scan_path, scan_task_id)
                        # self.save_to_json_file(view_result_file, response.json())
                        return 1
        except Exception as e:
            if self.logger is not None:
                self.logger.error("XcalInternalCommunicator", "upload_scan_result", ("failed, but continuing : %s" % str(e)))
            raise e

    def upload_file_info_to_webapi(self, scan_task_id, scan_path, file_info_path):
        try:
            with XcalLogger("XcalInternalCommunicator", "upload_file_info_to_webapi", parent=self.logger) as local_log:

                # Prepare Data to Upload -----------------------
                if file_info_path is None:
                    file_info_path = os.path.join(scan_path, FILE_INFO_FILE_NAME)
                    local_log.info("concat the file_info file name", (" file_info file : ", file_info_path))

                if not os.path.exists(file_info_path):
                    raise XcalException("XcalInternalCommunicator", "upload_file_info_to_webapi",
                                        ("file_info file does not exist, file_info_path : %s" % file_info_path),
                                        TaskErrorNo.E_SRV_UPLOAD_FILEINFO_NEXIST)

                size = os.path.getsize(file_info_path)
                if size > UPLOAD_FILE_MAX_SIZE:
                    local_log.error("XcalInternalCommunicator", "upload_file_info_to_webapi",
                                    "file info % is too large" % file_info_path)
                    self.upload_progress(scan_task_id, Stage.IMPORT_FILE_INFO, Status.FAILED,
                                         Percentage.END,
                                         "file info % is too large" % file_info_path,
                                         TaskErrorNo.E_SRV_UPLOAD_FILEINFO_OVERSIZE)
                    raise XcalException("XcalInternalCommunicator", "upload_file_info_to_webapi",
                                        ("file info %s is too large, size = %d" % (file_info_path, size)),
                                        TaskErrorNo.E_SRV_UPLOAD_FILEINFO_OVERSIZE)

                with open(file_info_path, 'rb') as binaryfile:
                    files = {'upload_file': binaryfile}
                    post_headers = {"Authorization": self.token_string}
                    response = self._send_http_request(local_log,
                                           APIData.fileinfo_url.replace("{id}", scan_task_id),
                                           data={'id': scan_task_id},
                                           header=post_headers,
                                           files=files, method="POST")
                    # FIXME: Use raise XcalException here
                    if response.status_code >= 300:
                        logging.error(response.content)
                        self.logger.error("XcalInternalCommunicator", "upload_file_info_to_webapi", "http request failed = %s" % (str(response.status_code)))
                        self.upload_progress(scan_task_id, Stage.IMPORT_FILE_INFO, Status.FAILED,
                                             Percentage.END, "import file info failed, response content: %s" % response.content,
                                             TaskErrorNo.E_SRV_UPLOAD_FILEINFO_FAILED)

        except Exception as e:
            logging.exception(e)
            if self.logger is not None:
                self.logger.error("XcalInternalCommunicator", "upload_file_info_to_webapi", ("failed, but continuing : %s" % str(e)))
            if not SKIP_API_CALL_ERRORS:
                raise e
        pass

    def upload_progress(self, scan_task_id, stage: Stage, status: Status, percentage: Percentage, message: str = "progress detail",
                        error_code: TaskErrorNo = None, async_api: bool = None):
        """

        :param scan_task_id:
        :param stage:
        :param status:
        :param percentage:
        :param message:
        :param error_code: TaskErrorNo enum or int
        :param async_api: whether use async api
        :return:
        """
        local_log = None
        try:
            with XcalLogger("XcalInternalCommunicator", "upload_progress", parent=self.logger) as local_log:
                local_log.trace("upload_progress",
                                "scan_task_id: %s, stage: %s, status: %s, percentage: %s, error_code: %s, message: %s" %
                                (scan_task_id, str(stage), str(status), str(percentage), str(error_code), message))

                data = {"id": scan_task_id, "stage": stage.name, "status": status.name, "percentage": percentage.value}

                if message is None:
                    message = "progress detail"

                if error_code is not None:
                    try:
                        error_code = TaskErrorNo(error_code)
                    except ValueError as e:
                        logging.exception(e)
                        local_log.error("XcalInternalCommunicator", "upload_progress", "unknown error code: %s" % error_code)
                        message = "[${%s}]" % (TaskErrorNo.E_SRV_SCAN_UNKNOWN_ERROR.name.replace("_", ".").lower()) + message
                        data["unifyErrorCode"] = hex(TaskErrorNo.E_SRV_SCAN_UNKNOWN_ERROR.value)
                    else:
                        if error_code.value & ERROR_CODE_VISIBLE:
                            message = "[${%s}]" % (error_code.name.replace("_", ".").lower()) + message
                        else:
                            message = "[${%s}]" % (TaskErrorNo.E_SRV_SCAN_UNKNOWN_ERROR.name.replace("_", ".").lower()) + message
                            local_log.error("XcalInternalCommunicator", "upload_progress", "invisible error code: %s" % hex(error_code.value))
                        data["unifyErrorCode"] = hex(error_code.value)

                data["message"] = message

                header = {"Content-Type": "application/json", "Authorization": self.token_string}
                if async_api:
                    server_uri = APIData.async_update_url.replace("{id}", scan_task_id)
                else:
                    server_uri = APIData.update_url.replace("{id}", scan_task_id)
                response = self._send_http_request(local_log, server_uri, data,
                                                  header, method="PUT")
                # FIXME: Use raise XcalException here, use correct logging API here.
                if response.status_code >= 300:
                    local_log.error("XcalInternalCommunicator", "update progress failed %s" % (str(response.status_code)), response.content)

        except Exception as e:
            if local_log is not None:
                local_log.error("XcalInternalCommunicator", "update_progress", ("failed, but continuing : %s" % str(e)))
            # TODO: Raise exception again here.
            if not SKIP_API_CALL_ERRORS:
                raise e

    def list_file_cache(self):
        with XcalLogger('XcalInternalCommunicator', 'list_file_cache', parent=self.logger) as local_log:
            header = {'Content-type': 'application/json', 'Authorization': self.token_string}
            response = self._send_http_request(local_log, APIData.file_cache_list_url, {}, header, method='GET')
            if response.status_code >= 300:
                local_log.error('XcalInternalCommunicator', 'list_file_cache', response.content)
                raise XcalException('XcalInternalCommunicator', 'list_file_cache', 'http request failed = %d' % response.status_code,
                                    TaskErrorNo.E_CONNECT_API_LIST_SETTING)
            return response.json()

    def create_file_cache(self, file_cache: dict):
        with XcalLogger('XcalInternalCommunicator', 'create_file_cache', parent=self.logger) as local_log:
            header = {'Content-type': 'application/json', 'Authorization': self.token_string}
            data = json.dumps(file_cache)
            response = self._send_http_request(local_log, APIData.file_cache_manage_url, data, header, method='POST')
            if response.status_code >= 300:
                local_log.error('XcalInternalCommunicator', 'create_file_cache', response.content)
                raise XcalException('XcalInternalCommunicator', 'create_file_cache', 'http request failed = %d' % response.status_code,
                                    TaskErrorNo.E_CONNECT_API_LIST_SETTING)

    def update_file_cache(self, file_cache: dict):
        local_log = None
        try:
            with XcalLogger('XcalInternalCommunicator', 'update_file_cache', parent=self.logger) as local_log:
                header = {'Content-type': 'application/json', 'Authorization': self.token_string}
                data = file_cache
                response = self._send_http_request(local_log, APIData.file_cache_manage_url, data, header, method='PUT')
                if response.status_code >= 300:
                    local_log.error('XcalInternalCommunicator', 'update_file_cache', response.content)
                    raise XcalException('XcalInternalCommunicator', 'update_file_cache', 'http request failed = %d' % response.status_code,
                                        TaskErrorNo.E_CONNECT_API_LIST_SETTING)
        except Exception as e:
            logging.exception(e)
            if local_log is not None:
                local_log.error('XcalInternalCommunicator', 'update_file_cache', 'failed, but continuing: %s' % str(e))
            raise e

    def get_file_cache_file_info(self, file_id: str):
        with XcalLogger('XcalInternalCommunicator', 'get_file_cache_file_info', parent=self.logger) as local_log:
            url = '%s/%s' % (APIData.file_cache_file_info_url, file_id)
            header = {'Content-type': 'application/json', 'Authorization': self.token_string}
            response = self._send_http_request(local_log, url, {}, header, method='GET')
            if response.status_code >= 300:
                local_log.error('XcalInternalCommunicator', 'get_file_cache_file_info', response.content)
                raise XcalException('XcalInternalCommunicator', 'get_file_cache_file_info', 'http request failed = %d' % response.status_code,
                                    TaskErrorNo.E_CONNECT_API_LIST_SETTING)
            return response.json()

    @staticmethod
    def _send_http_request(log:XcalLogger, url:str, data:dict, header:dict, files:dict = None, method:str = "PUT"):
        log.trace("_send_http_request", ("data:", data, "url:", url, "header:", header))

        headers = XcalLoggerExternalLinker.prepare_client_request_headers(url, method, log, header)

        log.trace("_send_http_request", "HTTP_CLIENT_RETRY_STATUS_LIST:"+str(HTTP_CLIENT_RETRY_STATUS_LIST))
        #Handle retry for http 
        requests = Session()
        Retry.BACKOFF_MAX =HTTP_CLIENT_RETRY_BACKOFF_MAX
        retry = Retry(
            total=HTTP_CLIENT_RETRY_TOTAL,
            backoff_factor=HTTP_CLIENT_RETRY_BACKOFF_FACTOR,
            status_forcelist=HTTP_CLIENT_RETRY_STATUS_LIST
        )
        requests.mount(url, HTTPAdapter(max_retries=retry))
        requests.keep_alive = True

        if method == "GET":
            update_response = requests.get(url, headers=headers)
        elif method == "POST":
            update_response = requests.post(url, data=data, headers=headers, files=files, timeout=(HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT))
        else:
            update_response = requests.put(url, data=json.dumps(data), headers=headers)

        return update_response

    def upload_diagnostic_info_to_webapi(self, scan_task_id, scan_path):
        try:
            with XcalLogger("XcalInternalCommunicator", "upload_diagnostic_info_to_webapi", parent=self.logger) as local_log:

                diagnostic_info_file = os.path.join(scan_path, SCAN_SERVICE_DIAGNOSTIC_INFO_FILE_NAME)

                with tarfile.open(diagnostic_info_file, mode='x:gz') as tar:
                    file_info = os.path.join(scan_path, 'fileinfo.json')
                    if os.path.exists(file_info):
                        tar.add(file_info, arcname='fileinfo.json', recursive=False)

                    v_file = os.path.join(scan_path, '%s.v' % scan_task_id)
                    if os.path.exists(v_file):
                        tar.add(v_file, arcname='%s.v' % scan_task_id, recursive=False)

                    xvsa_log = os.path.join(scan_path, '%s.xvsa.log' % scan_task_id)
                    if os.path.exists(xvsa_log):
                        tar.add(xvsa_log, arcname='%s.xvsa.log' % scan_task_id, recursive=False)

                    scan_log = os.path.join(scan_path, '.scan_log/scan.log')
                    if os.path.exists(scan_log):
                        tar.add(scan_log, arcname='scan.log', recursive=False)

                    scan_failed_list = os.path.join(scan_path, 'scan_failed_list')
                    if os.path.exists(scan_failed_list):
                        tar.add(scan_failed_list, arcname='scan_failed_list', recursive=False)

                if not os.path.exists(diagnostic_info_file):
                    raise XcalException("XcalInternalCommunicator", "upload_diagnostic_info_to_webapi",
                                        ("%s file does not exist, file_info_path : %s" % (SCAN_SERVICE_DIAGNOSTIC_INFO_FILE_NAME, scan_path)),
                                        TaskErrorNo.E_SRV_UPLOAD_FILEINFO_NEXIST)

                with open(diagnostic_info_file, 'rb') as binaryfile:
                    if binaryfile.readable():
                        files = {'upload_file': binaryfile}
                        post_headers = {"Authorization": self.token_string}
                        server_uri = APIData.diagnostic_log_upload_url.replace('{id}', scan_task_id)
                        response = self._send_http_request(local_log,
                                                          server_uri,
                                                          data={'id': scan_task_id},
                                                          header=post_headers,
                                                          files=files, method="POST")
                        # FIXME: Use raise XcalException here
                        if response.status_code >= 300:
                            logging.error(response.content)
                            self.logger.error("XcalInternalCommunicator", "upload_diagnostic_info_to_webapi",
                                              "http request failed = %s" % (str(response.status_code)))

        except Exception as e:
            if self.logger is not None:
                self.logger.error("XcalInternalCommunicator", "upload_file_info_to_webapi", ("failed, but continuing : %s" % str(e)))
            if not SKIP_API_CALL_ERRORS:
                raise e

    def upload_file(self, file_to_upload):
        """
        Upload a file and get its file-id
        :param file_to_upload:
        :return: file info id
        """
        with XcalLogger("XcalInternalCommunicator", "upload_file", parent = self.logger) as local_log:
            with open(file_to_upload, "rb") as open_file:
                try:
                    post_headers = {"Authorization": self.token_string}
                    result = self._send_http_request(local_log, APIData.upload_file,
                                                     data = {"file_checksum": str(HashUtility.get_crc32_checksum(file_to_upload))},
                                                     header = post_headers, files = {"upload_file": open_file}, method = "POST")
                    result.raise_for_status()
                    file_id = result.json().get("id")
                except requests.exceptions.RequestException as err:
                    raise XcalException("XcalInternalCommunicator", "upload_file", "upload_file failed: %s" % err,
                                        TaskErrorNo.E_UPLOAD_FILE_FAILED)
                except ValueError as err:
                    raise XcalException("XcalInternalCommunicator", "upload_file", "response info is not valid json format: %s" % err,
                                        TaskErrorNo.E_INVALID_JSON_FORMAT)
            return file_id

