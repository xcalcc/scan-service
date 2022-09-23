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
import threading
import time
import uuid

import kafka
from kafka import KafkaConsumer, KafkaProducer
from common.XcalLogger import XcalLogger
from common.XcalException import XcalException
from scanTaskService.Config import KAFKA_HOST, KAFKA_DEFAULT_GROUP_ID, KAFKA_PUBLISH_TIMEOUT, \
    TaskErrorNo, KAFKA_POLL_TIMEOUT_MS
from kafka import TopicPartition

from scanTaskService.util.TimeUtility import TimeUtility


class KafkaUtility(object):
    lock = threading.RLock()
    publish_lock = threading.RLock()
    topic_partition_map = {}
    def __init__(self, logger:XcalLogger):
        self.parent_logger = logger

    @staticmethod
    def kafka_receive(topic:str, max_entries:int = 1, consumer:KafkaConsumer = None, parent_logger:XcalLogger = None):
        with XcalLogger("KafkaUtility", "kafka_receive", parent=parent_logger) as log:
            log.debug("Kafka Receiving ... %s" % topic, "Topic : %s" % topic)
            if consumer is None:
                # Add a lock + release to make sure only one thread is
                # creating / removing KafkaConsumer in the list (KafkaUtility.consumers)
                try:
                    KafkaUtility.lock.acquire()
                    consumer = KafkaUtility.get_kafka_consumer(topic)
                finally:
                    KafkaUtility.lock.release()

            all_msgs = []
            # msg_count = 0

            if topic != "scan-engine-runner":
                log.debug("Kafka before polling", 'topic = %s, offset: %s' % (topic, consumer.committed(TopicPartition(topic, 0))))

            start = time.time()
            log.trace("Before Kafka Polling %d" % TimeUtility().get_utc_timestamp(), "")
            msgs = consumer.poll(timeout_ms=KAFKA_POLL_TIMEOUT_MS, max_records=max_entries)
            end = time.time()
            log.trace("After Kafka Polling", "Timestamp = %d, duration = %d" % (TimeUtility().get_utc_timestamp(), (end-start)))

            # Dict, as {TopicPartition: [Message]}
            for k, v in msgs.items():
                for one_msg in v:
                    all_msgs.append(one_msg)
            log.trace('kafka_receive', 'kafka message: %s' % str(all_msgs))

            if topic != "scan-engine-runner":
                log.debug('Kafka received polling result', 'Kafka offset: %s' % consumer.committed(TopicPartition(topic, 0)))

            # finally:
            #     consumer.unsubscribe()
            #     consumer.close(autocommit=False)
            #     consumer = None
        return all_msgs

    @staticmethod
    def kafka_publish(topic:str, data:str):
        try:
            with XcalLogger("KafkaUtility", "kafka_publish") as log:
                KafkaUtility.publish_lock.acquire();
                producer = KafkaProducer(bootstrap_servers=[KAFKA_HOST])
                topic_partitions = sorted(producer.partitions_for(topic))
                log.trace("Kafka publishing ... %s" % topic,
                          "Partitions %s" % (str(topic_partitions)))
                coming_partition_idx = (KafkaUtility.topic_partition_map.get(topic, 0) + 1) % len(topic_partitions)
                KafkaUtility.topic_partition_map[topic] = coming_partition_idx
                coming_partition = topic_partitions[coming_partition_idx]
                log.trace("Kafka publishing ... %s" % topic, "Topic : %s PartitionIdx: %s Partition: %s" % (topic, str(coming_partition_idx), str(coming_partition)))
                future = producer.send(topic, data.encode("UTF-8"), partition=coming_partition)
                record_meta = future.get(timeout=KAFKA_PUBLISH_TIMEOUT)
        except kafka.errors.NoBrokersAvailable as err:
            logging.exception(err)
            raise XcalException("KafkaUtility", "kafka_publish", "Kafka does not work well", TaskErrorNo.E_SRV_KAFKA_FAILED)
        except kafka.errors.KafkaTimeoutError as err:
            logging.exception(err)
            record_meta = {}
        finally:
            KafkaUtility.publish_lock.release();
        return record_meta

    @staticmethod
    def get_kafka_consumer(topic):
        consumer = KafkaConsumer(topic, group_id=KAFKA_DEFAULT_GROUP_ID + "-" + topic,
                                 client_id="scan-service-" + str(uuid.uuid1()),
                                 auto_offset_reset='earliest',
                                 max_poll_interval_ms=86400000,
                                 heartbeat_interval_ms=500,
                                 max_poll_records=1,
                                 bootstrap_servers=[KAFKA_HOST])
        return consumer

    @staticmethod
    def commit(consumer:KafkaConsumer = None):
        if consumer is None:
            logging.error("Try to commit but Consumer is null")
            return
            
        try:
            consumer.commit()  # <--- Report to Kafka Service that we have finished using the message
        except Exception as err:
            logging.exception(err)
            # Exception because nothing we can do about.