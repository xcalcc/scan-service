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

import sys
import json
import threading

from flask import jsonify, request, url_for

from common.CommonGlobals import Percentage, SOURCE_CODE_ARCHIVE_FILE_NAME, FILE_INFO_FILE_NAME, PREPROCESS_FILE_NAME, VCS_DIFF_RESULT_FILE_NAME

# Global Config
from common.AgentAuthentication import AgentValueVerifier
from common.XcalException import XcalException
from common.TokenExtractor import TokenObjectCreator
from common.ConfigObject import ConfigObject
from common.XcalLogger import XcalLoggerExternalLinker
from scanTaskService.components import LoggingHandler
from scanTaskService.components.AgentInfo import AgentWorkerInfo, AgentWorkerStatus, AgentInfoManagement

from scanTaskService.components.CachedFileStorage import CachedFileStorage
from scanTaskService.components.JobInitiator import JobListener
from scanTaskService.components.ScanServiceWorker import ScanServiceJobListener, ExpiredTaskRemover, \
    ScanEngineServiceJobListener, TimerProcessAgentInfo
from scanTaskService.components.XcalServices import ScanController, ProgressReporterService, ScanServiceBusinessLogic
from scanTaskService.Config import *
from scanTaskService.components.InternalCommunicator import XcalInternalCommunicator, Stage, Status
from scanTaskService.util.FileUtility import get_hash_of_dir
from scanTaskService.util.Metrics import ScanMetrics
from scanTaskService.util.TimeUtility import TimeUtility
from scanTaskService.components.ErrorRecover import POST_STATUS, PROC, STATUS, ERROR_RECOVER
from scanTaskService.util.KafkaUtility import KafkaUtility

import scanTaskService.components.ScanTaskScheduler

from scanTaskService.components.ErrorRecover import CONST_STR

from scanTaskService.util.file_util import get_client, FileUtil

"""

WARNING:

Any and all changes to the APIs on this list must also be accompanied by an
 change on the VERSION_INFO_STR in Config.py accordingly.

"""


# Fix Zentao Bug #697, start the following operations in a new thread
# Because the timeout is not guaranteed to work.
def try_send_push_gw():
    """
    Send scan task information to push gateway (Prometheus)
    :return:
    """
    try:
        scanTaskServiceCounter.labels(method='get', endpoint='/api/scan_task_service/v2').inc()
        from scanTaskService.Config import registry
        ScanMetrics.push_to_gateway(push_gateway_url, job='scanTaskService', reg=registry)
    except Exception as err:
        logging.exception(err)

@app.route('/api/scan_task_service/v3', methods = ['POST'])
def scan_task_service_of_new_client():
    # Starting a new thread to report to push gateway, ticking the counter.
    th = threading.Thread(target=try_send_push_gw)
    th.start()
    with XcalLoggerExternalLinker.prepare_server_span_scope('scanApp', 'scan_task_service', request.headers) as log:
        log.info("scan_task_service", "receive request")

        try:
            # Start Processing ---------------------------------
            task_config = request.get_json()
            log.trace("scan_task_service", "task_config: %s" % task_config)

            # Post Kafka message for client status
            writePreprocStatusToKafka(task_config)

            # TODO: need to think about whether client should upload to correct path to file service directly to avoid this move?
            project_id = task_config.get("projectId")
            scan_task_id = task_config.get('scanTaskId')
            client = get_client(log, FILE_SERVICE_URL)
            file_util = FileUtil(client, log)
            if file_util.file_exists(PREPROCESS_DATA_BUCKET_NAME, os.path.join(project_id, VCS_DIFF_RESULT_FILE_NAME)):
                file_util.move_object(PREPROCESS_DATA_BUCKET_NAME,  os.path.join(project_id, VCS_DIFF_RESULT_FILE_NAME), PREPROCESS_DATA_BUCKET_NAME, os.path.join(project_id, scan_task_id, VCS_DIFF_RESULT_FILE_NAME))
            if file_util.file_exists(PREPROCESS_DATA_BUCKET_NAME, os.path.join(project_id, SOURCE_CODE_ARCHIVE_FILE_NAME)):
                file_util.move_object(PREPROCESS_DATA_BUCKET_NAME,  os.path.join(project_id, SOURCE_CODE_ARCHIVE_FILE_NAME), PREPROCESS_DATA_BUCKET_NAME, os.path.join(project_id, scan_task_id, SOURCE_CODE_ARCHIVE_FILE_NAME))
            file_util.move_object(PREPROCESS_DATA_BUCKET_NAME, os.path.join(project_id, PREPROCESS_FILE_NAME), PREPROCESS_DATA_BUCKET_NAME, os.path.join(project_id, scan_task_id, PREPROCESS_FILE_NAME))
            file_util.move_object(PREPROCESS_DATA_BUCKET_NAME, os.path.join(project_id, FILE_INFO_FILE_NAME), PREPROCESS_DATA_BUCKET_NAME, os.path.join(project_id, scan_task_id, FILE_INFO_FILE_NAME))

            logic = ScanServiceBusinessLogic(log)
            config_object = logic.get_configs(task_config)
            log.trace("scan_task_service", "standard task_config: %s" % config_object)

            logic.initiate_scan_pipeline(config_object)
            resp = jsonify("scan_task_service pipeline started")
            resp.status_code = 200
            log.info("scan_task_service", "service execute successfully")
        except XcalException as err:
            logging.exception(err)
            if log is not None:
                log.error("scanApp", "scan_task_service",
                          "ErrorCode = %s, message = %s" % (str(err.err_code), err.message))
            resp = jsonify("scan_task_service pipeline creation failed ", str(err))
            resp.status_code = 500
        except Exception as exp:
            logging.exception(exp)
            if log is not None:
                log.error("scanApp", "scan_task_service",
                          ("Exception in request handling", exp))
            resp = jsonify("scan_task_service pipeline creation failed ", str(exp))
            resp.status_code = 500

    return resp

def writePreprocStatusToKafka(task_config):
    log.trace("scan_task_service", "Write preproc-done message to kafka")
    timestamp = int(round(time.time() * 1000))
    KafkaUtility.kafka_publish("preproc-done", json.dumps({
        "projectId": task_config.get("projectId"),
        "source": "PREPROC",
        "scanTaskId": task_config.get("scanTaskId"),
        "status": STATUS.SUCC.name,
        "dateTime": timestamp
    }, indent=1))

# args are inside the json body, if directInvoke is present, call controller directly
# VERSION_INFO_STR >= 0.0.1
@app.route('/api/scan_task_service/v2', methods = ['POST'])
@app.route('/api/v2/scan_task_service', methods = ['POST'])
@app.route('/v2/scan_task_service', methods = ['POST'])
def scan_task_service():
    # Starting a new thread to report to push gateway, ticking the counter.
    th = threading.Thread(target=try_send_push_gw)
    th.start()
    with XcalLoggerExternalLinker.prepare_server_span_scope('scanApp', 'scan_task_service', request.headers) as log:
        log.info("scan_task_service", "receive request")

        try:
            # Start Processing ---------------------------------
            task_config = request.get_json()
            log.trace("scan_task_service", "task_config: %s" % task_config)

            # Post Kafka message for client status
            writePreprocStatusToKafka( task_config)


            logic = ScanServiceBusinessLogic(log)

            config_object = logic.get_configs(task_config)
            logic.initiate_scan_pipeline(config_object)
            resp = jsonify("scan_task_service pipeline started")
            resp.status_code = 200
            log.info("scan_task_service", "service execute successfully")
        except XcalException as err:
            logging.exception(err)
            if log is not None:
                log.error("scanApp", "scan_task_service",
                          "ErrorCode = %s, message = %s" % (str(err.err_code), err.message))
            resp = jsonify("scan_task_service pipeline creation failed ", str(err))
            resp.status_code = 500
        except Exception as exp:
            logging.exception(exp)
            if log is not None:
                log.error("scanApp", "scan_task_service",
                          ("Exception in request handling", exp))
            resp = jsonify("scan_task_service pipeline creation failed ", str(exp))
            resp.status_code = 500

    return resp

def get_supported_job_queue_name_from_agent_request(args: dict, user_info: dict):
    """

    :param args: agent request args
    :param user_info:
    :return:
    """
    supported_job_queue_name = args.get("supportedJobQueueName", JOB_QUEUE_NAME)  # job queue can be one job or job list
    if supported_job_queue_name is None:
        raise XcalException("scanApp", "get_supported_job_queue_name_from_agent_request",
                            "supported_job_queue_name should not be None",
                            err_code = TaskErrorNo.E_JOB_QUEUE_NAME_INVALID)
    for job_name in supported_job_queue_name:
        if not AgentValueVerifier.is_name_valid(job_name):
            raise XcalException("scanApp", "get_supported_job_queue_name_from_agent_request",
                                "Invalid job queue name, only a-z,A-Z,0-9,-,_,."
                                "are allowed (without commas)",
                                err_code = TaskErrorNo.E_JOB_QUEUE_NAME_INVALID)

    if isinstance(supported_job_queue_name, list):
        for i, job_name in enumerate(supported_job_queue_name):
            if not str(job_name).startswith("public_"):
                supported_job_queue_name[i] = str(user_info.get("username")) + "_" + job_name
    else:
        if not str(supported_job_queue_name).startswith("public_"):
            supported_job_queue_name = str(user_info.get("username")) + "_" + supported_job_queue_name
        supported_job_queue_name = [supported_job_queue_name]   # to make sure supported_job_queue_name is a list

    return supported_job_queue_name


# args are inside the json body, if directInvoke is present, call controller directly
# VERSION_INFO_STR >= 0.0.1
@app.route('/api/scan_task_service/v3/agent/get_task', methods = ['POST', 'GET'])
def agent_get_task():
    log = None
    try:
        log = XcalLogger("scanApp", "agent_get_task")
        log.info("Received Agent Polling", " %s" % time.asctime())

        args = request.get_json()
        log.debug("agent_get_task", args)

        if args is not None:
            if args.get("agentToken") is None:
                raise XcalException("scanApp", "agent_get_task", "agent token must be provided",
                                    err_code = TaskErrorNo.E_NO_AGENT_TOKEN)
            task_config = ConfigObject({"token": args.get("agentToken")})
            user_info = XcalInternalCommunicator(log, task_config).get_current_user_info()
            user_info_json = user_info.json()  # need to check json
            if user_info_json.get("username") is None:
                raise XcalException("scanApp", "agent_get_task", "cannot find username",
                                    TaskErrorNo.E_GET_CURRENT_USER_INFO_FAILED)

            agent_name = args.get("agentName", AGENT_NAME_DEFAULT)
            if not AgentValueVerifier.is_name_valid(agent_name):
                raise XcalException("scanApp", "agent_get_task", "Invalid agent name, only a-z,A-Z,0-9,-,_,."
                                                                 "are allowed (without commas)",
                                    err_code = TaskErrorNo.E_AGENT_NAME_INVALID)

            supported_job_queue_name = get_supported_job_queue_name_from_agent_request(args, user_info_json)
        else:
            user_info_json = {"username": "unknown-username"}
            agent_name = AGENT_NAME_DEFAULT
            supported_job_queue_name = [JOB_QUEUE_NAME]

        log.trace("agent_get_task", " agent job queue: %s" % supported_job_queue_name)

        jobs_list = []
        for job_name in supported_job_queue_name:
            listener = JobListener(log)
            jobs_list = listener.poll_job_task(AGENT_TOPIC_PREFIX + job_name, AGENT_MAX_ENTRIES_PER_POLL)
            listener.commit_job_task()
            if len(jobs_list) > 0:
                break      # when get a job, jump from the loop

        resp = jsonify({"status": "ok",
                        "jobCount": len(jobs_list),
                        "jobs": jobs_list})

        log.debug("agent_get_task", "jobs_list: %s" % jobs_list)
        scan_task_id = None
        if len(jobs_list) != 0:
            scan_task_id = jobs_list[0].get("taskConfig").get("scanTaskId")

        if args is not None:
            worker_info = AgentWorkerInfo(args.get("threadId"), args.get("threadName"), AgentWorkerStatus.IDLE,
                                          pid = args.get("pid"), scan_task_id = scan_task_id)
            log.debug("agent_get_task", "worker_info: %s" % worker_info)
            AgentInfoManagement.update_agent_info(args.get("agentId"), agent_name, user_info_json.get("username"),
                                                  supported_job_queue_name, args.get("workerNum"), worker_info)

        resp.status_code = 200
        return resp
    except XcalException as exp:
        logging.exception(exp)
        if log is not None:
            log.info("agent_get_task", "error message: %s %s %s" % (exp.message, exp.service, exp.operation))
        resp = jsonify({"status": "failed", "detail": str(exp.message), "service": exp.service, "op": exp.operation})
        resp.status_code = 500
        return resp
    except Exception as exp:
        logging.exception(exp)
        if log is not None:
            log.info("Exception in request handling", ("Error unknown...", exp))
        resp = jsonify({"status": "failed"})
        resp.status_code = 500
        return resp


# args are: 1.token=... 2.checksum={SHA1 checksum of a file}, V0.0.5
@app.route('/api/scan_task_service/v2/agent/check_file_cache', methods = ['POST', 'GET'])
def check_file_cache():
    request_data = ConfigObject.merge_two_dicts(request.get_json(), request.args)
    token = request_data.get("token", "")
    checksum = request_data.get("checksum", "")
    log = XcalLogger("scanApp", "check_file_cache")
    try:
        if token is None or checksum is None or len(token) <= 1 or len(checksum) <= 1:
            raise XcalException("scanApp", "check_file_cache", "incorrect parameters given by agent",
                                TaskErrorNo.E_SRV_AGENT_CHECK_CACHE)
        else:
            task_config = TokenObjectCreator().inject_object({}, token)
            cache = CachedFileStorage(log, task_config)
            output = cache.check_storage_exists(checksum)
            if output is not None:
                # get rt.tgz file info with artifactFileId or fileId to avoid file not exists
                artifact_file_id = output.get('artifactFileId')
                if artifact_file_id is not None:
                    try:
                        XcalInternalCommunicator(log, task_config).get_file_cache_file_info(artifact_file_id)
                        return jsonify({"status": "existing", "fileId": output.get("fileId"), "obj": output.copy()})
                    except Exception as e:
                        pass
                file_id = output.get('fileId')
                if file_id is not None:
                    try:
                        XcalInternalCommunicator(log, task_config).get_file_cache_file_info(file_id)
                        return jsonify({"status": "existing", "fileId": output.get("fileId"), "obj": output.copy()})
                    except Exception as e:
                        pass
            return jsonify({"status": "not-found", "msg": "not-found"})
    except Exception as err:
        logging.exception(err)
        log.error("scanApp", "check_file_cache", "failed in checking cache files api")
        resp = jsonify({"msg": "failed", "reason": "Parameter failed", "status": "failed"})
        resp.status_code = 500
        return resp


# args are: 1.token=... 2.checksum={SHA1 checksum of a file} 3.fileid=..., V0.0.6
@app.route('/api/scan_task_service/v2/agent/save_file_cache', methods = ['POST', 'GET'])
def agent_save_file_cache():

    request_data = ConfigObject.merge_two_dicts(request.get_json(), request.args)
    token = request_data.get("token", "")
    checksum = request_data.get("checksum", "")
    file_id = request_data.get("fileId", "")
    log = XcalLogger("scanApp", "agent_save_file_cache")
    try:
        if token is None or checksum is None or file_id is None or len(token) <= 1 or len(checksum) <= 1 or len(file_id) <= 1:
            raise XcalException("scanApp", "agent_save_file_cache", "incorrect parameters given by agent",
                                TaskErrorNo.E_SRV_AGENT_CHECK_CACHE)
        else:
            task_config = TokenObjectCreator().inject_object({}, token)
            cache = CachedFileStorage(log, task_config)
            output = cache.save_to_storage(checksum, file_id)
            return jsonify({"status": "ok"})

    except Exception as err:
        logging.exception(err)
        log.error("scanApp", "agent_save_file_cache", "failed in checking cache files api")
        resp = jsonify({"msg": "failed", "reason": "Saving failed", "status": "failed"})
        resp.status_code = 500
        return resp


# args are: 1.token=... 2.checksum={SHA1 checksum of a file} 3.fileid=..., V0.0.6
@app.route('/api/scan_task_service/v2/agent/clear_file_cache', methods = ['POST', 'GET'])
def agent_clear_file_cache():

    request_data = ConfigObject.merge_two_dicts(request.get_json(), request.args)
    token = request_data.get("token", "")
    checksum = request_data.get("checksum", "")
    log = XcalLogger("scanApp", "agent_save_file_cache")
    try:
        if token is None or len(token) <= 1:
            raise XcalException("scanApp", "agent_save_file_cache", "incorrect parameters given by api request, token is None",
                                TaskErrorNo.E_SRV_AGENT_CHECK_CACHE)
        if checksum is not None:
            task_config = TokenObjectCreator().inject_object({}, token)
            cache = CachedFileStorage(log, task_config)
            count = cache.remove_file_storage(key=checksum)
            return jsonify({"status": "ok", "removedCount": count})
        else:
            task_config = TokenObjectCreator().inject_object({}, token)
            cache = CachedFileStorage(log, task_config)
            cache.remove_all_file_storage()

        return jsonify({"status": "ok"})

    except Exception as err:
        logging.exception(err)
        log.error("scanApp", "agent_save_file_cache", "failed in checking cache files api")
        resp = jsonify({"msg": "failed", "reason": "Saving failed", "status": "failed"})
        resp.status_code = 500
        return resp


# VERSION_INFO_STR >= 0.0.1
@app.route('/api/scan_task_service/<string:ver>/system/version')
@app.route('/api/<string:ver>/scan_task_service/system/version')
@app.route('/api/scan_task_service/system/version')
def get_version_info(ver="v0"):
    version_dict = {"version": VERSION_INFO_STR,
                    "apiVersion": SCAN_SERVICE_API_VER,
                    "checksum": get_hash_of_dir(os.path.dirname(__file__)),
                    "date": TimeUtility().get_utc_timestamp()}
    return jsonify(version_dict)


# args are inside the json body, if directInvoke is present, call controller directly
# VERSION_INFO_STR >= 0.0.1
@app.route('/api/scan_task_service/v3/agent/progress_report', methods = ['POST', 'GET'])
def agent_report_progress():
    with XcalLogger("scanApp", "agent_report_progress") as log:
        try:
            # Merging TaskConfig with JobConfig TODO: Refine this with only limited key override.
            agent_config = request.get_json()
            log.debug("agent_report_progress", agent_config.get("agentInfo"))

            agent_info = agent_config.get("agentInfo")
            worker_info = AgentWorkerInfo(agent_info.get("threadId"), agent_info.get("threadName"),
                                          AgentWorkerStatus.BUSY,
                                          pid = agent_info.get("pid"), scan_task_id = agent_info.get("scanTaskId"))
            log.debug("agent_report_progress", "worker_info: %s" % worker_info)
            AgentInfoManagement.update_agent_info(agent_info.get("agentId"), agent_info.get("agentName"),
                                                  agent_info.get("username"),
                                                  agent_info.get("supportedJobQueueName"), agent_info.get("workerNum"),
                                                  worker_info)

            task_config = agent_config["taskConfig"]
            intermediate_obj = ConfigObject.merge_two_dicts(agent_config, task_config)

            # Upload Progress
            log.trace("Received Agent Progress Report, obj = %s" % str(intermediate_obj), "")
            log.trace("Received Agent Progress Report, target = %s" % agent_config.get("target", "None"), "")

            post_prescan_obj = ConfigObject(intermediate_obj)

            if agent_config.get("target") == "progress":
                ProgressReporterService(log, post_prescan_obj, {"type": "uploadProgress"}).execute()
            elif agent_config.get("target") == "result":
                XcalInternalCommunicator(log, task_config).upload_progress(task_config.get("scanTaskId"),
                                                                           Stage.SCAN_QUEUE_GET_PRESCAN_RESULT,
                                                                           Status.PROCESSING,
                                                                           Percentage.START,
                                                                           "publish get prescan result job to mq")
                ScanController(log).commit_task_done(post_prescan_obj)
            else:
                logging.error("Erroneous Agent Response \n %s \n", json.dumps(agent_config))
                raise XcalException("scanApp", "agent_report_progress",
                                    "Unknown target, please check config", TaskErrorNo.E_API_AGENT_PARAM_TARGET)

            resp = jsonify({
                "status": "ok",
            })
            resp.status_code = 200
        except XcalException as exp:
            logging.exception(exp)
            log.error("XcalException", "API:agent_report_progress", ("XcalExcept", exp.message, exp.service, exp.operation))
            resp = jsonify({"msg": "Error occurred", "detail": str(exp.message), "service":exp.service, "op":exp.operation})
            resp.status_code = 500
        except Exception as exp:
            logging.exception(exp)
            log.error("XcalException", "API: BaseExcept in handling", ("Error unknown...", exp))
            resp = jsonify("Error occurred")
            resp.status_code = 500

        return resp


@app.route('/api/scan_task_service/v3/agent/status', methods = ['POST', 'GET'])
def report_agent_status():
    with XcalLogger("scanApp", "report_agent_status") as log:
        try:
            agent_info = request.get_json()
            log.debug("report_agent_status", agent_info)

            # TODO: may need to improve later
            AgentInfoManagement.remove_terminate_agent_info(agent_info.get("agentId"), agent_info.get("status"))

            resp = jsonify({"status": "ok"})
            resp.status_code = 200
        except XcalException as exp:
            logging.exception(exp)
            log.error("scanApp", "report_agent_status", ("XcalException", exp.message, exp.service, exp.operation))
            resp = jsonify(
                {"msg": "Error occurred", "detail": str(exp.message), "service": exp.service, "op": exp.operation})
            resp.status_code = 500
        except Exception as exp:
            logging.exception(exp)
            log.error("scanApp", "report_agent_status", ("Error unknown...", exp))
            resp = jsonify("Error occurred")
            resp.status_code = 500

        return resp


# VERSION_INFO_STR >= 0.0.1
@app.route('/api/scan_task_service/v2/admin/cancel_task', methods = ['POST', 'GET'])
def cancel_task():
    log = XcalLogger("scanApp", "agent_report_progress")
    args = request.args
    task_config = ConfigObject({"token": args.get("token")})
    comms = XcalInternalCommunicator(log, task_config)
    comms.upload_progress(args.get("scanTaskId"), Stage.TEST, Status.FAILED, Percentage.END,
                          "User cancelled the task manually.", TaskErrorNo.E_SRV_SCAN_CANCELLED)
    resp = jsonify({"status": "ok"})
    resp.status_code = 200
    return resp


@app.route('/api/scan_task_service/v3/cancel_scan_task', methods=['POST'])
def cancel_scan_task():
    with XcalLoggerExternalLinker.prepare_server_span_scope('scanApp', 'cancel_scan_task', request.headers) as logger:
        scan_task = request.json
        logger.trace('cancel_scan_task', str(scan_task))
        scanTaskService.components.ScanTaskScheduler.scheduler.del_task(scan_task)
        return jsonify('success')


# Do nothing ... but returns status ok,
# VERSION_INFO_STR = 0.0.1
@app.route('/api/scan_task_service/v2', methods = ['GET'])
@app.route('/v2/scan_task_service', methods = ['GET'])
def scan_task_get():
    try:
        raw_data = request.get_json()
        with XcalLoggerExternalLinker.prepare_server_span_scope('scan_task_get', "api_scan_task_service_get", request.headers) as log:
            log.info('[scan_task_get] raw_data=%s' % (json.dumps(raw_data)), threading.current_thread())
    finally:
        return json.dumps({"version": "v2", "status": "ok"})


def has_no_empty_params(rule):
    defaults = rule.defaults if rule.defaults is not None else ()
    arguments = rule.arguments if rule.arguments is not None else ()
    return len(defaults) >= len(arguments)


@app.route("/site-map")
def site_map():
    links = []
    for rule in app.url_map.iter_rules():
        # Filter out rules we can't navigate to in a browser
        # and rules that require parameters
        if ("GET" in rule.methods or "POST" in rule.methods) and has_no_empty_params(rule):
            url = url_for(rule.endpoint, **(rule.defaults or {}))
            links.append((url, rule.endpoint))
    return jsonify(links)
    # links is now a list of url, endpoint tuples

@app.route("/worker-health")
def worker_health():
    content=[]
    for worker in ScanEngineServiceJobListener.workers:
        workerDict={"name":worker.getName(), "isAlive":str(worker.is_alive())}
        content.append(workerDict)
    for worker in ScanServiceJobListener.workers:
        workerDict={"name":worker.getName(), "isAlive":str(worker.is_alive())}
        content.append(workerDict)
    return jsonify(content)

def is_policy_exist():
    if os.path.exists(CONST_STR.RECOVER_POLICY.value):
        return True
    else:
        return False

if __name__ == '__main__':
    # Setting up Flask Port
    port = os.getenv("SCAN_PORT", "80")

    # Initialize logging utilities
    LoggingHandler.initialize_logging_utilities()

    with XcalLogger("scanApp", "main") as log:
        log.info("Starting processes", "")

    # install_module("pympler")
    # HealthCheck().start()
    logging.warning("Starting ScanApp.py, starting daemon services")

    # Check if policy exist
    if not is_policy_exist():
        logging.error("policy file not exist, stopping service")
        sys.exit()
    else:
        logging.info("policy file exist")

    worker_count = int(os.getenv("SCANNER_WORKER_COUNT", SCANNER_WORKER_COUNT))
    ScanServiceJobListener().start_workers(worker_count)         # main scan service
    ScanEngineServiceJobListener().start_workers(worker_count)   # scan engine(xvsa) service
    ExpiredTaskRemover().start()
    TimerProcessAgentInfo.start()
    logging.warning("Starting ScanApp.py, starting HTTP service")
    app.run(host = '0.0.0.0', port = int(port), debug = False)
    logging.warning("HTTP Service Started [OK]")
