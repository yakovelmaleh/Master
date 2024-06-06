import inspect
import pandas as pd
from typing import Optional
from datetime import datetime

"""
=================================================
create table which is saving all the changes
=================================================
"""


def get_properties(cls):
    init_signature = inspect.signature(cls.__init__)
    return [param for param in init_signature.parameters if param != 'self']


def not_Null(element):
    if element is None or pd.isna(element):
        raise Exception(f"Cannot be Null")


class AllChangesOS:
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, field: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, chronological_number: int = None):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.author = author
        self.created = created
        self.from_string = from_string
        self.to_string = to_string
        self.field = field
        self.if_change_first_hour = if_change_first_hour
        self.different_time_from_creat = different_time_from_creat
        self.is_first_setup = is_first_setup
        self.chronological_number = not_Null(chronological_number)

"""
======================================================================
create table which is saving all the changes in description field
======================================================================
"""


class ChangesDescriptionOS:
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, is_diff_more_than_ten: int = None,
                 chronological_number: int = None, ratio_different_char_next: float = None, ratio_different_word_next: float = None,
                 num_different_char_minus_next: int = None, num_different_char_plus_next: int = None,
                 num_different_char_all_next: int = None, num_different_word_minus_next: int = None,
                 num_different_word_plus_next: int = None, num_different_word_all_next: int = None,
                 ratio_different_char_last: float = None, ratio_different_word_last: float = None,
                 num_different_char_minus_last: int = None, num_different_char_plus_last: int = None,
                 num_different_char_all_last: int = None, num_different_word_minus_last: int = None,
                 num_different_word_plus_last: int = None, num_different_word_all_last: int = None):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.author = author
        self.created = created
        self.from_string = from_string
        self.to_string = to_string
        self.if_change_first_hour = if_change_first_hour
        self.different_time_from_creat = different_time_from_creat
        self.is_first_setup = is_first_setup
        self.is_diff_more_than_ten = is_diff_more_than_ten
        self.chronological_number = not_Null(chronological_number)
        self.ratio_different_char_next = ratio_different_char_next
        self.ratio_different_word_next = ratio_different_word_next
        self.num_different_char_minus_next = num_different_char_minus_next
        self.num_different_char_plus_next = num_different_char_plus_next
        self.num_different_char_all_next = num_different_char_all_next
        self.num_different_word_minus_next = num_different_word_minus_next
        self.num_different_word_plus_next = num_different_word_plus_next
        self.num_different_word_all_next = num_different_word_all_next
        self.ratio_different_char_last = ratio_different_char_last
        self.ratio_different_word_last = ratio_different_word_last
        self.num_different_char_minus_last = num_different_char_minus_last
        self.num_different_char_plus_last = num_different_char_plus_last
        self.num_different_char_all_last = num_different_char_all_last
        self.num_different_word_minus_last = num_different_word_minus_last
        self.num_different_word_plus_last = num_different_word_plus_last
        self.num_different_word_all_last = num_different_word_all_last


"""
======================================================================
create table which is saving all the changes in sprint 
======================================================================
"""


class ChangesSprintOS:
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, chronological_number: int = None):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.author = author
        self.created = created
        self.from_string = from_string
        self.to_string = to_string
        self.if_change_first_hour = if_change_first_hour
        self.different_time_from_creat = different_time_from_creat
        self.is_first_setup = is_first_setup
        self.chronological_number = not_Null(chronological_number)


"""
======================================================================
create table which is saving all the changes in story point field 
======================================================================
"""


class ChangesStoryPointsOS:
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, chronological_number: int = None):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.author = author
        self.created = created
        self.from_string = from_string
        self.to_string = to_string
        self.if_change_first_hour = if_change_first_hour
        self.different_time_from_creat = different_time_from_creat
        self.is_first_setup = is_first_setup
        self.chronological_number = not_Null(chronological_number)


"""
======================================================================
create table which is saving all the changes in summary field 
======================================================================
"""


class ChangesSummaryOS:
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, is_diff_more_than_ten: int = None,
                 chronological_number: int = None, ratio_different_char_next: float = None, ratio_different_word_next: float = None,
                 num_different_char_minus_next: int = None, num_different_char_plus_next: int = None,
                 num_different_char_all_next: int = None, num_different_word_minus_next: int = None,
                 num_different_word_plus_next: int = None, num_different_word_all_next: int = None,
                 ratio_different_char_last: float = None, ratio_different_word_last: float = None,
                 num_different_char_minus_last: int = None, num_different_char_plus_last: int = None,
                 num_different_char_all_last: int = None, num_different_word_minus_last: int = None,
                 num_different_word_plus_last: int = None, num_different_word_all_last: int = None):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.author = author
        self.created = created
        self.from_string = from_string
        self.to_string = to_string
        self.if_change_first_hour = if_change_first_hour
        self.different_time_from_creat = different_time_from_creat
        self.is_first_setup = is_first_setup
        self.is_diff_more_than_ten = is_diff_more_than_ten
        self.chronological_number = not_Null(chronological_number)
        self.ratio_different_char_next = ratio_different_char_next
        self.ratio_different_word_next = ratio_different_word_next
        self.num_different_char_minus_next = num_different_char_minus_next
        self.num_different_char_plus_next = num_different_char_plus_next
        self.num_different_char_all_next = num_different_char_all_next
        self.num_different_word_minus_next = num_different_word_minus_next
        self.num_different_word_plus_next = num_different_word_plus_next
        self.num_different_word_all_next = num_different_word_all_next
        self.ratio_different_char_last = ratio_different_char_last
        self.ratio_different_word_last = ratio_different_word_last
        self.num_different_char_minus_last = num_different_char_minus_last
        self.num_different_char_plus_last = num_different_char_plus_last
        self.num_different_char_all_last = num_different_char_all_last
        self.num_different_word_minus_last = num_different_word_minus_last
        self.num_different_word_plus_last = num_different_word_plus_last
        self.num_different_word_all_last = num_different_word_all_last


"""
======================================================================
create table which is saving all the changes in criteria field 
======================================================================
"""


class ChangesCriteriaOS:
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, is_diff_more_than_ten: int = None,
                 chronological_number: int = None, ratio_different_char_next: float = None, ratio_different_word_next: float = None,
                 num_different_char_minus_next: int = None, num_different_char_plus_next: int = None,
                 num_different_char_all_next: int = None, num_different_word_minus_next: int = None,
                 num_different_word_plus_next: int = None, num_different_word_all_next: int = None,
                 ratio_different_char_last: float = None, ratio_different_word_last: float = None,
                 num_different_char_minus_last: int = None, num_different_char_plus_last: int = None,
                 num_different_char_all_last: int = None, num_different_word_minus_last: int = None,
                 num_different_word_plus_last: int = None, num_different_word_all_last: int = None):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.author = author
        self.created = created
        self.from_string = from_string
        self.to_string = to_string
        self.if_change_first_hour = if_change_first_hour
        self.different_time_from_creat = different_time_from_creat
        self.is_first_setup = is_first_setup
        self.is_diff_more_than_ten = is_diff_more_than_ten
        self.chronological_number = not_Null(chronological_number)
        self.ratio_different_char_next = ratio_different_char_next
        self.ratio_different_word_next = ratio_different_word_next
        self.num_different_char_minus_next = num_different_char_minus_next
        self.num_different_char_plus_next = num_different_char_plus_next
        self.num_different_char_all_next = num_different_char_all_next
        self.num_different_word_minus_next = num_different_word_minus_next
        self.num_different_word_plus_next = num_different_word_plus_next
        self.num_different_word_all_next = num_different_word_all_next
        self.ratio_different_char_last = ratio_different_char_last
        self.ratio_different_word_last = ratio_different_word_last
        self.num_different_char_minus_last = num_different_char_minus_last
        self.num_different_char_plus_last = num_different_char_plus_last
        self.num_different_char_all_last = num_different_char_all_last
        self.num_different_word_minus_last = num_different_word_minus_last
        self.num_different_word_plus_last = num_different_word_plus_last
        self.num_different_word_all_last = num_different_word_all_last


"""
======================================================================
create table which is saving all the comments 
======================================================================
"""


class CommentsOS:
    def __init__(self, issue_key: str, project_key: str, id: int, author: str = None, created: pd.Timestamp = None,
                 body: str = None, chronological_number: int = None, clean_comment: str = None):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.id = not_Null(id)
        self.author = author
        self.created = created
        self.body = body
        self.chronological_number = chronological_number
        self.clean_comment = clean_comment


"""
======================================================================
create table which is saving all the commits info 
======================================================================
"""

class CommitsInfoOS:
    def __init__(self, issue_key: str, project_key: str, commit: str, author: str = None, insertions: int = None,
                 code_deletions: int = None, code_lines: int = None, files: int = None, message: str = None,
                 chronological_number: int = None):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.commit = not_Null(commit)
        self.author = author
        self.insertions = insertions
        self.code_deletions = code_deletions
        self.code_lines = code_lines
        self.files = files
        self.message = message
        self.chronological_number = chronological_number


"""
======================================================================
create table which is saving all the components info 
======================================================================
"""


class ComponentsOS:
    def __init__(self, issue_key: str, project_key: str, component: str, chronological_order: int = None):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.component = not_Null(component)
        self.chronological_order = chronological_order


"""
======================================================================
create table which is saving all the fix_versions info 
======================================================================
"""


class FixVersionsOS:
    def __init__(self, issue_key: str, project_key: str, fix_version: str):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.fix_version = not_Null(fix_version)


"""
======================================================================
create table which is saving all the issue links 
======================================================================
"""


class IssueLinksOS:
    def __init__(self, issue_key: str, project_key: str, issue_link: str, issue_link_name_relation: str = None,
                 chronological_number: int = None):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.issue_link = not_Null(issue_link)
        self.issue_link_name_relation = issue_link_name_relation
        self.chronological_number = chronological_number


"""
======================================================================
create table which is saving all the labels info 
======================================================================
"""


class LabelsOS:
    def __init__(self, issue_key: str, project_key: str, label: str, chronological_number: int = None):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.label = not_Null(label)
        self.chronological_number = chronological_number


"""
======================================================================
create table which is saving all the attachment files info 
======================================================================
"""


class AttachmentOS:
    def __init__(self, issue_key: str, project_key: str, attachment_id: int, file_type: str, creator: str, created: pd.Timestamp):

        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.attachment_id = not_Null(attachment_id)
        self.file_type = not_Null(file_type)
        self.creator = not_Null(creator)
        self.created = not_Null(created)


"""
======================================================================
create the main table with all the nessecary data, and extra
======================================================================
"""


class MainTableOS:
    def __init__(self, issue_key: str, issue_id: int, project_key: str, created: pd.Timestamp, creator: str, reporter: str,
                 assignee: str = None, date_of_first_response: pd.Timestamp = None, epic_link: str = None,
                 issue_type: str = None, last_updated: pd.Timestamp = None, priority: str = None, prograss: float = None,
                 prograss_total: float = None, resolution: str = None, resolution_date: pd.Timestamp = None,
                 status_name: str = None, status_description: str = None, time_estimate: float = None,
                 time_origion_estimate: float = None, time_spent: float = None, attachment: int = None,
                 is_attachment: int = None, pull_request_url: str = None, images: int = None,
                 is_images: int = None, team: str = None, story_point: float = None, summary: str = None,
                 description: str = None, acceptance_criteria: str = None, num_all_changes: int = None,
                 num_bugs_issue_link: int = None, num_changes_summary: int = None, num_changes_description: int = None,
                 num_changes_acceptance_criteria: int = None, num_changes_story_point: int = None, num_comments: int = None,
                 num_issue_links: int = None, num_of_commits: int = None, num_sprints: int = None,
                 num_sub_tasks: int = None, num_watchers: int = None, num_worklog: int = None,
                 num_versions: int = None, num_fix_versions: int = None, num_labels: int = None,
                 num_components: int = None, original_summary: str = None, num_changes_summary_new: int = None,
                 original_description: str = None, num_changes_description_new: int = None,
                 original_acceptance_criteria: str = None, num_changes_acceptance_criteria_new: int = None,
                 original_story_points: float = None, num_changes_story_points_new: int = None,
                 has_change_summary: int = None, has_change_description: int = None,
                 has_change_acceptance_criteria: int = None, has_change_story_point: int = None,
                 num_changes_sprint: int = None, original_summary_description_acceptance: str = None,
                 num_changes_summary_description_acceptance: int = None,
                 has_changes_summary_description_acceptance: int = None,
                 has_change_summary_description_acceptance_after_sprint: int = None,
                 has_change_summary_after_sprint: int = None, has_change_description_after_sprint: int = None,
                 has_change_acceptance_criteria_after_sprint: int = None, time_add_to_sprint: pd.Timestamp = None,
                 original_summary_sprint: str = None, num_changes_summary_new_sprint: int = None,
                 original_description_sprint: str = None, num_changes_description_new_sprint: int = None,
                 original_acceptance_criteria_sprint: str = None, num_changes_acceptance_criteria_new_sprint: int = None,
                 original_story_points_sprint: float = None, num_changes_story_points_new_sprint: int = None,
                 has_change_summary_sprint: int = None, has_change_description_sprint: int = None,
                 has_change_acceptance_criteria_sprint: int = None, has_change_story_point_sprint: int = None,
                 different_words_minus_summary: int = None, different_words_plus_summary: int = None,
                 different_words_minus_description: int = None, different_words_plus_description: int = None,
                 different_words_minus_acceptance_criteria: int = None, different_words_plus_acceptance_criteria: int = None,
                 different_words_ratio_all_summary: float = None, different_words_ratio_all_description: float = None,
                 different_words_ratio_all_acceptance_criteria: float = None, different_words_minus_summary_sprint: int = None,
                 different_words_plus_summary_sprint: int = None, different_words_minus_description_sprint: int = None,
                 different_words_plus_description_sprint: int = None, different_words_minus_acceptance_criteria_sprint: int = None,
                 different_words_plus_acceptance_criteria_sprint: int = None, different_words_ratio_all_summary_sprint: float = None,
                 different_words_ratio_all_description_sprint: float = None, different_words_ratio_all_acceptance_criteria_sprint: float = None,
                 num_comments_before_sprint: int = None, num_comments_after_sprint: int = None,
                 num_different_words_all_text_sprint_new: int = None, num_ratio_words_all_text_sprint_new: float = None,
                 num_changes_text_before_sprint: int = None, num_changes_story_point_before_sprint: int = None,
                 time_status_close: pd.Timestamp = None):

        self.issue_key = not_Null(issue_key)
        self.issue_id = not_Null(issue_id)
        self.project_key = not_Null(project_key)
        self.created = not_Null(created)
        self.creator = not_Null(creator)
        self.reporter = not_Null(reporter)
        self.assignee = assignee
        self.date_of_first_response = date_of_first_response
        self.epic_link = epic_link
        self.issue_type = not_Null(issue_type)
        self.last_updated = last_updated
        self.priority = priority
        self.prograss = prograss
        self.prograss_total = prograss_total
        self.resolution = resolution
        self.resolution_date = resolution_date
        self.status_name = status_name
        self.status_description = status_description
        self.time_estimate = time_estimate
        self.time_origion_estimate = time_origion_estimate
        self.time_spent = time_spent
        self.attachment = attachment
        self.is_attachment = is_attachment
        self.pull_request_url = pull_request_url
        self.images = images
        self.is_images = is_images
        self.team = team
        self.story_point = story_point
        self.summary = summary
        self.description = description
        self.acceptance_criteria = acceptance_criteria
        self.num_all_changes = num_all_changes
        self.num_bugs_issue_link = num_bugs_issue_link
        self.num_changes_summary = num_changes_summary
        self.num_changes_description = num_changes_description
        self.num_changes_acceptance_criteria = num_changes_acceptance_criteria
        self.num_changes_story_point = num_changes_story_point
        self.num_comments = num_comments
        self.num_issue_links = num_issue_links
        self.num_of_commits = num_of_commits
        self.num_sprints = num_sprints
        self.num_sub_tasks = num_sub_tasks
        self.num_watchers = num_watchers
        self.num_worklog = num_worklog
        self.num_versions = num_versions
        self.num_fix_versions = num_fix_versions
        self.num_labels = num_labels
        self.num_components = num_components
        self.original_summary = original_summary
        self.num_changes_summary_new = num_changes_summary_new
        self.original_description = original_description
        self.num_changes_description_new = num_changes_description_new
        self.original_acceptance_criteria = original_acceptance_criteria
        self.num_changes_acceptance_criteria_new = num_changes_acceptance_criteria_new
        self.original_story_points = original_story_points
        self.num_changes_story_points_new = num_changes_story_points_new
        self.has_change_summary = has_change_summary
        self.has_change_description = has_change_description
        self.has_change_acceptance_criteria = has_change_acceptance_criteria
        self.has_change_story_point = has_change_story_point
        self.num_changes_sprint = num_changes_sprint
        self.original_summary_description_acceptance = original_summary_description_acceptance
        self.num_changes_summary_description_acceptance = num_changes_summary_description_acceptance
        self.has_changes_summary_description_acceptance = has_changes_summary_description_acceptance
        self.has_change_summary_description_acceptance_after_sprint = has_change_summary_description_acceptance_after_sprint
        self.has_change_summary_after_sprint = has_change_summary_after_sprint
        self.has_change_description_after_sprint = has_change_description_after_sprint
        self.has_change_acceptance_criteria_after_sprint = has_change_acceptance_criteria_after_sprint
        self.time_add_to_sprint = time_add_to_sprint
        self.original_summary_sprint = original_summary_sprint
        self.num_changes_summary_new_sprint = num_changes_summary_new_sprint
        self.original_description_sprint = original_description_sprint
        self.num_changes_description_new_sprint = num_changes_description_new_sprint
        self.original_acceptance_criteria_sprint = original_acceptance_criteria_sprint
        self.num_changes_acceptance_criteria_new_sprint = num_changes_acceptance_criteria_new_sprint
        self.original_story_points_sprint = original_story_points_sprint
        self.num_changes_story_points_new_sprint = num_changes_story_points_new_sprint
        self.has_change_summary_sprint = has_change_summary_sprint
        self.has_change_description_sprint = has_change_description_sprint
        self.has_change_acceptance_criteria_sprint = has_change_acceptance_criteria_sprint
        self.has_change_story_point_sprint = has_change_story_point_sprint
        self.different_words_minus_summary = different_words_minus_summary
        self.different_words_plus_summary = different_words_plus_summary
        self.different_words_minus_description = different_words_minus_description
        self.different_words_plus_description = different_words_plus_description
        self.different_words_minus_acceptance_criteria = different_words_minus_acceptance_criteria
        self.different_words_plus_acceptance_criteria = different_words_plus_acceptance_criteria
        self.different_words_ratio_all_summary = different_words_ratio_all_summary
        self.different_words_ratio_all_description = different_words_ratio_all_description
        self.different_words_ratio_all_acceptance_criteria = different_words_ratio_all_acceptance_criteria
        self.different_words_minus_summary_sprint = different_words_minus_summary_sprint
        self.different_words_plus_summary_sprint = different_words_plus_summary_sprint
        self.different_words_minus_description_sprint = different_words_minus_description_sprint
        self.different_words_plus_description_sprint = different_words_plus_description_sprint
        self.different_words_minus_acceptance_criteria_sprint = different_words_minus_acceptance_criteria_sprint
        self.different_words_plus_acceptance_criteria_sprint = different_words_plus_acceptance_criteria_sprint
        self.different_words_ratio_all_summary_sprint = different_words_ratio_all_summary_sprint
        self.different_words_ratio_all_description_sprint = different_words_ratio_all_description_sprint
        self.different_words_ratio_all_acceptance_criteria_sprint = different_words_ratio_all_acceptance_criteria_sprint
        self.num_comments_before_sprint = num_comments_before_sprint
        self.num_comments_after_sprint = num_comments_after_sprint
        self.num_different_words_all_text_sprint_new = num_different_words_all_text_sprint_new
        self.num_ratio_words_all_text_sprint_new = num_ratio_words_all_text_sprint_new
        self.num_changes_text_before_sprint = num_changes_text_before_sprint
        self.num_changes_story_point_before_sprint = num_changes_story_point_before_sprint
        self.time_status_close = time_status_close


"""
======================================================================
create table which is saving the bugs info
======================================================================
"""


class NamesBugsIssueLinksOS:
    def __init__(self, issue_key: str, project_key: str, bug_issue_link: str, chronological_number: Optional[int] = None):
        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.bug_issue_link = not_Null(bug_issue_link)
        self.chronological_number = chronological_number


"""
======================================================================
create table which is saving the sab tasks info
======================================================================
"""


class SabTaskNamesOS:
    def __init__(self, issue_key: str, project_key: str, sub_task_name: str, chronological_number: Optional[int] = None):
        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.sub_task_name = not_Null(sub_task_name)
        self.chronological_number = chronological_number


"""
======================================================================
create table which is saving the sprints info
======================================================================
"""


class SprintsOS:
    def __init__(self, issue_key: str, project_key: str, sprint_name: str, start_date: Optional[datetime] = None,
                 end_date: Optional[datetime] = None, is_over: Optional[int] = None,
                 chronological_number: Optional[int] = None):
        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.sprint_name = not_Null(sprint_name)
        self.start_date = start_date
        self.end_date = end_date
        self.is_over = is_over
        self.chronological_number = chronological_number


"""
======================================================================
create table which is saving the versions info
======================================================================
"""


class VersionsOS:
    def __init__(self, issue_key: str, project_key: str, version: str, chronological_number: Optional[int] = None):
        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.version = not_Null(version)
        self.chronological_number = chronological_number