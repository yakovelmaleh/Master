import pandas as pd
import Utils.GetInstabilityData as GetData


def add_N_columns_based_on_the_previous_labels(jira_name, N: int, k_unstable: int):
    df = pd.read_csv(f'Master/Data/{jira_name}/features_labels_table_os.csv')
    df = df[['issue_key', f'is_change_text_num_words_{k_unstable}']]

    if df.columns[0].startswith('is_change_text_num_words_'):
        df = df.iloc[1:]

    # Add N columns
    for i in range(1, N + 1):
        shifted_values = df[f'is_change_text_num_words_{k_unstable}'].shift(i)
        shifted_values = shifted_values.fillna(0)  # Fill NaN with 0
        df[f'previous_label_{i}'] = shifted_values.astype(int)  # Convert to int if needed

    df = df.drop(columns=['is_change_text_num_words_{k_unstable}'])
    return df


def get_train_valid_sets_for_optimize(jira_name, main_path, N):
    train_output = dict()
    valid_output = dict()

    for k_unstable in [5, 10, 15, 20]:
        features_data_train, features_data_valid = GetData.get_data_train_valid(jira_name, main_path, k_unstable)

        previous_labels = add_N_columns_based_on_the_previous_labels(jira_name, N, k_unstable)

        train_output[f'{k_unstable}'] = pd.merge(features_data_train, previous_labels, on='A', how='inner')
        valid_output[f'{k_unstable}'] = pd.merge(features_data_valid, previous_labels, on='A', how='inner')

    return train_output, valid_output


def get_train_valid_labels_for_optimize(project_name, main_path='Master/'):
    output_train = dict()
    output_valid = dict()
    for k_unstable in [5, 10, 15, 20]:
        output_train[f'{k_unstable}'], output_valid[f'{k_unstable}'] =\
            GetData.get_label_train_valid(project_name, main_path, k_unstable)

    return output_train, output_valid


def get_test_sets_for_prediction(jira_name, main_path, N):
    test_output = dict()

    for k_unstable in [5, 10, 15, 20]:
        test_set = GetData.get_test_data(jira_name, main_path, k_unstable)
        previous_labels = add_N_columns_based_on_the_previous_labels(jira_name, N, k_unstable)
        test_output[f'{k_unstable}'] = pd.merge(test_set, previous_labels, on='A', how='inner')

    return test_output


def get_test_labels_for_prediction(jira_name, main_path):
    test_output = dict()

    for k_unstable in [5, 10, 15, 20]:
        test_output[f'{k_unstable}'] = GetData.get_label_test(jira_name, main_path, k_unstable)

    return test_output


def get_train_sets_for_prediction(jira_name, main_path, N):
    train_output = dict()

    for k_unstable in [5, 10, 15, 20]:
        features_data_train = GetData.get_data_train(jira_name, main_path, k_unstable)

        previous_labels = add_N_columns_based_on_the_previous_labels(jira_name, N, k_unstable)

        train_output[f'{k_unstable}'] = pd.merge(features_data_train, previous_labels, on='A', how='inner')

    return train_output


def get_train_labels_for_prediction(project_name, main_path='Master/'):
    output_train = dict()
    for k_unstable in [5, 10, 15, 20]:
        output_train[f'{k_unstable}'] = GetData.get_label_train(project_name, main_path, k_unstable)

    return output_train
