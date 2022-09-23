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
from scanTaskService.scanApp import app
from scanTaskService.util.KafkaUtility import KafkaUtility

class TestKafkaUtility(unittest.TestCase):

    def setUp(self):
        logging.getLogger().setLevel(logging.INFO)
        self.app = app.test_client()
        self.logger = XcalLogger("Test_SshUtility", "main")

    def test_kafka_publish_ok(self):
        KafkaUtility.kafka_publish("abc", json.dumps({"a":"bc"}))

    def test_kafka_subcribe_ok(self):
        time.sleep(1)
        a = KafkaUtility.kafka_receive("abc")
        print(a) # Cannot guarantee ACID (I)

    def test_kafka_pub_subcribe_ok(self):
        consumer = KafkaUtility.get_kafka_consumer("abc")
        KafkaUtility.kafka_publish("abc", json.dumps({"a":"b"}))
        time.sleep(3)
        a = KafkaUtility.kafka_receive("abc", 1, consumer)
        print(a)
        ## This is not working TODO:
        self.assertGreater(len(a), 0)

    def test_kafka_poll(self):
        consumer = KafkaUtility.get_kafka_consumer("abc")
        KafkaUtility.kafka_publish("abc", json.dumps({"a":"b"}))
        time.sleep(3)
        lst = consumer.poll(timeout_ms=1000)