import Instability_With_BERT.Add_BERT_predication as Add_BERT_predication
import Instability_With_BERT.ml_algorithms_run_best_parameters as ml_algorithms_run_best_parameters
import pandas as pd
from pathlib import Path
import os

def addPath(path):
    return str(Path(os.getcwd()).joinpath(path))

def start(jira_name):
    """
    this script read all the feature data (train and test), and run prediction script with the best parametrs and features, and run the script ml_algorithms_run_best_parameters
    which get the features and parameters and run + return the results to all the different models.
    we write in this script the results to excel
    """
    results = pd.DataFrame(columns=['project_key', 'usability_label', 'Model', 'feature_importance', 'accuracy',
                                    'confusion_matrix', 'classification_report', 'area_under_pre_recall_curve',
                                    'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                                    'recall', 'thresholds'])

    dict_labels = {'is_change_text_num_words_5': 'num_unusable_issues_cretor_prev_text_word_5_ratio',
                   'is_change_text_num_words_10': 'num_unusable_issues_cretor_prev_text_word_10_ratio',
                   'is_change_text_num_words_15': 'num_unusable_issues_cretor_prev_text_word_15_ratio',
                   'is_change_text_num_words_20': 'num_unusable_issues_cretor_prev_text_word_20_ratio'}
    project_key = jira_name

    add_bert_predictions = Add_BERT_predication.start(jira_name, 'Master/')

    for label_name in dict_labels.items():
        print("data: {}, \n label_name.key: {}, \n".format(project_key, label_name[0]))
        all_but_one_group = True

        # by the best group:
        path = addPath(f'Master/Models/train_test_after_all_but/{project_key}/')
        features_data_train = pd.read_csv(
            f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', low_memory=False)
        features_data_test = pd.read_csv(
            f'{path}/features_data_test_{project_key}_{label_name[0]}.csv', low_memory=False)

        # add bert instability
        features_data_train = add_bert_predictions(data=features_data_train, data_name='train', k_unstable=label_name[0])
        features_data_test = add_bert_predictions(data=features_data_test, data_name='test', k_unstable=label_name[0])

        path = addPath(f'Master/Instability_With_BERT/Parameters/{project_key}/')
        parameters_rf = pd.read_csv(
            f'{path}/results_groups_{project_key}_label_{label_name[0]}_RF.csv', low_memory=False)
        parameters_xg = pd.read_csv(
            f'{path}/results_groups_{project_key}_label_{label_name[0]}_XGboost.csv', low_memory=False)
        parameters_nn = pd.read_csv(
            f'{path}/results_groups_{project_key}_label_{label_name[0]}_NN.csv', low_memory=False)

        path = addPath(f'Master/Models/train_test/{project_key}/')
        labels_train = pd.read_csv(
            f'{path}/labels_train_{project_key}_{label_name[0]}.csv', low_memory=False)
        labels_test = pd.read_csv(
            f'{path}/labels_test_{project_key}_{label_name[0]}.csv', low_memory=False)

        names = list(features_data_train.columns.values)
        if 'dominant_topic' in names:
            features_data_train = pd.get_dummies(features_data_train, columns=['dominant_topic'],
                                                 drop_first=True)
            features_data_test = pd.get_dummies(features_data_test, columns=['dominant_topic'],
                                                drop_first=True)
            # Get missing columns in the training test
            missing_cols = set(features_data_train.columns) - set(features_data_test.columns)
            # Add a missing column in test set with default value equal to 0
            for c in missing_cols:
                features_data_test[c] = 0
            # Ensure the order of column in the test set is in the same order than in train set
            features_data_test = features_data_test[features_data_train.columns]

        labels_train = labels_train['usability_label']
        labels_test = labels_test['usability_label']

        # RF:
        num_trees = parameters_rf['num_trees'][0]
        max_feature = parameters_rf['max_features'][0]
        max_depth = parameters_rf['max_depth'][0]
        min_samples_leaf = parameters_rf['min_samples_leaf'][0]
        min_samples_split = parameters_rf['min_samples_split'][0]
        bootstrap = parameters_rf['bootstrap'][0]

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc, \
            y_pred, feature_imp, precision, recall, thresholds = \
            ml_algorithms_run_best_parameters.run_RF(features_data_train, features_data_test, labels_train,
                                                       labels_test, num_trees, max_feature, max_depth, min_samples_leaf,
                                                       min_samples_split, bootstrap, project_key, label_name[0],
                                                       all_but_one_group)

        d = {
            'project_key': project_key, 'usability_label': label_name[0], 'feature_importance': feature_imp,
            'accuracy': accuracy, 'confusion_matrix': confusion_matrix, 'classification_report': classification_report,
            'area_under_pre_recall_curve':area_under_pre_recall_curve,'avg_precision': average_precision,
            'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision,'recall': recall,
            'thresholds': thresholds, 'Model': 'RF'
        }

        results = pd.concat([results,  pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

        # xgboost
        num_trees = parameters_xg['num_trees'][0]
        max_depth = parameters_xg['max_depth'][0]
        max_features = parameters_xg['max_features'][0]
        min_samples_split = parameters_xg['min_samples_split'][0]
        min_samples_leaf = parameters_xg['min_samples_leaf'][0]

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc, \
            y_pred, feature_imp, precision, recall, thresholds = \
            ml_algorithms_run_best_parameters.run_XG(features_data_train, features_data_test, labels_train,
                                                     labels_test, num_trees, max_depth, max_features,
                                                     min_samples_split, min_samples_leaf,
                                                     project_key, label_name[0], all_but_one_group)

        d = {
            'project_key': project_key, 'usability_label': label_name[0], 'feature_importance': feature_imp,
            'accuracy': accuracy, 'confusion_matrix': confusion_matrix, 'classification_report': classification_report,
            'area_under_pre_recall_curve':area_under_pre_recall_curve,'avg_precision': average_precision,
            'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision,'recall': recall,
            'thresholds': thresholds, 'Model': 'XGboost'
        }

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

        # NN
        hidden_layer_size = parameters_nn['num_units_hidden_layer'][0]
        max_iterations = parameters_nn['max_iterations'][0]
        activation = parameters_nn['activation'][0]
        solver = parameters_nn['solver'][0]
        alpha = parameters_nn['alpha'][0]
        learning_rate = parameters_nn['learning_rate'][0]
        num_batches_size = parameters_nn['num_batches_size'][0]

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc, \
            y_pred, feature_imp, precision, recall, thresholds = \
            ml_algorithms_run_best_parameters.run_NN(features_data_train, features_data_test, labels_train,
                                                     labels_test, solver, alpha, hidden_layer_size,
                                                     learning_rate, activation,max_iterations,num_batches_size,
                                                     project_key, label_name[0], all_but_one_group)

        d = {
            'project_key': project_key, 'usability_label': label_name[0], 'feature_importance': feature_imp,
            'accuracy': accuracy, 'confusion_matrix': confusion_matrix, 'classification_report': classification_report,
            'area_under_pre_recall_curve':area_under_pre_recall_curve,'avg_precision': average_precision,
            'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision,'recall': recall,
            'thresholds': thresholds, 'Model': 'NN'
        }

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

        # Naive Algorithms
        path = addPath(f'Master/Models/train_test/{project_key}')
        features_data_train2 = pd.read_csv(
            f'{path}/features_data_train_{project_key}_{label_name[0]}.csv', low_memory=False)
        features_data_test2 = pd.read_csv(
            f'{path}/features_data_test_{project_key}_{label_name[0]}.csv', low_memory=False)

        features_data_train['label_is_empty'] = features_data_train2['if_description_empty_tbd'].apply(
            lambda x: x)
        features_data_test['label_is_empty'] = features_data_test2['if_description_empty_tbd'].apply(lambda x: x)

        #empty
        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc, \
            y_pred, feature_imp, precision, recall, thresholds = \
            ml_algorithms_run_best_parameters.run_is_empty(features_data_train, features_data_test, labels_train,
                                                           labels_test, project_key, label_name[0], all_but_one_group)

        d = {
            'project_key': project_key, 'usability_label': label_name[0], 'feature_importance': feature_imp,
            'accuracy': accuracy, 'confusion_matrix': confusion_matrix, 'classification_report': classification_report,
            'area_under_pre_recall_curve':area_under_pre_recall_curve,'avg_precision': average_precision,
            'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision,'recall': recall,
            'thresholds': thresholds, 'Model': 'Empty'
        }

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

        # Zero
        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc, \
            y_pred, feature_imp, precision, recall, thresholds = \
            ml_algorithms_run_best_parameters.run_is_zero(features_data_train, features_data_test, labels_train,
                                                          labels_test, project_key, label_name[0], all_but_one_group)

        d = {
            'project_key': project_key, 'usability_label': label_name[0], 'feature_importance': feature_imp,
            'accuracy': accuracy, 'confusion_matrix': confusion_matrix, 'classification_report': classification_report,
            'area_under_pre_recall_curve':area_under_pre_recall_curve,'avg_precision': average_precision,
            'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision,'recall': recall,
            'thresholds': thresholds, 'Model': 'Zero'
        }

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

        #Random
        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc, \
            y_pred, feature_imp, precision, recall, thresholds = \
            ml_algorithms_run_best_parameters.run_random(features_data_train, features_data_test, labels_train,
                                                         labels_test, project_key, label_name[0], all_but_one_group)

        d = {
            'project_key': project_key, 'usability_label': label_name[0], 'feature_importance': feature_imp,
            'accuracy': accuracy, 'confusion_matrix': confusion_matrix, 'classification_report': classification_report,
            'area_under_pre_recall_curve':area_under_pre_recall_curve,'avg_precision': average_precision,
            'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision,'recall': recall,
            'thresholds': thresholds, 'Model': 'Random'
        }

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

        path = addPath(f'Master/Instability_With_BERT/Results/{project_key}')
        results.to_csv(f'{path}/results_{project_key}_{label_name[0]}.csv', index=False)

        results = pd.DataFrame(columns=['project_key', 'usability_label', 'Model', 'feature_importance', 'accuracy',
                                        'confusion_matrix', 'classification_report', 'area_under_pre_recall_curve',
                                        'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                                        'recall', 'thresholds'])


if __name__ == "__main__":
    print('Hello World')