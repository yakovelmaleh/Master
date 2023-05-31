import pandas as pd


def get_test_data(jira_name, main_path, k_unstable):
    path = f"{main_path}Data/{jira_name}/features_labels_table_os.csv"
    all_features = pd.read_csv(path)

    all_features = all_features[
        ['issue_key', 'original_summary_description_acceptance_sprint', f'is_change_text_num_words_{k_unstable}']]

    path = f"{main_path}Models/train_test/{jira_name}"
    test_keys = pd.read_csv(f'{path}/features_data_test_{jira_name}_is_change_text_num_words_{k_unstable}.csv')

    test_keys = test_keys[['issue_key']]
    test_data = test_keys.join(all_features.set_index('issue_key'), on='issue_key')

    test_data = test_data.reset_index()
    test_data = test_data.rename(
        columns={'index': 'idx', 'original_summary_description_acceptance_sprint': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})

    test_data = test_data.drop('issue_key', axis=1)

    return test_data


def get_data_train_with_labels(jira_name, main_path, k_unstable):
    path = f"{main_path}Data/{jira_name}/features_labels_table_os.csv"
    all_features = pd.read_csv(path)

    path = f"{main_path}Models/train_val/{jira_name}"
    train_keys = pd.read_csv(f'{path}/features_data_train_{jira_name}_is_change_text_num_words_{k_unstable}.csv')
    valid_keys = pd.read_csv(f'{path}/features_data_valid_{jira_name}_is_change_text_num_words_{k_unstable}.csv')

    train_keys = train_keys[['issue_key']]
    valid_keys = valid_keys[['issue_key']]

    all_features = all_features[
        ['issue_key', 'original_summary_description_acceptance_sprint', f'is_change_text_num_words_{k_unstable}']]

    train_data = train_keys.join(all_features.set_index('issue_key'), on='issue_key')
    valid_data = valid_keys.join(all_features.set_index('issue_key'), on='issue_key')

    train_data = train_data.reset_index()
    valid_data = valid_data.reset_index()

    train_data = train_data.rename(
        columns={'index': 'idx', 'original_summary_description_acceptance_sprint': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})
    valid_data = valid_data.rename(
        columns={'index': 'idx', 'original_summary_description_acceptance_sprint': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})

    train_data = train_data.drop('issue_key', axis=1)
    valid_data = valid_data.drop('issue_key', axis=1)

    return train_data, valid_data


def get_data_train(jira_name, main_path, k_unstable):
    path = f"{main_path}Data/{jira_name}/features_labels_table_os.csv"
    all_features = pd.read_csv(path)

    path = f"{main_path}Models/train_val/{jira_name}"
    train_keys = pd.read_csv(f'{path}/features_data_train_{jira_name}_is_change_text_num_words_{k_unstable}.csv')
    valid_keys = pd.read_csv(f'{path}/features_data_valid_{jira_name}_is_change_text_num_words_{k_unstable}.csv')

    train_keys = train_keys[['issue_key']]
    valid_keys = valid_keys[['issue_key']]

    all_features = all_features[
        ['issue_key', 'original_summary_description_acceptance_sprint', f'is_change_text_num_words_{k_unstable}']]

    train_data = train_keys.join(all_features.set_index('issue_key'), on='issue_key')
    valid_data = valid_keys.join(all_features.set_index('issue_key'), on='issue_key')

    train_data = train_data.reset_index()
    valid_data = valid_data.reset_index()

    train_data = train_data.rename(
        columns={'index': 'idx', 'original_summary_description_acceptance_sprint': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})
    valid_data = valid_data.rename(
        columns={'index': 'idx', 'original_summary_description_acceptance_sprint': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})

    train_data = train_data.drop('issue_key', axis=1)
    valid_data = valid_data.drop('issue_key', axis=1)

    train_data = pd.concat([train_data, valid_data], ignore_index=True)

    return train_data
