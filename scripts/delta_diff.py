#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import argparse
import sys
import json
import copy
import re
import hashlib
import time

# This function is used for dealing with Changes to the line number caused by the modification of the source file.
def line_change_check(line_change, symbol, line_change_check, line_change_list):
    if line_change_check is None:
        new_change_line = re.search(r'{0}(\d+)\,(\d+)'.format(symbol), line_change)
        if new_change_line is not None:
            sln = int(new_change_line.group(1))
            ln_change = int(new_change_line.group(2))
            for i in range(ln_change):
                line_change_list.append(sln + i)
        else:
            new_change_line = re.search(r'{0}(\d+)'.format(symbol), line_change)
            if new_change_line is not None:
                sln = int(new_change_line.group(1))
                line_change_list.append(sln)
            ln_change = 1
    else:
        new_change_line = re.search(r'{0}(\d+)\,0'.format(symbol), line_change)
        if new_change_line is not None:
            sln = int(new_change_line.group(1))
        ln_change = 0

    return ln_change, sln, line_change_list

# This function is used for calculate line number change when source code changed based on git diff results.
def line_no_count(content, new_line_match, change_file, count_add,
                  count_reduce, new_line_change, old_line_change):
    # This cover code line match , will calculate line number after code modify.
    line_change = re.search(r'@@ (\-.*) (\+.*) @@', content)
    if line_change is not None:
        new_line_change_check = re.search(r',0', line_change.group(2))
        old_line_change_check = re.search(r',0', line_change.group(1))

        new_change, new_sln, new_line_change = line_change_check(line_change.group(2), '\+',
                                                                 new_line_change_check, new_line_change)
        old_change, old_sln, old_line_change = line_change_check(line_change.group(1), '\-',
                                                                 old_line_change_check, old_line_change)
        # judge add line or delete line and calculate line number
        if new_change > old_change:
            count_add += (int(new_change) - int(old_change))
        if new_change < old_change:
            count_reduce += (int(old_change) - int(new_change))

        if count_add > 0 and count_reduce == 0:
            new_line_match['%s' % change_file][new_sln] = '+' + str(count_add)
        if count_add == 0 and count_reduce > 0:
            new_line_match['%s' % change_file][old_sln] = '-' + str(count_reduce)
        if count_add > 0 and count_reduce > 0:
            if count_add > count_reduce:
                new_line_match['%s' % change_file][new_sln] = '+' + str(count_add - count_reduce)
            if count_add < count_reduce:
                new_line_match['%s' % change_file][old_sln] = '-' + str(count_reduce - count_add)

    return new_line_match, new_line_change, count_add, count_reduce

def line_no_calculate(new_line_match, new_line_change):
    for diff_file in new_line_match.keys():
        tmp_list = []
        if len(new_line_match[diff_file]) > 1:
            for val in new_line_match[diff_file].keys():
                tmp_list.append(val)
            tmp_list.sort()
            i = 0
            while i < len(tmp_list) - 1:
                if new_line_match[diff_file][tmp_list[i]].find("+") != -1:
                    ln_change = re.sub(r"\+", "", new_line_match[diff_file][tmp_list[i]])
                    for ln in range(tmp_list[i], tmp_list[i+1]):
                        new_line_match[diff_file][ln] = ln - int(ln_change)
                else:
                    ln_change = re.sub(r"\-", "", new_line_match[diff_file][tmp_list[i]])
                    for ln in range(tmp_list[i], tmp_list[i + 1]):
                        new_line_match[diff_file][ln] = ln + int(ln_change)
                i = i + 1
        # This line is used pop start line number from line match results .
        for k in new_line_change:
            if k in new_line_match[diff_file].keys():
                if isinstance(new_line_match[diff_file][k], int):
                    new_line_match[diff_file].pop(k)

def get_line_change(git_diff_content, new_line_match, add_file_list, reduce_file_list,
                    new_line_change, old_line_change, count_add, count_reduce):
    for line_no, content in enumerate(git_diff_content):
        git_diff_diff = re.search(r'diff --git (.*)', content)
        if git_diff_diff is not None:
            git_diff_reduce = re.search(r'^a/(.*) (.*)', git_diff_diff.group(1))
            git_diff_add = re.search(r'^b/(.*)', git_diff_reduce.group(2))

            # count total line number of diff source file
            # in git diff results, it use "/dev/null" as a mark when add or delete file.
            # Check if delete file in this git push
            git_diff_null = "\/dev\/null"
            if git_diff_reduce is not None:
                git_diff_reduce_file = re.sub(r'^a/', "", git_diff_reduce.group(1))
                if git_diff_null in git_diff_reduce.group(1):
                    new_file = re.sub(r'^b/', "", git_diff_add.group(1))
                    add_file_list.append(new_file)

            # Check if add new file in this git push
            if git_diff_add is not None:
                git_diff_add_file = re.sub(r'^b/', "", git_diff_add.group(1))
                if git_diff_null in git_diff_add.group(1):
                    reduce_file = re.sub(r'^a/', "", git_diff_reduce.group(1))
                    reduce_file_list.append(reduce_file)
            # This cover modify file in this git push
            if git_diff_add_file == git_diff_reduce_file:
                change_file = git_diff_add_file
                if change_file not in new_line_match.keys():
                    new_line_match['%s' % change_file] = {}

        new_line_match, new_line_change, \
        count_add, count_reduce = line_no_count(content, new_line_match, change_file, count_add,
                                                count_reduce, new_line_change, old_line_change)

    if len(new_line_match) > 0:
        line_no_calculate(new_line_match, new_line_change)
    return new_line_match

# source file and line number match. return a dict of new source code line number map to old source code line number.
# This function just be used in product flow , for inner flow it's not need
def code_map(git_diff_result):
    try:
        if os.path.exists(git_diff_result):
            with open(git_diff_result, 'r') as git_diff_file:
                git_diff_read = git_diff_file.readlines()
    except IOError as error:
        print('Read git_diff_results.txt failed, please check this file.')
        sys.exit()

    #slice git diff results file based on file name.
    slice_file_line = []
    for line_no, content in enumerate(git_diff_read):
        git_diff_diff = re.search(r'diff --git (.*)', content)
        if git_diff_diff is not None:
            slice_line = int(line_no) + 1
            slice_file_line.append(slice_line)

    # length of git_diff_results.txt
    new_line_match = {}
    add_file_list = []
    reduce_file_list = []
    new_line_change = []
    old_line_change = []


    # This loop be used read git_diff_results.txt and output code_line_match.
    # "tln" is used to count line number change.
    if len(slice_file_line) == 1:
        count_add = 0
        count_reduce = 0
        git_diff_content = git_diff_read[:]
        new_line_match = get_line_change(git_diff_read, new_line_match, add_file_list, reduce_file_list,
                                         new_line_change, old_line_change, count_add, count_reduce)
    if len(slice_file_line) > 1:
        j = 0
        while j < len(slice_file_line) - 1:
            count_add = 0
            count_reduce = 0
            git_diff_content = git_diff_read[slice_file_line[j]-1:slice_file_line[j+1]-1]
            new_line_match = get_line_change(git_diff_content, new_line_match, add_file_list, reduce_file_list,
                                             new_line_change, old_line_change, count_add, count_reduce)
            j = j + 1
        else:
            count_add = 0
            count_reduce = 0
            git_diff_content = git_diff_read[slice_file_line[j]-1:]
            new_line_match = get_line_change(git_diff_content, new_line_match, add_file_list, reduce_file_list,
                                             new_line_change, old_line_change, count_add, count_reduce)

    return new_line_match

# This function is used for map fid to file name to avoid fid change in different scan results.
def fid_path_map(v_issues, v_files, checksum_list):
    for issue in v_issues:
        if "fid" in issue.keys():
            for fid_path in v_files:
                if fid_path["fid"] == issue["fid"]:
                    issue["fid"] = fid_path["path"]
                for issue_fid in issue["paths"]:
                    if fid_path["fid"] == issue_fid["fid"]:
                        issue_fid["fid"] = fid_path["path"]
            tmp_hash = hashlib.md5(str(issue).encode('utf-8')).hexdigest()
            checksum_list.append(tmp_hash)

    return v_issues, checksum_list

# This function is used for diff results based on code line match results.
def issue_map_diff(diff_issue, line_match_results):
    tmp_list = copy.deepcopy(diff_issue)
    if 'k' in tmp_list.keys():
        tmp_list.pop('k')

    # judge file whether need be matched , recursive match all sln which need be matched .
    for file_key in line_match_results.keys():
        # This for loop to get the biggest line number and related change line number.
        for k, v in line_match_results[file_key].items():
            if isinstance(k, str):
                ln_limit  = v
                if k.find("+") != -1:
                    ln_change = k.replace('+', '-')
                if k.find("-") != -1:
                    ln_change = k.replace('-', '+')
            if isinstance(v, str):
                ln_limit  = k
                ln_change = v

        if tmp_list["fid"].find(file_key) != -1:
            if tmp_list["sln"] in line_match_results[file_key].keys():
                if isinstance(line_match_results[file_key][tmp_list["sln"]], int):
                    tmp_list["sln"] = line_match_results[file_key][tmp_list["sln"]]
            if str(ln_change).find("+") != -1:
                change = re.sub(r"\+", "", ln_change)
                if tmp_list["sln"] > ln_limit + int(change):
                    tmp_list["sln"] = tmp_list["sln"] - int(change)
            if str(ln_change).find("-") != -1:
                change = re.sub(r"\-", "", ln_change)
                if tmp_list["sln"] > ln_limit:
                    tmp_list["sln"] = tmp_list["sln"] + int(change)

    for diff_path in tmp_list["paths"]:
        for file_key in line_match_results.keys():
            if diff_path["fid"].find(file_key) != -1:
                if diff_path["sln"] in line_match_results[file_key].keys():
                    if isinstance(line_match_results[file_key][diff_path["sln"]], int):
                        diff_path["sln"] = line_match_results[file_key][diff_path["sln"]]
                if str(ln_change).find("+") != -1:
                    change = re.sub(r"\+", "", ln_change)
                    if diff_path["sln"] > ln_limit + int(change):
                        diff_path["sln"] = diff_path["sln"] - int(change)
                if str(ln_change).find("-") != -1:
                    change = re.sub(r"\-", "", ln_change)
                    if diff_path["sln"] > ln_limit:
                        diff_path["sln"] = diff_path["sln"] + int(change)

    return tmp_list

# This function is used for delete "k" and "ic" avoid impact diff flow.
def value_pop(v_issues):
    for old_issue in v_issues:
        if 'k' in old_issue.keys():
            old_issue.pop('k')

# This function is used for write diff results to json format file, to new_issues.v/same_issues.v/fix_issues.v
def v_write(target_name, v_files, results, new_v_rulesets, new_v_v, new_v_id, new_v_s, new_v_m, new_v_eng,
            new_v_ev, new_v_er, new_v_x1, new_v_x2, new_v_ss, new_v_se, new_v_usr, new_v_sys, new_v_rss):
    # revert file name to fid for producing normal .v file
    for issue in results:
        if "fid" in issue.keys():
            for fid_path in v_files:
                if fid_path["path"] == issue["fid"]:
                    issue["fid"] = fid_path["fid"]
                for issue_fid in issue["paths"]:
                    if fid_path["path"] == issue_fid["fid"]:
                        issue_fid["fid"] = fid_path["fid"]

    results_dict = {
        "files": v_files,
        "issues": results,
        "rulesets": new_v_rulesets,
        "v": new_v_v,
        "id": new_v_id,
        "s": new_v_s,
        "m": new_v_m,
        "eng": new_v_eng,
        "ev": new_v_ev,
        "er": new_v_er,
        "x1": new_v_x1,
        "x2": new_v_x2,
        "ss": new_v_ss,
        "se": new_v_se,
        "usr": new_v_usr,
        "sys": new_v_sys,
        "rss": new_v_rss
    }

    json_format = json.dumps(results_dict, indent=1)
    with open('{0}'.format(target_name), 'w') as json_target:
        json_target.write(json_format)

# json results map and diff.
def json_map(old_v, new_v, line_match):
    # old .v json results load as diff baseline
    with open(old_v, "r") as old_v_file:
        old_v_data = json.load(old_v_file)

    old_v_files    = copy.deepcopy(old_v_data["files"])
    old_v_issues   = copy.deepcopy(old_v_data["issues"])

    # new .v json results load as diff baseline and write the data to diff results(three json files.)
    with open(new_v, "r") as new_v_file:
        new_v_data = json.load(new_v_file)

    new_v_files    = copy.deepcopy(new_v_data["files"])
    new_v_issues   = copy.deepcopy(new_v_data["issues"])
    new_v_rulesets = copy.deepcopy(new_v_data["rulesets"])
    new_v_v        = copy.deepcopy(new_v_data["v"])
    new_v_id       = copy.deepcopy(new_v_data["id"])
    new_v_s        = copy.deepcopy(new_v_data["s"])
    new_v_m        = copy.deepcopy(new_v_data["m"])
    new_v_eng      = copy.deepcopy(new_v_data["eng"])
    new_v_ev       = copy.deepcopy(new_v_data["ev"])
    new_v_er       = copy.deepcopy(new_v_data["er"])
    new_v_x1       = copy.deepcopy(new_v_data["x1"])
    new_v_x2       = copy.deepcopy(new_v_data["x2"])
    new_v_ss       = copy.deepcopy(new_v_data["ss"])
    new_v_se       = copy.deepcopy(new_v_data["se"])
    new_v_usr      = copy.deepcopy(new_v_data["usr"])
    new_v_sys      = copy.deepcopy(new_v_data["sys"])
    new_v_rss      = copy.deepcopy(new_v_data["rss"])

    diff_new_issue = []  # This list store the different issues from new results , it will be diff further.
    diff_old_issue = []  # This list store the different issues from old results , it will be diff further.

    #same_result = []  # This list store the same issues, and will be write to same results Json file.
    new_issues  = []  # This list store the add issues, and will be write to different results Json file.
    fix_issues  = []  # This list store the reduce issues, and will be write to different results Json file.

    ### 1. simple json diff, get the same issues.
    ### fid diff will be used add/delete file when commit to git repo.
    # diff new with old, get same & add results.
    # map fid to file name to avoid file name and fid mismatch scenarios.
    # add this fid & file name match can reduce the function that check add_file_list & reduce_file_list.
    new_v_checksum = [] # This list used to store the checksum of each issue from new v file and simple diff
    old_v_checksum = [] # This list used to store the checksum of each issue from old v file and simple diff
    new_v_issues, new_v_checksum = fid_path_map(new_v_issues, new_v_files, new_v_checksum)
    old_v_issues, old_v_checksum = fid_path_map(old_v_issues, old_v_files, old_v_checksum)

    for new_checksum in new_v_checksum:
        if new_checksum not in old_v_checksum:
            diff_new_issue.append(new_v_issues[new_v_checksum.index(new_checksum)])
        #else:
        #    same_result.append(new_v_issues[new_v_checksum.index(new_checksum)])
    for old_checksum in old_v_checksum:
        if old_checksum not in new_v_checksum:
            diff_old_issue.append(old_v_issues[old_v_checksum.index(old_checksum)])

    #same_issues     = copy.deepcopy(same_result)
    diff_new_issues = copy.deepcopy(diff_new_issue)
    diff_old_issues = copy.deepcopy(diff_old_issue)

    # call function to delete "k" and "ic" in v file which will not need in diff flow.
    value_pop(new_v_issues)
    value_pop(old_v_issues)

    ### 2. map resuts and diff them further.
    ### if diff_files is empty, it need not map & diff fid, just need map & diff line number and other 'k,vn,fn' value.
    # diff & map new with old , get the same & add results.
    if len(diff_new_issues) !=0 and len(diff_old_issues) != 0:
        for diff_issue in diff_new_issues:
            tmp_issue = issue_map_diff(diff_issue, line_match)
            #if tmp_issue in old_v_issues:
            #    same_issues.append(diff_issue)
            if tmp_issue not in old_v_issues:
                new_issues.append(diff_issue)

        # diff & map old with new , get the same & reduce results.
        # reverse new_line_match to get the dict of old line number match to new line number results.
        old_line_match = {}
        for f in line_match.keys():
            old_line_match[f] = dict(zip(line_match[f].values(), line_match[f].keys()))
        tmp_dict = {}
        for f in old_line_match.keys():
            for k in old_line_match[f].keys():
                if isinstance(k, str):
                    if k.find("+") != -1:
                        pop_f = f
                        pop_k = k
                        pop_v = old_line_match[f][k]
                        ln_change = k.replace('+', '-')
                        tmp_dict[pop_f] = { 'pop_k': pop_k,
                                            'pop_v': pop_v,
                                            'ln_change': ln_change}
                    if k.find("-") != -1:
                        pop_f = f
                        pop_k = k
                        pop_v = old_line_match[f][k]
                        ln_change = k.replace('-', '+')
                        tmp_dict[pop_f] = { 'pop_k': pop_k,
                                            'pop_v': pop_v,
                                            'ln_change': ln_change}
        if tmp_dict:
            for f in tmp_dict.keys():
                old_line_match[f].pop(tmp_dict[f]['pop_k'])
                old_line_match[f].update({int(tmp_dict[f]['pop_v']): str(tmp_dict[f]['ln_change'])})

        for diff_issue in diff_old_issues:
            tmp_issue = issue_map_diff(diff_issue, old_line_match)
            if tmp_issue not in new_v_issues:
                fix_issues.append(diff_issue)

    if len(diff_new_issues) == 0 and len(diff_old_issues) != 0:
        fix_issues = diff_old_issues

    if len(diff_new_issues) != 0 and len(diff_old_issues) == 0:
        new_issues = diff_new_issues

    ### 3. write the same & diff results to json file.
    #if same_issues:
    #    # revert file name to fid for producing normal .v file
    #    v_write('same_issues.v', new_v_files, same_issues, new_v_rulesets, new_v_v, new_v_id, new_v_s, new_v_m,
    #            new_v_eng, new_v_ev, new_v_er, new_v_x1, new_v_x2, new_v_ss, new_v_se, new_v_usr, new_v_sys,new_v_rss)
    if new_issues:
        # revert file name to fid for producing normal .v file
        v_write('new_issues.v', new_v_files, new_issues, new_v_rulesets, new_v_v, new_v_id, new_v_s, new_v_m,
                new_v_eng,new_v_ev, new_v_er, new_v_x1, new_v_x2, new_v_ss, new_v_se, new_v_usr, new_v_sys, new_v_rss)

    if fix_issues:
        # revert file name to fid for producing normal .v file
        v_write('fix_issues.v', old_v_files, fix_issues, new_v_rulesets, new_v_v, new_v_id, new_v_s, new_v_m,
                new_v_eng, new_v_ev, new_v_er, new_v_x1, new_v_x2, new_v_ss, new_v_se, new_v_usr, new_v_sys, new_v_rss)

if __name__ == "__main__":
    my_parser = argparse.ArgumentParser(description="Specify code line match file & old/new scan results !!!")
    my_parser.add_argument('-g',  action='store', dest='git_diff_result', required=True)
    my_parser.add_argument('-f1', action='store', dest='baseline_v', required=True)
    my_parser.add_argument('-f2', action='store', dest='current_v', required=True)
    my_parser.add_argument('-d', '--debug', dest='debug', action='store_true', help='debug mode')

    give_args = my_parser.parse_args()
    old_v     = give_args.baseline_v
    new_v     = give_args.current_v
    git_diff_result = give_args.git_diff_result

    # This function input is git_diff_results.txt
    if git_diff_result:
        # 1. call function to read git_diff_results.txt and output code line match results to code_line_match
        line_match = code_map(git_diff_result)
        # 2. input code_line_match, baseline,v and previous.v output diff results to add/reduce/same results .v
        json_map(old_v, new_v, line_match)