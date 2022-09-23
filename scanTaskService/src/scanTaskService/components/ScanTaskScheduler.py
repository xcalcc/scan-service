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

from concurrent.futures import ThreadPoolExecutor

from kafka import KafkaProducer, KafkaConsumer

from common.CommonGlobals import BASE_SCAN_PATH
from common.ConfigObject import ConfigObject
from common.XcalLogger import XcalLogger
from scanTaskService.components.ErrorRecover import POST_STATUS, STATUS
from scanTaskService.components.ScanController import ScanController

SCANNER_WORKER_COUNT = os.getenv('SCANNER_WORKER_COUNT', 1)

KAFKA_HOST = os.getenv('KAFKA_HOST', 'kafka')
KAFKA_PORT = os.getenv('KAFKA_PORT', 9092)

TOPIC_SCAN_TASK_START = 'topic-scan-task-start'
TOPIC_SCAN_TASK_STOP = 'topic-scan-task-stop'

GROUP_SCAN_TASK_START = 'group-scan-task-start'
GROUP_SCAN_TASK_STOP = 'group-scan-task-stop'

'''
A policy for resetting offsets on OffsetOutOfRange errors: 
‘earliest’ will move to the oldest available message, 
‘latest’ will move to the most recent. 
Any other value will raise the exception. 
Default: ‘latest’.
'''
AUTO_OFFSET_RESET = 'earliest'

'''
The maximum delay between invocations of poll() when using consumer group management. 
This places an upper bound on the amount of time that the consumer can be idle before fetching more records. 
If poll() is not called before expiration of this timeout, then the consumer is considered failed 
and the group will rebalance in order to reassign the partitions to another member. 
Default 300000
'''
MAX_POLL_INTERVAL_MS = 86400000

FUTURE_TIMEOUT = 10


def run_task(msg: str):
    task_config = json.loads(msg).get('config', {})
    ScanController(XcalLogger('ScanTaskScheduler', 'run_task'), ConfigObject(task_config)).sp_start()


def del_task(msg: str):
    try:
        logging.warning('recv: %s' % msg)
        json_msg = json.loads(msg)
        scan_task_id = json_msg["scanTaskId"] or ''
        if_cancel = True
        ps = POST_STATUS(scan_task_id, "", STATUS.CANCEL.value, BASE_SCAN_PATH, if_cancel)
        ps.cancel_scan_task()
    except Exception as e:
        logging.error('exception: %s' % repr(e))


def run_work():
    consumer = KafkaConsumer(TOPIC_SCAN_TASK_START, group_id=GROUP_SCAN_TASK_START,
                             auto_offset_reset=AUTO_OFFSET_RESET,
                             max_poll_interval_ms=MAX_POLL_INTERVAL_MS,
                             bootstrap_servers='%s:%d' % (KAFKA_HOST, int(KAFKA_PORT)))

    for msg in consumer:
        run_task(msg.value.decode('utf-8'))

    consumer.close()


def del_work():
    consumer = KafkaConsumer(TOPIC_SCAN_TASK_STOP, group_id=GROUP_SCAN_TASK_STOP,
                             auto_offset_reset=AUTO_OFFSET_RESET,
                             max_poll_interval_ms=MAX_POLL_INTERVAL_MS,
                             bootstrap_servers='%s:%d' % (KAFKA_HOST, int(KAFKA_PORT)))

    for msg in consumer:
        del_task(msg.value.decode('utf-8'))

    consumer.close()


class ScanTaskScheduler:

    def __init__(self):
        self.thread_pool = ThreadPoolExecutor(int(SCANNER_WORKER_COUNT) + 1)
        for i in range(int(SCANNER_WORKER_COUNT)):
            self.thread_pool.submit(run_work)
        self.thread_pool.submit(del_work)
        self.producer = KafkaProducer(bootstrap_servers=['%s:%d' % (KAFKA_HOST, int(KAFKA_PORT))])

    def __del__(self):
        self.producer.close()
        self.thread_pool.shutdown(True)

    def add_task(self, scan_task: dict):
        logging.warning('send: %s' % scan_task)
        future = self.producer.send(TOPIC_SCAN_TASK_START, json.dumps(scan_task).encode('utf-8'))
        future.get(timeout=FUTURE_TIMEOUT)

    def del_task(self, scan_task: dict):
        logging.warning('send: %s' % scan_task)
        future = self.producer.send(TOPIC_SCAN_TASK_STOP, json.dumps(scan_task).encode('utf-8'))
        future.get(timeout=FUTURE_TIMEOUT)


scheduler = ScanTaskScheduler()
