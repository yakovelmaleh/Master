import difflib

import git_pull_request

import Data_Analysis.JQL_Queries as JQL
import git
import Utils.DataBase as DB
from jira import JIRA
import datetime
import mysql.connector
import CreateDB
import json
import requests
import time
import requests
from urllib.request import urlopen
import xml.etree.ElementTree as ET
import xmltodict
from xml.etree import ElementTree
from github import Github
import re


def date_of_first_response(issue, name_map):
    issue_data_of_first_response = None
    try:
        flag = False
        issue_data_of_first = getattr(issue.fields, name_map['Date of First Comment'])
        if issue_data_of_first is not None:
            issue_data_of_first_response = create_date_from_string(issue_data_of_first)
        else:
            flag = True
            issue_data_of_first = getattr(issue.fields, name_map['First Response Date'])
            if issue_data_of_first is not None:
                issue_data_of_first_response = create_date_from_string(issue_data_of_first)
    except:
        if not flag:
            try:
                issue_data_of_first = getattr(issue.fields, name_map['First Response Date'])
                if issue_data_of_first is not None:
                    issue_data_of_first_response = create_date_from_string(issue_data_of_first)
            except:
                issue_data_of_first_response = None

    if issue_data_of_first_response == None:
        try:
            comments = issue.fields.comment.comments
            if len(comments) > 0:
                issue_data_of_first_response = create_date_from_string(comments[0].created)
        except:
            issue_data_of_first_response = None

    return issue_data_of_first_response


def get_different_between_string(from_str, to_str):
    if from_str is None:
        from_str = ""
    if to_str is None:
        to_str = ""
    ratio_char = difflib.SequenceMatcher(None, from_str, to_str).ratio()
    ratio_words = difflib.SequenceMatcher(None, from_str.split(), to_str.split()).ratio()

    diff_char_minus = len([(i, li) for i, li in enumerate(difflib.ndiff(from_str, to_str)) if li[0] == '-'])
    diff_char_plus = len([(i, li) for i, li in enumerate(difflib.ndiff(from_str, to_str)) if li[0] == '+'])
    diff_char_all = len([(i, li) for i, li in enumerate(difflib.ndiff(from_str, to_str)) if li[0] != ' '])

    diff_word_minus = len([(i, li) for i, li in enumerate(difflib.ndiff(from_str.split(), to_str.split()))
                           if li[0] == '-'])
    diff_word_plus = len([(i, li) for i, li in enumerate(difflib.ndiff(from_str.split(), to_str.split()))
                          if li[0] == '+'])
    diff_word_all = len([(i, li) for i, li in enumerate(difflib.ndiff(from_str.split(), to_str.split()))
                         if li[0] != ' '])

    return ratio_char, ratio_words, diff_char_minus, diff_char_plus, \
        diff_char_all, diff_word_minus, diff_word_plus, diff_word_all


def get_changes_issue(mydb, sql_all_changes, sql_changes_summary, sql_changes_description, sql_changes_story_points,
                      sql_changes_sprints, sql_changes_acceptance_criteria, issue_change, issue_key, project_key,
                      time_created_issue, summary_last,
                      description_last, acceptance_last, query, auth_jira):
    ''' the function get the issue and returns 4 lists of all types of his change, while each is a dict type
    with headlines of author, created, from string, to string, and in the dict of all changes also field.
    param: issue_change: the issue
    return: 4 lists, of 4 types of changes in issue- all, story point, summary, description
    '''
    try:
        histories = issue_change.changelog.histories
    except Exception as e:
        issue_change = auth_jira.search_issues(query + f" AND issuekey = {issue_key}", expand='changelog')[0]
        histories = issue_change.changelog.histories
    lst_all_changes = []
    lst_changes_summary = []
    lst_changes_description = []
    lst_changes_acceptance_criteria = []
    lst_changes_story_points = []
    lst_changes_sprints = []
    num_changes = 0
    num_changes_summary = 0
    num_changes_description = 0
    num_changes_acceptance_criteria = 0
    num_changes_story_point = 0
    num_changes_sprint = 0
    count_changes = 0
    count_changes_summary = 0
    count_changes_description = 0
    count_changes_acceptance_criteria = 0
    count_changes_story_point = 0
    count_changes_sprint = 0
    if len(histories) != 0:
        for i in range(0, len(histories)):
            for j in range(0, len(histories[i].items)):

                if histories[i].items[j].fromString is None:
                    is_first_setup = 1
                else:
                    num_changes += 1
                    is_first_setup = 0
                count_changes += 1

                created = create_date_from_string(histories[i].created)
                from_string = histories[i].items[j].fromString
                to_string = histories[i].items[j].toString
                field = histories[i].items[j].field
                different_dates = created - time_created_issue
                different_dates_in_hours = different_dates.total_seconds() / 3600

                if different_dates_in_hours < 1:
                    if_change_first_hour = 1
                else:
                    if_change_first_hour = 0
                try:
                    author = histories[i].author.displayName
                except AttributeError:
                    try:
                        author = str(histories[i].author)
                    except AttributeError:
                        author = None
                lst_all_changes.append((issue_key, project_key, author, created, from_string, to_string, field,
                                        if_change_first_hour, different_dates_in_hours, is_first_setup, count_changes))
                if field == 'Story Points':
                    count_changes_story_point += 1
                    if is_first_setup == 0:
                        num_changes_story_point += 1
                    lst_changes_story_points.append((issue_key, project_key, author, created, from_string, to_string,
                                                     if_change_first_hour, different_dates_in_hours, is_first_setup,
                                                     count_changes_story_point))
                if field == 'summary':
                    count_changes_summary += 1
                    if is_first_setup == 0:
                        num_changes_summary += 1

                    ratio_char_next, ratio_words_next, diff_char_minus_next, diff_char_plus_next, \
                        diff_char_all_next, diff_word_minus_next, diff_word_plus_next, \
                        diff_word_all_next = get_different_between_string(from_string, to_string)
                    ratio_char_last, ratio_words_last, diff_char_minus_last, \
                        diff_char_plus_last, diff_char_all_last, diff_word_minus_last, diff_word_plus_last, \
                        diff_word_all_last = get_different_between_string(from_string, summary_last)
                    if diff_char_all_last < 10:
                        is_diff_more_than_ten = 0
                    else:
                        is_diff_more_than_ten = 1

                    lst_changes_summary.append((issue_key, project_key, author, created, from_string, to_string,
                                                if_change_first_hour, different_dates_in_hours, is_first_setup,
                                                is_diff_more_than_ten, count_changes_summary, ratio_char_next,
                                                ratio_words_next, diff_char_minus_next, diff_char_plus_next,
                                                diff_char_all_next, diff_word_minus_next, diff_word_plus_next,
                                                diff_word_all_next, ratio_char_last, ratio_words_last,
                                                diff_char_minus_last, diff_char_plus_last, diff_char_all_last,
                                                diff_word_minus_last, diff_word_plus_last, diff_word_all_last))
                if field == 'description':
                    count_changes_description += 1
                    if is_first_setup == 0:
                        num_changes_description += 1

                    ratio_char_next, ratio_words_next, diff_char_minus_next, \
                        diff_char_plus_next, diff_char_all_next, diff_word_minus_next, diff_word_plus_next, \
                        diff_word_all_next = get_different_between_string(from_string, to_string)
                    ratio_char_last, ratio_words_last, diff_char_minus_last, diff_char_plus_last, \
                        diff_char_all_last, diff_word_minus_last, diff_word_plus_last, \
                        diff_word_all_last = get_different_between_string(from_string, description_last)

                    if diff_char_all_last < 10:
                        is_diff_more_than_ten = 0
                    else:
                        is_diff_more_than_ten = 1

                    lst_changes_description.append((issue_key, project_key, author, created, from_string, to_string,
                                                    if_change_first_hour, different_dates_in_hours, is_first_setup,
                                                    is_diff_more_than_ten, count_changes_description, ratio_char_next,
                                                    ratio_words_next, diff_char_minus_next, diff_char_plus_next,
                                                    diff_char_all_next, diff_word_minus_next, diff_word_plus_next,
                                                    diff_word_all_next, ratio_char_last, ratio_words_last,
                                                    diff_char_minus_last, diff_char_plus_last, diff_char_all_last,
                                                    diff_word_minus_last, diff_word_plus_last, diff_word_all_last))

                if field == 'Acceptance Criteria':
                    count_changes_acceptance_criteria += 1
                    if is_first_setup == 0:
                        num_changes_acceptance_criteria += 1

                    ratio_char_next, ratio_words_next, diff_char_minus_next, diff_char_plus_next, diff_char_all_next, \
                        diff_word_minus_next, diff_word_plus_next, \
                        diff_word_all_next = get_different_between_string(from_string, to_string)
                    ratio_char_last, ratio_words_last, diff_char_minus_last, diff_char_plus_last, diff_char_all_last, \
                        diff_word_minus_last, diff_word_plus_last, \
                        diff_word_all_last = get_different_between_string(from_string, acceptance_last)

                    if diff_char_all_last < 10:
                        is_diff_more_than_ten = 0
                    else:
                        is_diff_more_than_ten = 1

                    lst_changes_acceptance_criteria.append((issue_key, project_key, author, created, from_string,
                                                            to_string, if_change_first_hour, different_dates_in_hours,
                                                            is_first_setup, is_diff_more_than_ten,
                                                            count_changes_acceptance_criteria, ratio_char_next,
                                                            ratio_words_next, diff_char_minus_next, diff_char_plus_next,
                                                            diff_char_all_next, diff_word_minus_next,
                                                            diff_word_plus_next, diff_word_all_next, ratio_char_last,
                                                            ratio_words_last, diff_char_minus_last, diff_char_plus_last,
                                                            diff_char_all_last, diff_word_minus_last,
                                                            diff_word_plus_last, diff_word_all_last))

                if field == 'Sprint':
                    count_changes_sprint += 1
                    if is_first_setup == 0:
                        num_changes_sprint += 1
                    lst_changes_sprints.append((issue_key, project_key, author, created, from_string, to_string,
                                                if_change_first_hour, different_dates_in_hours, is_first_setup,
                                                count_changes_sprint))

    if len(lst_all_changes) != 0:
        commit_list_of_queries(mydb, sql_all_changes, lst_all_changes)

    if len(lst_changes_summary) != 0:
        commit_list_of_queries(mydb, sql_changes_summary, lst_changes_summary)

    if len(lst_changes_description) != 0:
        commit_list_of_queries(mydb, sql_changes_description, lst_changes_description)

    if len(lst_changes_acceptance_criteria) != 0:
        commit_list_of_queries(mydb, sql_changes_acceptance_criteria, lst_changes_acceptance_criteria)

    if len(lst_changes_story_points) != 0:
        commit_list_of_queries(mydb, sql_changes_story_points, lst_changes_story_points)

    if len(lst_changes_sprints) != 0:
        commit_list_of_queries(mydb, sql_changes_sprints, lst_changes_sprints)

    return num_changes, num_changes_summary, num_changes_description, num_changes_acceptance_criteria, \
        num_changes_story_point, num_changes_sprint


def get_num_from_commit_summary(commit_text, issue_key):
    s = commit_text.lower().replace(":", "").replace("#", ""). \
        replace("/", " ").replace("_", " ").replace(".", "").replace("'", "").replace(",", "").split()
    if issue_key in s:
        return 1
    return 0


def countChange(files, wordToCount):
    count = 0
    for file in files:
        count += file[wordToCount]
    return count


def commits_and_issues(url, issue_key, project_key, mydb, sql_commits):
    count = 0
    if url is not None:
        try:
            time.sleep(3)
            issue_key = issue_key.lower()
            lst_commits_info = []
            url = str(url).replace("/pull/", "/pulls/").replace("https://github.com/", "https://api.github.com/repos/")
            commits = requests.get(url + '/commits').json()
            for git_commit in commits:
                commit = requests.get(url[:url.find('/pulls/')]+'/commits/' + git_commit['sha']).json()
                message = git_commit["commit"]["message"]
                insertion = countChange(commit['files'], 'additions')
                deletions = countChange(commit['files'], 'deletions')
                changeLines = countChange(commit['files'], 'changes')
                totalFiles = len(commit['files'])

                lst_commits_info.append((
                    issue_key, project_key, git_commit["commit"]["author"]["name"], insertion,
                    deletions, changeLines, totalFiles, message, git_commit['sha'], count))
                count += 1

            if len(lst_commits_info) != 0:
                commit_list_of_queries(mydb, sql_commits, lst_commits_info)
        except Exception as e:
            print(e)
    return count


"""
def commits_and_issues(mydb, sql_commits, repo, issue_commit, issue_key1, project_key):
    # repo = git.Git('../Repos').clone('https://github.com/apache/usergrid.git')
    # repo = git.Repo("https://github.com/apache/usergrid.git")

    issue_key = issue_commit.key.lower()
    count = 1
    lst_commits_info = []

    for git_commit in repo.iter_commits():
        return_if_word_found_in_commit = get_num_from_commit_summary(git_commit.summary, issue_key)
        if return_if_word_found_in_commit != 0:
            lst_commits_info.append((
                issue_key1, project_key, git_commit.author.name, git_commit.stats.total['insertions'],
                git_commit.stats.total['deletions'], git_commit.stats.total['lines'], git_commit.stats.total['files'],
                git_commit.summary, git_commit.message, git_commit.hexsha, count))
            count += 1

    if len(lst_commits_info) != 0:
        commit_list_of_queries(mydb, sql_commits, lst_commits_info)

    return count
"""


def get_issue_priority(project_name, issue, name_map):
    issue_priority = ""
    try:
        issue_priority = getattr(issue.fields, name_map['Class of work']).value
    except:
        try:
            issue_priority = getattr(issue.fields, name_map['Priority Level'])
        except:
            try:
                issue_priority = getattr(issue.fields, name_map['Priority Level'])
            except:
                try:
                    issue_priority = str(issue.fields.priority)
                except:
                    try:
                        issue_priority = getattr(issue.fields, name_map['Priority'])
                    except:
                        return ''
    return str(issue_priority)


def get_issue_story_points(issue, name_map):
    try:
        story_points = getattr(issue.fields, name_map['Story Points'])
    except:
        story_points = None
    return story_points


def get_issue_acceptance_cri(issue, name_map):
    try:
        issue_acceptance_cri = getattr(issue.fields, name_map['Acceptance Criteria'])
    except:
        issue_acceptance_cri = None

    return issue_acceptance_cri


def commit_list_of_queries(mysql_con, query, values):
    cursor = mysql_con.cursor()
    try:
        cursor.executemany(query, values)
        mysql_con.commit()
        cursor.close()
    except mysql.connector.IntegrityError:
        print("ERROR: Kumquat already exists!")


def create_date_from_string(date):
    return datetime.datetime.strptime(date[:-5], '%Y-%m-%dT%H:%M:%S.%f')


def get_image(issue):
    try:
        images = issue.fields.thumbnail
        if images is not None:
            is_image = 1
        else:
            is_image = 0
    except:
        try:
            images = 0
            a = issue.key
            image_options = issue.fields.attachment
            for file in image_options:
                if file.mimeType.find('image') != -1:
                    images += 1
            is_image = images > 0
        except:
            images = None
            is_image = 0
    return images, is_image


def get_attachment(mysql_con, sql_attachment, issue):
    try:
        num_of_attachments = 0
        is_attachments = 0
        attachments = issue.fields.attachment
        if attachments is not None and len(attachments) > 0:
            upload_queries = []
            num_of_attachments = len(attachments)
            is_attachments = 1

            for attachment in attachments:
                upload_queries.append((issue.key, issue.fields.project.key, int(attachment.id), attachment.mimeType,
                                       attachment.author.displayName, create_date_from_string(attachment.created)))
            commit_list_of_queries(mysql_con, sql_attachment, upload_queries)

        else:
            is_attachments = 0

    except Exception as e:
        print(e)

    return num_of_attachments, is_attachments


def get_team(issue, name_map):
    try:
        team = getattr(issue.fields, name_map['Team'])
    except:
        team = None
    return team


def get_First_PR_From_List(auth_jira, issueKey):
    remoteLinks = auth_jira.remote_links(issueKey)
    for link in remoteLinks:
        check_git_link = link.globalId.split("github=")
        if len(check_git_link) > 0:
            return check_git_link[1]
    return None


def get_issue_pull_request_url(issue, name_map, auth_jira, issueKey, query):
    try:
        pull_request_url = getattr(issue.fields, name_map['Pull Request URL'])
    except:
        try:
            pull_request_url = getattr(issue.fields, name_map['External issue URL'])
        except:
            pull_request_url = None

    if pull_request_url is None:
        try:
            pull_request_url = get_First_PR_From_List(auth_jira, issueKey)
        except:
            try:
                issueKey = auth_jira.search_issues(f"{query} AND issuekey = {issueKey}", expand='changelog')[0].key
                pull_request_url = get_First_PR_From_List(auth_jira, issueKey)
            except:
                return get_PR_URL_From_comments(issue, auth_jira)
    if pull_request_url is None:
        return get_PR_URL_From_comments(issue, auth_jira)


def get_PR_URL_From_comments(issue, auth_jira):
    comments = auth_jira.comments(issue.id)
    for comment in comments:
        try:
            url = re.search("(?P<url>https?://[^\s]+)", comment.body).group("url")
            if url is not None and url.find("pull")!= -1 and url.find("https://github.com/") != -1:
                if url[len(url)-1] == ']':
                    url =  url[:-1]
                if url.find('|') != -1:
                    url = url[:url.find('|')]
                return url
        except Exception as e:
            ""
    return None


def get_issue_fix_versions(mydb, sql_fix_versions, issue, issue_key, project_key):
    try:
        fix_versions = issue.fields.fixVersions
    except:
        fix_versions = []
    num_fix_versions = len(fix_versions)
    lst_fix_versions = []

    for i in range(0, num_fix_versions):
        lst_fix_versions.append((issue_key, project_key, fix_versions[i].name, i + 1))

    if len(lst_fix_versions) != 0:
        commit_list_of_queries(mydb, sql_fix_versions, lst_fix_versions)

    return num_fix_versions


def get_issue_versions(mydb, sql_versions, issue, issue_key, project_key):
    lst_versions = []
    try:
        version = issue.fields.versions
    except:
        version = []
    num_versions = len(version)

    for i in range(0, num_versions):
        lst_versions.append((issue_key, project_key, version[i].name, i + 1))

    if len(lst_versions) != 0:
        commit_list_of_queries(mydb, sql_versions, lst_versions)

    return num_versions


def get_issue_labels(mydb, sql_labels, issue, issue_key, project_key):
    labels = issue.fields.labels
    num_labels = len(labels)
    lst_labels = []

    for i in range(0, num_labels):
        lst_labels.append((issue_key, project_key, labels[i], i + 1))

    if len(lst_labels) != 0:
        commit_list_of_queries(mydb, sql_labels, lst_labels)

    return num_labels


def get_issue_components(mydb, sql_components, issue, issue_key, project_key):
    components = issue.fields.components
    num_components = len(components)
    lst_components = []

    for i in range(0, num_components):
        lst_components.append((issue_key, project_key, components[i].name, i + 1))

    if len(lst_components) != 0:
        commit_list_of_queries(mydb, sql_components, lst_components)

    return num_components


def get_issue_link_bug_name(mydb, sql_names_bugs_issue_links, issue_l, issue_key, project_key):
    """the function return the issue links names of issues link from type bug.
        param: issue_l: issue
        return: lst_issue_links_bugs, list of names of issues link from type bug.
    """
    issue_links = issue_l.fields.issuelinks
    num_issue_links_bugs = 0
    lst_issue_links_bugs = []

    for i in range(0, len(issue_links)):
        try:
            lst_issue_links_bugs1 = issue_links[i].inwardIssue.fields.issuetype.name
            if lst_issue_links_bugs1 == 'Bug':
                num_issue_links_bugs += 1
                lst_issue_links_bugs.append((issue_key, project_key, issue_links[i].inwardIssue.key, i + 1))

        except:
            lst_issue_links_bugs1 = issue_links[i].outwardIssue.fields.issuetype.name
            if lst_issue_links_bugs1 == 'Bug':
                num_issue_links_bugs += 1
                lst_issue_links_bugs.append((issue_key, project_key, issue_links[i].outwardIssue.key, i + 1))

    if len(lst_issue_links_bugs) != 0:
        commit_list_of_queries(mydb, sql_names_bugs_issue_links, lst_issue_links_bugs)

    return num_issue_links_bugs


def get_issue_links_info(mydb, sql_issue_links, issue_l, issue_key, project_key):
    """the function return the issue links information - names of issues link, names of issue links
    type bus, number of issue links and number of issue links type bug.
    param: issue_l: issue
    return: issue_link_info,
    """
    issue_links = issue_l.fields.issuelinks
    num_issue_links = len(issue_links)
    lst_issue_links = []

    for i in range(0, num_issue_links):
        try:
            lst_issue_links.append((issue_key, project_key, issue_l.fields.issuelinks[i].inwardIssue.key,
                                    issue_l.fields.issuelinks[i].raw['type']['inward'], i + 1))
        except:
            lst_issue_links.append((issue_key, project_key, issue_l.fields.issuelinks[i].outwardIssue.key,
                                    issue_l.fields.issuelinks[i].raw['type']['outward'], i + 1))

    if len(lst_issue_links) != 0:
        commit_list_of_queries(mydb, sql_issue_links, lst_issue_links)

    return num_issue_links


def get_sub_tasks_info(mydb, sql_sab_task_names, issue_sub, issue_key, project_key):
    """ return the sub tasks information of an issue
    param: issue_sub: issue key
    return: sub_task_info, list of names of the sub tasks issue, and number of sub tasks
    """
    sub_tasks = issue_sub.fields.subtasks
    lst_sub_tasks_names = []
    if len(sub_tasks) != 0:
        num_sub_tasks = len(sub_tasks)
        for i in range(0, num_sub_tasks):
            lst_sub_tasks_names.append((issue_key, project_key, sub_tasks[i].key, i + 1))
    else:
        num_sub_tasks = 0
        return num_sub_tasks

    if len(lst_sub_tasks_names) != 0:
        commit_list_of_queries(mydb, sql_sab_task_names, lst_sub_tasks_names)

    return num_sub_tasks


def get_comments_info(mydb, sql_comments, issue_comment, auth_jira_comment, issue_key, project_key):
    """the function return the issue comments information
        param: issue_comment: issue,  auth_jira_work: auth jira_comment
        return: lst_comments_info, dictionary
    """
    lst_comments_info = []
    comments = auth_jira_comment.comments(issue_comment.id)
    num_comments = len(comments)
    for i in range(0, num_comments):
        created = create_date_from_string(comments[i].created)

        lst_comments_info.append(
            (issue_key, project_key, comments[i].author.displayName, comments[i].id, created,
             comments[i].body, i + 1))

    if len(lst_comments_info) != 0:
        commit_list_of_queries(mydb, sql_comments, lst_comments_info)

    return num_comments


def get_sprint_info(mydb, sql_sprints, issue_s, name_map, issue_key, project_key):
    """
    the function return and save the issue sprint information
        param: issue_s: issue,  name_map: name of all fields
        return: sprint_info, list 3 lists - names of sprints, start dates of sprints, end dates of sprints, and num of
        sprints.
    """
    sprint = getattr(issue_s.fields, name_map['Sprint'])
    sprints = []
    if sprint is not None:
        for i in range(0, len(sprint)):
            try:
                start_date1 = sprint[i].split("startDate=", 1)[1][:10]
                end_date1 = sprint[i].split("endDate=", 1)[1][:10]
            except Exception as e:
                start_date1 = sprint[i].startDate[:10]
                end_date1 = sprint[i].endDate[:10]
            is_over = 1
            if end_date1[1] == 'n':
                start_date = None
                end_date = None
                is_over = 0
            else:
                start_date = datetime.datetime.strptime(start_date1, '%Y-%m-%d')
                end_date = datetime.datetime.strptime(end_date1, '%Y-%m-%d')
            try:
                sprints.append((issue_key, project_key, sprint[i].split("name=")[1].split(",", 1)[0], start_date, end_date,
                                is_over, i + 1))
            except:
                sprints.append((issue_key, project_key, sprint[i].name, start_date, end_date,
                                is_over, i + 1))
        num_sprints = len(sprint)
    else:
        num_sprints = 0

    if len(sprints) != 0:
        commit_list_of_queries(mydb, sql_sprints, sprints)

    return num_sprints


def getFromDictOrDefault(issue, name_map, key, default):
    try:
        output = default()
    except:
        output = None
    if output is not None:
        return output
    try:
        return getattr(issue.fields, name_map[key])
    except Exception as e:
        return None


def startSetUp(jira_name, jira_obj):
    # connect to SQL && Create a cursor
    dbName = f"{DB.DB_NAME}_{jira_name.lower()}"
    mysql_con = DB.connectToSpecificDB(dbName)

    #delete Attachment
    cursor = mysql_con.cursor()
    #cursor.execute(f"SELECT * FROM {DB.DB_NAME}_{jira_name.lower()}.tables WHERE table_name = 'attachment_os'")
    #result = cursor.fetchall()
    CreateDB.createAttachmentWithoutDrop(mysql_con)
    print(f'connected to DB: {DB.DB_NAME}_{jira_name.lower()}')

    # Enforce UTF-8 for the connection
    cursor.execute('SET NAMES utf8mb4')
    cursor.execute("SET CHARACTER SET utf8mb4")
    cursor.execute("SET character_set_connection=utf8mb4")

    # the SQL queries to enter the data to the tables in sql
    sql_comments = """INSERT INTO comments_os (issue_key, project_key, author, id, created, body, 
                                                 chronological_number) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
    sql_commits = """INSERT INTO commits_info_os (issue_key, project_key, author, insertions, code_deletions, code_lines, files,
                      message, commit, chronological_number) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    sql_sprints = """INSERT INTO sprints_os (issue_key, project_key, sprint_name, start_date, end_date, is_over, 
                       chronological_number) VALUES (%s, %s, %s, %s, %s, %s, %s)"""
    sql_sab_task_names = """INSERT INTO sab_task_names_os (issue_key, project_key, sub_task_name, 
                              chronological_number) VALUES (%s, %s, %s, %s)"""
    sql_versions = """INSERT INTO versions_os (issue_key, project_key, version, 
                        chronological_number) VALUES (%s, %s, %s, %s)"""
    sql_issue_links = """INSERT INTO issue_links_os (issue_key, project_key, issue_link, issue_link_name_relation,
                           chronological_number) VALUES (%s, %s, %s, %s, %s)"""
    sql_names_bugs_issue_links = """INSERT INTO names_bugs_issue_links_os (issue_key, project_key, bug_issue_link, 
                                      chronological_number) VALUES (%s, %s, %s, %s)"""
    sql_fix_versions = """INSERT INTO fix_versions_os (issue_key, project_key, fix_version, 
                            chronological_number) VALUES (%s, %s, %s, %s)"""
    sql_labels = """INSERT INTO labels_os (issue_key, project_key, label, 
                      chronological_number) VALUES (%s, %s, %s, %s)"""
    sql_attachment = """INSERT INTO attachment_os (issue_key, project_key, attachment_id, file_type,creator,created) VALUES (
    %s, %s, %s, %s, %s, %s) """
    sql_components = """INSERT INTO components_os (issue_key, project_key, component, 
                          chronological_order) VALUES (%s, %s, %s, %s)"""
    sql_all_changes = """INSERT INTO all_changes_os (issue_key, project_key, author, created, from_string, to_string,
                           field, if_change_first_hour, different_time_from_creat, is_first_setup,
                           chronological_number) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    sql_changes_description = """INSERT INTO changes_description_os (issue_key, project_key, author, created, from_string,
                                   to_string, if_change_first_hour, different_time_from_creat, is_first_setup,
                                   is_diff_more_than_ten, chronological_number, ratio_different_char_next, 
                                   ratio_different_word_next, num_different_char_minus_next, num_different_char_plus_next,
                                   num_different_char_all_next, num_different_word_minus_next, 
                                   num_different_word_plus_next, num_different_word_all_next, ratio_different_char_last,
                                   ratio_different_word_last, num_different_char_minus_last, num_different_char_plus_last,
                                   num_different_char_all_last, num_different_word_minus_last, 
                                   num_different_word_plus_last, num_different_word_all_last) VALUES (%s, %s, %s, %s, %s, 
                                   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                                   %s, %s)"""
    sql_changes_summary = """INSERT INTO changes_summary_os (issue_key, project_key, author, created, from_string,
                                   to_string, if_change_first_hour, different_time_from_creat, is_first_setup,
                                   is_diff_more_than_ten, chronological_number, ratio_different_char_next, 
                                   ratio_different_word_next, num_different_char_minus_next, num_different_char_plus_next,
                                   num_different_char_all_next, num_different_word_minus_next, 
                                   num_different_word_plus_next, num_different_word_all_next, ratio_different_char_last,
                                   ratio_different_word_last, num_different_char_minus_last, num_different_char_plus_last,
                                   num_different_char_all_last, num_different_word_minus_last, 
                                   num_different_word_plus_last, num_different_word_all_last) VALUES (%s, %s, %s, %s, %s, 
                                   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                                   %s, %s)"""
    sql_changes_story_points = """INSERT INTO changes_story_points_os (issue_key, project_key, author, created, 
                                    from_string, to_string, if_change_first_hour, different_time_from_creat, 
                                    is_first_setup, chronological_number) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    sql_changes_sprint = """INSERT INTO changes_sprint_os (issue_key, project_key, author, created, 
                              from_string, to_string, if_change_first_hour, different_time_from_creat, 
                              is_first_setup, chronological_number) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    sql_changes_acceptance_criteria = """INSERT INTO changes_criteria_os (issue_key, project_key, author, created, from_string,
                                   to_string, if_change_first_hour, different_time_from_creat, is_first_setup,
                                   is_diff_more_than_ten, chronological_number, ratio_different_char_next, 
                                   ratio_different_word_next, num_different_char_minus_next, num_different_char_plus_next,
                                   num_different_char_all_next, num_different_word_minus_next, 
                                   num_different_word_plus_next, num_different_word_all_next, ratio_different_char_last,
                                   ratio_different_word_last, num_different_char_minus_last, num_different_char_plus_last,
                                   num_different_char_all_last, num_different_word_minus_last, 
                                   num_different_word_plus_last, num_different_word_all_last) VALUES (%s, %s, %s, %s, %s, 
                                   %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                                   %s, %s)"""
    sql_main_table = """INSERT INTO main_table_os (issue_key, issue_id, project_key, created, creator, reporter, 
                          assignee, date_of_first_response, epic_link, issue_type, last_updated, priority,    
                          prograss, prograss_total, resolution, resolution_date, status_name, status_description, 
                          time_estimate, time_origion_estimate, time_spent, attachment, is_attachment, pull_request_url,
                          images, is_images, team, story_point, summary, description, acceptance_criteria,
                          num_all_changes, num_bugs_issue_link, num_changes_summary, num_changes_description, 
                          num_changes_acceptance_criteria, num_changes_story_point, num_comments, num_issue_links, 
                          num_of_commits, num_sprints, num_sub_tasks, num_watchers, 
                          num_worklog, num_versions, num_fix_versions, num_labels, num_components) 
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                          %s, %s, %s, %s, %s)"""

    # run for all the 5 projects:
    auth_jira = JIRA(jira_obj['jira_url'])
    all_fields = auth_jira.fields()
    name_map = {field['name']: field['id'] for field in all_fields}

    flag = True
    MongoDB_issue_num = 0
    for project_name in auth_jira.projects():
        size = 100
        initial = 0
        while True:
            start = initial * size
            changelogFlag = True
            try:
                query = f"project={project_name} AND {JQL.filter_by_resolution(jira_name)}" \
                            f" AND {JQL.filter_by_status(jira_name)} AND {JQL.filter_by_noBugs()} " \
                            f" AND {JQL.filter_by_resolutionDate()} AND " \
                            f"{JQL.filter_by_NotEmptySprint()}"
                issues = auth_jira.search_issues(query, start, size, expand='changelog')
            except:
                try:
                    issues = auth_jira.search_issues(query, start, size)
                    changelogFlag = False
                except:
                    query = f"project='{project_name}' AND {JQL.filter_by_resolution(jira_name)}" \
                            f" AND {JQL.filter_by_status(jira_name)} AND {JQL.filter_by_noBugs()} " \
                            f" AND {JQL.filter_by_resolutionDate()} AND " \
                            f"{JQL.filter_by_NotEmptySprint()}"
                    try:
                        issues = auth_jira.search_issues(query, start, size, expand='changelog')
                        changelogFlag = True
                    except:
                        issues = auth_jira.search_issues(query, start, size)
                        changelogFlag = False
            print(f"query: {query} \n From {start} \n include changelog: {changelogFlag}")

            if len(issues) == 0:
                break
            initial += 1

            """
            *************** run over all issues****************
            for each issue, extract all the data fields from the net into the sql tables, some by using the fucntion in the start
            """
            if flag and MongoDB_issue_num < 16000:
                MongoDB_issue_num += len(issues)
                continue

            flag = False
            for issue in issues:
                try:
                    time.sleep(1)

                    issue_type = issue.fields.issuetype.name
                    issue_key = issue.key
                    issue_id = issue.id
                    resolution = str(issue.fields.resolution)
                    status_name = issue.fields.status.name

                    num_worklog = getNumberOfWorkLog(issue, auth_jira)
                    project_key = issue.fields.project.key
                    updated = create_date_from_string(issue.fields.updated)
                    resolution_date = create_date_from_string(issue.fields.resolutiondate) \
                        if issue.fields.resolutiondate is not None else None
                    created = create_date_from_string(issue.fields.created)
                    summary = issue.fields.summary
                    description = issue.fields.description
                    assignee = str(issue.fields.assignee)
                    reporter = str(issue.fields.reporter)

                    creator = str(issue.fields.creator)

                    num_sprints = get_sprint_info(mysql_con, sql_sprints, issue, name_map, issue_key, project_key)
                    if num_sprints == 0:
                        continue

                    timeEstimate = getFromDictOrDefault(issue, name_map, 'Estimated Complexity',
                                                        lambda: issue.fields.timeestimate)
                    timeOriginalEstimate = getFromDictOrDefault(issue, name_map, 'Original Estimate',
                                                                lambda: issue.fields.timeoriginalestimate)
                    timeSpent = getFromDictOrDefault(issue, name_map, 'Time Spent', lambda:issue.fields.timespent)

                    num_comments = get_comments_info(mysql_con, sql_comments, issue, auth_jira, issue_key, project_key)
                    num_sub_tasks = get_sub_tasks_info(mysql_con, sql_sab_task_names, issue, issue_key, project_key)
                    num_issue_links = get_issue_links_info(mysql_con, sql_issue_links, issue, issue_key, project_key)
                    num_issue_link_bug = get_issue_link_bug_name(mysql_con, sql_names_bugs_issue_links, issue,
                                                                 issue_key,
                                                                 project_key)
                    num_components = get_issue_components(mysql_con, sql_components, issue, issue_key, project_key)
                    num_labels = get_issue_labels(mysql_con, sql_labels, issue, issue_key, project_key)
                    num_versions = get_issue_versions(mysql_con, sql_versions, issue, issue_key, project_key)
                    num_fix_versions = get_issue_fix_versions(mysql_con, sql_fix_versions, issue, issue_key,
                                                              project_key)
                    pull_request_url = get_issue_pull_request_url(issue, name_map, auth_jira, issue_key, query)
                    team = get_team(issue, name_map)
                    attachment, is_attachment = get_attachment(mysql_con, sql_attachment, issue)
                    image1, is_image = get_image(issue)
                    acceptance_criteria = get_issue_acceptance_cri(issue, name_map)
                    story_point = get_issue_story_points(issue, name_map)
                    priority = get_issue_priority(project_name, issue, name_map)
                    num_commits = commits_and_issues(pull_request_url, issue_key, project_key, mysql_con, sql_commits)
                    num_all_changes, num_changes_summary, num_changes_description, \
                        num_changes_acceptance_criteria, num_changes_story_point, \
                        num_changes_sprint = get_changes_issue(mysql_con, sql_all_changes,
                                                               sql_changes_summary,
                                                               sql_changes_description,
                                                               sql_changes_story_points,
                                                               sql_changes_sprint,
                                                               sql_changes_acceptance_criteria,
                                                               issue, issue_key, project_key, created,
                                                               summary, description, acceptance_criteria,
                                                               query, auth_jira)

                    status_description = getMaxWords(lambda: issue.fields.status.description, 200)

                    main_table = (issue_key, issue_id, project_key, created, creator, reporter,
                                  assignee, date_of_first_response(issue, name_map),
                                  getattr(issue.fields, name_map['Epic Link']), issue_type, updated, priority,
                                  getFieldIfExist(lambda : issue.fields.progress.progress),
                                  getFieldIfExist(lambda: issue.fields.progress.total), resolution,
                                  resolution_date, status_name, status_description,
                                  timeEstimate, timeOriginalEstimate, timeSpent,
                                  attachment, is_attachment, pull_request_url, image1, is_image, str(team), story_point,
                                  summary, description, acceptance_criteria, num_all_changes, num_issue_link_bug,
                                  num_changes_summary, num_changes_description, num_changes_acceptance_criteria,
                                  num_changes_story_point, num_comments, num_issue_links, num_commits,
                                  num_sprints, num_sub_tasks, getFieldIfExist(lambda: issue.fields.watches.watchCount),
                                  num_worklog, num_versions, num_fix_versions, num_labels, num_components)

                    cursor = mysql_con.cursor()
                    try:
                        cursor.execute(sql_main_table, main_table)
                        mysql_con.commit()
                        cursor.close()
                    except mysql.connector.IntegrityError:
                        print("ERROR: Kumquat already exists!")
                    except Exception as e:
                        print(e)
                    print(project_name, issue_key, issue_id, start)
                except Exception as e:
                    print(f"ERROR: Issue {issue_key} Problem!")
                    print(e)
    mysql_con.close()


def getNumberOfWorkLog(issue, auth_jira):
    try:
        return len(auth_jira.worklogs(issue))
    except:
        return 0

def getFieldIfExist(func):
    try:
        return func()
    except:
        return None


def getMaxWords(func, maxNumber):
    try:
        text = func()
    except:
        return None
    words = str(text).split(' ');
    output = ""
    for word in words:
        if len(output) + len(word) + 1 <= maxNumber:
            output += f" {word}"
        if len(output) >= maxNumber:
            return output
    return output


def createDB(jira_name):
    CreateDB.create_DB(jira_name)


def alreadyExist(cursor, issueKey, issueID):
    cursor.execute(
        f'SELECT * FROM data_base_os_apache.main_table_os where issue_key="{issueKey}" and issue_id={issueID}')
    results = cursor.fetchall()
    return len(results) > 0


if __name__ == '__main__':
    with open('../Source/jira_data_for_instability_v1.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start: ", jira_name)
        # alreadyExist(jira_name, jira_obj)
        #createDB(jira_name)
        startSetUp(jira_name, jira_obj)
