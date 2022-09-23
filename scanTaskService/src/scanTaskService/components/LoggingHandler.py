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
from logging.handlers import RotatingFileHandler

from common.XcalLogger import XcalLogger
from logstash import TCPLogstashHandler
from scanTaskService.Config import DEFAULT_LOG_LEVEL, SCAN_SERVICE_LOG_PATH, LOGSTASH_HOST, LOGSTASH_PORT


class ContextFilter(logging.Filter):
    """
    This is a filter which removes some noisy logs from kafka utilities.
    """

    def filter(self, record):
        if record.getMessage() is not None:
            if record.getMessage().startswith('Heartbeat failed for group'):
                return False
            elif 'failed: Cancelled: <BrokerConnection' in record.getMessage():
                return False
        return True


def initialize_logging_utilities():
    """
    Initialize the whole logging configuration system used across scan service.
    :return:
    """

    # Set up the logging
    format = '%(asctime)s.%(msecs)3d %(levelname)10s %(process)5d --- [%(threadName)15s] %(module)40s: %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(format = format, datefmt = date_format, level = DEFAULT_LOG_LEVEL)
    logging.addLevelName(XcalLogger.XCAL_TRACE_LEVEL, 'TRACE')

    logger = logging.getLogger()
    if os.getenv('DEFAULT_LOG_LEVEL') is not None:
        env_log_level = os.getenv('DEFAULT_LOG_LEVEL')
        default_log_level = DEFAULT_LOG_LEVEL
        if env_log_level == 'DEBUG':
            default_log_level = logging.DEBUG
        elif env_log_level == 'INFO':
            default_log_level = logging.INFO
        elif env_log_level == 'WARN':
            default_log_level = logging.WARN
        elif env_log_level == 'ERROR':
            default_log_level = logging.ERROR
        elif env_log_level == 'FATAL':
            default_log_level = logging.FATAL
        logger.setLevel(default_log_level)

    if not os.path.exists(os.path.dirname(SCAN_SERVICE_LOG_PATH)):
        os.makedirs(os.path.dirname(SCAN_SERVICE_LOG_PATH))

    # Set up file logger
    fh = RotatingFileHandler(SCAN_SERVICE_LOG_PATH, maxBytes = 50000000, backupCount = 10)
    fh.setFormatter(logging.Formatter(format, date_format))
    logger.addHandler(fh)

    # Set up logstash logger
    lh = TCPLogstashHandler(LOGSTASH_HOST, LOGSTASH_PORT, version = 1)
    logger.addHandler(lh)

    logging.info('log file path: %s' % SCAN_SERVICE_LOG_PATH)


def ban_kafka_loggings():
    """
    Remove the future / consumer fetcher / coordinator logs that makes the log too lengthy.
    :return:
    """
    filter = ContextFilter()
    logging.getLogger('kafka.future').addFilter(filter)
    logging.getLogger('kafka.consumer.fetcher').addFilter(filter)
    logging.getLogger('kafka.coordinator').addFilter(filter)
