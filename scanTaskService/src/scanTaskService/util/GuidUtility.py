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

import time
from threading import Lock

from scanTaskService.Config import INITIAL_TIMESTAMP


class GuidUtility:
    DIGITS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' \
             'abcdefghijklmnopqrstuvwxyz' \
             '0123456789'
    SERVICE_ID_BITS = 0
    SEQUENCE_BITS = 30
    MAX_SERVICE_ID = ~(-1 << SERVICE_ID_BITS)
    SEQUENCE_MASK = ~(-1 << SEQUENCE_BITS)
    SERVICE_ID_OFFSET = SEQUENCE_BITS
    MIN_LENGTH = 5

    def __init__(self, service_id: int, init_ts: int):
        if (service_id > self.MAX_SERVICE_ID) or (service_id < 0):
            raise ValueError('service id cannot be greater than %d or less than 0' % self.MAX_SERVICE_ID)
        self.service_id = service_id
        self.init_ts = init_ts
        self.last_ts = -1
        self.mutex = Lock()

    def next_id(self):
        ts = self.time_gen()
        if ts < self.last_ts:
            raise RuntimeError('clock moved backwards. refusing to generate id for %d seconds' % (self.last_ts - ts))
        self.mutex.acquire()
        if ts == self.last_ts:
            ts = self.til_next_ts(self.last_ts)
        self.last_ts = ts
        self.mutex.release()
        seq = self.service_id << self.SERVICE_ID_OFFSET | ((ts - self.init_ts) & self.SEQUENCE_MASK)
        return self.base62(seq).rjust(self.MIN_LENGTH, self.DIGITS[0])

    @staticmethod
    def time_gen():
        return int(time.time())

    @staticmethod
    def til_next_ts(last_ts: int):
        ts = GuidUtility.time_gen()
        while ts <= last_ts:
            ts = GuidUtility.time_gen()
        return ts

    @staticmethod
    def base62(n: int):
        s = ''
        while n > 0:
            s += GuidUtility.DIGITS[n % 62]
            n //= 62
        return s[::-1]


guid = GuidUtility(0, INITIAL_TIMESTAMP)

if __name__ == '__main__':
    print(guid.next_id())
