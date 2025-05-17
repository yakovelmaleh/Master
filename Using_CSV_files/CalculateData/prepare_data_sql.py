import json
import os.path

import pandas as pd
import math
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Create_DB as Create_DB
import Using_CSV_files.Load_Data_From_Jira_To_CSV.TableColumns as TableColumns
from typing import List
import Using_CSV_files.FilesActivity as FilesActivity
import Using_CSV_files.Load_Data_From_Jira_To_CSV.Logger as Logger


def getChangesFromComments(comments_ObjectList: List[TableColumns.CommentsOS], issue_name,
                           time_add_to_sprint_from_filtered_main):
    filtered_list_by_IK = list(filter(lambda comment: comment.issue_key == issue_name, comments_ObjectList))

    filtered_list_by_IK_and_created = \
        list(filter(lambda comment: comment.created > time_add_to_sprint_from_filtered_main,
                    filtered_list_by_IK))

    num_comments_after_new_sprint = len(filtered_list_by_IK_and_created)
    num_comments_before_new_sprint = len(filtered_list_by_IK) - num_comments_after_new_sprint

    return num_comments_after_new_sprint, num_comments_before_new_sprint


def getChangesWithoutWords(change_ObjectList: List[TableColumns.Changes], defaultValue, issue_name,
                           time_add_to_sprint_from_filtered_main=None):
    original_story_points_sprint = defaultValue
    num_changes_story_points_new_sprint = 0

    # IK == Issue_Key, Get the summary changes after enter to fist sprint
    if time_add_to_sprint_from_filtered_main is not None:
        filter_change_summary_based_IK_and_created = \
            list(filter(lambda x: (x.issue_key == issue_name) and
                                  (x.created > time_add_to_sprint_from_filtered_main) and
                                  (x.different_time_from_creat > 1),
                        change_ObjectList))
    else:
        filter_change_summary_based_IK_and_created = \
            list(filter(lambda x: (x.issue_key == issue_name) and
                                  (x.different_time_from_creat > 1),
                        change_ObjectList))

    # get the first summary change delta after enter to the first sprint
    min_val_of_different_time_from_creat_change_summary = \
        min(filter_change_summary_based_IK_and_created,
            key=lambda x: x.different_time_from_creat).different_time_from_creat if filter_change_summary_based_IK_and_created else 0

    # get the first summary change after enter to the first sprint (should be list in length of 1)
    change_sum_issue_sprint: List[TableColumns.Changes] = list(filter(
        lambda x: x.different_time_from_creat == min_val_of_different_time_from_creat_change_summary,
        filter_change_summary_based_IK_and_created))

    if len(change_sum_issue_sprint) > 0 and change_sum_issue_sprint[0].from_string is not None:
        change_sum_issue_sprint_object = change_sum_issue_sprint[0]

        original_story_points_sprint = change_sum_issue_sprint_object.from_string
        num_changes_story_points_new_sprint = len(filter_change_summary_based_IK_and_created)

    return original_story_points_sprint, num_changes_story_points_new_sprint


def getChangesWithWords(change_ObjectList: List[TableColumns.ChangesWithWords], defaultValue,
                        issue_name, time_add_to_sprint_from_filtered_main=None):
    original_summary_sprint = defaultValue
    num_changes_summary_new_sprint = 0
    num_different_word_minus_last_summary_new_sprint = 0
    num_different_word_plus_last_summary_new_sprint = 0

    # IK == Issue_Key, Get the summary changes after enter to fist sprint
    if time_add_to_sprint_from_filtered_main is not None:
        filter_change_summary_based_IK_and_created = \
            list(filter(lambda x: (x.issue_key == issue_name) and
                                  (x.created > time_add_to_sprint_from_filtered_main) and
                                  (x.different_time_from_creat > 1),
                        change_ObjectList))
    else:
        filter_change_summary_based_IK_and_created = \
            list(filter(lambda x: (x.issue_key == issue_name) and
                                  (x.different_time_from_creat > 1),
                        change_ObjectList))

    # get the first summary change delta after enter to the first sprint
    min_val_of_different_time_from_creat_change_summary = \
        min(filter_change_summary_based_IK_and_created,
            key=lambda x: x.different_time_from_creat).different_time_from_creat if filter_change_summary_based_IK_and_created else 0

    # get the first summary change after enter to the first sprint (should be list in length of 1)
    change_sum_issue_sprint: List[TableColumns.ChangesWithWords] = list(filter(
        lambda x: x.different_time_from_creat == min_val_of_different_time_from_creat_change_summary,
        filter_change_summary_based_IK_and_created))

    if len(change_sum_issue_sprint) > 0 and change_sum_issue_sprint[0].from_string is not None:
        change_sum_issue_sprint_object = change_sum_issue_sprint[0]

        original_summary_sprint = change_sum_issue_sprint_object.from_string
        num_changes_summary_new_sprint = len(filter_change_summary_based_IK_and_created)
        num_different_word_minus_last_summary_new_sprint = \
            change_sum_issue_sprint_object.num_different_word_minus_last
        num_different_word_plus_last_summary_new_sprint = \
            change_sum_issue_sprint_object.num_different_word_plus_last

    return (original_summary_sprint, num_changes_summary_new_sprint,
            num_different_word_minus_last_summary_new_sprint, num_different_word_plus_last_summary_new_sprint)


def add_cal_columns_(path_to_save, mainDataObjectList: List[TableColumns.MainTableOS],
                     change_summaryObjectList: List[TableColumns.ChangesSummaryOS],
                     change_descriptionObjectList: List[TableColumns.ChangesDescriptionOS],
                     changes_acceptanceObjectList: List[TableColumns.ChangesCriteriaOS],
                     change_storyPointsObjectList: List[TableColumns.ChangesStoryPointsOS],
                     comment_objectList: List[TableColumns.CommentsOS]):
    """
    function who add columns of original summary and original description and num_changes_summary_new and
    num_changes_description_new (if change is in the first hour and distance is less than 10 so num changes = 0
    and original description  = description.
    input- sql connection, sql query, the neseccary tables with the data and indicator of looking on sprint or status (True means sprint, the second not in use)
    """
    logger = Logger.get_logger_with_path_and_name(path_to_save, "prepare_data_sql")
    for i in range(0, len(mainDataObjectList)):
        main_tableObject: TableColumns.MainTableOS = mainDataObjectList[i]
        issue_name = main_tableObject.issue_key

        try:
            filter_main_list_by_issueKey: List[TableColumns.MainTableOS] = \
                list(filter(lambda x: x.issue_key == issue_name, mainDataObjectList))
            time_add_to_sprint_from_filtered_main = filter_main_list_by_issueKey[0].time_add_to_sprint

            # summary
            # get the information of summary changes after the first sprint
            (original_summary_sprint, num_changes_summary_new_sprint, num_different_word_minus_last_summary_new_sprint,
             num_different_word_plus_last_summary_new_sprint) = \
                getChangesWithWords(
                    change_ObjectList=change_summaryObjectList,
                    defaultValue=main_tableObject.summary,
                    issue_name=issue_name,
                    time_add_to_sprint_from_filtered_main=time_add_to_sprint_from_filtered_main)

            # get the information of summary changes
            (original_summary, num_changes_summary_new, num_different_word_minus_last_summary_new,
             num_different_word_plus_last_summary_new) = \
                getChangesWithWords(
                    change_ObjectList=change_summaryObjectList,
                    defaultValue=main_tableObject.summary,
                    issue_name=issue_name)

            # description
            # get the information of description changes after the first sprint
            (original_description_sprint, num_changes_description_new_sprint,
             num_different_word_minus_last_description_new_sprint,
             num_different_word_plus_last_description_new_sprint) = \
                getChangesWithWords(
                    change_ObjectList=change_descriptionObjectList,
                    defaultValue=main_tableObject.description,
                    issue_name=issue_name,
                    time_add_to_sprint_from_filtered_main=time_add_to_sprint_from_filtered_main)

            # get the information of description changes
            (original_description, num_changes_description_new, num_different_word_minus_last_description_new,
             num_different_word_plus_last_description_new) = \
                getChangesWithWords(change_ObjectList=change_descriptionObjectList,
                                    defaultValue=main_tableObject.description,
                                    issue_name=issue_name)

            # changes_acceptance
            # get the information of acceptance changes after the first sprint
            (original_acceptance_sprint, num_changes_acceptance_new_sprint,
             num_different_word_minus_last_acceptance_criteria_new_sprint,
             num_different_word_plus_last_acceptance_criteria_new_sprint) = \
                getChangesWithWords(
                    change_ObjectList=changes_acceptanceObjectList,
                    defaultValue=main_tableObject.acceptance_criteria,
                    issue_name=issue_name,
                    time_add_to_sprint_from_filtered_main=time_add_to_sprint_from_filtered_main)

            # get the information of acceptance changes
            (original_acceptance, num_changes_acceptance_new, num_different_word_minus_last_acceptance_criteria_new,
             num_different_word_plus_last_acceptance_criteria_new) = getChangesWithWords(
                change_ObjectList=change_descriptionObjectList,
                defaultValue=main_tableObject.acceptance_criteria,
                issue_name=issue_name)

            # story point
            # get the information of story points changes after the first sprint
            (original_story_points_sprint, num_changes_story_points_new_sprint) = \
                getChangesWithoutWords(
                    change_ObjectList=change_storyPointsObjectList,
                    defaultValue=main_tableObject.story_point,
                    issue_name=issue_name,
                    time_add_to_sprint_from_filtered_main=time_add_to_sprint_from_filtered_main)

            # get the information of acceptance changes
            (original_story_points, num_changes_story_points_new) = \
                getChangesWithoutWords(
                    change_ObjectList=change_storyPointsObjectList,
                    defaultValue=main_tableObject.story_point,
                    issue_name=issue_name)

            try:
                if math.isnan(float(original_story_points_sprint)):
                    original_story_points_sprint = None
                else:
                    original_story_points_sprint = float(original_story_points_sprint)
            except TypeError:
                original_story_points_sprint = None
            try:
                if math.isnan(float(original_story_points)):
                    original_story_points = None
                else:
                    original_story_points = float(original_story_points)
            except TypeError:
                original_story_points = None

            # comments
            num_comments_after_new_sprint, num_comments_before_new_sprint = \
                getChangesFromComments(
                    comments_ObjectList=comment_objectList,
                    issue_name=issue_name,
                    time_add_to_sprint_from_filtered_main=time_add_to_sprint_from_filtered_main)

            num_changes_summary_description_acceptance = (
                    num_changes_summary_new + num_changes_description_new + num_changes_acceptance_new)

            num_different_words_all_text = \
                (num_different_word_minus_last_summary_new + num_different_word_plus_last_summary_new +
                 num_different_word_minus_last_description_new +
                 num_different_word_plus_last_description_new +
                 num_different_word_minus_last_acceptance_criteria_new +
                 num_different_word_plus_last_acceptance_criteria_new)

            num_changes_summary_description_acceptance_sprint = \
                (num_changes_summary_new_sprint + num_changes_description_new_sprint +
                 num_changes_acceptance_new_sprint)

            num_different_words_all_text_sprint = (num_different_word_minus_last_summary_new_sprint +
                                                   num_different_word_plus_last_summary_new_sprint +
                                                   num_different_word_minus_last_description_new_sprint +
                                                   num_different_word_plus_last_description_new_sprint +
                                                   num_different_word_minus_last_acceptance_criteria_new_sprint +
                                                   num_different_word_plus_last_acceptance_criteria_new_sprint)

            num_changes_text_before_sprint = (num_changes_summary_description_acceptance -
                                              num_changes_summary_description_acceptance_sprint)

            num_changes_story_point_before_sprint = (num_changes_story_points_new -
                                                     num_changes_story_points_new_sprint)

            is_changes_summary_sprint = int(num_changes_summary_new_sprint > 0)
            is_changes_description_sprint = int(num_changes_description_new_sprint > 0)
            is_changes_story_point_sprint = int(num_changes_story_points_new_sprint > 0)
            is_changes_acceptance_sprint = int(num_changes_acceptance_new_sprint > 0)
            is_changes_summary = int(num_changes_summary_new > 0)
            is_changes_description = int(num_changes_description_new > 0)
            is_changes_story_point = int(num_changes_story_points_new > 0)
            is_changes_acceptance = int(num_changes_acceptance_new > 0)
            is_comments_before_new_sprint = int(num_comments_before_new_sprint > 0)
            is_comments_after_new_sprint = int(num_comments_after_new_sprint > 0)

            main_tableObject.original_summary_sprint = original_summary_sprint
            main_tableObject.num_changes_summary_new_sprint = int(num_changes_summary_new_sprint)
            main_tableObject.original_description_sprint = original_description_sprint
            main_tableObject.num_changes_description_new_sprint = num_changes_description_new_sprint
            main_tableObject.original_story_points_sprint = original_story_points_sprint
            main_tableObject.num_changes_story_points_new_sprint = num_changes_story_points_new_sprint
            main_tableObject.original_acceptance_criteria_sprint = original_acceptance_sprint
            main_tableObject.num_changes_acceptance_criteria_new_sprint = num_changes_acceptance_new_sprint
            main_tableObject.num_changes_summary_description_acceptance_sprint = \
                num_changes_summary_description_acceptance_sprint
            main_tableObject.has_changes_summary_description_acceptance_sprint = \
                int(num_changes_summary_description_acceptance_sprint > 0)

            main_tableObject.has_change_summary_sprint = is_changes_summary_sprint
            main_tableObject.has_change_description_sprint = is_changes_description_sprint
            main_tableObject.has_change_story_point_sprint = is_changes_story_point_sprint
            main_tableObject.has_change_acceptance_criteria_sprint = is_changes_acceptance_sprint
            main_tableObject.different_words_minus_summary_sprint = num_different_word_minus_last_summary_new_sprint
            main_tableObject.different_words_plus_summary_sprint = num_different_word_plus_last_summary_new_sprint
            main_tableObject.different_words_minus_description_sprint = \
                num_different_word_minus_last_description_new_sprint
            main_tableObject.different_words_plus_description_sprint = \
                num_different_word_plus_last_description_new_sprint
            main_tableObject.different_words_minus_acceptance_criteria_sprint = \
                num_different_word_minus_last_acceptance_criteria_new_sprint
            main_tableObject.different_words_plus_acceptance_criteria_sprint = \
                num_different_word_plus_last_acceptance_criteria_new_sprint
            main_tableObject.num_different_words_all_text_sprint = num_different_words_all_text_sprint

            main_tableObject.original_summary = original_summary
            main_tableObject.num_changes_summary_new = num_changes_summary_new
            main_tableObject.original_description = original_description
            main_tableObject.num_changes_description_new = num_changes_description_new
            main_tableObject.original_story_points = original_story_points
            main_tableObject.num_changes_story_points_new = num_changes_story_points_new
            main_tableObject.original_acceptance_criteria = original_acceptance
            main_tableObject.num_changes_acceptance_criteria_new = num_changes_acceptance_new
            main_tableObject.num_changes_summary_description_acceptance = num_changes_summary_description_acceptance
            main_tableObject.has_changes_summary_description_acceptance = \
                int(num_changes_summary_description_acceptance > 0)
            main_tableObject.has_change_summary = is_changes_summary
            main_tableObject.has_change_description = is_changes_description
            main_tableObject.has_change_story_point = is_changes_story_point
            main_tableObject.has_change_acceptance_criteria = is_changes_acceptance
            main_tableObject.different_words_minus_summary = num_different_word_minus_last_summary_new
            main_tableObject.different_words_plus_summary = num_different_word_plus_last_summary_new
            main_tableObject.different_words_minus_description = num_different_word_minus_last_description_new
            main_tableObject.different_words_plus_description = num_different_word_plus_last_description_new
            main_tableObject.different_words_minus_acceptance_criteria = \
                num_different_word_minus_last_acceptance_criteria_new
            main_tableObject.different_words_plus_acceptance_criteria = \
                num_different_word_plus_last_acceptance_criteria_new
            main_tableObject.num_different_words_all_text = num_different_words_all_text
            main_tableObject.num_comments_before_sprint = num_comments_before_new_sprint
            main_tableObject.num_comments_after_sprint = num_comments_after_new_sprint
            main_tableObject.has_comments_after_new_sprint = is_comments_after_new_sprint
            main_tableObject.has_comments_before_new_sprint = is_comments_before_new_sprint

            main_tableObject.num_changes_text_before_sprint = num_changes_text_before_sprint
            main_tableObject.num_changes_story_point_before_sprint = num_changes_story_point_before_sprint

            FilesActivity.insert_element(path_to_save, TableColumns.MainTableOS, main_tableObject, logger)

            logger.debug(f'Insert {issue_name}')
            if i % 100 == 0:
                logger.debug(f'Insert {i} USs')

        except Exception as e:
            logger.error(f'ERROR: index:{i}, issue_key:{issue_name}\n message:{e}')
            print(f'ERROR: index:{i}, issue_key:{issue_name}\n message:{e}')
            raise e


def start(path_to_load, path_to_save):
    Create_DB.create_DB(path_to_save, False)

    main_data = pd.read_csv(os.path.join(path_to_load, FilesActivity.filesNames[TableColumns.MainTableOS]))
    changes_summary = pd.read_csv(os.path.join(path_to_load, FilesActivity.filesNames[TableColumns.ChangesSummaryOS]))
    changes_description = pd.read_csv(os.path.join(path_to_load,
                                                   FilesActivity.filesNames[TableColumns.ChangesDescriptionOS]))
    changes_story_points = pd.read_csv(os.path.join(path_to_load,
                                                    FilesActivity.filesNames[TableColumns.ChangesStoryPointsOS]))
    changes_acceptance = pd.read_csv(os.path.join(path_to_load,
                                                  FilesActivity.filesNames[TableColumns.ChangesCriteriaOS]))
    comments = pd.read_csv(os.path.join(path_to_load, FilesActivity.filesNames[TableColumns.CommentsOS]))

    mainDataObjectList: List[TableColumns.MainTableOS] = \
        [TableColumns.createMainObjectFromDataFrame(row) for index, row in main_data.iterrows()]

    change_summaryObjectList: List[TableColumns.ChangesSummaryOS] = \
        [TableColumns.createChangesSummaryOSObjectFromDataFrame(row) for index, row in changes_summary.iterrows()]

    change_descriptionObjectList: List[TableColumns.ChangesDescriptionOS] = \
        [TableColumns.createChangesDescriptionOSObjectFromDataFrame(row) for index, row in
         changes_description.iterrows()]

    changes_acceptanceObjectList: List[TableColumns.ChangesCriteriaOS] = \
        [TableColumns.createCChangesCriteriaOSObjectFromDataFrame(row) for index, row in changes_acceptance.iterrows()]

    change_storyPointsObjectList: List[TableColumns.ChangesStoryPointsOS] = \
        [TableColumns.createChangesStoryPointsOSObjectFromDataFrame(row) for
         index, row in changes_story_points.iterrows()]

    comment_objectList: List[TableColumns.CommentsOS] = \
        [TableColumns.createCommentsOSObjectFromDataFrame(row) for index, row in comments.iterrows()]

    add_cal_columns_(
        path_to_save=path_to_save,
        mainDataObjectList=mainDataObjectList,
        change_summaryObjectList=change_summaryObjectList,
        change_descriptionObjectList=change_descriptionObjectList,
        changes_acceptanceObjectList=changes_acceptanceObjectList,
        change_storyPointsObjectList=change_storyPointsObjectList,
        comment_objectList=comment_objectList)

    FilesActivity.copy_files_with_black_list(
        path_to_load=path_to_load,
        path_to_save=path_to_save,
        blackList=[TableColumns.MainTableOS])


if __name__ == '__main__':
    start(path_to_load="C:\\Users\\t-yelmaleh\\Downloads\\results_\\Simple_Data\\Sakai\\calculate_time_add_sprint",
          path_to_save="C:\\Users\\t-yelmaleh\\Downloads\\results_\\testing")
