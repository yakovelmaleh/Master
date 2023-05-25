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
import os

def addPath(path):
    return str(Path(os.getcwd()).joinpath(path))


"""
this script run the all the different model types,
get the data with the best features and hyper parameters, make predictions and return the prediction results.
"""


def run_is_empty(x_train, x_test, y_train, y_test, project_key, label, all_but_one_group):
    """
    this function predict by if is empty and return the results
    """
    # Train the model
    y_score = pd.DataFrame()
    y_score['0'] = x_test['label_is_empty'].apply(lambda x: 1.0 if x == 0 else 0.0)
    y_score['1'] = x_test['label_is_empty'].apply(lambda x: 1.0 if x == 1 else 0.0)
    accuracy = metrics.accuracy_score(y_test, x_test['label_is_empty'])
    # Model Accuracy
    print("Accuracy is_empty:", accuracy)
    confusion_matrix = metrics.confusion_matrix(y_test, x_test['label_is_empty'])
    print("confusion_matrix is_empty: \n {}".format(confusion_matrix))
    classification_report = metrics.classification_report(y_test, x_test['label_is_empty'])
    print("classification_report: \n {}".format(classification_report))
    # Create precision, recall curve
    average_precision = metrics.average_precision_score(y_test, y_score['1'])
    print('Average precision-recall score is_empty: {0:0.2f}'.format(average_precision))
    auc = metrics.roc_auc_score(y_test, y_score['1'], average='macro', sample_weight=None, max_fpr=None)
    print('AUC roc is_empty: {}'.format(auc))
    precision, recall, thresholds = metrics.precision_recall_curve(y_test, y_score['1'], pos_label=1)
    area_under_pre_recall_curve = metrics.auc(recall, precision)
    print('area_under_pre_recall_curve is_empty: {}'.format(area_under_pre_recall_curve))
    create_pre_rec_curve(y_test, y_score['1'], average_precision, 'Is_Empty', project_key, label, all_but_one_group)

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            x_test['label_is_empty'], [], precision, recall, thresholds]


def run_is_zero(x_train, x_test, y_train, y_test, project_key, label, all_but_one_group):
    """
    this function predict by is zero and return the results
    """
    # Train the model
    y_score = pd.DataFrame()
    y_score['0'] = x_test['label_is_empty'].apply(lambda x: 1.0)
    y_score['1'] = x_test['label_is_empty'].apply(lambda x: 0.0)
    y_score['all'] = 0
    accuracy = metrics.accuracy_score(y_test, y_score['all'])
    # Model Accuracy
    print("Accuracy is_zero:", accuracy)
    confusion_matrix = metrics.confusion_matrix(y_test, y_score['all'])
    print("confusion_matrix is_zero: \n {}".format(confusion_matrix))
    classification_report = metrics.classification_report(y_test, y_score['all'])
    print("classification_report: \n {}".format(classification_report))
    # Create precision, recall curve
    average_precision = metrics.average_precision_score(y_test, y_score['1'])
    print('Average precision-recall score is_zero: {0:0.2f}'.format(average_precision))
    auc = metrics.roc_auc_score(y_test, y_score['1'], average='macro', sample_weight=None, max_fpr=None)
    print('AUC roc is_zero: {}'.format(auc))
    precision, recall, thresholds = metrics.precision_recall_curve(y_test, y_score['1'], pos_label=1)
    area_under_pre_recall_curve = metrics.auc(recall, precision)
    print('area_under_pre_recall_curve is_zero: {}'.format(area_under_pre_recall_curve))
    create_pre_rec_curve(y_test, y_score['1'], average_precision, 'Is_Zero', project_key, label, all_but_one_group)

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_score['all'], [], precision, recall, thresholds]


def run_random(x_train, x_test, y_train, y_test, project_key, label, all_but_one_group):
    """
    this function predict randomly and return the results
    """
    # Train the model
    y_score = pd.DataFrame()
    y_score['0'] = x_test['label_is_empty'].apply(lambda x: random.uniform(0, 1))
    y_score['1'] = y_score['0'].apply(lambda x: 1-x)
    y_pred = pd.DataFrame()
    y_pred['pred'] = y_score['0'].apply(lambda x: 0 if x >= 0.5 else 1)
    accuracy = metrics.accuracy_score(y_test, y_pred['pred'])
    # Model Accuracy
    print("Accuracy is_random:", accuracy)
    confusion_matrix = metrics.confusion_matrix(y_test, y_pred['pred'])
    print("confusion_matrix is_random: \n {}".format(confusion_matrix))
    classification_report = metrics.classification_report(y_test, y_pred['pred'])
    print("classification_report is_random: \n {}".format(classification_report))
    # Create precision, recall curve
    average_precision = metrics.average_precision_score(y_test, y_score['1'])
    print('Average precision-recall score is_random: {0:0.2f}'.format(average_precision))
    auc = metrics.roc_auc_score(y_test, y_score['1'], average='macro', sample_weight=None, max_fpr=None)
    print('AUC roc is_random: {}'.format(auc))
    precision, recall, thresholds = metrics.precision_recall_curve(y_test, y_score['1'], pos_label=1)
    area_under_pre_recall_curve = metrics.auc(recall, precision)
    print('area_under_pre_recall_curve is_random: {}'.format(area_under_pre_recall_curve))
    create_pre_rec_curve(y_test, y_score['1'], average_precision, 'Random', project_key, label, all_but_one_group)

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred['pred'], [], precision, recall, thresholds]


def create_pre_rec_curve(y_test, y_score, auc, algorithm, project_key, label, all_but_one_group):
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
    plt.title('Precision-Recall curve {0}: Area under Curve={1:0.2f}'.format(project_key, auc))

    path = addPath(f'Master/Instability_With_BERT/Results/{project_key}')
    if all_but_one_group:
        plt.savefig(
            f'{path}/pre_recall_curve_groups_{project_key}_{label}_{algorithm}.png')

    else:
        plt.savefig(
            f'{path}/pre_recall_curve_{project_key}_{label}_{algorithm}.png')

    plt.close()
    return area


def run_RF(x_train, x_test, y_train, y_test, num_trees_rf, max_feature_rf,
           max_depth_rf, min_samples_leaf, min_samples_split, bootstrap, project_key, label, all_but_one_group):
    x_train = x_train.copy()
    x_test = x_test.copy()

    x_train = x_train.drop(columns=['created'])
    x_test = x_test.drop(columns=['created'])
    x_train = x_train.drop(columns=['issue_key'])
    x_test = x_test.drop(columns=['issue_key'])

    random_num_rf = 7
    clf = RandomForestClassifier(n_estimators=num_trees_rf, max_features=max_feature_rf, max_depth=max_depth_rf,
                                 random_state=7, min_samples_leaf=min_samples_leaf, min_samples_split=min_samples_split,
                                 bootstrap=bootstrap)

    return run_generic_model(clf, "RF", x_train, x_test, y_train, y_test, project_key, label, all_but_one_group)


def run_XG(x_train, x_test, y_train, y_test, num_trees, max_depth_xg,
           max_features, min_samples_split, min_samples_leaf, project_key, label, all_but_one_group):
    x_train = x_train.copy()
    x_test = x_test.copy()

    x_train = x_train.drop(columns=['created'])
    x_test = x_test.drop(columns=['created'])
    x_train = x_train.drop(columns=['issue_key'])
    x_test = x_test.drop(columns=['issue_key'])

    clf = GradientBoostingClassifier(n_estimators=num_trees, max_depth=max_depth_xg, max_features=max_features,
                                     min_samples_split=min_samples_split, min_samples_leaf=min_samples_leaf)

    return run_generic_model(clf, "XGboost", x_train, x_test, y_train, y_test, project_key, label, all_but_one_group)


def run_NN(x_train, x_test, y_train, y_test, solver_nn, alpha_nn,
           hidden_layer_size, learning_rate_nn, activation_nn, max_iterations, num_batches_size,
           project_key, label, all_but_one_group):
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

    a = hidden_layer_size.replace("(", "")
    a = a.replace(")", "")
    a = a.replace(",", "")
    b = tuple(map(int, a.split()))

    clf = MLPClassifier(solver=solver_nn, alpha=alpha_nn, hidden_layer_sizes=b, random_state=7,
                        max_iter=max_iterations, learning_rate=learning_rate_nn,
                        activation=activation_nn, batch_size=num_batches_size)

    return run_generic_model(clf, "NN", x_train_nn1, x_test_nn1, y_train, y_test, project_key, label, all_but_one_group)


def run_generic_model(clf, model_name, x_train, x_test, y_train, y_test, project_key, label, all_but_one_group):

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
    create_pre_rec_curve(y_test, y_score[:, 1], average_precision, model_name, project_key, label, all_but_one_group)

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred, feature_imp, precision, recall, thresholds]
