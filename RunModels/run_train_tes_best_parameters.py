import json

import Utils.ml_algorithms_run_best_parameters as ml_algorithms_run_best_parameters
import pandas as pd
import numpy as np
import os


if __name__ == "__main__":
    """
    this script read all the feature data (train and test), and run prediction script with the best parametrs and features, and run the script ml_algorithms_run_best_parameters
    which get the features and parameters and run + return the results to all the different models.
    we write in this script the results to excel
    """

    results = pd.DataFrame(columns=['project_key', 'usability_label', 'feature_importance', 'accuracy_rf',
                                    'confusion_matrix_rf', 'classification_report_rf', 'area_under_pre_recall_curve_rf',
                                    'avg_precision_rf', 'area_under_roc_curve_rf', 'y_pred_rf', 'precision_rf',
                                    'recall_rf', 'thresholds_rf', 'accuracy_nn', 'confusion_matrix_nn',
                                    'classification_report_nn', 'area_under_pre_recall_curve_nn',
                                    'avg_precision_nn', 'area_under_roc_curve_nn', 'y_pred_nn', 'precision_nn',
                                    'recall_nn', 'thresholds_nn', 'accuracy_xgboost', 'confusion_matrix_xgboost',
                                    'classification_report_xgboost', 'area_under_pre_recall_curve_xgboost',
                                    'avg_precision_xgboost', 'area_under_roc_curve_xgboost', 'y_pred_xgboost',
                                    'precision_xgboost', 'recall_xgboost', 'thresholds_xgboost', 'accuracy_empty',
                                    'confusion_matrix_empty', 'classification_report_empty',
                                    'area_under_pre_recall_curve_empty', 'avg_pre_empty',
                                    'area_under_roc_curve_empty', 'y_pred_empty', 'precision_empty', 'recall_empty',
                                    'thresholds_empty', 'accuracy_zero', 'confusion_matrix_zero',
                                    'classification_report_zero', 'area_under_pre_recall_curve_zero', 'avg_pre_zero',
                                    'area_under_roc_curve_zero', 'y_pred_zero', 'precision_zero', 'recall_zero',
                                    'thresholds_zero', 'accuracy_random', 'confusion_matrix_random',
                                    'classification_report_random', 'area_under_pre_recall_curve_random',
                                    'avg_pre_random', 'area_under_roc_curve_random', 'y_pred_random',
                                    'precision_random', 'recall_random', 'thresholds_random', 'y_test'])
    path = '..Models'
    text_type = 'original_summary_description_acceptance_sprint'

    dict_labels = {'is_change_text_num_words_5': 'num_unusable_issues_cretor_prev_text_word_5_ratio',
                   'is_change_text_num_words_10': 'num_unusable_issues_cretor_prev_text_word_10_ratio',
                   'is_change_text_num_words_15': 'num_unusable_issues_cretor_prev_text_word_15_ratio',
                   'is_change_text_num_words_20': 'num_unusable_issues_cretor_prev_text_word_20_ratio'}

    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    projects_key = []
    for jira_name, jira_obj in jira_data_sources.items():
        projects_key.append(jira_name)

    # check the results on each project and label
    for project_key in projects_key:
        for label_name in dict_labels.items():
            print("data: {}, \n label_name.key: {}, \n".format(project_key, label_name[0]))
            all_but_one_group = True
            # by the best group:
            if all_but_one_group:
                features_data_train = pd.read_csv(
                    '{}/train_test_after_all_but/features_data_train_{}_{}.csv'.format(
                    path,project_key, label_name[0]), low_memory=False)
                features_data_test = pd.read_csv(
                    '{}/train_test_after_all_but/features_data_test_{}_{}.csv'.format(
                    path,project_key, label_name[0]), low_memory=False)
                parameters_rf = pd.read_csv(
                    '{}/optimization_results/grid_results_groups_{}_label_{}_RF.csv'.format(
                        path,project_key, label_name[0]), low_memory=False)
                parameters_xg = pd.read_csv(
                    '{}/optimization_results/grid_results_groups_{}_label_{}_XGboost.csv'.format(
                        path,project_key, label_name[0]), low_memory=False)
                parameters_nn = pd.read_csv(
                    '{}/optimization_results/grid_results_groups_{}_label_{}_NN.csv'.format(
                        path,project_key, label_name[0]), low_memory=False)
            # all groups
            else:
                features_data_train = pd.read_csv(
                    '{}/train_test_after_chi/features_data_train_{}_{}.csv'.format(
                        path,project_key, label_name[0]), low_memory=False)
                features_data_test = pd.read_csv(
                    '{}/train_test_after_chi/features_data_test_{}_{}.csv'.format(
                        path,project_key, label_name[0]), low_memory=False)
                parameters_rf = pd.read_csv(
                    '{}/optimization_results/grid_results_{}_label_{}_RF.csv'.format(
                        path,project_key, label_name[0]), low_memory=False)
                parameters_xg = pd.read_csv(
                    '{}/optimization_results/grid_results_{}_label_{}_XGboost.csv'.format(
                        path,project_key, label_name[0]), low_memory=False)
                parameters_nn = pd.read_csv(
                    '{}/optimization_results/grid_results_{}_label_{}_NN.csv'.format(
                        path,project_key, label_name[0]), low_memory=False)
            labels_train = pd.read_csv(
                '{}/train_test/labels_train_{}_{}.csv'.format(
                    path,project_key, label_name[0]), low_memory=False)
            labels_test = pd.read_csv(
                '{}/train_test/labels_test_{}_{}.csv'.format(
                    path,project_key, label_name[0]), low_memory=False)

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

            # get the hyper parameters:
            num_trees_rf = parameters_rf['n_estimators_rf'][0]
            max_feature_rf = parameters_rf['max_features_rf'][0]
            max_depth_rf = parameters_rf['max_depth_rf'][0]
            num_trees_xg = parameters_xg['n_estimators_xgboost'][0]
            max_depth_xg = parameters_xg['max_depth_xgboost'][0]
            alpha_xg = parameters_xg['alpha_xgboost'][0]
            scale_pos_weight_xg = parameters_xg['scale_pos_weight_xgboost'][0]
            min_child_weight_xg = parameters_xg['min_child_weight_xgboost'][0]
            hidden_layer_size = parameters_nn['hidden_layer_sizes_nn'][0]
            activation_nn = parameters_nn['activation_nn'][0]
            solver_nn = parameters_nn['solver_nn'][0]
            alpha_nn = parameters_nn['alpha_nn'][0]
            learning_rate_nn = parameters_nn['learning_rate_nn'][0]
            feature_importance, accuracy_rf, confusion_matrix_rf, classification_report_rf, \
                area_under_pre_recall_curve_rf, avg_pre_rf, area_under_roc_curve_rf, y_pred_rf, precision_rf, \
                recall_rf, thresholds_rf, accuracy_nn, confusion_matrix_nn, classification_report_nn, \
                area_under_pre_recall_curve_nn, avg_pre_nn, area_under_roc_curve_nn, y_pred_nn, precision_nn, \
                recall_nn, thresholds_nn, accuracy_xgboost, confusion_matrix_xgboost, classification_report_xgboost, \
                area_under_pre_recall_curve_xgboost, avg_pre_xgboost, area_under_roc_curve_xgboost, y_pred_xgboost, \
                precision_xgboost, recall_xgboost, thresholds_xgboost = ml_algorithms_run_best_parameters.run_model(
                    features_data_train, features_data_test, labels_train,
                    labels_test, 0, project_key, label_name[0], num_trees_rf, max_feature_rf,
                    max_depth_rf, hidden_layer_size, activation_nn, solver_nn, alpha_nn, learning_rate_nn, num_trees_xg,
                    max_depth_xg, alpha_xg, scale_pos_weight_xg, min_child_weight_xg, all_but_one_group)

            features_data_train2 = pd.read_csv(
                '{}/train_test/features_data_train_{}_{}.csv'.format(
                    path,project_key, label_name[0]), low_memory=False)
            features_data_test2 = pd.read_csv(
                '{}/train_test/features_data_test_{}_{}.csv'.format(
                    path,project_key, label_name[0]), low_memory=False)
            features_data_train['label_is_empty'] = features_data_train2['if_description_empty_tbd'].apply(
                lambda x: x)
            features_data_test['label_is_empty'] = features_data_test2['if_description_empty_tbd'].apply(lambda x: x)

            accuracy_empty, confusion_matrix_empty, classification_report_empty, \
                area_under_pre_recall_curve_empty, avg_pre_empty, avg_auc_empty, y_pred_empty, precision_empty, \
                recall_empty, thresholds_empty, accuracy_zero, confusion_matrix_zero, classification_report_zero, \
                area_under_pre_recall_curve_zero, avg_pre_zero, avg_auc_zero, y_pred_zero, precision_zero, \
                recall_zero, thresholds_zero, accuracy_random, confusion_matrix_random, classification_report_random, \
                area_under_pre_recall_curve_random, avg_pre_random, avg_auc_random, y_pred_random, precision_random, \
                recall_random, thresholds_random = ml_algorithms_run_best_parameters.run_model(
                    features_data_train, features_data_test, labels_train,
                    labels_test, 1, project_key, label_name[0], 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, all_but_one_group)

            d = {'project_key': project_key, 'usability_label': label_name[0],
                 'feature_importance': feature_importance, 'accuracy_rf': accuracy_rf,
                 'confusion_matrix_rf': confusion_matrix_rf, 'classification_report_rf': classification_report_rf,
                 'area_under_pre_recall_curve_rf': area_under_pre_recall_curve_rf, 'avg_precision_rf': avg_pre_rf,
                 'area_under_roc_curve_rf': area_under_roc_curve_rf, 'y_pred_rf': y_pred_rf,
                 'precision_rf': precision_rf, 'recall_rf': recall_rf, 'thresholds_rf': thresholds_rf,
                 'accuracy_nn': accuracy_nn, 'confusion_matrix_nn': confusion_matrix_nn,
                 'classification_report_nn': classification_report_nn,
                 'area_under_pre_recall_curve_nn': area_under_pre_recall_curve_nn, 'avg_precision_nn': avg_pre_nn,
                 'area_under_roc_curve_nn': area_under_roc_curve_nn, 'y_pred_nn': y_pred_nn,
                 'precision_nn': precision_nn, 'recall_nn': recall_nn, 'thresholds_nn': thresholds_nn,
                 'accuracy_xgboost': accuracy_xgboost, 'confusion_matrix_xgboost': confusion_matrix_xgboost,
                 'classification_report_xgboost': classification_report_xgboost,
                 'area_under_pre_recall_curve_xgboost': area_under_pre_recall_curve_xgboost,
                 'avg_precision_xgboost': avg_pre_xgboost, 'area_under_roc_curve_xgboost': area_under_roc_curve_xgboost,
                 'y_pred_xgboost': y_pred_xgboost, 'precision_xgboost': precision_xgboost,
                 'recall_xgboost': recall_xgboost, 'thresholds_xgboost': thresholds_xgboost,
                 'accuracy_empty': accuracy_empty, 'confusion_matrix_empty': confusion_matrix_empty,
                 'classification_report_empty': classification_report_empty,
                 'area_under_pre_recall_curve_empty': area_under_pre_recall_curve_empty,
                 'avg_pre_empty': avg_pre_empty, 'area_under_roc_curve_empty': avg_auc_empty,
                 'y_pred_empty': y_pred_empty, 'precision_empty': precision_empty, 'recall_empty': recall_empty,
                 'thresholds_empty': thresholds_empty, 'accuracy_zero': accuracy_zero,
                 'confusion_matrix_zero': confusion_matrix_zero, 'classification_report_zero': classification_report_zero,
                 'area_under_pre_recall_curve_zero': area_under_pre_recall_curve_zero, 'avg_pre_zero': avg_pre_zero,
                 'area_under_roc_curve_zero': avg_auc_zero, 'y_pred_zero': y_pred_zero,
                 'precision_zero': precision_zero, 'recall_zero': recall_zero, 'thresholds_zero': thresholds_zero,
                 'accuracy_random': accuracy_random, 'confusion_matrix_random': confusion_matrix_random,
                 'classification_report_random': classification_report_random,
                 'area_under_pre_recall_curve_random': area_under_pre_recall_curve_random,
                 'avg_pre_random': avg_pre_random, 'area_under_roc_curve_random': avg_auc_random,
                 'y_pred_random': y_pred_random, 'precision_random': precision_random, 'recall_random': recall_random,
                 'thresholds_random': thresholds_random, 'y_test': labels_test['usability_label']}

            results = results.append(d, ignore_index=True)

            if all_but_one_group:
                results.to_csv('{}/results_best_para/results_groups_{}.csv'.format(path,project_key),
                               index=False)
            else:
                results.to_csv(
                    '{}/results_best_para/results_{}.csv'.format(path,project_key),
                    index=False)

        results = pd.DataFrame(
            columns=['project_key', 'usability_label', 'feature_importance', 'accuracy_rf',
                     'confusion_matrix_rf', 'classification_report_rf', 'area_under_pre_recall_curve_rf',
                     'avg_precision_rf', 'area_under_roc_curve_rf', 'y_pred_rf', 'precision_rf', 'recall_rf',
                     'thresholds_rf', 'accuracy_nn', 'confusion_matrix_nn', 'classification_report_nn',
                     'area_under_pre_recall_curve_nn', 'avg_precision_nn', 'area_under_roc_curve_nn', 'y_pred_nn',
                     'precision_nn', 'recall_nn', 'thresholds_nn', 'accuracy_xgboost',
                     'confusion_matrix_xgboost', 'classification_report_xgboost',
                     'area_under_pre_recall_curve_xgboost', 'avg_precision_xgboost',
                     'area_under_roc_curve_xgboost', 'y_pred_xgboost', 'precision_xgboost', 'recall_xgboost',
                     'thresholds_xgboost', 'accuracy_empty',
                     'confusion_matrix_empty', 'classification_report_empty', 'area_under_pre_recall_curve_empty',
                     'avg_pre_empty', 'area_under_roc_curve_empty', 'y_pred_empty', 'precision_empty',
                     'recall_empty', 'thresholds_empty', 'accuracy_zero', 'confusion_matrix_zero',
                     'classification_report_zero', 'area_under_pre_recall_curve_zero', 'avg_pre_zero',
                     'area_under_roc_curve_zero', 'y_pred_zero', 'precision_zero', 'recall_zero', 'thresholds_zero',
                     'accuracy_random', 'confusion_matrix_random', 'classification_report_random',
                     'area_under_pre_recall_curve_random', 'avg_pre_random', 'area_under_roc_curve_random',
                     'y_pred_random', 'precision_random', 'recall_random', 'thresholds_random', 'y_test'])
