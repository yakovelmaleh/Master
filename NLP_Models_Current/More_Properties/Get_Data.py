import pandas as pd
import Utils.GetNLPData as GetData


def get_train_valid_data_list(project_name, main_path='Master/'):
    output_train = dict()
    output_valid = dict()
    for k_unstable in [5, 10, 15, 20]:
        output_train[f'{k_unstable}'], output_valid[f'{k_unstable}'] = \
            get_data_train_valid_with_labels(project_name, main_path, k_unstable)

    return output_train, output_valid


def get_test_data_list(project_name, main_path='Master/'):
    output = dict()
    for k_unstable in [5, 10, 15, 20]:
        output[f'{k_unstable}'] = \
            get_test_data(project_name, main_path, k_unstable)

    return output


def get_data_train_valid_with_labels(jira_name, main_path, k_unstable):
    path = f"{main_path}Data/{jira_name}/features_labels_table_os.csv"
    all_features = pd.read_csv(path)

    path = f"{main_path}Models/train_val/{jira_name}"
    train_keys = pd.read_csv(f'{path}/features_data_train_{jira_name}_is_change_text_num_words_{k_unstable}.csv')
    valid_keys = pd.read_csv(f'{path}/features_data_valid_{jira_name}_is_change_text_num_words_{k_unstable}.csv')

    train_keys = train_keys[['issue_key']]
    valid_keys = valid_keys[['issue_key']]

    all_features['concat'] = all_features.apply(concat_columns, axis=1)

    all_features = all_features[
        ['issue_key', 'concat', f'is_change_text_num_words_{k_unstable}']]

    train_data = train_keys.join(all_features.set_index('issue_key'), on='issue_key')
    valid_data = valid_keys.join(all_features.set_index('issue_key'), on='issue_key')

    train_data = train_data.reset_index()
    valid_data = valid_data.reset_index()

    train_data = train_data.rename(
        columns={'index': 'idx', 'concat': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})
    valid_data = valid_data.rename(
        columns={'index': 'idx', 'concat': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})

    train_data = train_data.drop('issue_key', axis=1)
    valid_data = valid_data.drop('issue_key', axis=1)

    return train_data, valid_data


def concat_columns(row):
    column_names = ['issue_key', 'issue_type', 'project_key', 'created', 'epic_link', 'original_story_points_sprint',
                    'creator', 'reporter', 'priority', 'num_changes_text_before_sprint',
                    'num_changes_story_point_before_sprint', 'time_add_to_sprint', 'original_summary_sprint',
                    'original_description_sprint', 'original_acceptance_criteria_sprint', 'time_until_add_to_sprint',
                    'num_issues_cretor_prev', 'num_unusable_issues_cretor_prev_text_word_1',
                    'num_unusable_issues_cretor_prev_text_word_5', 'num_unusable_issues_cretor_prev_text_word_10',
                    'num_unusable_issues_cretor_prev_text_word_15', 'num_unusable_issues_cretor_prev_text_word_20'
                    ]
    output = ""

    for column in column_names:
        output = output + f'$ {column}: $ ' + (str(row[column]) if pd.notnull(row[column]) else "") + ' '

    return output


def get_test_data(jira_name, main_path, k_unstable):
    path = f"{main_path}Data/{jira_name}/features_labels_table_os.csv"
    all_features = pd.read_csv(path)

    all_features['concat'] = all_features.apply(concat_columns, axis=1)

    all_features = all_features[
        ['issue_key', 'concat', f'is_change_text_num_words_{k_unstable}']]

    path = f"{main_path}Models/train_test/{jira_name}"
    test_keys = pd.read_csv(f'{path}/features_data_test_{jira_name}_is_change_text_num_words_{k_unstable}.csv')

    test_keys = test_keys[['issue_key']]
    test_data = test_keys.join(all_features.set_index('issue_key'), on='issue_key')

    test_data = test_data.reset_index()
    test_data = test_data.rename(
        columns={'index': 'idx', 'concat': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})

    test_data = test_data.drop('issue_key', axis=1)

    return test_data
