#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import copy
import os
import re
import subprocess
import sys
import time

from common import XcalLogger
from common.XcalException import XcalException
from scanTaskService.Config import TaskErrorNo, SCAN_RESULT_COMPARATER


class DiffService(object):

    def __init__(self, logger: XcalLogger, diff_file_path: str, ntxt_file_path: str, ltxt_file_path:
                 str, etxt_file_path: str, ftxt_file_path: str, work_path: str, partial_scan: True):
        self.logger = logger
        self.diff_file_path = diff_file_path
        self.ntxt_file_path = ntxt_file_path
        self.ltxt_file_path = ltxt_file_path
        self.etxt_file_path = etxt_file_path
        self.ftxt_file_path = ftxt_file_path
        self.partial_scan = partial_scan
        self.work_path = work_path
        self.src_file_json = work_path + '/source_files.json'
        self.work_dir = work_path + '/scan_result'
        self.xvsa_mtxt = 'scan_result/xvsa-xfa-dummy.mtxt'
        os.chdir(self.work_dir)

    def diff_scan_result(self, baseline_project_path: str = None, current_project_path: str = None):
        mtxt_file_path = os.path.join(self.work_path, self.xvsa_mtxt)
        if not os.path.exists(mtxt_file_path):
            msg = 'execute vtxtreader -merge failed, cannot generate output file: %s' % mtxt_file_path
            self.logger.trace('diff_scan_result', msg)
            raise XcalException('DiffService', 'diff_scan_result', msg, TaskErrorNo.E_SRV_CURRENT_VTXT_NOT_EXISTS)

        line_match_file = None
        if self.diff_file_path is not None and os.path.exists(self.diff_file_path):
            self.logger.trace('diff_scan_result', 'begin to do code map, process vcs diff file')
            new_line_match, line_match_file = code_map(self.diff_file_path)

        self.logger.trace('diff_scan_result', 'begin to do diff')
        params = [SCAN_RESULT_COMPARATER, '-c', mtxt_file_path]

        while True:
            if self.ntxt_file_path is None or not os.path.exists(self.ntxt_file_path):
                break
            if self.ltxt_file_path is None or not os.path.exists(self.ltxt_file_path):
                break
            if self.etxt_file_path is None or not os.path.exists(self.etxt_file_path):
                break
            if self.ftxt_file_path is None or not os.path.exists(self.ftxt_file_path):
                break
            if line_match_file is None or not os.path.exists(line_match_file):
                break

            params.extend(['-n', self.ntxt_file_path])
            params.extend(['-l', self.ltxt_file_path])
            params.extend(['-e', self.etxt_file_path])
            params.extend(['-g', line_match_file])
            if self.partial_scan:
                params.extend(['-p', self.src_file_json])
            if baseline_project_path is not None and current_project_path is not None:
                params.extend(['-b', baseline_project_path])
                params.extend(['-o', current_project_path])
            break

        params.extend(['-d', os.path.join(self.work_path, '.scan_log')])

        self.logger.trace('diff_scan_result', ' '.join(params))
        try:
            st = time.time()
            p = subprocess.run(params, stdout=subprocess.PIPE, stderr = subprocess.PIPE, timeout=600)
            et = time.time()
            self.logger.trace('diff_scan_result', 'execute %s -c time: %f' % (SCAN_RESULT_COMPARATER, et - st))
            output = p.stdout.decode().split('\n')
            if len(output) > 1:
                self.logger.trace('diff_scan_result', output[-2])
        except subprocess.TimeoutExpired as e:
            msg = 'execute %s -c timeout' % SCAN_RESULT_COMPARATER
            self.logger.trace('diff_scan_result', msg)
            raise XcalException('DiffService', 'diff_scan_result', msg, TaskErrorNo.E_SRV_VTXTDIFF_EXEC_TIMEOUT)

        if p.returncode != 0:
            msg = 'execute %s -c failed, exit(%d)' % (SCAN_RESULT_COMPARATER, p.returncode)
            self.logger.trace('diff_scan_result', msg)
            self.logger.trace('diff_scan_result', 'stdout raw message: %s' % p.stdout)
            self.logger.trace('diff_scan_result', 'stderr raw message: %s' % p.stderr)
            raise XcalException('DiffService', 'diff_scan_result', msg, TaskErrorNo.E_SRV_VTXTDIFF_EXEC_FAILED)

        return params


def line_change_check(line_change, symbol, tmp_operation):
    """
    This function is used to get the info of line number change.
    Input is the contents from git diff results. Output is the changed line number info.
    ln_chang: line number changed in one line of modification.
    sln: start line number that which line modified code.
    line_change_list: the list that store the lines that be modified.
    """

    sln = 0
    new_change_line = re.search(b'(\d+),(\d+)', line_change)
    if new_change_line is not None:
        if symbol == "\+":
            sln = int(new_change_line.group(1))
            tmp_operation = "+"
        if symbol == "\-":
            tmp_operation = "-"
            sln = int(new_change_line.group(1))
        ln_change = int(new_change_line.group(2))
    else:
        new_change_line = re.search(b'(\d+)', line_change)
        if symbol == "\+":
            tmp_operation = "+"
            sln = int(new_change_line.group(1))
        if symbol == "\-":
            tmp_operation = "-"
            sln = int(new_change_line.group(1))
        ln_change = 1
    return ln_change, sln, tmp_operation


def line_no_count(content, new_line_match, change_file, count_add,
                  count_reduce, new_line_change, last_change):
    """
    Calculate line number change based on the output from function line_change_check.
    Input is the contents from git diff results. Output is the changed line number info.
    new_change: the number of lines added
    old_change: the number of lines deleted.
    last_change: the last change number. It be used when diff baseline/current v files.
    """
    # This cover code line match , will calculate line number after code modify.
    line_change = re.search(b'@@ (-.*) (\+.*) @@', content)
    if line_change is not None:
        tmp_operation = ''
        new_change, new_sln, tmp_operation = line_change_check(line_change.group(2), '\+', tmp_operation)
        if new_change:
            last_change = tmp_operation + str(new_change)

        old_change, old_sln, tmp_operation = line_change_check(line_change.group(1), '\-', tmp_operation)
        if old_change:
            last_change = tmp_operation + str(old_change)

        # judge add line or delete line and calculate line number
        if new_change > old_change:
            count_add += (int(new_change) - int(old_change))
        if new_change < old_change:
            count_reduce += (int(old_change) - int(new_change))

        # get the line number list that need be ignore when do line number map
        if old_change == 0:
            new_line_change.append(old_sln)
        if old_change > 0:
            for i in range(old_change):
                 new_line_change.append(old_sln + i)

        if count_add > 0 and count_reduce == 0:
            new_line_match['%s' % change_file][old_sln] = '+' + str(count_add)
        if count_add == 0 and count_reduce > 0:
            new_line_match['%s' % change_file][old_sln] = '-' + str(count_reduce)
        if count_add > 0 and count_reduce > 0:
            if count_add > count_reduce:
                new_line_match['%s' % change_file][old_sln] = '+' + str(count_add - count_reduce)
            if count_add < count_reduce:
                new_line_match['%s' % change_file][old_sln] = '-' + str(count_reduce - count_add)
            if count_add == count_reduce:
                new_line_match['%s' % change_file][old_sln] = int(count_add - count_reduce)

        if count_add == count_reduce:
            last_change = '0'
    return new_line_match, new_line_change, count_add, count_reduce, last_change


def line_no_calculate(new_line_match, new_line_change, last_change):
    """
    This function is used to calculate the line number in new_line_match.
    Input is new_line_match and new_line_change, output is new_line_match that be calculated.
    Calculate the lines change in each file that be modified. Pop some useless line number.
    Get lines changed and magic number that specify that last change line.
    """
    for diff_file in new_line_match.keys():
        tmp_list = []
        if len(new_line_match[diff_file]) == 1:
            ln = list(new_line_match[diff_file].keys())
            if isinstance(ln[0], int) and isinstance(new_line_match[diff_file][ln[0]], str):
                new_line_match[diff_file]['magic'] = {'ln_limit': ln[0],
                                                      'last_change': last_change,
                                                      'ln_change': new_line_match[diff_file][ln[0]]}
                new_line_match[diff_file].pop(ln[0])
        if len(new_line_match[diff_file]) > 1:
            for val in new_line_match[diff_file].keys():
                if isinstance(val, int):
                    tmp_list.append(val)
            tmp_list.sort()
            i = 0
            while i < len(tmp_list) - 1:
                if str(new_line_match[diff_file][tmp_list[i]]).find("+") != -1:
                    ln_change = re.sub(r"\+", "", str(new_line_match[diff_file][tmp_list[i]]))
                    for ln in range(tmp_list[i], tmp_list[i + 1]):
                        new_line_match[diff_file][ln] = ln + int(ln_change)
                if str(new_line_match[diff_file][tmp_list[i]]).find("-") != -1:
                    ln_change = re.sub(r"\-", "", str(new_line_match[diff_file][tmp_list[i]]))
                    for ln in range(tmp_list[i], tmp_list[i + 1]):
                        new_line_match[diff_file][ln] = ln - int(ln_change)
                i = i + 1
            ln = tmp_list[len(tmp_list) - 1]
            if isinstance(ln, int) and isinstance(new_line_match[diff_file][ln], str):
                new_line_match[diff_file]['magic'] = {'ln_limit': ln,
                                                      'last_change': last_change,
                                                      'ln_change': new_line_match[diff_file][ln]}
                new_line_match[diff_file].pop(ln)

        # This function is used to pop start line number from line match results .
        for k in new_line_change:
            if k in new_line_match[diff_file].keys():
                if isinstance(new_line_match[diff_file][k], int):
                    new_line_match[diff_file].pop(k)
    return new_line_match


def get_line_change(git_diff_content, new_line_match, add_file_list, reduce_file_list,
                    new_line_change, count_add, count_reduce, last_change):
    """
    This function is used to read git diff results and call related function to calculate.
    Input is git diff results contents and some initialized var/dict/list to store value.
    """
    for line_no, content in enumerate(git_diff_content):
        git_diff_diff = re.search(b'diff --git (.*)', content)
        if git_diff_diff is not None:
            git_diff_reduce = re.search(b'^a/(.*) (.*)', git_diff_diff.group(1))
            git_diff_add = re.search(b'^b/(.*)', git_diff_reduce.group(2))

            # count total line number of diff source file
            # in git diff results, it use "/dev/null" as a mark when add or delete file.
            # Check if delete file in this git push
            git_diff_null = "\/dev\/null"
            if git_diff_reduce is not None:
                git_diff_reduce_file = re.sub(b'^a/', "", git_diff_reduce.group(1))
                if git_diff_null in str(git_diff_reduce.group(1)):
                    new_file = re.sub(b'^b/', "", git_diff_add.group(1))
                    add_file_list.append(new_file)

            # Check if add new file in this git push
            if git_diff_add is not None:
                git_diff_add_file = re.sub(b'^b/', "", git_diff_add.group(1))
                if git_diff_null in str(git_diff_add.group(1)):
                    reduce_file = re.sub(b'^a/', "", git_diff_reduce.group(1))
                    reduce_file_list.append(reduce_file)
            # This cover modify file in this git push
            if git_diff_add_file == git_diff_reduce_file:
                change_file = git_diff_add_file
                if change_file not in new_line_match.keys():
                    change_file = re.sub(r'b\'', "", str(change_file))
                    change_file = re.sub(r'\'', "", str(change_file))
                    new_line_match['%s' % change_file] = {}

        new_line_match, new_line_change, \
        count_add, count_reduce, last_change = line_no_count(content, new_line_match, change_file, count_add,
                                                             count_reduce, new_line_change, last_change)
    if len(new_line_match) > 0:
        new_line_match = line_no_calculate(new_line_match, new_line_change, last_change)
    return new_line_match


def write_line_match_to_file(line_match, filename):
    with open('{0}'.format(filename), 'w') as target_file:
        if len(line_match) >= 1:
            tmp_dict = copy.deepcopy(line_match)
            for file_name in line_match.keys():
                if file_name:
                    tmp_dict['%s' % file_name]['fname'] = str(file_name)
                target_file.write(str(tmp_dict['%s' % file_name]))
                target_file.write('\n')
    file_path = os.path.abspath(filename)
    return file_path


def code_map(git_diff_result):
    """
    This function is used to read git diff results and initialized some value.
    It will slice git diff results, and transfer them to caller.
    Output is new_line_match that include all line number changed, it be used when diff v files.
    """
    try:
        if os.path.exists(git_diff_result):
            with open(git_diff_result, 'rb') as git_diff_file:
                git_diff_read = git_diff_file.readlines()
    except IOError as error:
        print('Read git_diff_results.txt failed, please check this file.')
        sys.exit()

    # slice git diff results file based on file name.
    slice_file_line = []
    for line_no, content in enumerate(git_diff_read):
        git_diff_diff = re.search(b'diff --git (.*)', content)
        if git_diff_diff is not None:
            slice_line = int(line_no) + 1
            slice_file_line.append(slice_line)

    # length of git_diff_results.txt
    new_line_match = {}
    add_file_list = []
    reduce_file_list = []
    new_line_change = []
    count_add = 0
    count_reduce = 0
    last_change = ''

    # This loop be used read git_diff_results.txt and output code_line_match.
    # "tln" is used to count line number change.
    if len(slice_file_line) == 1:
        git_diff_content = git_diff_read[:]
        new_line_match = get_line_change(git_diff_content, new_line_match, add_file_list, reduce_file_list,
                                         new_line_change, count_add, count_reduce, last_change)
    if len(slice_file_line) > 1:
        j = 0
        while j < len(slice_file_line) - 1:
            git_diff_content = git_diff_read[slice_file_line[j]-1:slice_file_line[j+1]-1]
            new_line_match = get_line_change(git_diff_content, new_line_match, add_file_list, reduce_file_list,
                                             new_line_change, count_add, count_reduce, last_change)
            j = j + 1
        else:
            git_diff_content = git_diff_read[slice_file_line[j]-1:]
            new_line_match = get_line_change(git_diff_content, new_line_match, add_file_list, reduce_file_list,
                                             new_line_change, count_add, count_reduce, last_change)
    new_line_match_file_path = write_line_match_to_file(new_line_match, 'git_diff_line_map')

    return new_line_match, new_line_match_file_path


if __name__ == "__main__":
    my_parser = argparse.ArgumentParser(description="Specify code line match file & old/new scan results !!!")
    my_parser.add_argument('-g', action='store', dest='git_diff_result')
    my_parser.add_argument('-n', action='store', dest='ntxt')
    my_parser.add_argument('-l', action='store', dest='ltxt')
    my_parser.add_argument('-e', action='store', dest='etxt')
    my_parser.add_argument('-c', action='store', dest='ctxt')
    my_parser.add_argument('-d', '--debug', dest='debug', action='store_true', help='debug mode')

    give_args = my_parser.parse_args()
    git_diff_result = give_args.git_diff_result
    n_txt = give_args.ntxt
    l_txt = give_args.ltxt
    e_txt = give_args.etxt
    c_txt = give_args.ctxt

    # This function input is git_diff_results.txt
    if git_diff_result:
        # 1. call function to read git_diff_results.txt and output code line match results to code_line_match
        new_line_match, line_match_file = code_map(git_diff_result)
