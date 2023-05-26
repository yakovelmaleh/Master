import json
import Instability_With_BERT.Add_BERT_predication as Add_BERT_predication
import pandas as pd
import Instability_With_BERT.ml_algorithms_optimization as ml_algorithms_optimization
from pathlib import Path
import os


def addPath(path):
    return str(Path(os.getcwd()).joinpath(path))

def start(jira_name):
    """
    this script read all the feature data (train and validation only), and run the optimization of the hyper parameters (ml_algorithms_optimization)
    """
    text_type = 'original_summary_description_acceptance_sprint'

    dict_labels = {'is_change_text_num_words_5': 'num_unusable_issues_cretor_prev_text_word_5_ratio',
                   'is_change_text_num_words_10': 'num_unusable_issues_cretor_prev_text_word_10_ratio',
                   'is_change_text_num_words_15': 'num_unusable_issues_cretor_prev_text_word_15_ratio',
                   'is_change_text_num_words_20': 'num_unusable_issues_cretor_prev_text_word_20_ratio'
                   }

    project_key = jira_name

    add_bert_predictions = Add_BERT_predication.start(jira_name, 'Master/')

    for label_name in dict_labels.items():
        print("data: {}, \n label_name.key: {}, \n".format(project_key, label_name[0]))
        all_but_one_group = True
        # get data

        path = addPath(f'Master/Models/train_val_after_all_but/{project_key}')
        features_data_train = pd.read_csv(
            f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', low_memory=False)
        features_data_valid = pd.read_csv(
            f'{path}/features_data_valid_{project_key}_{label_name[0]}.csv', low_memory=False)

        # add bert instability
        features_data_train = add_bert_predictions(data=features_data_train, data_name='train', k_unstable=label_name[0])
        features_data_test = add_bert_predictions(data=features_data_test, data_name='valid', k_unstable=label_name[0])

        path = addPath(f'Master/Models/train_val/{project_key}')
        labels_train = pd.read_csv(
            f'{path}/labels_train_{project_key}_{label_name[0]}.csv', low_memory=False)
        labels_valid = pd.read_csv(
            f'{path}/labels_valid_{project_key}_{label_name[0]}.csv', low_memory=False)

        names = list(features_data_train.columns.values)
        if 'dominant_topic' in names:
            features_data_train = pd.get_dummies(features_data_train, columns=['dominant_topic'],
                                                 drop_first=True)
            features_data_valid = pd.get_dummies(features_data_valid, columns=['dominant_topic'],
                                                 drop_first=True)
            # Get missing columns in the training test
            missing_cols = set(features_data_train.columns) - set(features_data_valid.columns)
            # Add a missing column in test set with default value equal to 0
            for c in missing_cols:
                features_data_valid[c] = 0
            # Ensure the order of column in the test set is in the same order than in train set
            features_data_valid = features_data_valid[features_data_train.columns]

        # get only train of the test set

        # run optimization:
        ml_algorithms_optimization.run_model_optimization(features_data_train, features_data_valid,
                                                          labels_train['usability_label'],
                                                          labels_valid['usability_label'], project_key,
                                                          label_name[0], all_but_one_group, path=path)


if __name__ == "__main__":
    """
    this script read all the feature data (train and validation only), and run the optimization of the hyper parameters (ml_algorithms_optimization)
    """
    print('Hello World')
