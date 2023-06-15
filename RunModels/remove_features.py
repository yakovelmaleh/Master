import pandas as pd
from pathlib import Path
import os


def addPath(path):
    return str(Path(os.getcwd()).joinpath(path))

def start(jira_name, main_path):
    dict_labels = {'is_change_text_num_words_5': 'num_unusable_issues_cretor_prev_text_word_5_ratio',
                   'is_change_text_num_words_10': 'num_unusable_issues_cretor_prev_text_word_10_ratio',
                   'is_change_text_num_words_15': 'num_unusable_issues_cretor_prev_text_word_15_ratio',
                   'is_change_text_num_words_20': 'num_unusable_issues_cretor_prev_text_word_20_ratio'}
    project_key = jira_name
    is_after_chi = True
    is_after_all_but = True

    if is_after_chi:
        # read all the data sets and delete from each one the unwanted features by the chi-square results in the excel files
        for label_name in dict_labels.items():
            print("data: {}, \n label_name.key: {}, \n".format(project_key, label_name[0]))
            path = addPath(f'{main_path}Models/train_val/{project_key}')
            features_data_train_valid = pd.read_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', low_memory=False)
            features_data_valid = pd.read_csv(
                f'{path}/features_data_valid_{project_key}_{label_name[0]}.csv', low_memory=False)

            path = addPath(f'{main_path}Models/train_test/{project_key}')
            features_data_train_test = pd.read_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', low_memory=False)
            features_data_test = pd.read_csv(
                f'{path}/features_data_test_{project_key}_{label_name[0]}.csv', low_memory=False)

            # update the new data
            # write train val
            path = addPath(f'{main_path}Models/train_val_after_chi/{project_key}')
            features_data_train_valid.to_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', index=False)
            features_data_valid.to_csv(
                f'{path}/features_data_valid_{project_key}_{label_name[0]}.csv', index=False)

            # write train test
            path = addPath(f'{main_path}Models/train_test_after_chi/{project_key}')
            features_data_train_test.to_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', index=False)
            features_data_test.to_csv(
                f'{path}/features_data_test_{project_key}_{label_name[0]}.csv', index=False)

    if is_after_all_but:
        # read all the data sets and delete from each one the unwanted features by the feature group omtimization results in the excel files
        for label_name in dict_labels.items():
            print("data: {}, \n label_name.key: {}, \n".format(project_key, label_name[0]))

            path = addPath(f'{main_path}Models/train_val_after_chi/{project_key}')
            features_data_train_valid = pd.read_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', low_memory=False)
            features_data_valid = pd.read_csv(
                f'{path}/features_data_valid_{project_key}_{label_name[0]}.csv', low_memory=False)

            path = addPath(f'{main_path}Models/train_test_after_chi/{project_key}')
            features_data_train_test = pd.read_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', low_memory=False)
            features_data_test = pd.read_csv(
                f'{path}/features_data_test_{project_key}_{label_name[0]}.csv', low_memory=False)

            # write train val
            path = addPath(f'{main_path}Models/train_val_after_all_but/{project_key}')
            features_data_train_valid.to_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', index=False)
            features_data_valid.to_csv(
                f'{path}/features_data_valid_{project_key}_{label_name[0]}.csv', index=False)

            # write train test
            path = addPath(f'{main_path}Models/train_test_after_all_but/{project_key}')
            features_data_train_test.to_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', index=False)
            features_data_test.to_csv(
                f'{path}/features_data_test_{project_key}_{label_name[0]}.csv', index=False)


if __name__ == "__main__":
    start('Apache', '../')
    print('Hello World')


