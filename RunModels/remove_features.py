import pandas as pd
from pathlib import Path
import os


def addPath(path):
    return str(Path(os.getcwd()).joinpath(path))

def start(jira_name):
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
            path = addPath(f'Master/Model/train_val/{project_key}')
            features_data_train_valid = pd.read_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', low_memory=False)
            features_data_valid = pd.read_csv(
                f'{path}/features_data_valid_{project_key}_{label_name[0]}.csv', low_memory=False)

            path = addPath(f'Master/Model/train_test/{project_key}')
            features_data_train_test = pd.read_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', low_memory=False)
            features_data_test = pd.read_csv(
                f'{path}/features_data_test_{project_key}_{label_name[0]}.csv', low_memory=False)

            if project_key == 'Apache':
                if label_name[0] == 'is_change_text_num_words_5':
                    features_data_train_valid.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_tbd',
                                                    'if_description_empty_tbd','priority'], axis=1, inplace=True)
                    #ssssssssssssssss
                    features_data_valid.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_tbd',
                                                    'if_description_empty_tbd','priority'], axis=1, inplace=True)
                    features_data_train_test.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_tbd',
                                                    'if_description_empty_tbd','priority'], axis=1, inplace=True)
                    features_data_test.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_tbd',
                                                    'if_description_empty_tbd','priority'], axis=1, inplace=True)
                else:
                    features_data_train_valid.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_tbd','has_please',
                                                    'if_description_empty_tbd','priority'], axis=1, inplace=True)
                    features_data_valid.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_tbd','has_please',
                                                    'if_description_empty_tbd','priority'], axis=1, inplace=True)
                    features_data_train_test.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_tbd','has_please',
                                                    'if_description_empty_tbd','priority'], axis=1, inplace=True)
                    features_data_test.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_tbd','has_please',
                                                    'if_description_empty_tbd','priority'], axis=1, inplace=True)

            # update the new data
            # write train val
            path = addPath(f'Master/Models/train_val_after_chi/{project_key}')
            features_data_train_valid.to_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', index=False)
            features_data_valid.to_csv(
                f'{path}/features_data_valid_{project_key}_{label_name[0]}.csv', index=False)

            # write train test
            path = addPath(f'Master/Models/train_test_after_chi/{project_key}')
            features_data_train_test.to_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', index=False)
            features_data_test.to_csv(
                f'{path}/features_data_test_{project_key}_{label_name[0]}.csv', index=False)

    if is_after_all_but:
        # read all the data sets and delete from each one the unwanted features by the feature group omtimization results in the excel files
        for label_name in dict_labels.items():
            print("data: {}, \n label_name.key: {}, \n".format(project_key, label_name[0]))

            path = addPath(f'Master/Model/train_val_after_chi/{project_key}')
            features_data_train_valid = pd.read_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', low_memory=False)
            features_data_valid = pd.read_csv(
                f'{path}/features_data_valid_{project_key}_{label_name[0]}.csv', low_memory=False)

            path = addPath(f'Master/Model/train_test_after_chi/{project_key}')
            features_data_train_test = pd.read_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', low_memory=False)
            features_data_test = pd.read_csv(
                f'{path}/features_data_test_{project_key}_{label_name[0]}.csv', low_memory=False)

            if project_key == 'Apache':
                features_data_train_valid.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
                                                '11', '12', '13', '14', 'if_acceptance_empty_tbd', 'len_acceptance',
                                                'noun_count', 'verb_count', 'adj_count',
                                                'adv_count', 'pron_count'], axis=1, inplace=True)
                features_data_valid.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
                                                '11', '12', '13', '14', 'if_acceptance_empty_tbd', 'len_acceptance',
                                                'noun_count', 'verb_count', 'adj_count',
                                                'adv_count', 'pron_count'], axis=1, inplace=True)
                features_data_train_test.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
                                                '11', '12', '13', '14', 'if_acceptance_empty_tbd', 'len_acceptance',
                                                'noun_count', 'verb_count', 'adj_count',
                                                'adv_count', 'pron_count'], axis=1, inplace=True)
                features_data_test.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
                                                '11', '12', '13', '14', 'if_acceptance_empty_tbd', 'len_acceptance',
                                                'noun_count', 'verb_count', 'adj_count',
                                                'adv_count', 'pron_count'], axis=1, inplace=True)

            # write train val
            path = addPath(f'Master/Models/train_val_after_all_but/{project_key}')
            features_data_train_valid.to_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', index=False)
            features_data_valid.to_csv(
                f'{path}/features_data_valid_{project_key}_{label_name[0]}.csv', index=False)

            # write train test
            path = addPath(f'Master/Models/train_test_after_all_but/{project_key}')
            features_data_train_test.to_csv(
                f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', index=False)
            features_data_test.to_csv(
                f'{path}/features_data_test_{project_key}_{label_name[0]}.csv', index=False)


if __name__ == "__main__":
    print('Hello World')


