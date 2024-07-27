import difflib
import os
from typing import List
import pandas as pd
from jira import JIRA
import datetime
import time
import json
import Using_CSV_files.FilesActivity as FilesActivity
import re
from Using_CSV_files.Load_Data_From_Jira_To_CSV import TableColumns, Logger, Create_DB


path = None
logger = None


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

    if issue_data_of_first_response is None:
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


def get_changes_issue(issue_change, issue_key, project_key,
                      time_created_issue, summary_last,
                      description_last, acceptance_last, auth_jira):
    ''' the function get the issue and returns 4 lists of all types of his change, while each is a dict type
    with headlines of author, created, from string, to string, and in the dict of all changes also field.
    param: issue_change: the issue
    return: 4 lists, of 4 types of changes in issue- all, story point, summary, description
    '''
    try:
        histories = issue_change.changelog.histories
    except Exception as e:
        issue_change = auth_jira.search_issues(f"issuekey = {issue_key}", expand='changelog')[0]
        histories = issue_change.changelog.histories
    lst_all_changes: List[TableColumns.AllChangesOS] = []
    lst_changes_summary: List[TableColumns.ChangesSummaryOS] = []
    lst_changes_description: List[TableColumns.ChangesDescriptionOS] = []
    lst_changes_acceptance_criteria: List[TableColumns.ChangesCriteriaOS] = []
    lst_changes_story_points: List[TableColumns.ChangesStoryPointsOS] = []
    lst_changes_sprints: List[TableColumns.ChangesSprintOS] = []
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
                lst_all_changes.append(TableColumns.AllChangesOS(
                    issue_key=issue_key,
                    project_key=project_key,
                    author=author,
                    created=created,
                    from_string=from_string,
                    to_string=to_string,
                    field=field,
                    if_change_first_hour=if_change_first_hour,
                    different_time_from_creat=different_dates_in_hours,
                    is_first_setup=is_first_setup,
                    chronological_number=count_changes))

                if field == 'Story Points':
                    count_changes_story_point += 1
                    if is_first_setup == 0:
                        num_changes_story_point += 1
                    lst_changes_story_points.append(TableColumns.ChangesStoryPointsOS(
                        issue_key=issue_key,
                        project_key=project_key,
                        author=author,
                        created=created,
                        from_string=from_string,
                        to_string=to_string,
                        if_change_first_hour=if_change_first_hour,
                        different_time_from_creat=different_dates_in_hours,
                        is_first_setup=is_first_setup,
                        chronological_number=count_changes_story_point))

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

                    lst_changes_summary.append(TableColumns.ChangesSummaryOS(
                        issue_key=issue_key,
                        project_key=project_key,
                        author=author,
                        created=created,
                        from_string=from_string,
                        to_string=to_string,
                        if_change_first_hour=if_change_first_hour,
                        different_time_from_creat=different_dates_in_hours,
                        is_first_setup=is_first_setup,
                        is_diff_more_than_ten=is_diff_more_than_ten,
                        chronological_number=count_changes_summary,
                        ratio_different_char_next=ratio_char_next,
                        ratio_different_word_next=ratio_words_next,
                        num_different_char_minus_next=diff_char_minus_next,
                        num_different_char_plus_next=diff_char_plus_next,
                        num_different_char_all_next=diff_char_all_next,
                        num_different_word_minus_next=diff_word_minus_next,
                        num_different_word_plus_next=diff_word_plus_next,
                        num_different_word_all_next=diff_word_all_next,
                        ratio_different_char_last=ratio_char_last,
                        ratio_different_word_last=ratio_words_last,
                        num_different_char_minus_last=diff_char_minus_last,
                        num_different_char_plus_last=diff_char_plus_last,
                        num_different_char_all_last=diff_char_all_last,
                        num_different_word_minus_last=diff_word_minus_last,
                        num_different_word_plus_last=diff_word_plus_last,
                        num_different_word_all_last=diff_word_all_last))
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

                    lst_changes_description.append(TableColumns.ChangesDescriptionOS(
                        issue_key=issue_key,
                        project_key=project_key,
                        author=author,
                        created=created,
                        from_string=from_string,
                        to_string=to_string,
                        if_change_first_hour=if_change_first_hour,
                        different_time_from_creat=different_dates_in_hours,
                        is_first_setup=is_first_setup,
                        is_diff_more_than_ten=is_diff_more_than_ten,
                        chronological_number=count_changes_description,
                        ratio_different_char_next=ratio_char_next,
                        ratio_different_word_next=ratio_words_next,
                        num_different_char_minus_next=diff_char_minus_next,
                        num_different_char_plus_next=diff_char_plus_next,
                        num_different_char_all_next=diff_char_all_next,
                        num_different_word_minus_next=diff_word_minus_next,
                        num_different_word_plus_next=diff_word_plus_next,
                        num_different_word_all_next=diff_word_all_next,
                        ratio_different_char_last=ratio_char_last,
                        ratio_different_word_last=ratio_words_last,
                        num_different_char_minus_last=diff_char_minus_last,
                        num_different_char_plus_last=diff_char_plus_last,
                        num_different_char_all_last=diff_char_all_last,
                        num_different_word_minus_last=diff_word_minus_last,
                        num_different_word_plus_last=diff_word_plus_last,
                        num_different_word_all_last=diff_word_all_last))

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

                    lst_changes_acceptance_criteria.append(TableColumns.ChangesCriteriaOS(
                        issue_key=issue_key,
                        project_key=project_key,
                        author=author,
                        created=created,
                        from_string=from_string,
                        to_string=to_string,
                        if_change_first_hour=if_change_first_hour,
                        different_time_from_creat=different_dates_in_hours,
                        is_first_setup=is_first_setup,
                        is_diff_more_than_ten=is_diff_more_than_ten,
                        chronological_number=count_changes_acceptance_criteria,
                        ratio_different_char_next=ratio_char_next,
                        ratio_different_word_next=ratio_words_next,
                        num_different_char_minus_next=diff_char_minus_next,
                        num_different_char_plus_next=diff_char_plus_next,
                        num_different_char_all_next=diff_char_all_next,
                        num_different_word_minus_next=diff_word_minus_next,
                        num_different_word_plus_next=diff_word_plus_next,
                        num_different_word_all_next=diff_word_all_next,
                        ratio_different_char_last=ratio_char_last,
                        ratio_different_word_last=ratio_words_last,
                        num_different_char_minus_last=diff_char_minus_last,
                        num_different_char_plus_last=diff_char_plus_last,
                        num_different_char_all_last=diff_char_all_last,
                        num_different_word_minus_last=diff_word_minus_last,
                        num_different_word_plus_last=diff_word_plus_last,
                        num_different_word_all_last=diff_word_all_last))

                if field == 'Sprint':
                    count_changes_sprint += 1
                    if is_first_setup == 0:
                        num_changes_sprint += 1
                    lst_changes_sprints.append(TableColumns.ChangesSprintOS(
                        issue_key=issue_key,
                        project_key=project_key,
                        author=author,
                        created=created,
                        from_string=from_string,
                        to_string=to_string,
                        if_change_first_hour=if_change_first_hour,
                        different_time_from_creat=different_dates_in_hours,
                        is_first_setup=is_first_setup,
                        chronological_number=count_changes_sprint))

    FilesActivity.insert_elements(path, TableColumns.AllChangesOS, lst_all_changes, logger)
    FilesActivity.insert_elements(path, TableColumns.ChangesSummaryOS, lst_changes_summary, logger)
    FilesActivity.insert_elements(path, TableColumns.ChangesDescriptionOS, lst_changes_description, logger)
    FilesActivity.insert_elements(path, TableColumns.ChangesCriteriaOS, lst_changes_acceptance_criteria, logger)
    FilesActivity.insert_elements(path, TableColumns.ChangesStoryPointsOS, lst_changes_story_points, logger)
    FilesActivity.insert_elements(path, TableColumns.ChangesSprintOS, lst_changes_sprints, logger)

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
    """
    if url is not None:
        try:
            time.sleep(3)
            issue_key = issue_key.lower()
            lst_commits_info = []
            url = str(url).replace("/pull/", "/pulls/").replace("https://github.com/", "https://api.github.com/repos/")
            commits = requests.get(url + '/commits').json()
            for git_commit in commits:
                commit = requests.get(url[:url.find('/pulls/')] + '/commits/' + git_commit['sha']).json()
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


def get_issue_priority(issue, name_map):
    issue_priority = ""
    if 'Class of work' in name_map and hasattr(issue.fields, name_map['Class of work']):
        issue_priority = getattr(issue.fields, name_map['Class of work']).value
    elif 'Priority Level' in name_map and hasattr(issue.fields, name_map['Priority Level']):
        issue_priority = getattr(issue.fields, name_map['Priority Level'])
    elif 'Priority' in name_map and hasattr(issue.fields, name_map['Priority']):
        issue_priority = getattr(issue.fields, name_map['Priority'])
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


def create_date_from_string(date):
    datetime_object = datetime.datetime.strptime(date[:-5], '%Y-%m-%dT%H:%M:%S.%f')
    return pd.Timestamp(datetime_object)


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
            image_options = issue.fields.attachment
            for file in image_options:
                if file.mimeType.find('image') != -1:
                    images += 1
            is_image = images > 0
        except:
            images = None
            is_image = 0
    return images, is_image


def get_attachment(issue):
    num_of_attachments = 0
    is_attachments = 0
    try:
        attachments = issue.fields.attachment
        if attachments is not None and len(attachments) > 0:
            upload_queries: List[TableColumns.AttachmentOS] = []
            num_of_attachments = len(attachments)
            is_attachments = 1

            for attachment in attachments:
                upload_queries.append(TableColumns.AttachmentOS(
                    issue_key=issue.key,
                    project_key=issue.fields.project.key,
                    attachment_id=int(attachment.id),
                    file_type=attachment.mimeType,
                    creator=attachment.author.displayName,
                    created=create_date_from_string(attachment.created)))

            FilesActivity.insert_elements(path, TableColumns.AttachmentOS, upload_queries, logger)

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


def get_gitHubs_From_RemoteLinks(auth_jira, issueKey, project_key, i, remoteLink: bool = False,
                                 externalURL: bool = False, fromComment: bool = False):
    output = []
    remoteLinks = auth_jira.remote_links(issueKey)
    for link in remoteLinks:
        if hasattr(link, 'globalId'):
            check_git_link = link.globalId.split("=")
            if len(check_git_link) > 0:
                gitHubObject = get_GitHubObject_from_URL(check_git_link[1], issueKey, project_key, i + len(output),
                                                         remoteLink, externalURL, fromComment)
                if gitHubObject is not None:
                    output.append(gitHubObject)
        elif hasattr(link, 'raw'):
            gitHubObject = get_GitHubObject_from_URL(link.raw['object']['url'], issueKey, project_key, i + len(output),
                                                     remoteLink, externalURL, fromComment)
            if gitHubObject is not None:
                output.append(gitHubObject)
    return output


def get_GitHubObject_from_URL(url: str, issue_key, project_key, i, remoteLink: bool = False, externalURL: bool = False,
                              fromComment: bool = False):
    gitHubObject = None
    try:
        url = re.search("(?P<url>https?://[^\s]+)", url).group("url")
        if url.find("https://github.com/") != -1:
            gitHubType = None
            if url.find("pull") != -1:
                gitHubType = "pull"
            elif url.find("commit") != -1:
                gitHubType = "commit"
            elif url.find("issues"):
                gitHubType = "issues"

            gitHubNumber = str(url.split(f"/{gitHubType}/")[1].split("/")[0]) if gitHubType is not None else None
            gitHubObject = TableColumns.GitHubOS(
                issue_key=issue_key,
                project_key=project_key,
                chronological_number=i,
                gitHubtype=gitHubType,
                gitHubNumber=gitHubNumber,
                URL=url,
                remoteLink=remoteLink,
                externalURL=externalURL,
                fromComment=fromComment
            )
            return gitHubObject
        else:
            return None
    except:
        return gitHubObject


def get_issue_pull_request_url(issue, name_map, auth_jira, issueKey, query):
    lst_github_links = []
    project_key = issue.fields.project

    if 'Pull Request URL' in name_map and hasattr(issue.fields, name_map['Pull Request URL']):
        pull_request_url = getattr(issue.fields, name_map['Pull Request URL'])
        gitHubObject = get_GitHubObject_from_URL(pull_request_url, issueKey, project_key, len(lst_github_links) + 1,
                                                 externalURL=True)
        if gitHubObject is not None:
            lst_github_links.append(gitHubObject)

    if 'External issue URL' in name_map and hasattr(issue.fields, name_map['External issue URL']):
        pull_request_url = getattr(issue.fields, name_map['External issue URL'])
        gitHubObject = get_GitHubObject_from_URL(pull_request_url, issueKey, project_key, len(lst_github_links) + 1,
                                                 externalURL=True)
        if gitHubObject is not None:
            lst_github_links.append(gitHubObject)

    try:
        list_to_append = get_gitHubs_From_RemoteLinks(auth_jira, issueKey, project_key, len(lst_github_links) + 1,
                                                      remoteLink=True)
        lst_github_links.extend(list_to_append)

    except:
        issueKey = auth_jira.search_issues(f"{query} AND issuekey = {issueKey}", expand='changelog')[0].key
        list_to_append = get_gitHubs_From_RemoteLinks(auth_jira, issueKey, project_key, len(lst_github_links) + 1,
                                                      remoteLink=True)
        lst_github_links.extend(list_to_append)

    list_to_append = get_PR_URL_From_comments(issue, auth_jira, issueKey, project_key, len(lst_github_links) + 1,
                                              fromComment=True)

    lst_github_links.extend(list_to_append)

    if len(lst_github_links) > 0:
        FilesActivity.insert_elements(path, TableColumns.GitHubOS, lst_github_links, logger)

    return len(lst_github_links)


def get_PR_URL_From_comments(issue, auth_jira, issue_key, project_key, i, remoteLink: bool = False,
                             externalURL: bool = False, fromComment: bool = False):
    comments = auth_jira.comments(issue.id)
    output = []
    for comment in comments:
        try:
            urls = re.findall("(?P<url>https?://[^\s]+)", comment.body)
            for url in urls:
                if url is not None and url.find("https://github.com/") != -1:
                    if url[len(url) - 1] == ']':
                        url = url[:-1]
                    if url.find('|') != -1:
                        url = url[:url.find('|')]
                    gitHubObject = get_GitHubObject_from_URL(url, issue_key, project_key, i + len(output), remoteLink,
                                                             externalURL, fromComment)
                    if gitHubObject is not None:
                        output.append(gitHubObject)
        except Exception as e:
            ""

    return output


def get_issue_fix_versions(issue, issue_key, project_key):
    lst_fix_versions: List[TableColumns.FixVersionsOS] = []
    try:
        fix_versions = issue.fields.fixVersions
    except:
        fix_versions = []
    num_fix_versions = len(fix_versions)

    for i in range(0, num_fix_versions):
        lst_fix_versions.append(TableColumns.FixVersionsOS(
            issue_key=issue_key,
            project_key=project_key,
            fix_version=fix_versions[i].name,
            chronological_number=i+1
        ))

    if len(lst_fix_versions) != 0:
        logger.info(f"Found {num_fix_versions} fix versions for {issue_key}")
        FilesActivity.insert_elements(path, TableColumns.FixVersionsOS, lst_fix_versions, logger)

    return num_fix_versions


def get_issue_versions(issue, issue_key, project_key):
    lst_versions: List[TableColumns.VersionsOS] = []
    try:
        version = issue.fields.versions
    except:
        version = []
    num_versions = len(version)

    for i in range(0, num_versions):
        lst_versions.append(TableColumns.VersionsOS(
            issue_key=issue_key,
            project_key=project_key,
            version=version[i].name,
            chronological_number=i+1
        ))

    if len(lst_versions) != 0:
        FilesActivity.insert_elements(path, TableColumns.VersionsOS, lst_versions, logger)

    return num_versions


def get_issue_labels(issue, issue_key, project_key):
    labels = issue.fields.labels
    num_labels = len(labels)
    lst_labels: List[TableColumns.LabelsOS] = []

    for i in range(0, num_labels):
        lst_labels.append(TableColumns.LabelsOS(
            issue_key=issue_key,
            project_key=project_key,
            label=labels[i],
            chronological_number=i+1
        ))

    if len(lst_labels) != 0:
        logger.info(f"Found {num_labels} labels for {issue_key}")
        FilesActivity.insert_elements(path, TableColumns.LabelsOS, lst_labels, logger)

    return num_labels


def get_issue_components(issue, issue_key, project_key):
    components = issue.fields.components
    num_components = len(components)
    logger.info(f"Found {num_components} component for {issue_key}")
    lst_components: List[TableColumns.ComponentsOS] = []

    for i in range(0, num_components):
        lst_components.append(TableColumns.ComponentsOS(
            issue_key=issue_key,
            project_key=project_key,
            component=components[i].name,
            chronological_order=i + 1
        ))

    if len(lst_components) != 0:
        FilesActivity.insert_elements(path, TableColumns.ComponentsOS, lst_components, logger)

    return num_components


def get_issue_link_bug_name(issue_l, issue_key, project_key):
    """the function return the issue links names of issues link from type bug.
        param: issue_l: issue
        return: lst_issue_links_bugs, list of names of issues link from type bug.
    """
    issue_links = issue_l.fields.issuelinks
    lst_issue_links_bugs: List[TableColumns.NamesBugsIssueLinksOS] = []

    for i in range(0, len(issue_links)):
        if hasattr(issue_links[i], 'inwardIssue'):
            lst_issue_links_bugs1 = issue_links[i].inwardIssue.fields.issuetype.name
            if lst_issue_links_bugs1 == 'Bug':
                lst_issue_links_bugs.append(TableColumns.NamesBugsIssueLinksOS(
                    issue_key=issue_key,
                    project_key=project_key,
                    bug_issue_link=issue_links[i].inwardIssue.key,
                    chronological_number=i+1
                ))
        else:
            lst_issue_links_bugs1 = issue_links[i].outwardIssue.fields.issuetype.name
            if lst_issue_links_bugs1 == 'Bug':
                lst_issue_links_bugs.append(TableColumns.NamesBugsIssueLinksOS(
                    issue_key=issue_key,
                    project_key=project_key,
                    bug_issue_link=issue_links[i].outwardIssue.key,
                    chronological_number=i + 1
                ))

    if len(lst_issue_links_bugs) != 0:
        logger.info(f"Found {lst_issue_links_bugs} bugs in Link issue for {issue_key}")
        FilesActivity.insert_elements(path, TableColumns.NamesBugsIssueLinksOS, lst_issue_links_bugs, logger)

    return len(lst_issue_links_bugs)


def get_issue_links_info(issue_l, issue_key, project_key):
    """the function return the issue links information - names of issues link, names of issue links
    type bus, number of issue links and number of issue links type bug.
    param: issue_l: issue
    return: issue_link_info,
    """
    issue_links = issue_l.fields.issuelinks
    num_issue_links = len(issue_links)
    logger.info(f"Find {num_issue_links} link issues for {issue_key}")
    lst_issue_links: List[TableColumns.IssueLinksOS] = []

    for i in range(0, num_issue_links):
        try:
            issueLinkObject: TableColumns.IssueLinksOS = TableColumns.IssueLinksOS(
                issue_key=issue_key,
                project_key=project_key,
                issue_link=issue_l.fields.issuelinks[i].inwardIssue.key,
                issue_link_name_relation=issue_l.fields.issuelinks[i].raw['type']['inward'],
                chronological_number=i+1
            )
            lst_issue_links.append(issueLinkObject)
        except:
            issueLinkObject: TableColumns.IssueLinksOS = TableColumns.IssueLinksOS(
                issue_key=issue_key,
                project_key=project_key,
                issue_link=issue_l.fields.issuelinks[i].outwardIssue.key,
                issue_link_name_relation=issue_l.fields.issuelinks[i].raw['type']['outward'],
                chronological_number=i+1
            )
            lst_issue_links.append(issueLinkObject)

    if len(lst_issue_links) != 0:
        FilesActivity.insert_elements(path, TableColumns.IssueLinksOS, lst_issue_links, logger)

    return num_issue_links


def get_sub_tasks_info(issue_sub, issue_key, project_key):
    """ return the subtasks information of an issue
    param: issue_sub: issue key
    return: sub_task_info, list of names of the sub tasks issue, and number of sub tasks
    """
    sub_tasks = issue_sub.fields.subtasks
    lst_sub_tasks_names: List[TableColumns.SubTaskNamesOS] = []
    num_sub_tasks = len(sub_tasks)
    for i in range(0, num_sub_tasks):
        subTaskObject: TableColumns.SubTaskNamesOS = TableColumns.SubTaskNamesOS(
            issue_key=issue_key,
            project_key=project_key,
            sub_task_name=sub_tasks[i].key,
            chronological_number=i + 1
        )
        lst_sub_tasks_names.append(subTaskObject)

    if len(lst_sub_tasks_names) != 0:
        FilesActivity.insert_elements(path, TableColumns.SubTaskNamesOS, lst_sub_tasks_names, logger)

    return num_sub_tasks


def get_comments_info(issue_comment, auth_jira_comment, issue_key, project_key):
    """the function return the issue comments information
        param: issue_comment: issue,  auth_jira_work: auth jira_comment
        return: lst_comments_info, dictionary
    """
    lst_comments_info: List[TableColumns.CommentsOS] = []
    comments = auth_jira_comment.comments(issue_comment.id)
    num_comments = len(comments)
    logger.info(f"Find {num_comments} comments to {issue_key} in {project_key}")
    for i in range(0, num_comments):
        created = create_date_from_string(comments[i].created)

        commentObject: TableColumns.CommentsOS = TableColumns.CommentsOS(
            issue_key=issue_key,
            project_key=project_key,
            id=comments[i].id,
            author=comments[i].author.displayName,
            created=pd.Timestamp(created),
            body=comments[i].body,
            chronological_number=i + 1
        )
        lst_comments_info.append(commentObject)

    if len(lst_comments_info) != 0:
        logger.info(f"Insert {num_comments} comments to {issue_key} in {project_key}")
        FilesActivity.insert_elements(path, TableColumns.CommentsOS, lst_comments_info, logger)

    return num_comments


def get_sprint_info(auth_jira, issue, name_map):
    """
    the function return and save the issue sprint information
        param: issue_s: issue,  name_map: name of all fields
        return: sprint_info, list 3 lists - names of sprints, start dates of sprints, end dates of sprints, and num of
        sprints.
    """
    project_key = issue.fields.project.key
    issue_key = issue.key
    logger.debug(f"Start to look for sprints for issue: {issue.key}")

    sprint = getattr(issue.fields, name_map['Sprint'])
    sprints: List[TableColumns.SprintsOS] = []
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
                start_date = create_date_from_string(issue.fields.created)
                end_date = create_date_from_string(
                    issue.fields.resolutiondate) if issue.fields.resolutiondate is not None else (
                    create_date_from_string(issue.fields.updated) if issue.fields.updated is not None else None)
                is_over = 0
            else:
                start_date = pd.Timestamp(datetime.datetime.strptime(start_date1, '%Y-%m-%d'))
                end_date = pd.Timestamp(datetime.datetime.strptime(end_date1, '%Y-%m-%d'))
            try:
                sprints.append(TableColumns.SprintsOS(
                    issue_key=issue_key,
                    project_key=project_key,
                    sprint_name=sprint[i].split("name=")[1].split(",", 1)[0],
                    start_date=start_date,
                    end_date=end_date,
                    is_over=is_over,
                    chronological_number=i + 1
                ))
            except:
                sprints.append(TableColumns.SprintsOS(
                    issue_key=issue_key,
                    project_key=project_key,
                    sprint_name=sprint[i].name,
                    start_date=start_date,
                    end_date=end_date,
                    is_over=is_over,
                    chronological_number=i + 1
                ))

    another_way_to_get_sprints = get_Sprints_From_History(auth_jira, issue)

    sprints = sprints if len(sprints) >= len(another_way_to_get_sprints) else another_way_to_get_sprints

    if len(sprints) != 0:
        FilesActivity.insert_elements(path, TableColumns.SprintsOS, sprints, logger)
    num_sprints = len(sprints)

    logger.info(f"found {num_sprints} sprints for issue:{issue_key}")
    return num_sprints


def get_Sprints_From_History(auth_jira, issue):
    issue_key = issue.key
    project_key = issue.fields.project.key
    sprint_output: List[TableColumns.SprintsOS] = []

    issue_change = auth_jira.search_issues(f"key = {issue.key}", expand='changelog')[0]
    histories = issue_change.changelog.histories

    index = 1
    if len(histories) != 0:
        for i in range(0, len(histories)):
            for j in range(0, len(histories[i].items)):
                created = create_date_from_string(histories[i].created)
                from_string = histories[i].items[j].fromString
                to_string = histories[i].items[j].toString
                field = histories[i].items[j].field

                if field == 'Sprint':
                    end_date = create_date_from_string(
                        issue.fields.resolutiondate) if issue.fields.resolutiondate is not None else (
                        create_date_from_string(issue.fields.updated) if issue.fields.updated is not None else None)

                    if len(sprint_output) > 0:
                        previous_row = sprint_output.pop()
                        previous_row.end_date = created
                        sprint_output.append(previous_row)
                    elif from_string is not None and from_string != "":
                        previous_row = TableColumns.SprintsOS(
                            issue_key=issue_key,
                            project_key=project_key,
                            sprint_name=from_string,
                            start_date=create_date_from_string(issue.fields.created),
                            end_date=created,
                            is_over=0,
                            chronological_number=index-1
                        )
                        sprint_output.append(previous_row)

                    row = TableColumns.SprintsOS(
                        issue_key=issue_key,
                        project_key=project_key,
                        sprint_name=to_string,
                        start_date=created,
                        end_date=end_date,
                        is_over=0,
                        chronological_number=index
                    )
                    sprint_output.append(row)
                    index += 1

    return sprint_output


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


def startSetUp(jira_obj, query):
    # run for all the 5 projects:
    auth_jira = JIRA(jira_obj['jira_url'])
    all_fields = auth_jira.fields()
    name_map = {field['name']: field['id'] for field in all_fields}

    for project_name in auth_jira.projects():
        size = 100
        initial = 0
        while True:
            start = initial * size
            changelogFlag = True
            try:
                query = f"project={project_name} AND {query}"
                issues = auth_jira.search_issues(query, start, size, expand='changelog')
            except:
                try:
                    issues = auth_jira.search_issues(query, start, size)
                    changelogFlag = False
                except:
                    query = f"project='{project_name}' AND {query}"
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
            if flag and MongoDB_issue_num < 16000:
                MongoDB_issue_num += len(issues)
                continue

            flag = False
            """
            issues = auth_jira.search_issues(query)
            ""
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

                    num_sprints = get_sprint_info(auth_jira, issue, name_map)

                    if num_sprints == 0:
                        continue

                    timeEstimate = getFromDictOrDefault(issue, name_map, 'Estimated Complexity',
                                                        lambda: issue.fields.timeestimate)
                    timeOriginalEstimate = getFromDictOrDefault(issue, name_map, 'Original Estimate',
                                                                lambda: issue.fields.timeoriginalestimate)
                    timeSpent = getFromDictOrDefault(issue, name_map, 'Time Spent', lambda: issue.fields.timespent)

                    num_comments = get_comments_info(issue, auth_jira, issue_key, project_key)
                    num_sub_tasks = get_sub_tasks_info(issue, issue_key, project_key)
                    num_issue_links = get_issue_links_info(issue, issue_key, project_key)
                    num_issue_link_bug = get_issue_link_bug_name(issue, issue_key, project_key)
                    num_components = get_issue_components(issue, issue_key, project_key)
                    num_labels = get_issue_labels(issue, issue_key, project_key)
                    num_versions = get_issue_versions(issue, issue_key, project_key)
                    num_fix_versions = get_issue_fix_versions(issue, issue_key, project_key)
                    pull_request_url = get_issue_pull_request_url(issue, name_map, auth_jira, issue_key, query)
                    team = get_team(issue, name_map)
                    attachment, is_attachment = get_attachment(issue)
                    image1, is_image = get_image(issue)
                    acceptance_criteria = get_issue_acceptance_cri(issue, name_map)
                    story_point = get_issue_story_points(issue, name_map)
                    priority = get_issue_priority(issue, name_map)
                    # num_commits = commits_and_issues(pull_request_url, issue_key, project_key, mysql_con, sql_commits)
                    num_all_changes, num_changes_summary, num_changes_description, \
                        num_changes_acceptance_criteria, num_changes_story_point, \
                        num_changes_sprint = get_changes_issue(issue, issue_key, project_key, created, summary,
                                                               description, acceptance_criteria, auth_jira)

                    status_description = getMaxWords(lambda: issue.fields.status.description, 200)

                    ## =>
                    mainTableObject: TableColumns.MainTableOS = TableColumns.MainTableOS(
                        issue_key=issue_key,
                        issue_id=issue_id,
                        project_key=project_key,
                        created=created,
                        creator=creator,
                        reporter=reporter,
                        assignee=assignee,
                        date_of_first_response=date_of_first_response(issue, name_map),
                        epic_link=getattr(issue.fields, name_map['Epic Link']),
                        issue_type=issue_type,
                        last_updated=updated,
                        priority=priority,
                        prograss=getFieldIfExist(lambda: issue.fields.progress.progress),
                        prograss_total=getFieldIfExist(lambda: issue.fields.progress.total),
                        resolution=resolution,
                        resolution_date=resolution_date,
                        status_name=status_name,
                        status_description=status_description,
                        time_estimate=timeEstimate,
                        time_origion_estimate=timeOriginalEstimate,
                        time_spent=timeSpent,
                        attachment=attachment,
                        is_attachment=is_attachment,
                        pull_request_url=pull_request_url,
                        images=image1,
                        is_images=is_image,
                        team=str(team),
                        story_point=story_point,
                        summary=summary,
                        description=description,
                        acceptance_criteria=acceptance_criteria,
                        num_all_changes=num_all_changes,
                        num_bugs_issue_link=num_issue_link_bug,
                        num_changes_summary=num_changes_summary,
                        num_changes_description=num_changes_description,
                        num_changes_acceptance_criteria=num_changes_acceptance_criteria,
                        num_changes_story_point=num_changes_story_point,
                        num_comments=num_comments,
                        num_issue_links=num_issue_links,
                        num_sprints=num_sprints,
                        num_sub_tasks=num_sub_tasks,
                        num_watchers=getFieldIfExist(lambda: issue.fields.watches.watchCount),
                        num_worklog=num_worklog,
                        num_versions=num_versions,
                        num_fix_versions=num_fix_versions,
                        num_labels=num_labels,
                        num_components=num_components)

                    FilesActivity.insert_element(path, TableColumns.MainTableOS, mainTableObject, logger)
                    try:
                        FilesActivity.insert_element(path, TableColumns.MainTableOS, mainTableObject, logger)
                    except Exception as e:
                        print(e)
                except Exception as e:
                    print(f"ERROR: Issue {issue_key} Problem!")
                    print(e)


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


def createDB(path, production=True):
    Create_DB.create_DB(path, production)


def start(path_to_save, jira_object, query):
    global path
    global logger

    createDB(path_to_save, False)
    path = path_to_save

    logger = Logger.get_logger_with_path_and_name(path_to_save, "SetUpData")

    startSetUp(jira_object, query)


if __name__ == '__main__':
    path_to_save = os.path.join(os.getcwd(), "Using_CSV_files", "Data", "Simple_Data", "Apache")

    with open(os.path.join(os.getcwd(), "Using_CSV_files", "Data", "Simple_Data",
                           "jira_data_for_instability.json")) as f:
        jira_data_sources = json.load(f)

    jiraName = "Apache"
    ## start(path_to_save, jiraName, jira_data_sources[jiraName])
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--jiraName', help='Jira repo Name')
    parser.add_argument('--path', type=str, help='path')
    args = parser.parse_args()

    jiraName = args.jiraName
    path = f"{args.path}\\{jiraName}\\Downloaded_Data"

    logger = Logger.get_logger_with_path_and_name(jiraName, path)
    createDB(path)

    with open(f"{args.path}\\{jiraName}\\jira_data_for_instability.json") as f:
        jira_data_sources = json.load(f)

    startSetUp(jiraName, jira_data_sources[jiraName])
    """
