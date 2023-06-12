import Instability_sample_weight.Add_BERT_predication as Add_BERT_predication
import Cross_Project_Instability.ml_algorithms_run_best_parameters as ml_algorithms_run_best_parameters
import pandas as pd
from pathlib import Path
import os
import numpy as np
import Utils.GetInstabilityData as GetInstabilityData

def addPath(path):
    return str(Path(os.getcwd()).joinpath(path))

def start():
    """
    this script read all the feature data (train and test), and run prediction script with the best parametrs and features, and run the script ml_algorithms_run_best_parameters
    which get the features and parameters and run + return the results to all the different models.
    we write in this script the results to excel
    """
    results = pd.DataFrame(columns=['usability_label', 'Model', 'feature_importance', 'accuracy',
                                    'confusion_matrix', 'classification_report', 'area_under_pre_recall_curve',
                                    'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                                    'recall', 'thresholds'])

    for k_unstable in [5, 10, 15, 20]:
        all_but_one_group = True

        # by the best group:
        features_data_train = GetInstabilityData.get_data_all_train('Master/', k_unstable)
        features_data_test = GetInstabilityData.get_data_all_test('Master/', k_unstable)

        path = addPath(f'Master/Instability_sample_weight/Parameters')
        parameters_rf = pd.read_csv(
            f'{path}/results_groups_label_{k_unstable}_RF.csv', low_memory=False)
        parameters_xg = pd.read_csv(
            f'{path}/results_groups_label_{k_unstable}_XGboost.csv', low_memory=False)
        parameters_nn = pd.read_csv(
            f'{path}/results_groups_label_{k_unstable}_NN.csv', low_memory=False)

        labels_train = GetInstabilityData.get_label_all_train('Master/', k_unstable)
        labels_test = GetInstabilityData.get_label_all_test('Master/', k_unstable)

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
        max_feature = parameters_rf['max_features'][0]\
            if type(parameters_rf['max_features'][0]) is not np.float64 else None
        max_depth = parameters_rf['max_depth'][0]
        min_samples_leaf = parameters_rf['min_samples_leaf'][0]
        min_samples_split = parameters_rf['min_samples_split'][0]
        bootstrap = parameters_rf['bootstrap'][0]
        class_weight = parameters_rf['class_weight'][0]\
            if type(parameters_rf['class_weight'][0]) is not np.float64 else None
        random_state = int(parameters_rf['random_state'][0])

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc, \
            y_pred, feature_imp, precision, recall, thresholds = \
            ml_algorithms_run_best_parameters.run_RF(features_data_train, features_data_test, labels_train,
                                                     labels_test, num_trees, max_feature, max_depth, min_samples_leaf,
                                                     min_samples_split, bootstrap, random_state, class_weight,
                                                     k_unstable, all_but_one_group)

        d = {
            'usability_label': k_unstable, 'feature_importance': feature_imp,
            'accuracy': accuracy, 'confusion_matrix': confusion_matrix, 'classification_report': classification_report,
            'area_under_pre_recall_curve':area_under_pre_recall_curve,'avg_precision': average_precision,
            'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision,'recall': recall,
            'thresholds': thresholds, 'Model': 'RF'
        }

        results = pd.concat([results,  pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

        # xgboost
        num_trees = parameters_xg['num_trees'][0]
        max_depth = parameters_xg['max_depth'][0]
        max_features = parameters_xg['max_features'][0]\
            if type(parameters_xg['max_features'][0]) is not np.float64 else None
        min_samples_split = parameters_xg['min_samples_split'][0]
        min_samples_leaf = parameters_xg['min_samples_leaf'][0]
        learning_rate = parameters_xg['learning_rate'][0]
        subsample = parameters_xg['subsample'][0]
        random_state = int(parameters_xg['random_state'][0])

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc, \
            y_pred, feature_imp, precision, recall, thresholds = \
            ml_algorithms_run_best_parameters.run_XG(features_data_train, features_data_test, labels_train,
                                                     labels_test, num_trees, max_depth, max_features,
                                                     min_samples_split, min_samples_leaf, learning_rate, subsample,
                                                     random_state, k_unstable, all_but_one_group)

        d = {
            'usability_label': k_unstable, 'feature_importance': feature_imp,
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
        random_state = int(parameters_nn['random_state'][0])

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc, \
            y_pred, feature_imp, precision, recall, thresholds = \
            ml_algorithms_run_best_parameters.run_NN(features_data_train, features_data_test, labels_train,
                                                     labels_test, solver, alpha, hidden_layer_size,
                                                     learning_rate, activation, max_iterations, num_batches_size,
                                                     random_state, k_unstable, all_but_one_group)

        d = {
            'usability_label': k_unstable, 'feature_importance': feature_imp,
            'accuracy': accuracy, 'confusion_matrix': confusion_matrix, 'classification_report': classification_report,
            'area_under_pre_recall_curve':area_under_pre_recall_curve,'avg_precision': average_precision,
            'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision,'recall': recall,
            'thresholds': thresholds, 'Model': 'NN'
        }

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

        path = addPath(f'Master/Cross_Project_Instability/Results')
        results.to_csv(f'{path}/results_{k_unstable}_2.csv', index=False)

        results = pd.DataFrame(columns=['usability_label', 'Model', 'feature_importance', 'accuracy',
                                        'confusion_matrix', 'classification_report', 'area_under_pre_recall_curve',
                                        'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                                        'recall', 'thresholds'])
