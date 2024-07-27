import pandas as pd


def get_information_from_main(df: pd.DataFrame) -> pd.DataFrame:
    df['has_date_of_first_response_before_add_to_sprint'] = int(df['date_of_first_response'] is not None and
                                                                df['date_of_first_response'] < df['time_add_to_sprint'])
    df['has_last_updated_before_add_to_sprint'] = int(df['last_updated'] is not None and
                                                      df['last_updated'] < df['time_add_to_sprint'])
    df['has_resolution_date'] = int(df['resolution_date'] is not None
                                    and df['resolution_date'] < df['time_add_to_sprint'])
    df['num_changes_summary_before_sprint'] = df['num_changes_summary_new'] - df['num_changes_summary_new_sprint']
    df['has_changes_summary_before_sprint'] = int(df['num_changes_summary_new'] - df['num_changes_summary_new_sprint'] > 0)
    df['num_changes_description_before_sprint'] = (df['num_changes_description_new'] -
                                                   df['num_changes_description_new_sprint'])
    df['has_changes_description_before_sprint'] = (
        int(df['num_changes_description_new'] - df['num_changes_description_new_sprint'] > 0))
    df['num_changes_acceptance_criteria_before_sprint'] = (df['num_changes_acceptance_criteria_new'] -
                                                           df['num_changes_acceptance_criteria_new_sprint'])
    df['has_changes_acceptance_criteria_before_sprint'] = int(df['num_changes_acceptance_criteria_new'] -
                                                              df['num_changes_acceptance_criteria_new_sprint'] > 0)
    df['num_changes_story_points_before_sprint'] = (df['num_changes_story_points_new'] -
                                                    df['num_changes_story_points_new_sprint'])
    df['has_changes_story_points_before_sprint'] = int(df['num_changes_story_points_new'] -
                                                       df['num_changes_story_points_new_sprint'] > 0)
    df['time_status_close_before_sprint'] = int(df['time_status_close'] is not None and
                                                df['time_status_close'] < df['time_add_to_sprint'])

    #instability
    df['is_change_text_num_words_1'] = int(df['num_different_words_all_text_sprint'] > 0 and
                                           df['num_changes_summary_description_acceptance_sprint'] > 0)
    df['is_change_text_num_words_5'] = int(df['num_different_words_all_text_sprint'] >= 5 and
                                           df['num_changes_summary_description_acceptance_sprint'] > 0)
    df['is_change_text_num_words_10'] = int(df['num_different_words_all_text_sprint'] >= 10 and
                                            df['num_changes_summary_description_acceptance_sprint'] > 0)
    df['is_change_text_num_words_15'] = int(df['num_different_words_all_text_sprint'] >= 15 and
                                            df['num_changes_summary_description_acceptance_sprint'] > 0)
    df['is_change_text_num_words_20'] = int(df['num_different_words_all_text_sprint'] >= 20 and
                                            df['num_changes_summary_description_acceptance_sprint'] > 0)
    df['is_change_text_sp_sprint'] = int(df['is_change_text_num_words_5'] > 0 and
                                         (df['num_changes_story_points_new_sprint'] > 0 or df['num_sprints'] > 1))
    df['time_until_add_to_sprint'] = (df['time_add_to_sprint'] - df['created']).total_seconds() / 60

    main_list = ['issue_key', 'issue_id', 'project_key', 'created', 'creator', 'reporter', 'assignee', 'priority',
                 'prograss', 'prograss_total', 'num_comments', 'num_issue_links', 'status_name',
                 'has_date_of_first_response_before_add_to_sprint', 'epic_link', 'issue_type',
                 'has_last_updated_before_add_to_sprint', 'has_resolution_date', 'status_description',
                 'time_estimate', 'time_origion_estimate', 'time_spent', 'team', 'story_point', 'summary',
                 'description', 'acceptance_criteria', 'num_all_changes', 'num_bugs_issue_link', 'num_of_commits',
                 'num_sprints', 'num_sub_tasks', 'num_watchers', 'num_worklog', 'num_versions', 'num_fix_versions',
                 'num_labels', 'num_components', 'num_changes_summary_before_sprint',
                 'num_changes_description_before_sprint', 'num_changes_acceptance_criteria_before_sprint',
                 'has_changes_summary_before_sprint', 'has_changes_description_before_sprint',
                 'has_changes_acceptance_criteria_before_sprint', 'original_summary', 'original_description',
                 'original_acceptance_criteria', 'original_story_points', 'num_changes_story_points_before_sprint',
                 'has_changes_story_points_before_sprint', 'has_change_story_point', 'num_changes_sprint',
                 'time_add_to_sprint', 'original_summary_sprint', 'num_changes_summary_new_sprint',
                 'original_description_sprint', 'num_changes_description_new_sprint',
                 'original_acceptance_criteria_sprint', 'num_changes_acceptance_criteria_new_sprint',
                 'original_story_points_sprint', 'num_changes_story_points_new_sprint',
                 'has_change_summary_sprint', 'has_change_description_sprint',
                 'has_change_acceptance_criteria_sprint', 'has_change_story_point_sprint',
                 'num_comments_before_sprint', 'num_comments_after_sprint',
                 'num_different_words_all_text_sprint_new', 'num_ratio_words_all_text_sprint_new',
                 'num_ratio_words_all_text_sprint_new', 'num_changes_text_before_sprint',
                 'num_changes_story_point_before_sprint', 'time_status_close_before_sprint',
                 'has_comments_after_new_sprint', 'has_comments_before_new_sprint',
                 'summary_description_acceptance', 'original_summary_description_acceptance_sprint',
                 'num_changes_summary_description_acceptance_sprint', 'num_different_words_all_text_sprint',
                 'attachment', 'is_attachment', 'pull_request_url', 'images', 'is_images',
                 'is_change_text_num_words_1', 'is_change_text_num_words_5', 'is_change_text_num_words_10',
                 'is_change_text_num_words_15', 'is_change_text_num_words_20', 'is_change_text_sp_sprint',
                 'time_until_add_to_sprint'
                 ]

    for column in main_list:
        if column.startswith("num_") or column.startswith("has_"):
            df[column] = df[column].fillna(0)

    return df[main_list]


