from sklearn.neighbors import KNeighborsClassifier
from imblearn.under_sampling import RandomUnderSampler
import Utils.Add_BERT_predication as Add_BERT_predication
from sklearn import metrics
import pandas as pd


def getData(jira_name, label):
    path = f'Master/Models/train_test_after_all_but/{jira_name}/'
    features_data_train = pd.read_csv(
        f'{path}/features_data_train_{jira_name}_{label}.csv', low_memory=False)
    features_data_test = pd.read_csv(
        f'{path}/features_data_test_{jira_name}_{label}.csv', low_memory=False)

    path = f'Master/Models/train_test/{jira_name}/'
    labels_train = pd.read_csv(
        f'{path}/labels_train_{jira_name}_{label}.csv', low_memory=False)
    labels_test = pd.read_csv(
        f'{path}/labels_test_{jira_name}_{label}.csv', low_memory=False)

    return features_data_train, features_data_test, labels_train, labels_test


def start(jira_name):
    results = pd.DataFrame(
        columns=['project_key', 'usability_label', 'accuracy', 'confusion_matrix', 'classification_report',
                 'area_under_pre_recall_curve', 'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                 'recall', 'thresholds', 'knn'])

    add_bert_predictions = Add_BERT_predication.start(jira_name, 'Master/')

    for k_unstable in [5, 10, 15, 20]:
        x_train, x_test, y_train, y_test = getData(jira_name, k_unstable)

        # add bert instability
        x_train = add_bert_predictions(data=x_train, data_name='train', k_unstable=k_unstable)
        x_test = add_bert_predictions(data=x_test, data_name='test', k_unstable=k_unstable)

        # Create an instance of the KNeighborsClassifier
        for knn_number in [1, 3, 5, 7]:
            d = run_KNN(x_train, x_test, y_train, y_test, jira_name, k_unstable, knn_number)
            results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

        results.to_csv(f'Master/KNN/Results/{jira_name}/KNN_withBERT_{k_unstable}.csv')

        results = pd.DataFrame(
            columns=['project_key', 'usability_label', 'accuracy', 'confusion_matrix', 'classification_report',
                     'area_under_pre_recall_curve', 'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                     'recall', 'thresholds', 'knn'])


def run_KNN(x_train, x_test, y_train, y_test, jira_name, k_unstable, knn_number):
    # Create an instance of the KNeighborsClassifier
    knn = KNeighborsClassifier(n_neighbors=knn_number)

    # Undersample the majority class
    rus = RandomUnderSampler(random_state=42)
    x_train_resampled, y_train_resampled = rus.fit_resample(x_train, y_train)

    # Fit the KNeighborsClassifier on the resampled data
    knn.fit(x_train_resampled, y_train_resampled)

    # Predict on the test data
    y_pred = knn.predict(x_test)
    y_score = knn.predict_proba(x_test)

    precision, recall, thresholds = metrics.precision_recall_curve(y_test, y_score[:, 1])

    d = {
        'project_key': jira_name,
        'usability_label': k_unstable,
        'accuracy': metrics.accuracy_score(y_test, y_pred),
        'confusion_matrix': metrics.confusion_matrix(y_test, y_pred),
        'classification_report': metrics.classification_report(y_test, y_pred),
        'area_under_pre_recall_curve': metrics.auc(recall, precision),
        'avg_precision': metrics.average_precision_score(y_test, y_score[:, 1]),
        'area_under_roc_curve': metrics.roc_auc_score(y_test, y_score[:, 1]),
        'y_pred': y_pred,
        'precision': precision,
        'recall': recall,
        'thresholds': thresholds,
        'knn': knn_number
    }
    return d
