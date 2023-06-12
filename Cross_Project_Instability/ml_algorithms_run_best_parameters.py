from numpy import random
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn import metrics
from funcsigs import signature
import matplotlib.pyplot as plt
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingClassifier
from pathlib import Path
from imblearn.over_sampling import RandomOverSampler
import os
import numpy as np

def addPath(path):
    return str(Path(os.getcwd()).joinpath(path))


"""
this script run the all the different model types,
get the data with the best features and hyper parameters, make predictions and return the prediction results.
"""

def create_pre_rec_curve(y_test, y_score, auc, algorithm, label, all_but_one_group):
    """
    this function create the precision and recall curve and save the fig results 
    """
    precision, recall, thresholds = metrics.precision_recall_curve(y_test, y_score, pos_label=1)
    area = metrics.auc(recall, precision)
    print('Area Under Curve: {0:0.2f}'.format(area))
    step_kwargs = ({'step': 'post'} if 'step' in signature(plt.fill_between).parameters else {})
    plt.step(recall, precision, color='b', alpha=0.2, where='post')
    plt.fill_between(recall, precision, alpha=0.2, color='b', **step_kwargs)
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.ylim([0.0, 1.05])
    plt.xlim([0.0, 1.0])

    path = addPath(f'Master/Cross_Project_Instability/Results')
    if all_but_one_group:
        plt.savefig(
            f'{path}/pre_recall_curve_groups_{label}_{algorithm}_2.png')

    else:
        plt.savefig(
            f'{path}/pre_recall_curve_{label}_{algorithm}.png')

    plt.close()
    return area


def run_RF(x_train, x_test, y_train, y_test, num_trees_rf, max_feature_rf,
           max_depth_rf, min_samples_leaf, min_samples_split, bootstrap, random_state, class_weight, label,
           all_but_one_group):
    x_train = x_train.copy()
    x_test = x_test.copy()

    x_train = x_train.drop(columns=['created'])
    x_test = x_test.drop(columns=['created'])
    x_train = x_train.drop(columns=['issue_key'])
    x_test = x_test.drop(columns=['issue_key'])

    clf = RandomForestClassifier(n_estimators=num_trees_rf, max_features=max_feature_rf, max_depth=max_depth_rf,
                                 random_state=random_state, min_samples_leaf=min_samples_leaf, min_samples_split=min_samples_split,
                                 bootstrap=bootstrap, class_weight=class_weight)

    return run_generic_model_with_sample_weight(clf, "RF", x_train, x_test, y_train, y_test, label, all_but_one_group)


def run_XG(x_train, x_test, y_train, y_test, num_trees, max_depth_xg,
           max_features, min_samples_split, min_samples_leaf, learning_rate, subsample, random_state, label, all_but_one_group):
    x_train = x_train.copy()
    x_test = x_test.copy()

    x_train = x_train.drop(columns=['created'])
    x_test = x_test.drop(columns=['created'])
    x_train = x_train.drop(columns=['issue_key'])
    x_test = x_test.drop(columns=['issue_key'])

    clf = GradientBoostingClassifier(n_estimators=num_trees, max_depth=max_depth_xg, max_features=max_features,
                                     min_samples_split=min_samples_split, min_samples_leaf=min_samples_leaf,
                                     learning_rate=learning_rate, subsample=subsample, random_state=random_state)

    return run_generic_model_with_sample_weight(clf, "XGboost", x_train, x_test, y_train, y_test, label, all_but_one_group)


def run_NN(x_train, x_test, y_train, y_test, solver_nn, alpha_nn,
           hidden_layer_size, learning_rate_nn, activation_nn, max_iterations, num_batches_size, random_state,
           label, all_but_one_group):
    x_train = x_train.drop(columns=['created'])
    x_test = x_test.drop(columns=['created'])
    x_train = x_train.drop(columns=['issue_key'])
    x_test = x_test.drop(columns=['issue_key'])

    x_train_nn = x_train.copy()
    x_test_nn = x_test.copy()

    names = list(x_train_nn.columns.values)
    x_train_nn[names] = x_train_nn[names].astype(float)
    x_test_nn[names] = x_test_nn[names].astype(float)
    scaler = StandardScaler()
    scaler.fit(x_train_nn)
    x_train_nn1 = scaler.transform(x_train_nn[names])
    x_test_nn1 = scaler.transform(x_test_nn[names])

    oversampler = RandomOverSampler()
    X_train_resampled, y_train_resampled = oversampler.fit_resample(x_train_nn1, y_train)

    a = hidden_layer_size.replace("(", "")
    a = a.replace(")", "")
    a = a.replace(",", "")
    b = tuple(map(int, a.split()))

    clf = MLPClassifier(solver=solver_nn, alpha=alpha_nn, hidden_layer_sizes=b, random_state=random_state,
                        max_iter=max_iterations, learning_rate=learning_rate_nn,
                        activation=activation_nn, batch_size=num_batches_size)

    return run_generic_model(clf, "NN", X_train_resampled, x_test_nn1, y_train_resampled,
                             y_test, label, all_but_one_group)


def run_generic_model(clf, model_name, x_train, x_test, y_train, y_test, label, all_but_one_group):

    # Train the model
    clf.fit(x_train, y_train)
    try:
        feature_imp = pd.Series(clf.feature_importances_, index=list(x_train.columns.values)).sort_values(ascending=False)
    except:
        feature_imp = []

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
    auc = metrics.roc_auc_score(y_test, y_score[:, 1])
    print(f'AUC roc {model_name}: {auc}')
    precision, recall, thresholds = metrics.precision_recall_curve(y_test, y_score[:, 1])
    area_under_pre_recall_curve = metrics.auc(recall, precision)
    print(f'area_under_pre_recall_curve {model_name}: {area_under_pre_recall_curve}')
    create_pre_rec_curve(y_test, y_score[:, 1], average_precision, model_name, label, all_but_one_group)

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred, feature_imp, precision, recall, thresholds]


def run_generic_model_with_sample_weight(clf, model_name, x_train, x_test,
                                         y_train, y_test, label, all_but_one_group):
    class_weights = dict(
        zip([0, 1], [(len(y_train) / (2 * np.bincount(y_train)))[0], (len(y_train) / (2 * np.bincount(y_train)))[1]]))
    sample_weight = np.array([class_weights[label] for label in y_train])

    # Train the model
    clf.fit(x_train, y_train, sample_weight=sample_weight)

    # Test sample_weight
    class_weights = dict(
        zip([0, 1], [(len(y_test) / (2 * np.bincount(y_test)))[0], (len(y_test) / (2 * np.bincount(y_test)))[1]]))
    sample_weight = np.array([class_weights[label] for label in y_test])

    try:
        feature_imp = pd.Series(clf.feature_importances_, index=list(x_train.columns.values)).sort_values(ascending=False)
    except:
        feature_imp = []

    y_pred = clf.predict(x_test)
    y_score = clf.predict_proba(x_test)
    accuracy = metrics.accuracy_score(y_test, y_pred)
    # Model Accuracy
    print(f"Accuracy {model_name}:", accuracy)
    confusion_matrix = metrics.confusion_matrix(y_test, y_pred, sample_weight=sample_weight)
    print(f"confusion_matrix {model_name}: \n {confusion_matrix}")
    classification_report = metrics.classification_report(y_test, y_pred,sample_weight=sample_weight)
    print(f"classification_report {model_name}: \n {classification_report}")
    # Create precision, recall curve
    average_precision = metrics.average_precision_score(y_test, y_score[:, 1],sample_weight=sample_weight)
    print(f'Average precision-recall score {model_name}: {average_precision}')
    auc = metrics.roc_auc_score(y_test, y_score[:, 1])
    print(f'AUC roc {model_name}: {auc}')
    precision, recall, thresholds = metrics.precision_recall_curve(y_test, y_score[:, 1], sample_weight=sample_weight)
    area_under_pre_recall_curve = metrics.auc(recall, precision)
    print(f'area_under_pre_recall_curve {model_name}: {area_under_pre_recall_curve}')
    create_pre_rec_curve2(y_test, y_score[:, 1], sample_weight,
                          average_precision, model_name, label, all_but_one_group)

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred, feature_imp, precision, recall, thresholds]


def create_pre_rec_curve2(y_test, y_score, sample_weight, auc, algorithm, label, all_but_one_group):
    """
    this function create the precision and recall curve and save the fig results
    """
    precision, recall, thresholds =\
        metrics.precision_recall_curve(y_test, y_score, pos_label=1, sample_weight=sample_weight)
    area = metrics.auc(recall, precision)
    print('Area Under Curve: {0:0.2f}'.format(area))
    step_kwargs = ({'step': 'post'} if 'step' in signature(plt.fill_between).parameters else {})
    plt.step(recall, precision, color='b', alpha=0.2, where='post')
    plt.fill_between(recall, precision, alpha=0.2, color='b', **step_kwargs)
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.ylim([0.0, 1.05])
    plt.xlim([0.0, 1.0])

    path = addPath(f'Master/Cross_Project_Instability/Results')
    if all_but_one_group:
        plt.savefig(
            f'{path}/pre_recall_curve_groups_{label}_{algorithm}_2.png')

    else:
        plt.savefig(
            f'{path}/pre_recall_curve_{label}_{algorithm}.png')

    plt.close()
    return area
