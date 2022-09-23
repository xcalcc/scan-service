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


import os
import logging
import hashlib
import traceback


def get_files_size_and_line_number(file_path, file_format):
    """
    return the size and line number of all the files end with file_format in file_path
    :param file_path:
    :param file_format: calculate the file with specific file format
    :return: size and line number of all files with specific file format
    """
    logging.info("[get_file_size_and_line_number] file_path: %s, file_format: %s", file_path, file_format)
    size = 0
    lines = 0
    file_count = 0
    for root, dirs, files in os.walk(file_path):
        for file in files:
            for one_format in file_format:
                if file.endswith(one_format):
                    size += os.path.getsize(os.path.join(root, file))
                    lines += get_file_lines(os.path.join(root, file))
                    file_count += 1
    return size, lines, file_count


def get_file_lines(filename):
    """
    Get number of lines of the file
    :param filename: file path
    :return: the number of lines of the file
    """
    if not os.path.isfile(filename):
        logging.error("[get_file_lines] %s not found", filename)
        return -1

    if not os.access(filename, os.R_OK):
        logging.error("[get_file_lines] %s cannot be read", filename)
        return -1

    i = -1
    with open(filename) as f:
        try:
            for i, l in enumerate(f):
                pass
        except UnicodeDecodeError:
            return -1
    return i + 1


def get_hash_of_dir(directory):
    SHAhash = hashlib.sha1()
    if not os.path.exists(directory):
        return -1

    try:
        for root, dirs, files in os.walk(directory):
            for names in files:
                filepath = os.path.join(root, names)
                if filepath.find(".py") == -1 and filepath.find(".txt") == -1 and filepath.find(".json"):
                  continue

                f1 = None
                try:
                    f1 = open(filepath, 'rb')
                except:
                    # You can't open the file for some reason
                    if f1 is not None:
                        f1.close()
                    continue

                while 1:
                    # Read file in as little chunks
                    buf = f1.read(4096)
                    if not buf: break
                    SHAhash.update(hashlib.sha1(buf).hexdigest().encode("UTF-8"))
                f1.close()

    except:
        # Print the stack traceback
        traceback.print_exc()
        return -2

    return SHAhash.hexdigest()