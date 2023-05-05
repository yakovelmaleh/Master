import json
import os

import pandas as pd
from gensim.models.doc2vec import Doc2Vec, TaggedDocument
from nltk import bigrams, ngrams
from sklearn.ensemble import RandomForestClassifier
from sklearn import metrics
import Utils.clean_text as clean_text
import Utils.DataBase as DB
from pathlib import Path

def split_train_valid_test(data_to_split):
    """
    the function get the data and splot it to train validation and test set
    """
    data_to_split = data_to_split.sort_values(by=['time_add_to_sprint'])
    data_to_split = data_to_split.reset_index(drop=True)
    # with validation
    num_rows_train = round(0.6*len(data_to_split))
    num_rows_valid = round(0.8*len(data_to_split))

    train = data_to_split.loc[0:num_rows_train-1, :].reset_index(drop=True)
    valid = data_to_split.loc[num_rows_train:num_rows_valid-1, :].reset_index(drop=True)
    test = data_to_split.loc[num_rows_valid:, :].reset_index(drop=True)
    return train, valid, test


def tag_docs(docs, col):
    tagged = docs.apply(
        lambda r: TaggedDocument(words=(r['clean_text_new']),  tags=[(r['issue_key'])]), axis=1)

    return tagged


def train_doc2vec_model(tagged_docs, window, size):
    sents = tagged_docs.values
    doc2vec_model = Doc2Vec(sents, size = size, window=window, iter=20, dm=1)
    return doc2vec_model


def vec_for_learning(doc2vec_model, tagged_docs):
    sents = tagged_docs.values
    doc_vectors = [(doc2vec_model.infer_vector(doc.words, steps=20)) for doc in sents]
    return doc_vectors


def run_random_forest(x_train, x_test, y_train, y_test):
    """
    funcrion which get the train and test, run random forest prediction and return the results (accuracy, confusion_matrix, classification_report, 
                                                                                                area_under_pre_recall_curve, average_precision, auc,
                                                                                                y_pred, feature_imp, precision, recall, thresholds)
    """
    clf = RandomForestClassifier(n_estimators=1000, max_features='sqrt', random_state=7)
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

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc,
            y_pred, feature_imp, precision, recall, thresholds]


def create_doc_to_vec(train_data, test_data, labels_train, labels_test, project_key):
    """
    function who gets the project data, calculate the doc2vec to each size of the vector between 5,10,15,20
    run the presiction model and save the results in excel file
    """
    path = ''
    results = pd.DataFrame(columns=['project_key', 'usability_label', 'size', 'feature_importance', 'accuracy_rf',
                                    'confusion_matrix_rf', 'classification_report_rf', 'area_under_pre_recall_curve_rf',
                                    'avg_precision_rf', 'area_under_roc_curve_rf', 'y_pred_rf', 'precision_rf',
                                    'recall_rf', 'thresholds_rf', 'y_test', 'features'])
    train_index = train_data.index.values
    test_index = test_data.index.values

    train_data1 = train_data.copy()
    test_data1 = test_data.copy()
    train_tagged = tag_docs(train_data1, 'clean_text_new')
    test_tagged = tag_docs(test_data1, 'clean_text_new')
    # create_directory_if_not_exist('word_vector')

    size_vec = [5, 10, 15, 20]

    for size in size_vec:
        # Init the Doc2Vec model
        model = Doc2Vec(size = size, min_count=2, alpha=0.025, seed=5, epochs=50, dm=1)
        # Build the Volabulary
        model.build_vocab(train_tagged)
        # Train the Doc2Vec model
        model.train(train_tagged, total_examples=model.corpus_count, epochs=model.epochs)
        # saving the created model
        # create_directory_if_not_exist('word_vector')
        path = addPath(f'Master/Models/word_vector/{project_key}/doc2vec_{size}_{project_key}.model')
        model.save(path)
        #model = Doc2Vec.load('doc2vec_{}_{}.model'.format(size,project_key))
        x_train = model.docvecs.vectors_docs
        #x_train = train_data1.copy()
        x_train = pd.DataFrame(x_train)
        x_test = vec_for_learning(model, test_tagged)
        x_test = pd.DataFrame(x_test)
        accuracy_rf, confusion_matrix_rf, classification_report_rf, area_under_pre_recall_curve_rf, avg_pre_rf, \
            avg_auc_rf, y_pred_rf, feature_importance, precision_rf, recall_rf, \
            thresholds_rf = run_random_forest(x_train, x_test, labels_train['usability_label'],
                                              labels_test['usability_label'])

        d = {'project_key': project_key, 'usability_label': 'is_change_text_num_words_5', 'size': size,
             'feature_importance': feature_importance, 'accuracy_rf': accuracy_rf,
             'confusion_matrix_rf': confusion_matrix_rf, 'classification_report_rf': classification_report_rf,
             'area_under_pre_recall_curve_rf': area_under_pre_recall_curve_rf, 'avg_precision_rf': avg_pre_rf,
             'area_under_roc_curve_rf': avg_auc_rf, 'y_pred_rf': y_pred_rf,
             'precision_rf': precision_rf, 'recall_rf': recall_rf, 'thresholds_rf': thresholds_rf,
             'y_test': labels_test['usability_label'], 'features': 'only vec'}

        results = results.append(d, ignore_index=True)
        # write the results to excel
        path = addPath(f'Master/Models/word_vector/{project_key}/results_{project_key}_label_is_change_text_num_words_5.csv')
        results.to_csv(path, index=False)


def create_directory_if_not_exist(dir_name):
    path = os.getcwd()[:os.getcwd().find("RunModels")]

    if not os.path.isdir(path + "Models"):
        path = path + "Models"
        os.mkdir(path)

    if not os.path.isdir(path + "\\" + dir_name):
        os.mkdir(path +"\\"+ dir_name)


def start(jira_name):
    dbName = f"{DB.DB_NAME}_{jira_name.lower()}"
    """
    mysql_con = DB.connectToSpecificDB(dbName)
    cursor = mysql_con.cursor()
    print(f'connected to DB: {DB.DB_NAME}_{jira_name.lower()}')

    # Enforce UTF-8 for the connection
    cursor.execute('SET NAMES utf8mb4')
    cursor.execute("SET CHARACTER SET utf8mb4")
    cursor.execute("SET character_set_connection=utf8mb4")
    
    data = pd.read_sql(f"SELECT * FROM {dbName}.features_labels_table_os", con= mysql_con)
    """
    path = addPath(f'Master/Data/{jira_name}/features_labels_table_os.csv')
    data = pd.read_csv(path)
    text_type = 'original_summary_description_acceptance_sprint'

    dict_labels = {'is_change_text_num_words_5': 'num_unusable_issues_cretor_prev_text_word_5_ratio',
                   'is_change_text_num_words_10': 'num_unusable_issues_cretor_prev_text_word_10_ratio',
                   'is_change_text_num_words_15': 'num_unusable_issues_cretor_prev_text_word_15_ratio',
                   'is_change_text_num_words_20': 'num_unusable_issues_cretor_prev_text_word_20_ratio'}

    train, valid, test = split_train_valid_test(data)

    # ############################ clean text ######################
    clean_text.create_clean_text(train, text_type)
    clean_text.create_clean_text(valid, text_type)

    labels_train = pd.DataFrame()
    labels_valid = pd.DataFrame()
    labels_train['usability_label'] = train['is_change_text_num_words_5']
    labels_valid['usability_label'] = valid['is_change_text_num_words_5']
    labels_train['issue_key'] = train['issue_key']
    labels_valid['issue_key'] = valid['issue_key']

    create_doc_to_vec(train, valid, labels_train, labels_valid, jira_name)

def addPath(path):
    return str(Path(os.getcwd()).joinpath(path))


if __name__ == "__main__":
    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start select_length_doc_vector, DB: ", jira_name)
        start(jira_name)
    print("finish to select_length_doc_vector")

