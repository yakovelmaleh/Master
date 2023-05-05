import json

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn import metrics

def run_random_forest(x_train, x_test, y_train, y_test):
    """
    this function run random forest prediction and return the results
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


def start(jira_name):
    
    # create the feature vector with all the combination of groups
    features_vector = [['num_headlines', 'has_code', 'has_url', 'num_question_marks', 'has_template', 'len_sum_desc',
                        'len_description', 'if_description_empty_tbd', 'if_acceptance_empty_tbd', 'len_acceptance',
                        'num_sentences', 'num_words', 'avg_word_len', 'avg_num_word_in_sentence',
                        'has_please', 'has_tbd', 'has_acceptance_criteria', 'num_issues_cretor_prev', 'priority',
                        'ratio_unusable_issues_text_by_previous', 'num_comments_before_sprint',
                        'num_changes_text_before_sprint', 'num_changes_story_point_before_sprint',
                        'original_story_points_sprint', 'noun_count', 'verb_count', 'adj_count', 'adv_count',
                        'pron_count', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14',
                        'dominant_topic', 'num_stopwords', 'time_until_add_sprint', 'block', 'block_by', 'duplicate',
                        'relates', 'duplicate_by'],
                       # only a
                       ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', 'dominant_topic'],
                       # only b
                       ['num_headlines', 'has_code', 'has_url', 'num_question_marks', 'has_template', 'len_sum_desc',
                        'len_description', 'if_description_empty_tbd', 'if_acceptance_empty_tbd', 'len_acceptance',
                        'num_sentences', 'num_words', 'avg_word_len', 'avg_num_word_in_sentence',
                        'has_please', 'has_tbd', 'has_acceptance_criteria', 'noun_count', 'verb_count', 'adj_count',
                        'adv_count', 'pron_count', 'num_stopwords'],
                       # only c
                       ['priority', 'num_comments_before_sprint', 'num_changes_text_before_sprint',
                        'time_until_add_sprint', 'num_changes_story_point_before_sprint',
                        'original_story_points_sprint', 'block', 'block_by', 'duplicate', 'relates', 'duplicate_by'],
                       # only d
                       ['num_issues_cretor_prev', 'ratio_unusable_issues_text_by_previous'],

                       # all but a
                       ['num_headlines', 'has_code', 'has_url', 'num_question_marks', 'has_template', 'len_sum_desc',
                        'len_description', 'if_description_empty_tbd', 'if_acceptance_empty_tbd', 'len_acceptance',
                        'num_sentences', 'num_words', 'avg_word_len', 'avg_num_word_in_sentence',
                        'has_please', 'has_tbd', 'has_acceptance_criteria', 'num_issues_cretor_prev', 'priority',
                        'ratio_unusable_issues_text_by_previous', 'num_comments_before_sprint',
                        'num_changes_text_before_sprint', 'num_changes_story_point_before_sprint',
                        'original_story_points_sprint', 'noun_count', 'verb_count', 'adj_count', 'adv_count',
                        'pron_count', 'num_stopwords', 'block', 'block_by', 'duplicate', 'relates',
                        'duplicate_by', 'time_until_add_sprint'],
                       # all but b
                       ['num_issues_cretor_prev', 'priority', 'ratio_unusable_issues_text_by_previous',
                        'num_comments_before_sprint', 'num_changes_text_before_sprint',
                        'num_changes_story_point_before_sprint', 'original_story_points_sprint',
                        '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14',
                        'dominant_topic', 'block', 'block_by', 'duplicate', 'relates', 'duplicate_by',
                        'time_until_add_sprint'],
                       # all but c
                       ['num_headlines', 'has_code', 'has_url', 'num_question_marks', 'has_template', 'len_sum_desc',
                        'len_description', 'if_description_empty_tbd', 'if_acceptance_empty_tbd', 'len_acceptance',
                        'num_sentences', 'num_words', 'avg_word_len', 'avg_num_word_in_sentence',
                        'has_please', 'has_tbd', 'has_acceptance_criteria', 'num_issues_cretor_prev',
                        'ratio_unusable_issues_text_by_previous', 'noun_count', 'verb_count', 'adj_count', 'adv_count',
                        'pron_count', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14',
                        'dominant_topic', 'num_stopwords'],
                       # all but d
                       ['num_headlines', 'has_code', 'has_url', 'num_question_marks', 'has_template', 'len_sum_desc',
                        'len_description', 'if_description_empty_tbd', 'if_acceptance_empty_tbd', 'len_acceptance',
                        'num_sentences', 'num_words', 'avg_word_len', 'avg_num_word_in_sentence',
                        'has_please', 'has_tbd', 'has_acceptance_criteria', 'priority', 'num_comments_before_sprint',
                        'num_changes_text_before_sprint', 'num_changes_story_point_before_sprint',
                        'original_story_points_sprint', 'noun_count', 'verb_count', 'adj_count', 'adv_count',
                        'pron_count', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14',
                        'dominant_topic', 'num_stopwords', 'block', 'block_by', 'duplicate', 'relates', 'duplicate_by',
                        'time_until_add_sprint'],
                       # a + b
                       ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14',
                        'dominant_topic', 'num_headlines', 'has_code', 'has_url', 'num_question_marks', 'has_template',
                        'len_sum_desc', 'len_description', 'if_description_empty_tbd', 'if_acceptance_empty_tbd',
                        'len_acceptance', 'num_sentences', 'num_words', 'avg_word_len', 'avg_num_word_in_sentence',
                        'has_please', 'has_tbd', 'has_acceptance_criteria', 'noun_count', 'verb_count',
                        'adj_count', 'adv_count', 'pron_count', 'num_stopwords'],
                       # a + c
                       ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14',
                        'dominant_topic', 'priority', 'num_comments_before_sprint', 'num_changes_text_before_sprint',
                        'time_until_add_sprint', 'num_changes_story_point_before_sprint',
                        'original_story_points_sprint', 'block', 'block_by', 'duplicate', 'relates', 'duplicate_by'],
                       # a + d
                       ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14',
                        'dominant_topic', 'num_issues_cretor_prev', 'ratio_unusable_issues_text_by_previous'],
                       # b + c
                       ['priority', 'num_comments_before_sprint', 'num_changes_text_before_sprint',
                        'time_until_add_sprint', 'num_changes_story_point_before_sprint',
                        'original_story_points_sprint', 'block', 'block_by', 'duplicate', 'relates', 'duplicate_by',
                        'num_headlines', 'has_code', 'has_url', 'num_question_marks', 'has_template', 'len_sum_desc',
                        'len_description', 'if_description_empty_tbd', 'if_acceptance_empty_tbd', 'len_acceptance',
                        'num_sentences', 'num_words', 'avg_word_len', 'avg_num_word_in_sentence',
                        'has_please', 'has_tbd', 'has_acceptance_criteria', 'noun_count', 'verb_count', 'adj_count',
                        'adv_count', 'pron_count', 'num_stopwords'],
                       # b + d
                       ['num_issues_cretor_prev', 'ratio_unusable_issues_text_by_previous'
                        'num_headlines', 'has_code', 'has_url', 'num_question_marks', 'has_template', 'len_sum_desc',
                        'len_description', 'if_description_empty_tbd', 'if_acceptance_empty_tbd', 'len_acceptance',
                        'num_sentences', 'num_words', 'avg_word_len', 'avg_num_word_in_sentence',
                        'has_please', 'has_tbd', 'has_acceptance_criteria', 'noun_count', 'verb_count', 'adj_count',
                        'adv_count', 'pron_count', 'num_stopwords'],
                       # c + d
                       ['priority', 'num_comments_before_sprint', 'num_changes_text_before_sprint',
                        'time_until_add_sprint', 'num_changes_story_point_before_sprint',
                        'original_story_points_sprint', 'block', 'block_by', 'duplicate', 'relates', 'duplicate_by',
                        'num_issues_cretor_prev', 'ratio_unusable_issues_text_by_previous'],
                       # only b else
                       ['has_template', 'len_sum_desc', 'len_description', 'if_description_empty_tbd',
                        'if_acceptance_empty_tbd', 'len_acceptance', 'has_please', 'has_tbd',
                        'has_acceptance_criteria']
                       ]
    ########################################################################################################
    # ################################   create table to write results:    #################################
    ########################################################################################################

    results = pd.DataFrame(columns=['project_key', 'usability_label', 'group', 'features', 'feature_importance',
                                    'accuracy_rf', 'confusion_matrix_rf', 'classification_report_rf',
                                    'area_under_pre_recall_curve_rf', 'avg_precision_rf', 'area_under_roc_curve_rf',
                                    'y_pred_rf', 'y_valid'])
    path = ''
    text_type = 'original_summary_description_acceptance_sprint'

    group_name = ['all', 'only_a_nlp', 'only_b_text', 'only_c_jira', 'only_d_writer', 'all_but_a', 'all_but_b',
                  'all_but_c', 'all_but_d', 'a_and_b', 'a_and_c', 'a_and_d', 'b_and_c', 'b_and_d', 'c_and_d',
                  'only_b_else']

    dict_labels = {'is_change_text_num_words_5': 'num_unusable_issues_cretor_prev_text_word_5_ratio',
                   'is_change_text_num_words_10': 'num_unusable_issues_cretor_prev_text_word_10_ratio',
                   'is_change_text_num_words_15': 'num_unusable_issues_cretor_prev_text_word_15_ratio',
                   'is_change_text_num_words_20': 'num_unusable_issues_cretor_prev_text_word_20_ratio'}

    project_key = jira_name

    # for each feature group run random forest prediction model and write the results to excel
    for label_name in dict_labels.items():
        print("data: {}, \n label_name.key: {}, \n".format(project_key, label_name[0]))
        features_data_train1 = pd.read_csv(
            '..Models/train_val_after_chi/features_data_train_{}_{}.csv'.format(project_key, label_name[0]),
            low_memory=False)
        features_data_valid1 = pd.read_csv(
            '..Models/train_val_after_chi/features_data_valid_{}_{}.csv'.format(project_key, label_name[0]),
            low_memory=False)
        labels_train = pd.read_csv(
            './train_val/labels_train_{}_{}.csv'.format(project_key, label_name[0]), low_memory=False)
        labels_valid = pd.read_csv(
            './train_val/labels_valid_{}_{}.csv'.format(project_key, label_name[0]), low_memory=False)

        num_group = 0
        for feature in features_vector:
            features_data_train = features_data_train1.copy()
            features_data_valid = features_data_valid1.copy()

            names = list(features_data_train.columns.values)
            features = [x for x in feature if x in names]

            features_data_train = features_data_train[features]
            features_data_valid = features_data_valid[features]
            if 'dominant_topic' in features:
                features_data_train = pd.get_dummies(features_data_train, columns=['dominant_topic'],
                                                     drop_first=True)
                features_data_valid = pd.get_dummies(features_data_valid, columns=['dominant_topic'],
                                                     drop_first=True)
                # Get missing columns in the training test
                missing_cols = set(features_data_train.columns) - set(features_data_valid.columns)
                # Add a missing column in test set with default value equal to 0
                for c in missing_cols:
                    features_data_valid[c] = 0
                # Ensure the order of column in the test set is in the same order than in train set
                features_data_valid = features_data_valid[features_data_train.columns]

            accuracy_rf, confusion_matrix_rf, classification_report_rf, area_under_pre_recall_curve_rf, \
                avg_pre_rf, area_under_roc_curve_rf, y_pred_rf, feature_importance, precision_rf, recall_rf, \
                thresholds_rf = run_random_forest(features_data_train, features_data_valid,
                                                  labels_train['usability_label'], labels_valid['usability_label'])

            d = {'project_key': project_key, 'usability_label': label_name[0], 'group': group_name[num_group],
                 'features': features, 'feature_importance': feature_importance, 'accuracy_rf': accuracy_rf,
                 'confusion_matrix_rf': confusion_matrix_rf, 'classification_report_rf': classification_report_rf,
                 'area_under_pre_recall_curve_rf': area_under_pre_recall_curve_rf, 'avg_precision_rf': avg_pre_rf,
                 'area_under_roc_curve_rf': area_under_roc_curve_rf, 'y_pred_rf': y_pred_rf,
                 'y_valid': labels_valid['usability_label']}

            results = results.append(d, ignore_index=True)
            num_group = num_group + 1

        results.to_csv('..Models/feature_selection/results_groups2_{}_label_{}.csv'.format(project_key,
                                                                                    label_name[0]), index=False)

        results = pd.DataFrame(
            columns=['project_key', 'usability_label', 'group', 'features', 'feature_importance', 'accuracy_rf',
                     'confusion_matrix_rf', 'classification_report_rf', 'area_under_pre_recall_curve_rf',
                     'avg_precision_rf', 'area_under_roc_curve_rf', 'y_pred_rf', 'y_valid'])

            
if __name__ == "__main__":

    with open('../Source/jira_data_for_instability.json') as f:
        jira_data_sources = json.load(f)

    for jira_name, jira_obj in jira_data_sources.items():
        print("start feature_selection_groups, DB: ", jira_name)
        start(jira_name)
    print("finish to feature_selection_groups")