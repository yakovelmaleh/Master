import pandas as pd
from typing import Optional
from datetime import datetime
from typing import get_origin, get_args, Union
import inspect

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
    return element


class Changes:
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


class ChangesWithWords(Changes):
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, is_diff_more_than_ten: int = None,
                 chronological_number: int = None, ratio_different_char_next: float = None,
                 ratio_different_word_next: float = None,
                 num_different_char_minus_next: int = None, num_different_char_plus_next: int = None,
                 num_different_char_all_next: int = None, num_different_word_minus_next: int = None,
                 num_different_word_plus_next: int = None, num_different_word_all_next: int = None,
                 ratio_different_char_last: float = None, ratio_different_word_last: float = None,
                 num_different_char_minus_last: int = None, num_different_char_plus_last: int = None,
                 num_different_char_all_last: int = None, num_different_word_minus_last: int = None,
                 num_different_word_plus_last: int = None, num_different_word_all_last: int = None):
        super().__init__(
            issue_key=issue_key,
            project_key=project_key,
            author=author,
            created=created,
            from_string=from_string,
            to_string=to_string,
            if_change_first_hour=if_change_first_hour,
            different_time_from_creat=different_time_from_creat,
            is_first_setup=is_first_setup,
            chronological_number=chronological_number
        )
        self.is_diff_more_than_ten = is_diff_more_than_ten
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


class AllChangesOS(Changes):
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, field: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, chronological_number: int = None,
                 time_add_to_sprint: pd.Timestamp = None, is_after_sprint: int = None,
                 time_from_sprint: float = None, is_after_close: int = None):
        super().__init__(
            issue_key=not_Null(issue_key),
            project_key=not_Null(project_key),
            author=author,
            created=created,
            from_string=from_string,
            to_string=to_string,
            if_change_first_hour=if_change_first_hour,
            different_time_from_creat=different_time_from_creat,
            is_first_setup=is_first_setup,
            chronological_number=not_Null(chronological_number)
        )
        self.field = field
        self.time_add_to_sprint = time_add_to_sprint
        self.is_after_sprint = is_after_sprint
        self.time_from_sprint = time_from_sprint
        self.is_after_close = is_after_close


def createAllChangesOSObjectFromDataFrame(df: pd.Series) -> AllChangesOS:
    return AllChangesOS(
        issue_key=convert_value_by_table(AllChangesOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(AllChangesOS, 'project_key', df['project_key']),
        author=convert_value_by_table(AllChangesOS, 'author', df['author']),
        created=convert_value_by_table(AllChangesOS, 'created', df['created']),
        from_string=convert_value_by_table(AllChangesOS, 'from_string', df['from_string']),
        to_string=convert_value_by_table(AllChangesOS, 'to_string', df['to_string']),
        if_change_first_hour=
        convert_value_by_table(AllChangesOS, 'if_change_first_hour', df['if_change_first_hour']),
        different_time_from_creat=
        convert_value_by_table(AllChangesOS, 'different_time_from_creat', df['different_time_from_creat']),
        is_first_setup=convert_value_by_table(AllChangesOS, 'is_first_setup', df['is_first_setup']),
        chronological_number=convert_value_by_table(AllChangesOS, 'chronological_number', df['chronological_number']),
        field=convert_value_by_table(AllChangesOS, 'field', df['field']),
        time_add_to_sprint=convert_value_by_table(AllChangesOS, 'time_add_to_sprint', df['time_add_to_sprint']),
        is_after_sprint=convert_value_by_table(AllChangesOS, 'is_after_sprint', df['is_after_sprint']),
        time_from_sprint=convert_value_by_table(AllChangesOS, 'time_from_sprint', df['time_from_sprint']),
        is_after_close=convert_value_by_table(AllChangesOS, 'is_after_close', df['is_after_close']))

"""
======================================================================
create table which is saving all the changes in description field
======================================================================
"""


class ChangesDescriptionOS(ChangesWithWords):
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, is_diff_more_than_ten: int = None,
                 chronological_number: int = None, ratio_different_char_next: float = None,
                 ratio_different_word_next: float = None,
                 num_different_char_minus_next: int = None, num_different_char_plus_next: int = None,
                 num_different_char_all_next: int = None, num_different_word_minus_next: int = None,
                 num_different_word_plus_next: int = None, num_different_word_all_next: int = None,
                 ratio_different_char_last: float = None, ratio_different_word_last: float = None,
                 num_different_char_minus_last: int = None, num_different_char_plus_last: int = None,
                 num_different_char_all_last: int = None, num_different_word_minus_last: int = None,
                 num_different_word_plus_last: int = None, num_different_word_all_last: int = None):
        super().__init__(
            issue_key=not_Null(issue_key),
            project_key=not_Null(project_key),
            author=author,
            created=created,
            from_string=from_string,
            to_string=to_string,
            if_change_first_hour=if_change_first_hour,
            different_time_from_creat=different_time_from_creat,
            is_first_setup=is_first_setup,
            is_diff_more_than_ten=is_diff_more_than_ten,
            chronological_number=not_Null(chronological_number),
            ratio_different_char_next=ratio_different_char_next,
            ratio_different_word_next=ratio_different_word_next,
            num_different_char_minus_next=num_different_char_minus_next,
            num_different_char_plus_next=num_different_char_plus_next,
            num_different_char_all_next=num_different_char_all_next,
            num_different_word_minus_next=num_different_word_minus_next,
            num_different_word_plus_next=num_different_word_plus_next,
            num_different_word_all_next=num_different_word_all_next,
            ratio_different_char_last=ratio_different_char_last,
            ratio_different_word_last=ratio_different_word_last,
            num_different_char_minus_last=num_different_char_minus_last,
            num_different_char_plus_last=num_different_char_plus_last,
            num_different_char_all_last=num_different_char_all_last,
            num_different_word_minus_last=num_different_word_minus_last,
            num_different_word_plus_last=num_different_word_plus_last,
            num_different_word_all_last=num_different_word_all_last)


def createChangesDescriptionOSObjectFromDataFrame(df: pd.Series) -> ChangesDescriptionOS:
    return ChangesDescriptionOS(
        issue_key=convert_value_by_table(ChangesDescriptionOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(ChangesDescriptionOS, 'project_key', df['project_key']),
        author=convert_value_by_table(ChangesDescriptionOS, 'author', df['author']),
        created=convert_value_by_table(ChangesDescriptionOS, 'created', df['created']),
        from_string=convert_value_by_table(ChangesDescriptionOS, 'from_string', df['from_string']),
        to_string=convert_value_by_table(ChangesDescriptionOS, 'to_string', df['to_string']),
        if_change_first_hour=
        convert_value_by_table(ChangesDescriptionOS, 'if_change_first_hour', df['if_change_first_hour']),
        different_time_from_creat=
        convert_value_by_table(ChangesDescriptionOS, 'different_time_from_creat', df['different_time_from_creat']),
        is_first_setup=convert_value_by_table(ChangesDescriptionOS, 'is_first_setup', df['is_first_setup']),
        is_diff_more_than_ten=convert_value_by_table(ChangesDescriptionOS, 'is_diff_more_than_ten', df['is_diff_more_than_ten']),
        ratio_different_char_next=convert_value_by_table(ChangesDescriptionOS, 'ratio_different_char_next',
                                                         df['ratio_different_char_next']),
        ratio_different_word_next=convert_value_by_table(ChangesDescriptionOS, 'ratio_different_word_next',
                                                         df['ratio_different_word_next']),
        num_different_char_minus_next=convert_value_by_table(ChangesDescriptionOS, 'num_different_char_minus_next',
                                                             df['num_different_char_minus_next']),
        num_different_char_plus_next=convert_value_by_table(ChangesDescriptionOS, 'num_different_char_plus_next',
                                                            df['num_different_char_plus_next']),
        num_different_char_all_next=convert_value_by_table(ChangesDescriptionOS, 'num_different_char_all_next',
                                                           df['num_different_char_all_next']),
        num_different_word_minus_next=convert_value_by_table(ChangesDescriptionOS, 'num_different_word_minus_next',
                                                             df['num_different_word_minus_next']),
        num_different_word_plus_next=convert_value_by_table(ChangesDescriptionOS, 'num_different_word_plus_next',
                                                            df['num_different_word_plus_next']),
        num_different_word_all_next=convert_value_by_table(ChangesDescriptionOS, 'num_different_word_all_next',
                                                           df['num_different_word_all_next']),
        ratio_different_char_last=convert_value_by_table(ChangesDescriptionOS, 'ratio_different_char_last',
                                                         df['ratio_different_char_last']),
        ratio_different_word_last=convert_value_by_table(ChangesDescriptionOS, 'ratio_different_word_last',
                                                         df['ratio_different_word_last']),
        num_different_char_minus_last=convert_value_by_table(ChangesDescriptionOS, 'num_different_char_minus_last',
                                                             df['num_different_char_minus_last']),
        num_different_char_plus_last=convert_value_by_table(ChangesDescriptionOS, 'num_different_char_plus_last',
                                                            df['num_different_char_plus_last']),
        num_different_char_all_last=convert_value_by_table(ChangesDescriptionOS, 'num_different_char_all_last',
                                                           df['num_different_char_all_last']),
        num_different_word_minus_last=convert_value_by_table(ChangesDescriptionOS, 'num_different_word_minus_last',
                                                             df['num_different_word_minus_last']),
        num_different_word_plus_last=convert_value_by_table(ChangesDescriptionOS, 'num_different_word_plus_last',
                                                            df['num_different_word_plus_last']),
        num_different_word_all_last=convert_value_by_table(ChangesDescriptionOS, 'num_different_word_all_last',
                                                           df['num_different_word_all_last']),
        chronological_number=convert_value_by_table(ChangesDescriptionOS, 'chronological_number', df['chronological_number']))


"""
======================================================================
create table which is saving all the changes in sprint 
======================================================================
"""


class ChangesSprintOS(Changes):
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, chronological_number: int = None):
        super().__init__(
            issue_key=not_Null(issue_key),
            project_key=not_Null(project_key),
            author=author,
            created=created,
            from_string=from_string,
            to_string=to_string,
            if_change_first_hour=if_change_first_hour,
            different_time_from_creat=different_time_from_creat,
            is_first_setup=is_first_setup,
            chronological_number=not_Null(chronological_number))


def createChangesSprintOSObjectFromDataFrame(df: pd.Series) -> ChangesSprintOS:
    return ChangesSprintOS(
        issue_key=convert_value_by_table(ChangesSprintOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(ChangesSprintOS, 'project_key', df['project_key']),
        author=convert_value_by_table(ChangesSprintOS, 'author', df['author']),
        created=convert_value_by_table(ChangesSprintOS, 'created', df['created']),
        from_string=convert_value_by_table(ChangesSprintOS, 'from_string', df['from_string']),
        to_string=convert_value_by_table(ChangesSprintOS, 'to_string', df['to_string']),
        if_change_first_hour=
        convert_value_by_table(ChangesSprintOS, 'if_change_first_hour', df['if_change_first_hour']),
        different_time_from_creat=
        convert_value_by_table(ChangesSprintOS, 'different_time_from_creat', df['different_time_from_creat']),
        is_first_setup=convert_value_by_table(ChangesSprintOS, 'is_first_setup', df['is_first_setup']),
        chronological_number=convert_value_by_table(ChangesSprintOS, 'chronological_number', df['chronological_number']))


"""
======================================================================
create table which is saving all the changes in story point field 
======================================================================
"""


class ChangesStoryPointsOS(Changes):
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, chronological_number: int = None):
        super().__init__(
            issue_key=not_Null(issue_key),
            project_key=not_Null(project_key),
            author=author,
            created=created,
            from_string=from_string,
            to_string=to_string,
            if_change_first_hour=if_change_first_hour,
            different_time_from_creat=different_time_from_creat,
            is_first_setup=is_first_setup,
            chronological_number=not_Null(chronological_number))


def createChangesStoryPointsOSObjectFromDataFrame(df: pd.Series) -> ChangesStoryPointsOS:
    return ChangesStoryPointsOS(
        issue_key=convert_value_by_table(ChangesStoryPointsOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(ChangesStoryPointsOS, 'project_key', df['project_key']),
        author=convert_value_by_table(ChangesStoryPointsOS, 'author', df['author']),
        created=convert_value_by_table(ChangesStoryPointsOS, 'created', df['created']),
        from_string=convert_value_by_table(ChangesStoryPointsOS, 'from_string', df['from_string']),
        to_string=convert_value_by_table(ChangesStoryPointsOS, 'to_string', df['to_string']),
        if_change_first_hour=
        convert_value_by_table(ChangesStoryPointsOS, 'if_change_first_hour', df['if_change_first_hour']),
        different_time_from_creat=
        convert_value_by_table(ChangesStoryPointsOS, 'different_time_from_creat', df['different_time_from_creat']),
        is_first_setup=convert_value_by_table(ChangesStoryPointsOS, 'is_first_setup', df['is_first_setup']),
        chronological_number=convert_value_by_table(ChangesStoryPointsOS, 'chronological_number', df['chronological_number']))


"""
======================================================================
create table which is saving all the changes in summary field 
======================================================================
"""


class ChangesSummaryOS(ChangesWithWords):
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, is_diff_more_than_ten: int = None,
                 chronological_number: int = None, ratio_different_char_next: float = None,
                 ratio_different_word_next: float = None,
                 num_different_char_minus_next: int = None, num_different_char_plus_next: int = None,
                 num_different_char_all_next: int = None, num_different_word_minus_next: int = None,
                 num_different_word_plus_next: int = None, num_different_word_all_next: int = None,
                 ratio_different_char_last: float = None, ratio_different_word_last: float = None,
                 num_different_char_minus_last: int = None, num_different_char_plus_last: int = None,
                 num_different_char_all_last: int = None, num_different_word_minus_last: int = None,
                 num_different_word_plus_last: int = None, num_different_word_all_last: int = None):
        super().__init__(
            issue_key=not_Null(issue_key),
            project_key=not_Null(project_key),
            author=author,
            created=created,
            from_string=from_string,
            to_string=to_string,
            if_change_first_hour=if_change_first_hour,
            different_time_from_creat=different_time_from_creat,
            is_first_setup=is_first_setup,
            is_diff_more_than_ten=is_diff_more_than_ten,
            chronological_number=not_Null(chronological_number),
            ratio_different_char_next=ratio_different_char_next,
            ratio_different_word_next=ratio_different_word_next,
            num_different_char_minus_next=num_different_char_minus_next,
            num_different_char_plus_next=num_different_char_plus_next,
            num_different_char_all_next=num_different_char_all_next,
            num_different_word_minus_next=num_different_word_minus_next,
            num_different_word_plus_next=num_different_word_plus_next,
            num_different_word_all_next=num_different_word_all_next,
            ratio_different_char_last=ratio_different_char_last,
            ratio_different_word_last=ratio_different_word_last,
            num_different_char_minus_last=num_different_char_minus_last,
            num_different_char_plus_last=num_different_char_plus_last,
            num_different_char_all_last=num_different_char_all_last,
            num_different_word_minus_last=num_different_word_minus_last,
            num_different_word_plus_last=num_different_word_plus_last,
            num_different_word_all_last=num_different_word_all_last)


def createChangesSummaryOSObjectFromDataFrame(df: pd.Series) -> ChangesSummaryOS:
    return ChangesSummaryOS(
        issue_key=convert_value_by_table(ChangesSummaryOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(ChangesSummaryOS, 'project_key', df['project_key']),
        author=convert_value_by_table(ChangesSummaryOS, 'author', df['author']),
        created=convert_value_by_table(ChangesSummaryOS, 'created', df['created']),
        from_string=convert_value_by_table(ChangesSummaryOS, 'from_string', df['from_string']),
        to_string=convert_value_by_table(ChangesSummaryOS, 'to_string', df['to_string']),
        if_change_first_hour=
        convert_value_by_table(ChangesSummaryOS, 'if_change_first_hour', df['if_change_first_hour']),
        different_time_from_creat=
        convert_value_by_table(ChangesSummaryOS, 'different_time_from_creat', df['different_time_from_creat']),
        is_first_setup=convert_value_by_table(ChangesSummaryOS, 'is_first_setup', df['is_first_setup']),
        is_diff_more_than_ten=convert_value_by_table(ChangesSummaryOS, 'is_diff_more_than_ten', df['is_diff_more_than_ten']),
        ratio_different_char_next=convert_value_by_table(ChangesSummaryOS, 'ratio_different_char_next',
                                                         df['ratio_different_char_next']),
        ratio_different_word_next=convert_value_by_table(ChangesSummaryOS, 'ratio_different_word_next',
                                                         df['ratio_different_word_next']),
        num_different_char_minus_next=convert_value_by_table(ChangesSummaryOS, 'num_different_char_minus_next',
                                                             df['num_different_char_minus_next']),
        num_different_char_plus_next=convert_value_by_table(ChangesSummaryOS, 'num_different_char_plus_next',
                                                            df['num_different_char_plus_next']),
        num_different_char_all_next=convert_value_by_table(ChangesSummaryOS, 'num_different_char_all_next',
                                                           df['num_different_char_all_next']),
        num_different_word_minus_next=convert_value_by_table(ChangesSummaryOS, 'num_different_word_minus_next',
                                                             df['num_different_word_minus_next']),
        num_different_word_plus_next=convert_value_by_table(ChangesSummaryOS, 'num_different_word_plus_next',
                                                            df['num_different_word_plus_next']),
        num_different_word_all_next=convert_value_by_table(ChangesSummaryOS, 'num_different_word_all_next',
                                                           df['num_different_word_all_next']),
        ratio_different_char_last=convert_value_by_table(ChangesSummaryOS, 'ratio_different_char_last',
                                                         df['ratio_different_char_last']),
        ratio_different_word_last=convert_value_by_table(ChangesSummaryOS, 'ratio_different_word_last',
                                                         df['ratio_different_word_last']),
        num_different_char_minus_last=convert_value_by_table(ChangesSummaryOS, 'num_different_char_minus_last',
                                                             df['num_different_char_minus_last']),
        num_different_char_plus_last=convert_value_by_table(ChangesSummaryOS, 'num_different_char_plus_last',
                                                            df['num_different_char_plus_last']),
        num_different_char_all_last=convert_value_by_table(ChangesSummaryOS, 'num_different_char_all_last',
                                                           df['num_different_char_all_last']),
        num_different_word_minus_last=convert_value_by_table(ChangesSummaryOS, 'num_different_word_minus_last',
                                                             df['num_different_word_minus_last']),
        num_different_word_plus_last=convert_value_by_table(ChangesSummaryOS, 'num_different_word_plus_last',
                                                            df['num_different_word_plus_last']),
        num_different_word_all_last=convert_value_by_table(ChangesSummaryOS, 'num_different_word_all_last',
                                                           df['num_different_word_all_last']),
        chronological_number=convert_value_by_table(ChangesSummaryOS, 'chronological_number', df['chronological_number']))


"""
======================================================================
create table which is saving all the changes in criteria field 
======================================================================
"""


class ChangesCriteriaOS(ChangesWithWords):
    def __init__(self, issue_key: str, project_key: str, author: str = None, created: pd.Timestamp = None,
                 from_string: str = None, to_string: str = None, if_change_first_hour: int = None,
                 different_time_from_creat: float = None, is_first_setup: int = None, is_diff_more_than_ten: int = None,
                 chronological_number: int = None, ratio_different_char_next: float = None,
                 ratio_different_word_next: float = None,
                 num_different_char_minus_next: int = None, num_different_char_plus_next: int = None,
                 num_different_char_all_next: int = None, num_different_word_minus_next: int = None,
                 num_different_word_plus_next: int = None, num_different_word_all_next: int = None,
                 ratio_different_char_last: float = None, ratio_different_word_last: float = None,
                 num_different_char_minus_last: int = None, num_different_char_plus_last: int = None,
                 num_different_char_all_last: int = None, num_different_word_minus_last: int = None,
                 num_different_word_plus_last: int = None, num_different_word_all_last: int = None):
        super().__init__(
            issue_key=not_Null(issue_key),
            project_key=not_Null(project_key),
            author=author,
            created=created,
            from_string=from_string,
            to_string=to_string,
            if_change_first_hour=if_change_first_hour,
            different_time_from_creat=different_time_from_creat,
            is_first_setup=is_first_setup,
            is_diff_more_than_ten=is_diff_more_than_ten,
            chronological_number=not_Null(chronological_number),
            ratio_different_char_next=ratio_different_char_next,
            ratio_different_word_next=ratio_different_word_next,
            num_different_char_minus_next=num_different_char_minus_next,
            num_different_char_plus_next=num_different_char_plus_next,
            num_different_char_all_next=num_different_char_all_next,
            num_different_word_minus_next=num_different_word_minus_next,
            num_different_word_plus_next=num_different_word_plus_next,
            num_different_word_all_next=num_different_word_all_next,
            ratio_different_char_last=ratio_different_char_last,
            ratio_different_word_last=ratio_different_word_last,
            num_different_char_minus_last=num_different_char_minus_last,
            num_different_char_plus_last=num_different_char_plus_last,
            num_different_char_all_last=num_different_char_all_last,
            num_different_word_minus_last=num_different_word_minus_last,
            num_different_word_plus_last=num_different_word_plus_last,
            num_different_word_all_last=num_different_word_all_last)


def createCChangesCriteriaOSObjectFromDataFrame(df: pd.Series) -> ChangesCriteriaOS:
    return ChangesCriteriaOS(
        issue_key=convert_value_by_table(ChangesCriteriaOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(ChangesCriteriaOS, 'project_key', df['project_key']),
        author=convert_value_by_table(ChangesCriteriaOS, 'author', df['author']),
        created=convert_value_by_table(ChangesCriteriaOS, 'created', df['created']),
        from_string=convert_value_by_table(ChangesCriteriaOS, 'from_string', df['from_string']),
        to_string=convert_value_by_table(ChangesCriteriaOS, 'to_string', df['to_string']),
        if_change_first_hour=
        convert_value_by_table(ChangesCriteriaOS, 'if_change_first_hour', df['if_change_first_hour']),
        different_time_from_creat=
        convert_value_by_table(ChangesCriteriaOS, 'different_time_from_creat', df['different_time_from_creat']),
        is_first_setup=convert_value_by_table(ChangesCriteriaOS, 'is_first_setup', df['is_first_setup']),
        is_diff_more_than_ten=convert_value_by_table(ChangesCriteriaOS, 'is_diff_more_than_ten', df['is_diff_more_than_ten']),
        ratio_different_char_next=convert_value_by_table(ChangesCriteriaOS, 'ratio_different_char_next',
                                                         df['ratio_different_char_next']),
        ratio_different_word_next=convert_value_by_table(ChangesCriteriaOS, 'ratio_different_word_next',
                                                         df['ratio_different_word_next']),
        num_different_char_minus_next=convert_value_by_table(ChangesCriteriaOS, 'num_different_char_minus_next',
                                                             df['num_different_char_minus_next']),
        num_different_char_plus_next=convert_value_by_table(ChangesCriteriaOS, 'num_different_char_plus_next',
                                                            df['num_different_char_plus_next']),
        num_different_char_all_next=convert_value_by_table(ChangesCriteriaOS, 'num_different_char_all_next',
                                                           df['num_different_char_all_next']),
        num_different_word_minus_next=convert_value_by_table(ChangesCriteriaOS, 'num_different_word_minus_next',
                                                             df['num_different_word_minus_next']),
        num_different_word_plus_next=convert_value_by_table(ChangesCriteriaOS, 'num_different_word_plus_next',
                                                            df['num_different_word_plus_next']),
        num_different_word_all_next=convert_value_by_table(ChangesCriteriaOS, 'num_different_word_all_next',
                                                           df['num_different_word_all_next']),
        ratio_different_char_last=convert_value_by_table(ChangesCriteriaOS, 'ratio_different_char_last',
                                                         df['ratio_different_char_last']),
        ratio_different_word_last=convert_value_by_table(ChangesCriteriaOS, 'ratio_different_word_last',
                                                         df['ratio_different_word_last']),
        num_different_char_minus_last=convert_value_by_table(ChangesCriteriaOS, 'num_different_char_minus_last',
                                                             df['num_different_char_minus_last']),
        num_different_char_plus_last=convert_value_by_table(ChangesCriteriaOS, 'num_different_char_plus_last',
                                                            df['num_different_char_plus_last']),
        num_different_char_all_last=convert_value_by_table(ChangesCriteriaOS, 'num_different_char_all_last',
                                                           df['num_different_char_all_last']),
        num_different_word_minus_last=convert_value_by_table(ChangesCriteriaOS, 'num_different_word_minus_last',
                                                             df['num_different_word_minus_last']),
        num_different_word_plus_last=convert_value_by_table(ChangesCriteriaOS, 'num_different_word_plus_last',
                                                            df['num_different_word_plus_last']),
        num_different_word_all_last=convert_value_by_table(ChangesCriteriaOS, 'num_different_word_all_last',
                                                           df['num_different_word_all_last']),
        chronological_number=convert_value_by_table(ChangesCriteriaOS, 'chronological_number', df['chronological_number']))


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


def createCommentsOSObjectFromDataFrame(df: pd.Series) -> CommentsOS:
    return CommentsOS(
        issue_key=convert_value_by_table(CommentsOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(CommentsOS, 'project_key', df['project_key']),
        id=convert_value_by_table(CommentsOS, 'id', df['id']),
        author=convert_value_by_table(CommentsOS, 'author', df['author']),
        created=convert_value_by_table(CommentsOS, 'created', df['created']),
        body=convert_value_by_table(CommentsOS, 'body', df['body']),
        chronological_number=convert_value_by_table(CommentsOS, 'chronological_number', df['chronological_number']),
        clean_comment=convert_value_by_table(CommentsOS, 'clean_comment', df['clean_comment'])
    )


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


def createCommitsInfoOSObjectFromDataFrame(df: pd.Series) -> CommitsInfoOS:
    return CommitsInfoOS(
        issue_key=convert_value_by_table(CommitsInfoOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(CommitsInfoOS, 'project_key', df['project_key']),
        commit=convert_value_by_table(CommitsInfoOS, 'commit', df['commit']),
        author=convert_value_by_table(CommitsInfoOS, 'author', df['author']),
        insertions=convert_value_by_table(CommitsInfoOS, 'insertions', df['insertions']),
        code_deletions=convert_value_by_table(CommitsInfoOS, 'code_deletions', df['code_deletions']),
        code_lines=convert_value_by_table(CommitsInfoOS, 'code_lines', df['code_lines']),
        files=convert_value_by_table(CommitsInfoOS, 'files', df['files']),
        chronological_number=convert_value_by_table(CommitsInfoOS, 'chronological_number', df['chronological_number']),
        message=convert_value_by_table(CommitsInfoOS, 'message', df['message'])
    )
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


def createComponentsOSObjectFromDataFrame(df: pd.Series) -> ComponentsOS:
    return ComponentsOS(
        issue_key=convert_value_by_table(ComponentsOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(ComponentsOS, 'project_key', df['project_key']),
        component=convert_value_by_table(ComponentsOS, 'component', df['component']),
        chronological_order=convert_value_by_table(ComponentsOS, 'chronological_order', df['chronological_order']),
    )


"""
======================================================================
create table which is saving all the fix_versions info 
======================================================================
"""


class FixVersionsOS:
    def __init__(self, issue_key: str, project_key: str, fix_version: str, chronological_number: int = None):
        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.fix_version = not_Null(fix_version)
        self.chronological_number = chronological_number


def createFixVersionsOSObjectFromDataFrame(df: pd.Series) -> FixVersionsOS:
    return FixVersionsOS(
        issue_key=convert_value_by_table(FixVersionsOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(FixVersionsOS, 'project_key', df['project_key']),
        fix_version=convert_value_by_table(FixVersionsOS, 'fix_version', df['fix_version']),
        chronological_number=convert_value_by_table(FixVersionsOS, 'chronological_number', df['chronological_number']),
    )
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


def createIssueLinksOSObjectFromDataFrame(df: pd.Series) -> IssueLinksOS:
    return IssueLinksOS(
        issue_key=convert_value_by_table(IssueLinksOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(IssueLinksOS, 'project_key', df['project_key']),
        issue_link=convert_value_by_table(IssueLinksOS, 'issue_link', df['issue_link']),
        issue_link_name_relation=convert_value_by_table(IssueLinksOS, 'issue_link_name_relation', df['issue_link_name_relation']),
        chronological_number=convert_value_by_table(IssueLinksOS, 'chronological_number', df['chronological_number']),
    )
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


def createLabelsOSObjectFromDataFrame(df: pd.Series) -> LabelsOS:
    return LabelsOS(
        issue_key=convert_value_by_table(LabelsOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(LabelsOS, 'project_key', df['project_key']),
        label=convert_value_by_table(LabelsOS, 'label', df['label']),
        chronological_number=convert_value_by_table(LabelsOS, 'chronological_number', df['chronological_number']),
    )
"""
======================================================================
create table which is saving all the attachment files info 
======================================================================
"""


class AttachmentOS:
    def __init__(self, issue_key: str, project_key: str, attachment_id: int, file_type: str, creator: str,
                 created: pd.Timestamp):
        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.attachment_id = not_Null(attachment_id)
        self.file_type = not_Null(file_type)
        self.creator = not_Null(creator)
        self.created = not_Null(created)


def createAttachmentOSObjectFromDataFrame(df: pd.Series) -> AttachmentOS:
    return AttachmentOS(
        issue_key=convert_value_by_table(AttachmentOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(AttachmentOS, 'project_key', df['project_key']),
        attachment_id=convert_value_by_table(AttachmentOS, 'attachment_id', df['attachment_id']),
        file_type=convert_value_by_table(AttachmentOS, 'file_type', df['file_type']),
        creator=convert_value_by_table(AttachmentOS, 'creator', df['creator']),
        created=convert_value_by_table(AttachmentOS, 'created', df['created'])
    )


class GitHubOS:
    def __init__(self, issue_key: str, project_key: str, chronological_number: int, URL: str, gitHubtype: str = None,
                 gitHubNumber: str = None, remoteLink: bool = False, externalURL: bool = False,
                 fromComment: bool = False):
        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.chronological_number = not_Null(chronological_number)
        self.gitHubtype = gitHubtype
        self.gitHubNumber = gitHubNumber,
        self.URL = URL,
        self.remoteLink = remoteLink
        self.externalURL = externalURL
        self.fromComment = fromComment


def createGitHubOSObjectFromDataFrame(df: pd.Series) -> GitHubOS:
    return GitHubOS(
        issue_key=convert_value_by_table(GitHubOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(GitHubOS, 'project_key', df['project_key']),
        chronological_number=convert_value_by_table(GitHubOS, 'chronological_number', df['chronological_number']),
        gitHubtype=convert_value_by_table(GitHubOS, 'gitHubtype', df['gitHubtype']),
        URL=convert_value_by_table(GitHubOS, 'URL', df['URL']),
        remoteLink=convert_value_by_table(GitHubOS, 'remoteLink', df['remoteLink']),
        externalURL=convert_value_by_table(GitHubOS, 'externalURL', df['externalURL']),
        fromComment=convert_value_by_table(GitHubOS, 'fromComment', df['fromComment'])
    )
"""
======================================================================
create the main table with all the nessecary data, and extra
======================================================================
"""


class MainTableOS:
    def __init__(self, issue_key: str, issue_id: str, project_key: str, created: pd.Timestamp, creator: str, reporter: str,
                 assignee: str = None, date_of_first_response: pd.Timestamp = None, epic_link: str = None,
                 issue_type: str = None, last_updated: pd.Timestamp = None, priority: str = None,
                 prograss: float = None,
                 prograss_total: float = None, resolution: str = None, resolution_date: pd.Timestamp = None,
                 status_name: str = None, status_description: str = None, time_estimate: float = None,
                 time_origion_estimate: float = None, time_spent: float = None, attachment: int = None,
                 is_attachment: int = None, pull_request_url: int = None, images: int = None,
                 is_images: int = None, team: str = None, story_point: float = None, summary: str = None,
                 description: str = None, acceptance_criteria: str = None, num_all_changes: int = None,
                 num_bugs_issue_link: int = None, num_changes_summary: int = None, num_changes_description: int = None,
                 num_changes_acceptance_criteria: int = None, num_changes_story_point: int = None,
                 num_comments: int = None,
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
                 original_acceptance_criteria_sprint: str = None,
                 num_changes_acceptance_criteria_new_sprint: int = None,
                 original_story_points_sprint: float = None, num_changes_story_points_new_sprint: int = None,
                 has_change_summary_sprint: int = None, has_change_description_sprint: int = None,
                 has_change_acceptance_criteria_sprint: int = None, has_change_story_point_sprint: int = None,
                 different_words_minus_summary: int = None, different_words_plus_summary: int = None,
                 different_words_minus_description: int = None, different_words_plus_description: int = None,
                 different_words_minus_acceptance_criteria: int = None,
                 different_words_plus_acceptance_criteria: int = None,
                 different_words_ratio_all_summary: float = None, different_words_ratio_all_description: float = None,
                 different_words_ratio_all_acceptance_criteria: float = None,
                 different_words_minus_summary_sprint: int = None,
                 different_words_plus_summary_sprint: int = None, different_words_minus_description_sprint: int = None,
                 different_words_plus_description_sprint: int = None,
                 different_words_minus_acceptance_criteria_sprint: int = None,
                 different_words_plus_acceptance_criteria_sprint: int = None,
                 different_words_ratio_all_summary_sprint: float = None,
                 different_words_ratio_all_description_sprint: float = None,
                 different_words_ratio_all_acceptance_criteria_sprint: float = None,
                 num_comments_before_sprint: int = None, num_comments_after_sprint: int = None,
                 num_different_words_all_text_sprint_new: int = None, num_ratio_words_all_text_sprint_new: float = None,
                 num_changes_text_before_sprint: int = None, num_changes_story_point_before_sprint: int = None,
                 time_status_close: pd.Timestamp = None, has_comments_after_new_sprint: str = None,
                 has_comments_before_new_sprint: str = None, summary_description_acceptance: str = None,
                 num_different_words_all_text: int = None, original_summary_description_acceptance_sprint:  str = None,
                 num_changes_summary_description_acceptance_sprint: int = None,
                 has_changes_summary_description_acceptance_sprint: int = None,
                 num_different_words_all_text_sprint: int = None):
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
        self.has_change_summary_description_acceptance_after_sprint =\
            has_change_summary_description_acceptance_after_sprint
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
        self.has_comments_after_new_sprint = has_comments_after_new_sprint
        self.has_comments_before_new_sprint = has_comments_before_new_sprint
        self.summary_description_acceptance = summary_description_acceptance
        self.num_different_words_all_text = num_different_words_all_text
        self.original_summary_description_acceptance_sprint =\
            original_summary_description_acceptance_sprint
        self.num_changes_summary_description_acceptance_sprint =\
            num_changes_summary_description_acceptance_sprint
        self.has_changes_summary_description_acceptance_sprint =\
            has_changes_summary_description_acceptance_sprint
        self.num_different_words_all_text_sprint = num_different_words_all_text_sprint


def createMainObjectFromDataFrame(df: pd.Series) -> MainTableOS:
    return MainTableOS(
        issue_key=convert_value_by_table(MainTableOS, 'issue_key', df['issue_key']),
        issue_id=convert_value_by_table(MainTableOS, 'issue_id', df['issue_id']),
        project_key=convert_value_by_table(MainTableOS, 'project_key', df['project_key']),
        created=convert_value_by_table(MainTableOS, 'created', df['created']),
        creator=convert_value_by_table(MainTableOS, 'creator', df['creator']),
        reporter=convert_value_by_table(MainTableOS, 'reporter', df['reporter']),
        assignee=convert_value_by_table(MainTableOS, 'assignee', df['assignee']),
        date_of_first_response=convert_value_by_table(MainTableOS, 'date_of_first_response',
                                                      df['date_of_first_response']),
        epic_link=convert_value_by_table(MainTableOS, 'epic_link', df['epic_link']),
        issue_type=convert_value_by_table(MainTableOS, 'issue_type', df['issue_type']),
        last_updated=convert_value_by_table(MainTableOS, 'last_updated', df['last_updated']),
        priority=convert_value_by_table(MainTableOS, 'priority', df['priority']),
        prograss=convert_value_by_table(MainTableOS, 'prograss', df['prograss']),
        prograss_total=convert_value_by_table(MainTableOS, 'prograss_total', df['prograss_total']),
        resolution=convert_value_by_table(MainTableOS, 'resolution', df['resolution']),
        resolution_date=convert_value_by_table(MainTableOS, 'resolution_date', df['resolution_date']),
        status_name=convert_value_by_table(MainTableOS, 'status_name', df['status_name']),
        status_description=convert_value_by_table(MainTableOS, 'status_description', df['status_description']),
        time_estimate=convert_value_by_table(MainTableOS, 'time_estimate', df['time_estimate']),
        time_origion_estimate=convert_value_by_table(MainTableOS, 'time_origion_estimate', df['time_origion_estimate']),
        time_spent=convert_value_by_table(MainTableOS, 'time_spent', df['time_spent']),
        attachment=convert_value_by_table(MainTableOS, 'attachment', df['attachment']),
        is_attachment=convert_value_by_table(MainTableOS, 'is_attachment', df['is_attachment']),
        pull_request_url=convert_value_by_table(MainTableOS, 'pull_request_url', df['pull_request_url']),
        images=convert_value_by_table(MainTableOS, 'images', df['images']),
        is_images=convert_value_by_table(MainTableOS, 'is_images', df['is_images']),
        team=convert_value_by_table(MainTableOS, 'team', df['team']),
        story_point=convert_value_by_table(MainTableOS, 'story_point', df['story_point']),
        summary=convert_value_by_table(MainTableOS, 'summary', df['summary']),
        description=convert_value_by_table(MainTableOS, 'description', df['description']),
        acceptance_criteria=convert_value_by_table(MainTableOS, 'acceptance_criteria', df['acceptance_criteria']),
        num_all_changes=convert_value_by_table(MainTableOS, 'num_all_changes', df['num_all_changes']),
        num_bugs_issue_link=convert_value_by_table(MainTableOS, 'num_bugs_issue_link', df['num_bugs_issue_link']),
        num_changes_summary=convert_value_by_table(MainTableOS, 'num_changes_summary', df['num_changes_summary']),
        num_changes_description=convert_value_by_table(MainTableOS, 'num_changes_description',
                                                       df['num_changes_description']),
        num_changes_acceptance_criteria=convert_value_by_table(MainTableOS, 'num_changes_acceptance_criteria',
                                                               df['num_changes_acceptance_criteria']),
        num_changes_story_point=convert_value_by_table(MainTableOS, 'num_changes_story_point',
                                                       df['num_changes_story_point']),
        num_comments=convert_value_by_table(MainTableOS, 'num_comments', df['num_comments']),
        num_issue_links=convert_value_by_table(MainTableOS, 'num_issue_links', df['num_issue_links']),
        num_of_commits=convert_value_by_table(MainTableOS, 'num_of_commits', df['num_of_commits']),
        num_sprints=convert_value_by_table(MainTableOS, 'num_sprints', df['num_sprints']),
        num_sub_tasks=convert_value_by_table(MainTableOS, 'num_sub_tasks', df['num_sub_tasks']),
        num_watchers=convert_value_by_table(MainTableOS, 'num_watchers', df['num_watchers']),
        num_worklog=convert_value_by_table(MainTableOS, 'num_worklog', df['num_worklog']),
        num_versions=convert_value_by_table(MainTableOS, 'num_versions', df['num_versions']),
        num_fix_versions=convert_value_by_table(MainTableOS, 'num_fix_versions', df['num_fix_versions']),
        num_labels=convert_value_by_table(MainTableOS, 'num_labels', df['num_labels']),
        num_components=convert_value_by_table(MainTableOS, 'num_components', df['num_components']),
        original_summary=convert_value_by_table(MainTableOS, 'original_summary', df['original_summary']),
        num_changes_summary_new=convert_value_by_table(MainTableOS, 'num_changes_summary_new',
                                                       df['num_changes_summary_new']),
        original_description=convert_value_by_table(MainTableOS, 'original_description', df['original_description']),
        num_changes_description_new=convert_value_by_table(MainTableOS, 'num_changes_description_new',
                                                           df['num_changes_description_new']),
        original_acceptance_criteria=convert_value_by_table(MainTableOS, 'original_acceptance_criteria',
                                                            df['original_acceptance_criteria']),
        num_changes_acceptance_criteria_new=convert_value_by_table(MainTableOS, 'num_changes_acceptance_criteria_new',
                                                                   df['num_changes_acceptance_criteria_new']),
        original_story_points=convert_value_by_table(MainTableOS, 'original_story_points', df['original_story_points']),
        num_changes_story_points_new=convert_value_by_table(MainTableOS, 'num_changes_story_points_new',
                                                            df['num_changes_story_points_new']),
        has_change_summary=convert_value_by_table(MainTableOS, 'has_change_summary', df['has_change_summary']),
        has_change_description=convert_value_by_table(MainTableOS, 'has_change_description',
                                                      df['has_change_description']),
        has_change_acceptance_criteria=convert_value_by_table(MainTableOS, 'has_change_acceptance_criteria',
                                                              df['has_change_acceptance_criteria']),
        has_change_story_point=convert_value_by_table(MainTableOS, 'has_change_story_point',
                                                      df['has_change_story_point']),
        num_changes_sprint=convert_value_by_table(MainTableOS, 'num_changes_sprint', df['num_changes_sprint']),
        original_summary_description_acceptance=convert_value_by_table(MainTableOS,
                                                                       'original_summary_description_acceptance',
                                                                       df['original_summary_description_acceptance']),
        num_changes_summary_description_acceptance=
        convert_value_by_table(MainTableOS,'num_changes_summary_description_acceptance',
                               df['num_changes_summary_description_acceptance']),
        has_changes_summary_description_acceptance=
        convert_value_by_table(MainTableOS,'has_changes_summary_description_acceptance',
                               df['has_changes_summary_description_acceptance']),
        has_change_summary_description_acceptance_after_sprint=
        convert_value_by_table(MainTableOS,'has_change_summary_description_acceptance_after_sprint',
                               df['has_change_summary_description_acceptance_after_sprint']),
        has_change_summary_after_sprint=convert_value_by_table(MainTableOS, 'has_change_summary_after_sprint',
                                                               df['has_change_summary_after_sprint']),
        has_change_description_after_sprint=convert_value_by_table(MainTableOS, 'has_change_description_after_sprint',
                                                                   df['has_change_description_after_sprint']),
        has_change_acceptance_criteria_after_sprint=
        convert_value_by_table(MainTableOS,'has_change_acceptance_criteria_after_sprint',
                               df['has_change_acceptance_criteria_after_sprint']),
        time_add_to_sprint=convert_value_by_table(MainTableOS, 'time_add_to_sprint', df['time_add_to_sprint']),
        original_summary_sprint=convert_value_by_table(MainTableOS, 'original_summary_sprint',
                                                       df['original_summary_sprint']),
        num_changes_summary_new_sprint=convert_value_by_table(MainTableOS, 'num_changes_summary_new_sprint',
                                                              df['num_changes_summary_new_sprint']),
        original_description_sprint=convert_value_by_table(MainTableOS, 'original_description_sprint',
                                                           df['original_description_sprint']),
        num_changes_description_new_sprint=convert_value_by_table(MainTableOS, 'num_changes_description_new_sprint',
                                                                  df['num_changes_description_new_sprint']),
        original_acceptance_criteria_sprint=convert_value_by_table(MainTableOS, 'original_acceptance_criteria_sprint',
                                                                   df['original_acceptance_criteria_sprint']),
        num_changes_acceptance_criteria_new_sprint=
        convert_value_by_table(MainTableOS,'num_changes_acceptance_criteria_new_sprint',
                               df['num_changes_acceptance_criteria_new_sprint']),
        original_story_points_sprint=convert_value_by_table(MainTableOS, 'original_story_points_sprint',
                                                            df['original_story_points_sprint']),
        num_changes_story_points_new_sprint=convert_value_by_table(MainTableOS, 'num_changes_story_points_new_sprint',
                                                                   df['num_changes_story_points_new_sprint']),
        has_change_summary_sprint=convert_value_by_table(MainTableOS, 'has_change_summary_sprint',
                                                         df['has_change_summary_sprint']),
        has_change_description_sprint=convert_value_by_table(MainTableOS, 'has_change_description_sprint',
                                                             df['has_change_description_sprint']),
        has_change_acceptance_criteria_sprint=convert_value_by_table(MainTableOS,
                                                                     'has_change_acceptance_criteria_sprint',
                                                                     df['has_change_acceptance_criteria_sprint']),
        has_change_story_point_sprint=convert_value_by_table(MainTableOS, 'has_change_story_point_sprint',
                                                             df['has_change_story_point_sprint']),
        different_words_minus_summary=convert_value_by_table(MainTableOS, 'different_words_minus_summary',
                                                             df['different_words_minus_summary']),
        different_words_plus_summary=convert_value_by_table(MainTableOS, 'different_words_plus_summary',
                                                            df['different_words_plus_summary']),
        different_words_minus_description=convert_value_by_table(MainTableOS, 'different_words_minus_description',
                                                                 df['different_words_minus_description']),
        different_words_plus_description=convert_value_by_table(MainTableOS, 'different_words_plus_description',
                                                                df['different_words_plus_description']),
        different_words_minus_acceptance_criteria=
        convert_value_by_table(MainTableOS,'different_words_minus_acceptance_criteria',
                               df['different_words_minus_acceptance_criteria']),
        different_words_plus_acceptance_criteria=
        convert_value_by_table(MainTableOS,'different_words_plus_acceptance_criteria',
                               df['different_words_plus_acceptance_criteria']),
        different_words_ratio_all_summary=
        convert_value_by_table(MainTableOS, 'different_words_ratio_all_summary',
                               df['different_words_ratio_all_summary']),
        different_words_ratio_all_description=
        convert_value_by_table(MainTableOS,'different_words_ratio_all_description',
                               df['different_words_ratio_all_description']),
        different_words_ratio_all_acceptance_criteria=
        convert_value_by_table(MainTableOS, 'different_words_ratio_all_acceptance_criteria',
                               df['different_words_ratio_all_acceptance_criteria']),
        different_words_minus_summary_sprint=convert_value_by_table(MainTableOS, 'different_words_minus_summary_sprint',
                                                                    df['different_words_minus_summary_sprint']),
        different_words_plus_summary_sprint=convert_value_by_table(MainTableOS, 'different_words_plus_summary_sprint',
                                                                   df['different_words_plus_summary_sprint']),
        different_words_minus_description_sprint=convert_value_by_table(MainTableOS,
                                                                        'different_words_minus_description_sprint',
                                                                        df['different_words_minus_description_sprint']),
        different_words_plus_description_sprint=convert_value_by_table(MainTableOS,
                                                                       'different_words_plus_description_sprint',
                                                                       df['different_words_plus_description_sprint']),
        different_words_minus_acceptance_criteria_sprint=
        convert_value_by_table(MainTableOS, 'different_words_minus_acceptance_criteria_sprint',
                               df['different_words_minus_acceptance_criteria_sprint']),
        different_words_plus_acceptance_criteria_sprint=
        convert_value_by_table(MainTableOS,'different_words_plus_acceptance_criteria_sprint',
                               df['different_words_plus_acceptance_criteria_sprint']),
        different_words_ratio_all_summary_sprint=convert_value_by_table(MainTableOS,
                                                                        'different_words_ratio_all_summary_sprint',
                                                                        df['different_words_ratio_all_summary_sprint']),
        different_words_ratio_all_description_sprint=
        convert_value_by_table(MainTableOS, 'different_words_ratio_all_description_sprint',
                               df['different_words_ratio_all_description_sprint']),
        different_words_ratio_all_acceptance_criteria_sprint=
        convert_value_by_table(MainTableOS,'different_words_ratio_all_acceptance_criteria_sprint',
                               df['different_words_ratio_all_acceptance_criteria_sprint']),
        num_comments_before_sprint=convert_value_by_table(MainTableOS, 'num_comments_before_sprint',
                                                          df['num_comments_before_sprint']),
        num_comments_after_sprint=convert_value_by_table(MainTableOS, 'num_comments_after_sprint',
                                                         df['num_comments_after_sprint']),
        num_different_words_all_text_sprint_new=
        convert_value_by_table(MainTableOS,'num_different_words_all_text_sprint_new',
                               df['num_different_words_all_text_sprint_new']),
        num_ratio_words_all_text_sprint_new=
        convert_value_by_table(MainTableOS, 'num_ratio_words_all_text_sprint_new',
                               df['num_ratio_words_all_text_sprint_new']),
        num_changes_text_before_sprint=
        convert_value_by_table(MainTableOS, 'num_changes_text_before_sprint',
                               df['num_changes_text_before_sprint']),
        num_changes_story_point_before_sprint
        =convert_value_by_table(MainTableOS,'num_changes_story_point_before_sprint',
                                df['num_changes_story_point_before_sprint']),
        time_status_close=
        convert_value_by_table(MainTableOS, 'time_status_close', df['time_status_close']),
        has_comments_after_new_sprint=
        convert_value_by_table(MainTableOS, 'has_comments_after_new_sprint',
                               df['has_comments_after_new_sprint']),
        has_comments_before_new_sprint=
        convert_value_by_table(MainTableOS, 'has_comments_before_new_sprint',
                               df['has_comments_before_new_sprint']),
        summary_description_acceptance=
        convert_value_by_table(MainTableOS, 'summary_description_acceptance',
                               df['summary_description_acceptance']),
        num_different_words_all_text =
        convert_value_by_table(MainTableOS, 'num_different_words_all_text',
                               df['num_different_words_all_text']),
        original_summary_description_acceptance_sprint=
        convert_value_by_table(MainTableOS, 'original_summary_description_acceptance_sprint',
                               df['original_summary_description_acceptance_sprint']),
        num_changes_summary_description_acceptance_sprint=
        convert_value_by_table(MainTableOS, 'num_changes_summary_description_acceptance_sprint',
                               df['num_changes_summary_description_acceptance_sprint']),
        has_changes_summary_description_acceptance_sprint=
        convert_value_by_table(MainTableOS, 'has_changes_summary_description_acceptance_sprint',
                               df['has_changes_summary_description_acceptance_sprint']),
        num_different_words_all_text_sprint=
        convert_value_by_table(MainTableOS, 'num_different_words_all_text_sprint',
                               df['num_different_words_all_text_sprint'])
    )


"""
======================================================================
create table which is saving the bugs info
======================================================================
"""


class NamesBugsIssueLinksOS:
    def __init__(self, issue_key: str, project_key: str, bug_issue_link: str,
                 chronological_number: Optional[int] = None):
        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.bug_issue_link = not_Null(bug_issue_link)
        self.chronological_number = chronological_number


def createNamesBugsIssueLinksOSObjectFromDataFrame(df: pd.Series) -> NamesBugsIssueLinksOS:
    return NamesBugsIssueLinksOS(
        issue_key=convert_value_by_table(NamesBugsIssueLinksOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(NamesBugsIssueLinksOS, 'project_key', df['project_key']),
        chronological_number=convert_value_by_table(NamesBugsIssueLinksOS, 'chronological_number', df['chronological_number']),
        bug_issue_link=convert_value_by_table(NamesBugsIssueLinksOS, 'bug_issue_link', df['bug_issue_link'])
    )
"""
======================================================================
create table which is saving the sab tasks info
======================================================================
"""


class SubTaskNamesOS:
    def __init__(self, issue_key: str, project_key: str, sub_task_name: str,
                 chronological_number: Optional[int] = None):
        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.sub_task_name = not_Null(sub_task_name)
        self.chronological_number = chronological_number


def createSubTaskNamesOSObjectFromDataFrame(df: pd.Series) -> SubTaskNamesOS:
    return SubTaskNamesOS(
        issue_key=convert_value_by_table(SubTaskNamesOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(SubTaskNamesOS, 'project_key', df['project_key']),
        chronological_number=convert_value_by_table(SubTaskNamesOS, 'chronological_number', df['chronological_number']),
        sub_task_name=convert_value_by_table(SubTaskNamesOS, 'sub_task_name', df['sub_task_name'])
    )
"""
======================================================================
create table which is saving the sprints info
======================================================================
"""


class SprintsOS:
    def __init__(self, issue_key: str, project_key: str, sprint_name: str, start_date: pd.Timestamp = None,
                 end_date: pd.Timestamp = None, is_over: Optional[int] = None,
                 chronological_number: Optional[int] = None):
        self.issue_key = not_Null(issue_key)
        self.project_key = not_Null(project_key)
        self.sprint_name = not_Null(sprint_name)
        self.start_date = start_date
        self.end_date = end_date
        self.is_over = is_over
        self.chronological_number = chronological_number


def createSprintsOSObjectFromDataFrame(df: pd.Series) -> SprintsOS:
    return SprintsOS(
        issue_key=convert_value_by_table(SprintsOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(SprintsOS, 'project_key', df['project_key']),
        chronological_number=convert_value_by_table(SprintsOS, 'chronological_number', df['chronological_number']),
        start_date=convert_value_by_table(SprintsOS, 'start_date', df['start_date']),
        end_date=convert_value_by_table(SprintsOS, 'end_date', df['end_date']),
        is_over=convert_value_by_table(SprintsOS, 'is_over', df['is_over']),
        sprint_name=convert_value_by_table(SprintsOS, 'sprint_name', df['sprint_name'])
    )
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


def createVersionsOSObjectFromDataFrame(df: pd.Series) -> VersionsOS:
    return VersionsOS(
        issue_key=convert_value_by_table(VersionsOS, 'issue_key', df['issue_key']),
        project_key=convert_value_by_table(VersionsOS, 'project_key', df['project_key']),
        chronological_number=convert_value_by_table(VersionsOS, 'chronological_number', df['chronological_number']),
        version=convert_value_by_table(VersionsOS, 'version', df['version'])
    )


def convert_value_by_table(classType, propertyName, value):
    date_format = "%Y-%m-%d %H:%M:%S"
    propertyType = classType.__init__.__annotations__.get(propertyName, None)
    defaultType = inspect.signature(classType.__init__).parameters[propertyName].default

    if (value is None or pd.isna(value)) and defaultType is None:
        return None

    if get_origin(propertyType) is Union:
        if get_args(propertyType)[0] is datetime:
            return pd.Timestamp(datetime.strptime(value, date_format))

        return get_args(propertyType)[0](value)

    elif value is None or pd.isna(value):
        raise Exception(f" {classType} class has {propertyName} which should be from  {defaultType} type!!!")

    else:
        return propertyType(value)
