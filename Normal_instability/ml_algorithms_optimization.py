import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn import metrics
from sklearn.model_selection import RandomizedSearchCV
from funcsigs import signature
import matplotlib.pyplot as plt
from sklearn.neural_network import MLPClassifier

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


def run_random_forest(x_train, x_test, y_train, y_test, num_trees, max_feature, max_depths, min_sample_split,
                      min_sample_leaf, bootstraps, project_key, label, all_but_one_group):
    """
    this function predict with the random forest model and return the results
    """
    clf = RandomForestClassifier(n_estimators=num_trees, max_features=max_feature, max_depth=max_depths,
                                 min_samples_leaf=min_sample_leaf, min_samples_split=min_sample_split,
                                 bootstrap=bootstraps, random_state=7)
    # Train the model
    clf.fit(x_train, y_train)
    feature_imp = pd.Series(clf.feature_importances_, index=list(x_train.columns.values)).sort_values(ascending=False)
    print("feature importance RF{}".format(feature_imp))
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
    auc = metrics.roc_auc_score(y_test, y_score[:, 1], average='macro', sample_weight=None, max_fpr=None)
    print('AUC roc RF: {}'.format(auc))
    area_under_pre_recall_curve = create_pre_rec_curve(y_test, y_score, average_precision, project_key=project_key,
                                                       label=label, all_but_one_group=all_but_one_group, algorithm="RF")
    print('area_under_pre_recall_curve RF: {}'.format(area_under_pre_recall_curve))

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred, feature_imp]


def run_neural_net(x_train, x_test, y_train, y_test, num_unit_hidden_layer, max_iteration, solvers, num_batch,
                   activations, project_key, label, all_but_one_group):
    """
    this function predict with the neural network model and return the results
    """
    clf = MLPClassifier(solver=solvers, hidden_layer_sizes=num_unit_hidden_layer, random_state=1,
                        max_iter=max_iteration, batch_size=num_batch, activation=activations)
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
    auc = metrics.roc_auc_score(y_test, y_score[:, 1], average='macro', sample_weight=None, max_fpr=None)
    print('AUC roc NN: {}'.format(auc))
    print(8)
    area_under_pre_recall_curve = create_pre_rec_curve(y_test, y_score, average_precision, project_key=project_key,
                                                       label=label, all_but_one_group=all_but_one_group, algorithm="NN")
    print('area_under_pre_recall_curve NN: {}'.format(area_under_pre_recall_curve))

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred]


def run_xgboost(x_train, x_test, y_train, y_test, num_trees, max_feature, max_depths, alpha_t, scale_pos,
                num_child_weight_t, project_key, label, all_but_one_group):
    """
    this function predict with the xgboost model and return the results
    """
    clf = GradientBoostingClassifier(n_estimators=num_trees, max_features=max_feature, max_depth=max_depths,
                                     random_state=7)
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
    auc = metrics.roc_auc_score(y_test, y_score[:, 1], average='macro', sample_weight=None, max_fpr=None)
    print('AUC roc xgboost: {}'.format(auc))
    area_under_pre_recall_curve = create_pre_rec_curve(y_test, y_score, average_precision, project_key=project_key,
                                                       label=label, all_but_one_group=all_but_one_group, algorithm="XG")
    print('area_under_pre_recall_curve xgboost: {}'.format(area_under_pre_recall_curve))

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred]


def create_pre_rec_curve(y_test, y_score, average_precision, project_key, label, all_but_one_group, algorithm):
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
    path = addPath(f'Master/Normal_instability/Parameters/{project_key}')
    if all_but_one_group:
        plt.savefig(
            f'{path}/pre_recall_curve_groups_{project_key}_{label}_{algorithm}.png')
    else:
        plt.savefig(
            f'{path}/pre_recall_curve_{project_key}_{label}_{algorithm}_2.png')
    plt.close()
    return area


def tuning_random_forest(x_train, y_train, project_key, label_name, all_but_one_group):
    ''''
    # Number of trees in random forest
    n_estimators = [int(x) for x in np.linspace(start=100, stop=2000, num=50)]
    # Number of features to consider at every split
    max_features = ['auto', 'sqrt', 4, 5, 7, 10, 15]
    # Maximum number of levels in tree
    max_depth = [int(j) for j in np.linspace(5, 50, num=10)]
    max_depth.append(None)
    # Create the random grid
    random_grid = {'n_estimators': n_estimators, 'max_features': max_features, 'max_depth': max_depth}
    # Use the random grid to search for best hyperparameters
    # First create the base model to tune
    rf = RandomForestClassifier()
    # Random search of parameters, using 3 fold cross validation,
    # search across 100 different combinations, and use all available cores
    rf_random = RandomizedSearchCV(estimator=rf, param_distributions=random_grid, n_iter=100, cv=4, verbose=2,
                                   random_state=12)
    # Fit the random search model
    rf_random.fit(x_train, y_train)
    best_para = rf_random.best_params_
    print("best parameters rf project {}: {}".format(project_key, best_para))'''

    if all_but_one_group:
        parameter_space = {
            'n_estimators': [int(x) for x in np.linspace(start=50, stop=2000, num=40)],
            'max_features': ['auto', 'sqrt', 4, 5, 7, 10],
            'max_depth': [int(j) for j in np.linspace(5, 50, num=10)],
        }
    else:
        parameter_space = {
            'n_estimators': [int(x) for x in np.linspace(start=50, stop=2000, num=40)],
            'max_features': ['auto', 'sqrt', 4, 5, 7, 10, 15],
            'max_depth': [int(j) for j in np.linspace(5, 50, num=10)]}

    rf = RandomForestClassifier()
    rf_random = RandomizedSearchCV(rf, parameter_space, cv=4, scoring='average_precision', random_state=7)
    # Fit the random search model
    rf_random.fit(x_train, y_train)
    best_para = rf_random.best_params_
    print("best parameters rf  project {} label name {} : {}".format(project_key, label_name, best_para))

    return best_para


def tuning_xgboost(x_train, y_train, project_key, label_name):
    parameter_space = {
        'n_estimators': [int(x) for x in np.linspace(start=50, stop=2000, num=40)],
        'max_depth': [int(j) for j in np.linspace(5, 50, num=10)],
        'alpha': [0, 0.0001, 0.005, 0.01, 0.05],
        'scale_pos_weight': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
                             y_train[y_train == 0].count() / float(y_train[y_train == 1].count())],
        'min_child_weight': range(1, 6, 2),
    }

    xgboost = XGBClassifier()

    xgboost_random = RandomizedSearchCV(xgboost, parameter_space, cv=4, scoring='average_precision', random_state=7)
    # Fit the random search model
    xgboost_random.fit(x_train, y_train)
    best_para = xgboost_random.best_params_
    print("best parameters xgboost  project {} label name {} : {}".format(project_key, label_name, best_para))

    return best_para


def tuning_neural_network(x_train, y_train, project_key, label_name):
    parameter_space = {
        'hidden_layer_sizes': [(50, 50, 50), (50, 100, 50), (100,), (20,), (30,), (50,), (5, 10,), (20, 30,), (30, 50,),
                               (50, 50,), (80, 50,), (50, 50,), (20, 20, 20), (50, 30, 20), (15, 20, 30)],
        'activation': ['tanh', 'relu'],
        'solver': ['sgd', 'adam', 'lbfgs'],
        'alpha': [0.0001, 0.005, 0.01, 0.05],
        'learning_rate': ['constant', 'adaptive'],
    }
    mlp = MLPClassifier(max_iter=7000)
    clf = RandomizedSearchCV(mlp, parameter_space, cv=4, scoring='average_precision', random_state=7)
    # Fit the random search model
    clf.fit(x_train, y_train)
    best_para = clf.best_params_
    print("best parameters nn  project {} label name {}: {}".format(project_key, label_name, best_para))

    return best_para


def run_model_grid(x_train, y_train, project_key, label, all_but_one_group, path):
    print(list(x_train))
    x_train = x_train.drop(columns=['created'])
    x_train = x_train.drop(columns=['issue_key'])
    features = list(x_train)
    rf_results = pd.DataFrame(columns=['project_key', 'usability_label', 'features', 'n_estimators_rf',
                                       'max_features_rf', 'max_depth_rf'])
    # tuning grid search:
    best_para_rf = tuning_random_forest(x_train, y_train, project_key, label, all_but_one_group)

    d = {'project_key': project_key, 'usability_label': label, 'features': features,
         'n_estimators_rf': best_para_rf['n_estimators'], 'max_features_rf': best_para_rf['max_features'],
         'max_depth_rf': best_para_rf['max_depth']}

    rf_results = pd.concat([rf_results, pd.DataFrame([d.values()], columns=d.keys())],
                           ignore_index=True)
    # rf_results = rf_results.append(d, ignore_index=True)

    path = addPath(f'Master/Models/optimization_results/{project_key}')
    if all_but_one_group:
        rf_results.to_csv(
            f'{path}/grid_results_groups_{project_key}_label_{label}_RF.csv', index=False)
    else:
        rf_results.to_csv(
            f'{path}/grid_results_{project_key}_label_{label}_RF.csv', index=False)

    # XGboost:
    xgboost_results = pd.DataFrame(columns=['project_key', 'usability_label', 'features', 'n_estimators_xgboost',
                                            'max_depth_xgboost', 'alpha_xgboost',
                                            'scale_pos_weight_xgboost', 'min_child_weight_xgboost',
                                            ])
    # tuning grid search:
    best_para_xgboost = tuning_xgboost(x_train, y_train, project_key, label)

    d = {'project_key': project_key, 'usability_label': label, 'features': features,
         'n_estimators_xgboost': best_para_xgboost['n_estimators'],
         'max_depth_xgboost': best_para_xgboost['max_depth'], 'alpha_xgboost': best_para_xgboost['alpha'],
         'scale_pos_weight_xgboost': best_para_xgboost['scale_pos_weight'],
         'min_child_weight_xgboost': best_para_xgboost['min_child_weight']}

    xgboost_results = pd.concat([xgboost_results, pd.DataFrame([d.values()], columns=d.keys())],
                                ignore_index=True)
    # xgboost_results = xgboost_results.append(d, ignore_index=True)

    path = addPath(f'Master/Models/optimization_results/{project_key}')
    if all_but_one_group:
        xgboost_results.to_csv(
            f'{path}/optimization_results/grid_results_groups_{project_key}_label_{label}_XGboost.csv', index=False)
    else:
        xgboost_results.to_csv(
            f'{path}/grid_results_{project_key}_label_{label}_XGboost.csv', index=False)

    # NN:
    nn_results = pd.DataFrame(columns=['project_key', 'usability_label', 'features', 'hidden_layer_sizes_nn',
                                       'activation_nn', 'solver_nn', 'alpha_nn', 'learning_rate_nn'])

    x_train_nn = x_train
    names = list(x_train_nn.columns.values)
    x_train_nn[names] = x_train_nn[names].astype(float)
    scaler = StandardScaler()
    scaler.fit(x_train_nn)
    x_train_nn[names] = scaler.transform(x_train_nn[names])
    print("features:")
    print(x_train_nn.columns.values)
    best_para_nn = tuning_neural_network(x_train, y_train, project_key, label)

    d = {'project_key': project_key, 'usability_label': label, 'features': features,
         'hidden_layer_sizes_nn': best_para_nn['hidden_layer_sizes'],
         'activation_nn': best_para_nn['activation'], 'solver_nn': best_para_nn['solver'],
         'alpha_nn': best_para_nn['alpha'], 'learning_rate_nn': best_para_nn['learning_rate']}

    nn_results = pd.concat([nn_results, pd.DataFrame([d.values()], columns=d.keys())],
                           ignore_index=True)
    # nn_results = nn_results.append(d, ignore_index=True)

    path = addPath(f'Master/Models/optimization_results/{project_key}')
    if all_but_one_group:
        nn_results.to_csv(
            f'{path}/grid_results_groups_{project_key}_label_{label}_NN.csv', index=False)
    else:
        nn_results.to_csv(
            f'{path}/grid_results_{project_key}_label_{label}_NN.csv', index=False)


def run_model_optimization(x_train, x_test, y_train, y_test, project_key, label, all_but_one_group, path):
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
    rf_results = pd.DataFrame(columns=['project_key', 'usability_label', 'features', 'feature_importance',
                                       'accuracy_rf', 'confusion_matrix_rf', 'classification_report_rf',
                                       'area_under_pre_recall_curve_rf', 'avg_precision_rf',
                                       'area_under_roc_curve_rf', 'y_pred_rf', 'num_trees', 'max_features',
                                       'max_depth', 'min_samples_split', 'min_samples_leaf', 'bootstrap'])
    parmas = {
        'class_weight': ["balanced", 'balanced_subsample', None],
        'n_estimators': [int(x) for x in np.linspace(start=200, stop=2000, num=10)],
        'max_features': ['auto', 'sqrt', 'log2', None],
        'max_depth': [int(x) for x in np.linspace(10, 110, num=11)],
        'min_samples_leaf': [1, 2, 3, 4, 5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        'min_samples_split': [2, 3, 4, 5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        'bootstrap': [True, False]
    }

    accuracy_rf, confusion_matrix_rf, classification_report_rf, \
        area_under_pre_recall_curve_rf, avg_pre_rf, avg_auc_rf, y_pred_rf, \
        feature_importance, best_params = run_best_params_CV(model=RandomForestClassifier(), dict=parmas,
                                                             model_name="RF",
                                                             x_train=x_train, x_test=x_test, y_train=y_train,
                                                             y_test=y_test, project_key=project_key, label=label,
                                                             all_but_one_group=all_but_one_group)

    d = {'project_key': project_key, 'usability_label': label, 'features': features,
         'feature_importance': feature_importance, 'accuracy_rf': accuracy_rf,
         'confusion_matrix_rf': confusion_matrix_rf,
         'classification_report_rf': classification_report_rf,
         'area_under_pre_recall_curve_rf': area_under_pre_recall_curve_rf,
         'avg_precision_rf': avg_pre_rf, 'area_under_roc_curve_rf': avg_auc_rf,
         'y_pred_rf': y_pred_rf, 'num_trees': best_params['n_estimators'], 'max_features': best_params['max_features'],
         'max_depth': best_params['max_depth'], 'min_samples_split': best_params['min_samples_split'],
         'min_samples_leaf': best_params['min_samples_leaf'],
         'class_weight': best_params['class_weight'],
         'bootstrap': best_params['bootstrap']}

    rf_results = pd.concat([rf_results, pd.DataFrame([d.values()], columns=d.keys())],
                           ignore_index=True)

    path = addPath(f'Master/Normal_instability/Parameters/{project_key}')

    if all_but_one_group:
        rf_results.to_csv(
            f'{path}/results_groups_{project_key}_label_{label}_RF_2.csv', index=False)
    else:
        rf_results.to_csv(
            f'{path}/results_{project_key}_label_{label}_RF.csv', index=False)

    # XGboost:
    xgboost_results = pd.DataFrame(columns=['project_key', 'usability_label', 'accuracy_xgboost',
                                            'confusion_matrix_xgboost', 'classification_report_xgboost',
                                            'area_under_pre_recall_curve_xgboost', 'avg_precision_xgboost',
                                            'area_under_roc_curve_xgboost', 'y_pred_xgboost', 'num_trees',
                                            'max_features', 'max_depth', 'min_samples_split', 'min_samples_leaf'
                                            ])
    parmas = {
        'n_estimators': [int(x) for x in np.linspace(start=200, stop=2000, num=10)],
        'max_features': ['auto', 'sqrt', 'log2', None],
        'max_depth': [int(x) for x in np.linspace(10, 110, num=11)],
        'min_samples_leaf': [1, 2, 4, 5, 10, 15, 20, 50, 100],
        'min_samples_split': [2, 5, 10, 15, 20, 50, 100],
        'learning_rate': [0.0001, 0.005, 0.01, 0.05, 0.07, 0.1, 0.15, 0.2],
        'subsample': [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    }

    accuracy_xgboost, confusion_matrix_xgboost, classification_report_xgboost, \
        area_under_pre_recall_curve_xgboost, avg_pre_xgboost, avg_auc_xgboost, \
        y_pred_xgboost, feature_importance, best_params = run_best_params_CV(model=GradientBoostingClassifier(),
                                                                             dict=parmas, model_name='XGboost',
                                                                             x_train=x_train, x_test=x_test,
                                                                             y_train=y_train, y_test=y_test,
                                                                             project_key=project_key, label=label,
                                                                             all_but_one_group=all_but_one_group)

    d = {'project_key': project_key, 'usability_label': label,
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
         'subsample': best_params['subsample']
         }

    xgboost_results = pd.concat([xgboost_results, pd.DataFrame([d.values()], columns=d.keys())],
                                ignore_index=True)

    path = addPath(f'Master/Normal_instability/Parameters/{project_key}')

    if all_but_one_group:
        xgboost_results.to_csv(
            f'{path}/results_groups_{project_key}_label_{label}_XGboost_2.csv', index=False)
    else:
        xgboost_results.to_csv(
            f'{path}/results_{project_key}_label_{label}_XGboost.csv', index=False)

    # NN:
    nn_results = pd.DataFrame(columns=['project_key', 'usability_label', 'accuracy_nn',
                                       'confusion_matrix_nn', 'classification_report_nn',
                                       'area_under_pre_recall_curve_nn', 'avg_precision_nn',
                                       'area_under_roc_curve_nn', 'y_pred_nn', 'num_units_hidden_layer',
                                       'max_iterations', 'solver', 'num_batches_size', 'activation', 'alpha',
                                       'learning_rate'])
    x_train_nn = x_train
    x_test_nn = x_test
    names = list(x_train_nn.columns.values)
    x_train_nn[names] = x_train_nn[names].astype(float)
    x_test_nn[names] = x_test_nn[names].astype(float)
    scaler = StandardScaler()
    scaler.fit(x_train_nn)
    x_train_nn[names] = scaler.transform(x_train_nn[names])
    x_test_nn[names] = scaler.transform(x_test_nn[names])

    parmas = {
        'solver': ['adam', 'sgd', 'lbfgs'],
        'hidden_layer_sizes': [(10,), (20,), (30,), (50,), (70,), (100,),(64, 32) , (50, 50, 50), (5, 20, 30), (30, 70, 30),
                               (100, 50, 100),(32, 64),(64,32,64,32,64)],
        'random_state': [1],
        'max_iter': [200, 300, 400, 500,  600, 800, 1000, 1500, 2000],
        'batch_size': ['auto', 20, 30, 40, 50, 100],
        'activation': ['logistic', 'tanh', 'relu'],
        'alpha': [0.0001, 0.005, 0.01, 0.05, 0.07, 0.1, 0.15, 0.2],
        'learning_rate': ['constant', 'adaptive'],
    }
    accuracy_nn, confusion_matrix_nn, classification_report_nn, \
        area_under_pre_recall_curve_nn, avg_pre_nn, avg_auc_nn, \
        y_pred_nn, features, best_params = run_best_params_CV(model=MLPClassifier(), dict=parmas, model_name='NN',
                                                              x_train=x_train_nn,
                                                              x_test=x_test_nn, y_train=y_train, y_test=y_test,
                                                              project_key=project_key, label=label,
                                                              all_but_one_group=all_but_one_group)

    d = {'project_key': project_key, 'usability_label': label,
         'accuracy_nn': accuracy_nn, 'confusion_matrix_nn': confusion_matrix_nn,
         'classification_report_nn': classification_report_nn,
         'area_under_pre_recall_curve_nn': area_under_pre_recall_curve_nn,
         'avg_precision_nn': avg_pre_nn, 'area_under_roc_curve_nn': avg_auc_nn,
         'y_pred_nn': y_pred_nn, 'num_units_hidden_layer': best_params['hidden_layer_sizes'],
         'max_iterations': best_params['max_iter'], 'solver': best_params['solver'],
         'num_batches_size': best_params['batch_size'],
         'activation': best_params['activation'], 'alpha': best_params['alpha'],
         'learning_rate': best_params['learning_rate']}

    nn_results = pd.concat([nn_results, pd.DataFrame([d.values()], columns=d.keys())],
                           ignore_index=True)

    path = addPath(f'Master/Normal_instability/Parameters/{project_key}')
    if all_but_one_group:
        nn_results.to_csv(
            f'{path}/results_groups_{project_key}_label_{label}_NN_2.csv', index=False)
    else:
        nn_results.to_csv(
            f'{path}/results_{project_key}_label_{label}_NN.csv', index=False)


def run_best_params_CV(model, dict, model_name, x_train, x_test, y_train, y_test, project_key, label,
                       all_but_one_group):
    """
    this function predict with the best params per model
    """

    clf = RandomizedSearchCV(estimator=model, param_distributions=dict, cv=3, verbose=0, random_state=42)
    clf.fit(x_train, y_train)

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
    area_under_pre_recall_curve = create_pre_rec_curve(y_test, y_score, average_precision, project_key=project_key,
                                                       label=label, all_but_one_group=all_but_one_group,
                                                       algorithm=model_name)
    print(f'area_under_pre_recall_curve {model_name}: {area_under_pre_recall_curve}')

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred, features, clf.best_params_]
