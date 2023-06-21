import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn import metrics
from sklearn.model_selection import RandomizedSearchCV
from funcsigs import signature
import matplotlib.pyplot as plt
from sklearn.neural_network import MLPClassifier
from imblearn.over_sampling import RandomOverSampler
import numpy as np
from sklearn.preprocessing import StandardScaler

from sklearn.ensemble import GradientBoostingClassifier

from xgboost import XGBClassifier
from pathlib import Path
import os


def addPath(path):
    return str(Path(os.getcwd()).joinpath(path))


"""
this script run the all the different model types,
get the data with the best features the selected parameters, make predictions and return the prediction results.
in the main function we run the prediction every time with different parameters,
and return the results
"""


def create_pre_rec_curve(y_test, y_score, average_precision, label, all_but_one_group, algorithm,
                         auc_PRC_path=None):
    """
    this function create the precision and recall curve and save the fig results
    """
    precision, recall, thresholds = metrics.precision_recall_curve(y_test, y_score[:, 1], pos_label=1)
    area = metrics.auc(recall, precision)
    print('Area Under Curve: {0:0.2f}'.format(area))
    step_kwargs = ({'step': 'post'} if 'step' in signature(plt.fill_between).parameters else {})
    plt.step(recall, precision, color='b', alpha=0.2, where='post')
    plt.fill_between(recall, precision, alpha=0.2, color='b', **step_kwargs)
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.ylim([0.0, 1.05])
    plt.xlim([0.0, 1.0])
    plt.title('2-class Precision-Recall curve: AP={0:0.2f}'.format(average_precision))
    if auc_PRC_path is not None:
        plt.savefig(
            f'{auc_PRC_path}/AUC_PRC_VALIDATION_{label}_{algorithm}.png')
    plt.close()
    return area


def run_model_optimization(x_train, x_test, y_train, y_test, label, all_but_one_group, parameters_path):
    print(list(x_train))
    x_train = x_train.drop(columns=['created'])
    x_test = x_test.drop(columns=['created'])
    x_train = x_train.drop(columns=['issue_key'])
    x_test = x_test.drop(columns=['issue_key'])
    features = list(x_train)
    # down/up_sampling
    # x_train, y_train = down_sampling1(x_train, y_train, True)

    # run model:
    # RF:
    rf_results = pd.DataFrame(columns=['usability_label', 'features', 'feature_importance',
                                       'accuracy_rf', 'confusion_matrix_rf', 'classification_report_rf',
                                       'area_under_pre_recall_curve_rf', 'avg_precision_rf',
                                       'area_under_roc_curve_rf', 'y_pred_rf', 'num_trees', 'max_features',
                                       'max_depth', 'min_samples_split', 'min_samples_leaf', 'bootstrap',
                                       'random_state'])
    parmas = {
        'class_weight': ["balanced", 'balanced_subsample', None],
        'n_estimators': [int(x) for x in np.linspace(start=200, stop=2000, num=10)],
        'max_features': ['auto', 'sqrt', 'log2', None],
        'max_depth': [int(x) for x in np.linspace(10, 110, num=11)],
        'min_samples_leaf': [1, 2, 3, 4, 5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100, 150, 200, 250, 300],
        'min_samples_split': [2, 3, 4, 5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100, 150, 200, 250, 300],
        'bootstrap': [True, False],
        'random_state': [0, 1, 2, 3, 4, 5, 7, 10, 15]
    }

    accuracy_rf, confusion_matrix_rf, classification_report_rf, \
        area_under_pre_recall_curve_rf, avg_pre_rf, avg_auc_rf, y_pred_rf, \
        feature_importance, best_params = \
        run_best_params_CV_with_sample_weight(model=RandomForestClassifier(), diction=parmas,
                                              model_name="RF",
                                              x_train=x_train, x_test=x_test, y_train=y_train,
                                              y_test=y_test, label=label,
                                              all_but_one_group=all_but_one_group,
                                              auc_PRC_path=parameters_path)

    d = {'usability_label': label, 'features': features,
         'feature_importance': feature_importance, 'accuracy_rf': accuracy_rf,
         'confusion_matrix_rf': confusion_matrix_rf,
         'classification_report_rf': classification_report_rf,
         'area_under_pre_recall_curve_rf': area_under_pre_recall_curve_rf,
         'avg_precision_rf': avg_pre_rf, 'area_under_roc_curve_rf': avg_auc_rf,
         'y_pred_rf': y_pred_rf, 'num_trees': best_params['n_estimators'], 'max_features': best_params['max_features'],
         'max_depth': best_params['max_depth'], 'min_samples_split': best_params['min_samples_split'],
         'min_samples_leaf': best_params['min_samples_leaf'],
         'class_weight': best_params['class_weight'],
         'bootstrap': best_params['bootstrap'],
         'random_state': best_params['random_state']}

    rf_results = pd.concat([rf_results, pd.DataFrame([d.values()], columns=d.keys())],
                           ignore_index=True)

    rf_results.to_csv(
        f'{parameters_path}/Parameters_{label}_RF.csv', index=False)

    # XGboost:
    xgboost_results = pd.DataFrame(columns=['usability_label', 'accuracy_xgboost',
                                            'confusion_matrix_xgboost', 'classification_report_xgboost',
                                            'area_under_pre_recall_curve_xgboost', 'avg_precision_xgboost',
                                            'area_under_roc_curve_xgboost', 'y_pred_xgboost', 'num_trees',
                                            'max_features', 'max_depth', 'min_samples_split', 'min_samples_leaf',
                                            'random_state'])
    parmas = {
        'n_estimators': [int(x) for x in np.linspace(start=200, stop=2000, num=10)],
        'max_features': ['auto', 'sqrt', 'log2', None],
        'max_depth': [int(x) for x in np.linspace(10, 110, num=11)],
        'min_samples_leaf': [1, 2, 4, 5, 10, 15, 20, 50, 100, 150, 200, 250, 300],
        'min_samples_split': [2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 50, 100, 150, 200, 250, 300],
        'learning_rate': [0.0001, 0.005, 0.01, 0.05, 0.07, 0.8, 0.9, 0.1, 0.11, 0.15, 0.2],
        'subsample': [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        'random_state': [0, 1, 2, 3, 4, 5, 7, 10, 15]
    }

    accuracy_xgboost, confusion_matrix_xgboost, classification_report_xgboost, \
        area_under_pre_recall_curve_xgboost, avg_pre_xgboost, avg_auc_xgboost, \
        y_pred_xgboost, feature_importance, best_params = \
        run_best_params_CV_with_sample_weight(model=GradientBoostingClassifier(),
                                              diction=parmas, model_name='XGboost',
                                              x_train=x_train, x_test=x_test,
                                              y_train=y_train, y_test=y_test, label=label,
                                              all_but_one_group=all_but_one_group,
                                              auc_PRC_path=parameters_path)

    d = {'usability_label': label,
         'accuracy_xgboost': accuracy_xgboost,
         'confusion_matrix_xgboost': confusion_matrix_xgboost,
         'classification_report_xgboost': classification_report_xgboost,
         'area_under_pre_recall_curve_xgboost': area_under_pre_recall_curve_xgboost,
         'avg_precision_xgboost': avg_pre_xgboost, 'area_under_roc_curve_xgboost': avg_auc_xgboost,
         'y_pred_xgboost': y_pred_xgboost, 'num_trees': best_params['n_estimators'],
         'max_features': best_params['max_features'],
         'max_depth': best_params['max_depth'], 'min_samples_split': best_params['min_samples_split'],
         'min_samples_leaf': best_params['min_samples_leaf'],
         'learning_rate': best_params['learning_rate'],
         'subsample': best_params['subsample'],
         'random_state': best_params['random_state'],
         }

    xgboost_results = pd.concat([xgboost_results, pd.DataFrame([d.values()], columns=d.keys())],
                                ignore_index=True)

    xgboost_results.to_csv(
        f'{parameters_path}/Parameters_{label}_XGboost.csv', index=False)

    # NN:
    nn_results = pd.DataFrame(columns=['usability_label', 'accuracy_nn',
                                       'confusion_matrix_nn', 'classification_report_nn',
                                       'area_under_pre_recall_curve_nn', 'avg_precision_nn',
                                       'area_under_roc_curve_nn', 'y_pred_nn', 'num_units_hidden_layer',
                                       'max_iterations', 'solver', 'num_batches_size', 'activation', 'alpha',
                                       'learning_rate', 'random_state'])
    x_train_nn = x_train
    x_test_nn = x_test
    names = list(x_train_nn.columns.values)
    x_train_nn[names] = x_train_nn[names].astype(float)
    x_test_nn[names] = x_test_nn[names].astype(float)
    scaler = StandardScaler()
    scaler.fit(x_train_nn)
    x_train_nn[names] = scaler.transform(x_train_nn[names])
    x_test_nn[names] = scaler.transform(x_test_nn[names])

    oversampler = RandomOverSampler()
    X_train_resampled, y_train_resampled = oversampler.fit_resample(x_train_nn, y_train)

    parmas = {
        'solver': ['adam', 'sgd', 'lbfgs'],
        'hidden_layer_sizes': [(10,), (20,), (30,), (50,), (70,), (100,), (64, 32), (50, 50, 50), (5, 20, 30),
                               (30, 70, 30),
                               (100, 50, 100), (32, 64), (64, 32, 64, 32, 64)],
        'random_state': [0, 1, 2, 3, 4, 5, 7, 10, 15],
        'max_iter': [200, 300, 400, 500, 600, 800, 1000, 1500, 2000],
        'batch_size': ['auto', 20, 30, 40, 50, 100],
        'activation': ['logistic', 'tanh', 'relu'],
        'alpha': [0.0001, 0.005, 0.01, 0.05, 0.07, 0.8, 0.9, 0.1, 0.11, 0.15, 0.2],
        'learning_rate': ['constant', 'adaptive'],
    }
    accuracy_nn, confusion_matrix_nn, classification_report_nn, \
        area_under_pre_recall_curve_nn, avg_pre_nn, avg_auc_nn, \
        y_pred_nn, features, best_params = run_best_params_CV(model=MLPClassifier(), dict=parmas, model_name='NN',
                                                              x_train=X_train_resampled,
                                                              x_test=x_test_nn, y_train=y_train_resampled, y_test=y_test,
                                                            label=label,
                                                              all_but_one_group=all_but_one_group,
                                                              auc_PRC_path=parameters_path)

    d = {'usability_label': label,
         'accuracy_nn': accuracy_nn, 'confusion_matrix_nn': confusion_matrix_nn,
         'classification_report_nn': classification_report_nn,
         'area_under_pre_recall_curve_nn': area_under_pre_recall_curve_nn,
         'avg_precision_nn': avg_pre_nn, 'area_under_roc_curve_nn': avg_auc_nn,
         'y_pred_nn': y_pred_nn, 'num_units_hidden_layer': best_params['hidden_layer_sizes'],
         'max_iterations': best_params['max_iter'], 'solver': best_params['solver'],
         'num_batches_size': best_params['batch_size'],
         'activation': best_params['activation'], 'alpha': best_params['alpha'],
         'learning_rate': best_params['learning_rate'], 'random_state': best_params['random_state']}

    nn_results = pd.concat([nn_results, pd.DataFrame([d.values()], columns=d.keys())],
                           ignore_index=True)

    nn_results.to_csv(
        f'{parameters_path}/Parameters_{label}_NN.csv', index=False)


def run_best_params_CV(model, dict, model_name, x_train, x_test, y_train, y_test, label,
                       all_but_one_group, auc_PRC_path=None):
    """
    this function predict with the best params per model
    """

    clf = RandomizedSearchCV(estimator=model, param_distributions=dict, cv=3, verbose=0, random_state=42)

    # Train the model
    clf.fit(x_train, y_train)

    try:
        features = pd.Series(clf.feature_importances_, index=list(x_train.columns.values)).sort_values(ascending=False)
    except:
        features = 0
    # feature_imp = pd.Series(clf.feature_importances_, index=list(x_train.columns.values)).sort_values(ascending=False)
    # print(f"feature importance {model_name}:{feature_imp}")
    y_pred = clf.predict(x_test)
    y_score = clf.predict_proba(x_test)
    accuracy = metrics.accuracy_score(y_test, y_pred)
    # Model Accuracy
    print(f"Accuracy {model_name}:", accuracy)
    confusion_matrix = metrics.confusion_matrix(y_test, y_pred)
    print(f"confusion_matrix {model_name}: \n {confusion_matrix}")
    classification_report = metrics.classification_report(y_test, y_pred)
    print(f"classification_report {model_name}: \n {classification_report}")
    # Create precision, recall curve
    average_precision = metrics.average_precision_score(y_test, y_score[:, 1])
    print(f'Average precision-recall score {model_name}: {average_precision}')
    auc = metrics.roc_auc_score(y_test, y_score[:, 1], average='macro', sample_weight=None, max_fpr=None)
    print(f'AUC roc {model_name}: {auc}')
    area_under_pre_recall_curve = create_pre_rec_curve(y_test, y_score, average_precision,
                                                       label=label, all_but_one_group=all_but_one_group,
                                                       algorithm=model_name, auc_PRC_path=auc_PRC_path)
    print(f'area_under_pre_recall_curve {model_name}: {area_under_pre_recall_curve}')

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred, features, clf.best_params_]


def run_best_params_CV_with_sample_weight(model, diction, model_name, x_train, x_test, y_train, y_test, label,
                                          all_but_one_group, auc_PRC_path=None):
    """
    this function predict with the best params per model
    """

    clf = RandomizedSearchCV(estimator=model, param_distributions=diction, cv=3, verbose=0, random_state=42)

    # Train the model
    class_weights = dict(
        zip([0, 1], [(len(y_train) / (2 * np.bincount(y_train)))[0], (len(y_train) / (2 * np.bincount(y_train)))[1]]))
    sample_weight = np.array([class_weights[label] for label in y_train])

    fit_params = {'sample_weight': sample_weight}
    clf.fit(x_train, y_train, **fit_params)

    # Test sample_weight
    class_weights = dict(
        zip([0, 1], [(len(y_test) / (2 * np.bincount(y_test)))[0], (len(y_test) / (2 * np.bincount(y_test)))[1]]))
    sample_weight = np.array([class_weights[label] for label in y_test])

    try:
        features = pd.Series(clf.feature_importances_, index=list(x_train.columns.values)).sort_values(ascending=False)
    except:
        features = 0
    # feature_imp = pd.Series(clf.feature_importances_, index=list(x_train.columns.values)).sort_values(ascending=False)
    # print(f"feature importance {model_name}:{feature_imp}")
    y_pred = clf.predict(x_test)
    y_score = clf.predict_proba(x_test)
    accuracy = metrics.accuracy_score(y_test, y_pred, sample_weight=sample_weight)
    # Model Accuracy
    print(f"Accuracy {model_name}:", accuracy)
    confusion_matrix = metrics.confusion_matrix(y_test, y_pred, sample_weight=sample_weight)
    print(f"confusion_matrix {model_name}: \n {confusion_matrix}")
    classification_report = metrics.classification_report(y_test, y_pred, sample_weight=sample_weight)
    print(f"classification_report {model_name}: \n {classification_report}")
    # Create precision, recall curve
    average_precision = metrics.average_precision_score(y_test, y_score[:, 1], sample_weight=sample_weight)
    print(f'Average precision-recall score {model_name}: {average_precision}')
    auc = metrics.roc_auc_score(y_test, y_score[:, 1], average='macro', sample_weight=sample_weight, max_fpr=None)
    print(f'AUC roc {model_name}: {auc}')
    area_under_pre_recall_curve = create_pre_rec_curve2(y_test, y_score, average_precision, sample_weight,
                                                        label=label, all_but_one_group=all_but_one_group,
                                                        algorithm=model_name, auc_PRC_path=auc_PRC_path)
    print(f'area_under_pre_recall_curve {model_name}: {area_under_pre_recall_curve}')

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred, features, clf.best_params_]


def create_pre_rec_curve2(y_test, y_score, average_precision, sample_weight, label, all_but_one_group, algorithm,
                          auc_PRC_path=None):
    """
    this function create the precision and recall curve and save the fig results
    """
    precision, recall, thresholds =\
        metrics.precision_recall_curve(y_test, y_score[:, 1], pos_label=1,sample_weight=sample_weight)
    area = metrics.auc(recall, precision)
    print('Area Under Curve: {0:0.2f}'.format(area))
    step_kwargs = ({'step': 'post'} if 'step' in signature(plt.fill_between).parameters else {})
    plt.step(recall, precision, color='b', alpha=0.2, where='post')
    plt.fill_between(recall, precision, alpha=0.2, color='b', **step_kwargs)
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.ylim([0.0, 1.05])
    plt.xlim([0.0, 1.0])
    plt.title('2-class Precision-Recall curve: AP={0:0.2f}'.format(average_precision))
    if auc_PRC_path is not None:
        plt.savefig(
            f'{auc_PRC_path}/AUC_PRC_VALIDATION_{label}_{algorithm}.png')
    plt.close()

    return area
