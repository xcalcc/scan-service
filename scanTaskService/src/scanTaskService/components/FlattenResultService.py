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


import glob
import json
import os

from common.CommonGlobals import TaskErrorNo, Percentage, BASE_SCAN_PATH
from common.ConfigObject import ConfigObject
from common.XcalException import XcalException
from common.XcalLogger import XcalLogger
from scanTaskService.Config import FLATTEN_V_FILE_BUFFERING, MAXIMUM_SINGLE_V_FILE_SIZE
from scanTaskService.components.InternalCommunicator import XcalInternalCommunicator, Status, Stage


class FlattenResultService(object):
    def __init__(self, logger:XcalLogger, task_config:ConfigObject, stage:dict):
        self.logger = XcalLogger("FlattenResultService", "__init__", parent=logger)
        self.scan_id = task_config.get("scanTaskId")
        self.task_config = task_config
        self.indentation = 1
        self.v_file_encoding = "UTF-8"
        if task_config.get("flattenIndent") is not None:
            self.indentation = int(task_config.get("flattenIndent"))
        if task_config.get("flattenEncoding") is not None:
            self.v_file_encoding = task_config.get("flattenEncoding")
        self.scan_work_dir = os.path.join(BASE_SCAN_PATH, self.scan_id)
        self.stage = stage
        self.comms = XcalInternalCommunicator(self.logger, task_config)
        self.complete_status = Status.COMPLETED
        # Task Specific Data Structures
        self.headers = None
        self.global_filename_to_id_map = {}
        self.global_file_id_next = 1
        self.full_issues = []
        if int(self.stage.get("completeRatio")) != 100:
            self.complete_status = Status.PROCESSING

    def flatten_scan_result(self):
        # Open scan folder and count output v file numbers.
        # If no v file was found, report error.
        v_file_src_list = []
        tmpdir = self.scan_work_dir
        result_file_path = os.path.join(self.scan_work_dir, "%s.v" % (self.scan_id))

        for filename in glob.glob(os.path.join(tmpdir, "scan_result", "*.v")):
            v_file_src_list.append(filename)

        if len(v_file_src_list) == 1:
            self.logger.trace("flatten_scan_result", "only one scan result file, no need to do flatten")
            return result_file_path

        self.comms.upload_progress(self.scan_id, Stage.SCANNING, Status.PROCESSING,
                                   Percentage.START, "starting flatten v files")

        self.logger.trace("flatten_scan_result",
                          "flatten multiple result files, flattened result file will be: %s" % result_file_path)

        if os.path.exists(result_file_path):
            os.rename(result_file_path,
                      os.path.join(os.path.dirname(result_file_path),
                                   os.path.basename(result_file_path) + ".origin.v"))

        # Use mechanism to sort the filenames to guarantee consistent result.
        v_file_src_list.sort()

        # Used for mapping filename to a global_file_id
        self.global_filename_to_id_map = {}
        self.global_file_id_next = 1

        # Read a file to the
        for filename in v_file_src_list:
            # Used for mapping local file-id to global-file-id
            local_to_global_map = {}
            self.logger.trace("Processing one v-file", filename)

            if os.path.getsize(filename) > MAXIMUM_SINGLE_V_FILE_SIZE:
                self.logger.warn("flatten_scan_result", "scan result %s is larger than 500M" % filename)

            with open(filename, "r", encoding=self.v_file_encoding) as f:
                # Open the file with json.load
                one_file = json.load(f)

                # Build the local to global map and
                # add the not-existing filenames to global map
                self.prepare_id_mapping(local_to_global_map, one_file)

                # Add V-File Content to List, which does not make copies of single issue,
                # Instead, issue should be bound to new list only.
                self.collect_issues(local_to_global_map, one_file)

                # There are still references to issues inside one_file
                one_file = None

        self.logger.trace("flatten_scan_result", "write result v file, ready to write files. Issues size: %d" % (len(self.full_issues)))

        with open(result_file_path, "w", buffering=FLATTEN_V_FILE_BUFFERING) as result_fp:
            # Preparing the global file list
            global_file_list = []
            for k,v in self.global_filename_to_id_map.items():
                global_file_list.append({"fid": v, "path": k})

            self.logger.trace("flatten_scan_result", "writing results, final issue size = %d, files size = %d" %
                        (len(self.full_issues), len(global_file_list)))

            self.headers["files"] = global_file_list
            self.headers["issues"] = self.full_issues
            result_str = json.dumps(self.headers,
                                    indent=self.indentation)
            result_fp.write(result_str)

        self.comms.upload_progress(self.scan_id, Stage.SCANNING, Status.PROCESSING,
                                   Percentage.MIDDLE, "flatten v files done")
        pass

    def collect_issues(self, local_to_global_map, one_file:dict):
        """
        Process one v file's all issues, and append to list
        :param local_to_global_map: local file-id to global-file-id map
        :param one_file: the v-file to be processed
        :return: None
        """
        for one_entry in one_file.get("issues"):
            local_id = one_entry.get("fid")
            # The below action could result in failure, we need to
            global_id = local_to_global_map.get(local_id)
            if global_id is None:
                raise XcalException("FlattenResultService", "collect_issues", "Cannot map fid to its files entry",
                                    TaskErrorNo.E_SRV_FLATTEN_FID_INVALID)
            changed_one_entry = one_entry
            changed_one_entry["fid"] = str(global_id)
            for one_path in changed_one_entry.get("paths"):
                local_id = one_path.get("fid")
                global_id = local_to_global_map.get(local_id)
                if global_id is None:
                    raise XcalException("FlattenResultService", "collect_issues", "Cannot map path fid to its files entry",
                                        TaskErrorNo.E_SRV_FLATTEN_PATH_FID_INVALID)
                one_path["fid"] = str(global_id)
            self.full_issues.append(changed_one_entry)
        pass

    def prepare_id_mapping(self, local_to_global_map:dict, one_file:dict):
        """
        Add the files to the local_to_global_map and global_filename_to_id_map,
        While keeping a largest global file id at global_file_id_next = current_max + 1
        :param local_to_global_map:
        :param one_file:
        :return: None
        """
        if self.headers is None:
            self.headers = {"rulesets": one_file["rulesets"], "v": one_file["v"],
                            "id": self.scan_id, "s": one_file["s"],
                            "m": one_file["m"], "eng": one_file["eng"],
                            "ev": one_file["ev"], "er": one_file["er"],
                            "x1": one_file["x1"], "x2": one_file["x2"],
                            "ss": one_file["ss"], "se": one_file["se"],
                            "usr": one_file["usr"], "sys": one_file["sys"],
                            "rss": one_file["rss"]}

        for one in one_file.get("files"):
            if self.global_filename_to_id_map.get(one.get("path")) is not None:
                local_to_global_map[one.get("fid")] = self.global_filename_to_id_map.get(one.get("path"))
            else:
                self.global_filename_to_id_map[one.get("path")] = str(self.global_file_id_next)
                local_to_global_map[one.get("fid")] = str(self.global_file_id_next)
                self.global_file_id_next += 1

    # Not used right now.
    def process_issues(self, issue, issue_list: list, key_list: list):
        # print(issue)
        path = issue["paths"][0]
        lastitem = len(issue["paths"]) - 1
        lastpath = issue["paths"][lastitem]
        key = path["fid"] + "-" + str(path["sln"])
        lastkey = lastpath["fid"] + "-" + str(lastpath["sln"])
        # print(key + " - " + lastkey)
        if key not in key_list and \
                lastkey not in key_list:
            key_list.append(key)
            key_list.append(lastkey)
            issue_list.append(issue)

    # Not used right now.
    def process_result_file(self, file_name, debug_mode=False):
        # TODO: need to check the size of the json file
        with open(file_name, "r") as v_file:
            v_data = json.load(v_file)

            rule_codes_set = set()
            for issue in v_data["issues"]:
                rule_codes_set.add(issue["rc"])

            if debug_mode:
                self.logger.info("rule_codes_set: %s" % rule_codes_set, "")

            rule_code_issues_map = {}
            for rule_code in rule_codes_set:
                rule_code_issues_map[rule_code] = []

            for issue in v_data["issues"]:
                rule_code_issues_map[issue["rc"]].append(issue)

            issues_list = []
            for key in rule_code_issues_map:
                key_list = []
                for issue in rule_code_issues_map[key]:
                    self.process_issues(issue, issues_list, key_list)

            new_v_data = {"files": v_data["files"], "issues": issues_list,
                          "rulesets": v_data["rulesets"], "v": v_data["v"],
                          "id": v_data["id"], "s": v_data["s"],
                          "m": v_data["m"], "eng": v_data["eng"],
                          "ev": v_data["ev"], "er": v_data["er"],
                          "cmd": v_data["cmd"], "env": v_data["env"],
                          "ss": v_data["ss"], "se": v_data["se"]}

        # TODO: result file name should be specified or default value
        with open(os.path.join(BASE_SCAN_PATH, self.scan_id,
                               "%s.v" % (self.scan_id)), 'w') as outfile:
            json.dump(new_v_data, outfile, indent = 1)

