from numpy import random
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn import metrics
#from sklearn.model_selection import RandomizedSearchCV
#from sklearn.utils.fixes import signature
from funcsigs import signature
import matplotlib.pyplot as plt
from sklearn.neural_network import MLPClassifier
#from sklearn.model_selection import KFold
import numpy as np
from sklearn.preprocessing import StandardScaler
#from sklearn.preprocessing import MinMaxScaler
#from sklearn.decomposition import PCA
#from sklearn.ensemble import GradientBoostingClassifier
#import sklearn
#import xgboost as xgb
from xgboost import XGBClassifier

"""
this script run the all the different model types,
get the data with the best features and hyper parameters, make predictions and return the prediction results.
"""

def down_sampling1(x, y, is_down):
    # down_sampling:
    # Indicies of each class' observations
    y0_indices = [i for i in range(len(y)) if y[i] == 0]
    y1_indices = [i for i in range(len(y)) if y[i] == 1]
    # Number of observations in each class
    num_class0 = len(y0_indices)
    num_class1 = len(y1_indices)
    if is_down:
        # For every observation of class 0, randomly sample from class 1 without replacement
        i_class0_downsampled = np.random.choice(y0_indices, size=num_class1, replace=False)
        # Join together class 0's target vector with the downsampled class 1's target vector
        y = y[i_class0_downsampled].append(y[y1_indices], ignore_index=True)
        x = pd.DataFrame(x)
        x = x.iloc[i_class0_downsampled].append(x.iloc[y1_indices], ignore_index=True)
    else:
        #  ######## up sampling: ##################
        # For every observation in class 0, randomly sample from class 1 with replacement
        i_class1_upsampled = np.random.choice(y1_indices, size=int(num_class0), replace=True)
        # Join together class 1's upsampled target vector with class 0's target vector
        y = y[i_class1_upsampled].append(y[y0_indices], ignore_index=True)
        x = pd.DataFrame(x)
        x = x.iloc[i_class1_upsampled].append(x.iloc[y0_indices], ignore_index=True)

    return x, y


def run_random_forest(x_train, x_test, y_train, y_test, num_trees, max_feature, max_depth_rf, random_num,
                      project_key, label, all_but_one_group):
    """
    this function predict with the random forest model and return the results
    """
    clf = RandomForestClassifier(n_estimators=num_trees, max_features=max_feature, max_depth=max_depth_rf,
                                 random_state=random_num)
    # Train the model
    clf.fit(x_train, y_train)
    feature_imp = pd.Series(clf.feature_importances_, index=list(x_train.columns.values)).sort_values(ascending=False)
    y_pred = clf.predict(x_test)
    y_score = clf.predict_proba(x_test)
    accuracy = metrics.accuracy_score(y_test, y_pred)
    # Model Accuracy
    print("Accuracy RF:", accuracy)
    confusion_matrix = metrics.confusion_matrix(y_test, y_pred)
    print("confusion_matrix RF: \n {}".format(confusion_matrix))
    classification_report = metrics.classification_report(y_test, y_pred)
    print("classification_report RF: \n {}".format(classification_report))
    # Create precision, recall curve
    average_precision = metrics.average_precision_score(y_test, y_score[:, 1])
    print('Average precision-recall score RF: {0:0.2f}'.format(average_precision))
    auc = metrics.roc_auc_score(y_test, y_score[:, 1])
    print('AUC roc RF: {}'.format(auc))
    precision, recall, thresholds = metrics.precision_recall_curve(y_test, y_score[:, 1])
    area_under_pre_recall_curve = metrics.auc(recall, precision)
    print('area_under_pre_recall_curve RF: {}'.format(area_under_pre_recall_curve))
    create_pre_rec_curve(y_test, y_score[:, 1], average_precision, 'RF', project_key, label, all_but_one_group)
    print(8)

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred, feature_imp, precision, recall, thresholds]


def run_neural_net(x_train, x_test, y_train, y_test, hidden_layer_size, activation_nn, solver_nn, alpha_nn,
                   learning_rate_nn, random_num, project_key, label, all_but_one_group):
    """
    this function predict with the neural network model and return the results
    """
    a = hidden_layer_size.replace("(", "")
    a = a.replace(")", "")
    a = a.replace(",", "")
    b = tuple(map(int, a.split()))
    clf = MLPClassifier(solver=solver_nn, alpha=alpha_nn, hidden_layer_sizes=b, random_state=random_num,
                        max_iter=7000, learning_rate=learning_rate_nn, activation=activation_nn)
    # Train the model
    clf.fit(x_train, y_train)
    y_pred = clf.predict(x_test)
    y_score = clf.predict_proba(x_test)
    accuracy = metrics.accuracy_score(y_test, y_pred)
    # Model Accuracy
    print("Accuracy NN:", accuracy)
    confusion_matrix = metrics.confusion_matrix(y_test, y_pred)
    print("confusion_matrix NN: \n {}".format(confusion_matrix))
    classification_report = metrics.classification_report(y_test, y_pred)
    print("classification_report NN: \n {}".format(classification_report))
    # Create precision, recall curve
    average_precision = metrics.average_precision_score(y_test, y_score[:, 1])
    print('Average precision-recall score NN: {0:0.2f}'.format(average_precision))
    auc = metrics.roc_auc_score(y_test, y_score[:, 1])
    print('AUC roc NN: {}'.format(auc))
    precision, recall, thresholds = metrics.precision_recall_curve(y_test, y_score[:, 1])
    area_under_pre_recall_curve = metrics.auc(recall, precision)
    print('area_under_pre_recall_curve NN: {}'.format(area_under_pre_recall_curve))
    create_pre_rec_curve(y_test, y_score[:, 1], average_precision, 'NN', project_key, label, all_but_one_group)

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred, precision, recall, thresholds]


def run_xgboost(x_train, x_test, y_train, y_test, num_trees, max_depth_xg,
                alpha_xg, scale_pos_weight_xg , min_child_weight_xg, seed_xg, project_key, label, all_but_one_group):
    """
    this function predict with the xgboost model and return the results
    """
    
    clf = XGBClassifier(n_estimators=num_trees, max_depth=max_depth_xg, alpha=alpha_xg,
                        scale_pos_weight=scale_pos_weight_xg, min_child_weight=min_child_weight_xg, seed=seed_xg)
    # Train the model
    clf.fit(x_train, y_train)
    y_pred = clf.predict(x_test)
    y_score = clf.predict_proba(x_test)
    accuracy = metrics.accuracy_score(y_test, y_pred)
    # Model Accuracy
    print("Accuracy xgboost:", accuracy)
    confusion_matrix = metrics.confusion_matrix(y_test, y_pred)
    print("confusion_matrix xgboost: \n {}".format(confusion_matrix))
    classification_report = metrics.classification_report(y_test, y_pred)
    print("classification_report: \n {}".format(classification_report))
    # Create precision, recall curve
    average_precision = metrics.average_precision_score(y_test, y_score[:, 1])
    print('Average precision-recall score xgboost: {0:0.2f}'.format(average_precision))
    auc = metrics.roc_auc_score(y_test, y_score[:, 1])
    print('AUC roc xgboost: {}'.format(auc))
    precision, recall, thresholds = metrics.precision_recall_curve(y_test, y_score[:, 1])
    area_under_pre_recall_curve = metrics.auc(recall, precision)
    print('area_under_pre_recall_curve xgboost: {}'.format(area_under_pre_recall_curve))
    create_pre_rec_curve(y_test, y_score[:, 1], average_precision, 'XGboost', project_key, label, all_but_one_group)

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred, precision, recall, thresholds]


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
            x_test['label_is_empty'], precision, recall, thresholds]


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
            y_score['all'], precision, recall, thresholds]


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
            y_pred['pred'], precision, recall, thresholds]


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
    if all_but_one_group:
        plt.savefig(
            '..Models/results_best_para/pre_recall_curve_groups_{}_{}_{}.png'.format(
                project_key, label, algorithm))
    else:
        plt.savefig(
            '..Models/results_best_para/pre_recall_curve_{}_{}_{}.png'.format(
                project_key, label, algorithm))
    plt.close()
    return area


def run_model(x_train, x_test, y_train, y_test, is_base, project_key, label, num_trees_rf, max_feature_rf, max_depth_rf,
              hidden_layer_size, activation_nn, solver_nn, alpha_nn, learning_rate_nn, num_trees_xg, max_depth_xg,
              alpha_xg, scale_pos_weight_xg, min_child_weight_xg, all_but_one_group):
    """
    this function run all the prediction models with the functions detailed above and return the results
    """
    
    if is_base == 1:

        accuracy_empty, confusion_matrix_empty, classification_report_empty, area_under_pre_recall_curve_empty, \
            avg_pre_empty, avg_auc_empty, y_pred_empty, precision_empty, recall_empty, \
            thresholds_empty = run_is_empty(x_train, x_test, y_train['usability_label'], y_test['usability_label'],
                                            project_key, label, all_but_one_group)

        accuracy_zero, confusion_matrix_zero, classification_report_zero, area_under_pre_recall_curve_zero, \
            avg_pre_zero, avg_auc_zero, y_pred_zero, precision_zero, recall_zero, \
            thresholds_zero = run_is_zero(x_train, x_test, y_train['usability_label'], y_test['usability_label'],
                                          project_key, label, all_but_one_group)

        accuracy_random, confusion_matrix_random, classification_report_random, area_under_pre_recall_curve_random, \
            avg_pre_random, avg_auc_random, y_pred_random, precision_random, recall_random, \
            thresholds_random = run_random(x_train, x_test, y_train['usability_label'], y_test['usability_label'],
                                           project_key, label, all_but_one_group)
        return accuracy_empty, confusion_matrix_empty, classification_report_empty, \
            area_under_pre_recall_curve_empty, avg_pre_empty, avg_auc_empty, y_pred_empty, precision_empty, \
            recall_empty, thresholds_empty, accuracy_zero, confusion_matrix_zero, classification_report_zero, \
            area_under_pre_recall_curve_zero, avg_pre_zero, avg_auc_zero, y_pred_zero, precision_zero, recall_zero, \
            thresholds_zero, accuracy_random, confusion_matrix_random, classification_report_random, \
            area_under_pre_recall_curve_random, avg_pre_random, avg_auc_random, y_pred_random, precision_random, \
            recall_random, thresholds_random
    else:
        x_train = x_train.drop(columns=['created'])
        x_test = x_test.drop(columns=['created'])
        x_train = x_train.drop(columns=['issue_key'])
        x_test = x_test.drop(columns=['issue_key'])

        # down/up_sampling
        # x_train, y_train = down_sampling1(x_train, y_train['usability_label'], False)
        random_num_rf = 7
        accuracy_rf, confusion_matrix_rf, classification_report_rf, area_under_pre_recall_curve_rf, avg_pre_rf, \
            avg_auc_rf, y_pred_rf, feature_importance, precision_rf, recall_rf, \
            thresholds_rf = run_random_forest(x_train, x_test, y_train['usability_label'], y_test['usability_label'],
                                              num_trees_rf, max_feature_rf, max_depth_rf, random_num_rf,
                                              project_key, label, all_but_one_group)
        seed_xg = 7
        accuracy_xgboost, confusion_matrix_xgboost, classification_report_xgboost, area_under_pre_recall_curve_xgboost, \
            avg_pre_xgboost, avg_auc_xgboost, y_pred_xgboost, precision_xgboost, recall_xgboost, \
            thresholds_xgboost = run_xgboost(x_train, x_test, y_train['usability_label'], y_test['usability_label'],
                                             num_trees_xg, max_depth_xg, alpha_xg, scale_pos_weight_xg,
                                             min_child_weight_xg, seed_xg, project_key, label, all_but_one_group)

        x_train_nn = x_train
        x_test_nn = x_test
        names = list(x_train_nn.columns.values)
        x_train_nn[names] = x_train_nn[names].astype(float)
        x_test_nn[names] = x_test_nn[names].astype(float)
        scaler = StandardScaler()
        scaler.fit(x_train_nn)
        x_train_nn1 = scaler.transform(x_train_nn[names])
        x_test_nn1 = scaler.transform(x_test_nn[names])

        random_num_nn = 7
        accuracy_nn, confusion_matrix_nn, classification_report_nn, area_under_pre_recall_curve_nn, avg_pre_nn, \
            avg_auc_nn, y_pred_nn, precision_nn, recall_nn, \
            thresholds_nn = run_neural_net(x_train_nn1, x_test_nn1, y_train['usability_label'],
                                           y_test['usability_label'], hidden_layer_size, activation_nn, solver_nn,
                                           alpha_nn, learning_rate_nn, random_num_nn, project_key, label,
                                           all_but_one_group)
        y_test['y_pred'] = y_pred_nn
        # results:
        print("features:")
        print(x_train.columns.values)

        return feature_importance, accuracy_rf, confusion_matrix_rf, classification_report_rf, \
            area_under_pre_recall_curve_rf, avg_pre_rf, avg_auc_rf, y_pred_rf, precision_rf, recall_rf, \
            thresholds_rf, accuracy_nn, confusion_matrix_nn, classification_report_nn, area_under_pre_recall_curve_nn, \
            avg_pre_nn, avg_auc_nn, y_pred_nn, precision_nn, recall_nn, thresholds_nn, accuracy_xgboost, \
            confusion_matrix_xgboost, classification_report_xgboost, area_under_pre_recall_curve_xgboost, \
            avg_pre_xgboost, avg_auc_xgboost, y_pred_xgboost, precision_xgboost, recall_xgboost, thresholds_xgboost
