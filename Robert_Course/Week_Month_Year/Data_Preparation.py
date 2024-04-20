import pandas as pd
import Utils.GetInstabilityData as GetData


def create_column_names(column_name, value):
    if pd.isnull(value):
        return f"{column_name}_NaN"
    else:
        return f"{column_name}_{value}"


def get_dummies(df: pd.DataFrame, column_name):
    one_hot_encoded = pd.get_dummies(df[column_name]).astype(int)

    # Create new column names for one-hot encoded columns
    new_column_names = [create_column_names(column_name, value) for value in one_hot_encoded.columns]

    # Rename columns of one-hot encoded DataFrame
    one_hot_encoded.columns = new_column_names

    # Create a column indicating NaN values
    nan_column = df[column_name].isna().astype(int)

    # Concatenate the one-hot encoded columns and the NaN column with the original DataFrame
    result = pd.concat([df, one_hot_encoded, nan_column.rename(f'{column_name}_NaN')], axis=1)

    return result.drop(columns=[column_name])


def convert_nan_to_binary(df: pd.DataFrame, column_name: str):
    nan_binary_column = df[column_name].notna().astype(int)
    df[column_name] = nan_binary_column
    return df


def count_earlier_within_week(row, df, count, k_unstable):
    earlier_dates = df.loc[(df['created'] < row['created']) & (df['created'] + pd.Timedelta(days=count) >= row['created'])]
    return len(earlier_dates), earlier_dates[f'is_change_text_num_words_{k_unstable}'].sum()


def add_N_columns_based_on_the_previous_labels(jira_name, N: int, k_unstable: int):
    df = pd.read_csv(f'Master/Data/{jira_name}/features_labels_table_os.csv')
    df = df[['issue_key', f'is_change_text_num_words_{k_unstable}', 'created',
             'issue_type', 'project_key', 'creator', 'reporter', 'priority',
             'original_summary_sprint', 'original_description_sprint', 'original_acceptance_criteria_sprint'
             ]]

    column_list_to_convert = ['issue_type', 'project_key', 'creator', 'reporter', 'priority']
    column_list_tp_convert_to_1_0 = ['original_summary_sprint',
                                     'original_description_sprint', 'original_acceptance_criteria_sprint']

    if df.columns[0].startswith('is_change_text_num_words_'):
        df = df.iloc[1:]

    df['created'] = pd.to_datetime(df['created'])
    for time, count in [('W', 7), ('M', 30), ('Y', 365)]:
        df[f'count_earlier_within_{time}'], df[f'sum_{time}'] = zip(*df.apply(count_earlier_within_week,
                                                                              args=(df, count, k_unstable), axis=1))
    # Add N columns
    for i in range(1, N + 1):
        shifted_values = df[f'is_change_text_num_words_{k_unstable}'].shift(i)
        shifted_values = shifted_values.fillna(0)  # Fill NaN with 0
        df[f'previous_label_{i}'] = shifted_values.astype(int)  # Convert to int if needed

    df = df.drop(columns=[f'is_change_text_num_words_{k_unstable}', 'created'])

    for column in column_list_to_convert:
        df = get_dummies(df, column)

    for column in column_list_tp_convert_to_1_0:
        df = convert_nan_to_binary(df, column)

    return df


def get_train_valid_sets_for_optimize(jira_name, main_path, N):
    train_output = dict()
    valid_output = dict()

    for k_unstable in [5, 10, 15, 20]:
        features_data_train, features_data_valid = GetData.get_data_train_valid(jira_name, main_path, k_unstable)

        previous_labels = add_N_columns_based_on_the_previous_labels(jira_name, N, k_unstable)

        train_output[f'{k_unstable}'] = pd.merge(features_data_train, previous_labels, on='issue_key', how='inner')
        valid_output[f'{k_unstable}'] = pd.merge(features_data_valid, previous_labels, on='issue_key', how='inner')

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
        test_output[f'{k_unstable}'] = pd.merge(test_set, previous_labels, on='issue_key', how='inner')

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

        train_output[f'{k_unstable}'] = pd.merge(features_data_train, previous_labels, on='issue_key', how='inner')

    return train_output


def get_train_labels_for_prediction(project_name, main_path='Master/'):
    output_train = dict()
    for k_unstable in [5, 10, 15, 20]:
        output_train[f'{k_unstable}'] = GetData.get_label_train(project_name, main_path, k_unstable)

    return output_train
