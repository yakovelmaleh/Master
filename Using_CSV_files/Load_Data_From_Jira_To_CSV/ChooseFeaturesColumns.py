import pandas as pd


def get_int_values_by_less_then(df: pd.DataFrame, first_column_name: str, second_column_name: str):
    if df.empty:
        return pd.Series(dtype=int)

    return (df[first_column_name].notna() & (df[first_column_name] < df[second_column_name])
            ).astype(int)


def get_int_values_by_delta(df: pd.DataFrame, first_column_name: str, second_column_name: str):
    if df.empty:
        return pd.Series(dtype=int)

    return (df[first_column_name] - df[second_column_name] > 0).astype(int)


def get_int_instability_by_threshold(df: pd.DataFrame, threshold: int):
    if df.empty:
        return pd.Series(dtype=int)

    return (
            df['num_different_words_all_text_sprint'] >= threshold &
            df['num_changes_summary_description_acceptance_sprint'] > 0).astype(int)


def get_information_from_main(df: pd.DataFrame) -> pd.DataFrame:

    df['has_date_of_first_response_before_add_to_sprint'] = (
        get_int_values_by_less_then(df, 'date_of_first_response', 'time_add_to_sprint'))
    df['has_last_updated_before_add_to_sprint'] = (
        get_int_values_by_less_then(df, 'last_updated', 'time_add_to_sprint'))
    df['has_resolution_date'] = (
        get_int_values_by_less_then(df, 'resolution_date', 'time_add_to_sprint'))
    df['time_status_close_before_sprint'] = (
        get_int_values_by_less_then(df, 'time_status_close', 'time_add_to_sprint'))

    df['has_changes_summary_before_sprint'] = (
        get_int_values_by_delta(df, 'num_changes_summary_new', 'num_changes_summary_new_sprint'))
    df['has_changes_description_before_sprint'] = (
        get_int_values_by_delta(df, 'num_changes_summary_new', 'num_changes_summary_new_sprint'))
    df['has_changes_acceptance_criteria_before_sprint'] = (
        get_int_values_by_delta(df, 'num_changes_acceptance_criteria_new', 'num_changes_acceptance_criteria_new_sprint'))
    df['has_changes_story_points_before_sprint'] = (
        get_int_values_by_delta(df, 'num_changes_story_points_new', 'num_changes_story_points_new_sprint'))

    df['num_changes_summary_before_sprint'] = df['num_changes_summary_new'] - df['num_changes_summary_new_sprint']
    df['num_changes_description_before_sprint'] = (df['num_changes_description_new'] -
                                                   df['num_changes_description_new_sprint'])
    df['num_changes_acceptance_criteria_before_sprint'] = (df['num_changes_acceptance_criteria_new'] -
                                                           df['num_changes_acceptance_criteria_new_sprint'])
    df['num_changes_story_points_before_sprint'] = (df['num_changes_story_points_new'] -
                                                    df['num_changes_story_points_new_sprint'])

    #instability
    df['is_change_text_num_words_1'] = get_int_instability_by_threshold(df, 1)
    df['is_change_text_num_words_5'] = get_int_instability_by_threshold(df, 5)
    df['is_change_text_num_words_10'] = get_int_instability_by_threshold(df, 10)
    df['is_change_text_num_words_15'] = get_int_instability_by_threshold(df, 15)
    df['is_change_text_num_words_20'] = get_int_instability_by_threshold(df, 20)

    df['is_change_text_sp_sprint'] = (
            (df['is_change_text_num_words_5'] > 0) &
            ((df['num_changes_story_points_new_sprint'] > 0) | (df['num_sprints'] > 1))
    ).astype(int)

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


