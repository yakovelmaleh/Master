import pandas as pd


if __name__ == "__main__":

    ### Not Ready !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    path = ''
    dict_labels = {'is_change_text_num_words_5': 'num_unusable_issues_cretor_prev_text_word_5_ratio',
                   'is_change_text_num_words_10': 'num_unusable_issues_cretor_prev_text_word_10_ratio',
                   'is_change_text_num_words_15': 'num_unusable_issues_cretor_prev_text_word_15_ratio',
                   'is_change_text_num_words_20': 'num_unusable_issues_cretor_prev_text_word_20_ratio'}

    projects_key = ['DEVELOPER', 'REPO', 'XD', 'DM']
    is_after_chi = True
    is_after_all_but = True

    if is_after_chi:
        # read all the data sets and delete from each one the unwanted features by the chi-square results in the excel files
        for project_key in projects_key:
            for label_name in dict_labels.items():
                print("data: {}, \n label_name.key: {}, \n".format(project_key, label_name[0]))
                features_data_train_valid = pd.read_csv(
                    '..Models/train_val/features_data_train_{}_{}.csv'.format(
                        project_key, label_name[0]), low_memory=False)
                features_data_valid = pd.read_csv(
                    '..Models/train_val/features_data_valid_{}_{}.csv'.format(
                        project_key, label_name[0]), low_memory=False)
                features_data_train_test = pd.read_csv(
                    '..Models/train_test/features_data_train_{}_{}.csv'.format(
                        project_key, label_name[0]), low_memory=False)
                features_data_test = pd.read_csv(
                    '..Models/train_test/features_data_test_{}_{}.csv'.format(
                        project_key, label_name[0]), low_memory=False)

                # remove features by chi square:
                if project_key == 'DEVELOPER':
                    features_data_train_valid.drop(['has_code', 'has_url', 'has_tbd', 'has_please',
                                                    'priority'], axis=1, inplace=True)
                    features_data_valid.drop(['has_code', 'has_url', 'has_tbd', 'has_please',
                                              'priority'], axis=1, inplace=True)
                    features_data_train_test.drop(['has_code', 'has_url', 'has_tbd', 'has_please',
                                                   'priority'], axis=1, inplace=True)
                    features_data_test.drop(['has_code', 'has_url', 'has_tbd', 'has_please',
                                             'priority'], axis=1, inplace=True)
                if project_key == 'REPO':
                    features_data_train_valid.drop(['has_code', 'has_url', 'has_tbd',
                                                    'has_please'], axis=1, inplace=True)
                    features_data_valid.drop(['has_code', 'has_url', 'has_tbd', 'has_please'], axis=1, inplace=True)
                    features_data_train_test.drop(['has_code', 'has_url', 'has_tbd',
                                                   'has_please'], axis=1, inplace=True)
                    features_data_test.drop(['has_code', 'has_url', 'has_tbd', 'has_please'], axis=1, inplace=True)
                if project_key == 'XD':
                    features_data_train_valid.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_please',
                                                    'if_description_empty_tbd', 'priority'], axis=1, inplace=True)
                    features_data_valid.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_please',
                                              'if_description_empty_tbd', 'priority'], axis=1, inplace=True)
                    features_data_train_test.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_please',
                                                   'if_description_empty_tbd', 'priority'], axis=1, inplace=True)
                    features_data_test.drop(['has_code', 'has_url', 'if_acceptance_empty_tbd', 'has_please',
                                             'if_description_empty_tbd', 'priority'], axis=1, inplace=True)
                if project_key == 'DM':
                    if label_name[0] == 'is_change_text_num_words_5':
                        features_data_train_valid.drop(['has_url', 'has_template', 'has_acceptance_criteria',
                                                        'has_tbd', 'priority'], axis=1, inplace=True)
                        features_data_valid.drop(['has_url', 'has_template', 'has_acceptance_criteria',
                                                  'has_tbd', 'priority'], axis=1, inplace=True)
                        features_data_train_test.drop(['has_url', 'has_template', 'has_acceptance_criteria',
                                                       'has_tbd', 'priority'], axis=1, inplace=True)
                        features_data_test.drop(['has_url', 'has_template', 'has_acceptance_criteria',
                                                 'has_tbd', 'priority'], axis=1, inplace=True)
                    else:
                        features_data_train_valid.drop(['has_code', 'has_url', 'has_template', 'has_acceptance_criteria',
                                                        'has_please', 'has_tbd', 'priority'], axis=1, inplace=True)
                        features_data_valid.drop(['has_code', 'has_url', 'has_template', 'has_acceptance_criteria',
                                                  'has_please', 'has_tbd', 'priority'], axis=1, inplace=True)
                        features_data_train_test.drop(['has_code', 'has_url', 'has_template', 'has_acceptance_criteria',
                                                       'has_please', 'has_tbd', 'priority'], axis=1, inplace=True)
                        features_data_test.drop(['has_code', 'has_url', 'has_template', 'has_acceptance_criteria',
                                                 'has_please', 'has_tbd', 'priority'], axis=1, inplace=True)

                # update the new data
                # write train val
                features_data_train_valid.to_csv(
                    '..Models/train_val_after_chi/features_data_train_{}_{}.csv'.format(
                        project_key, label_name[0]), index=False)
                features_data_valid.to_csv(
                    '..Models/train_val_after_chi/features_data_valid_{}_{}.csv'.format(
                        project_key, label_name[0]), index=False)

                # write train test
                features_data_train_test.to_csv(
                    '..Models/train_test_after_chi/features_data_train_{}_{}.csv'.format(
                        project_key, label_name[0]), index=False)
                features_data_test.to_csv(
                    '..Models/train_test_after_chi/features_data_test_{}_{}.csv'.format(
                        project_key, label_name[0]), index=False)

    if is_after_all_but:
        # read all the data sets and delete from each one the unwanted features by the feature group omtimization results in the excel files
        for project_key in projects_key:
            for label_name in dict_labels.items():
                print("data: {}, \n label_name.key: {}, \n".format(project_key, label_name[0]))
                features_data_train_valid = pd.read_csv(
                    '..Models/train_val_after_chi/features_data_train_{}_{}.csv'.format(
                        project_key, label_name[0]), low_memory=False)
                features_data_valid = pd.read_csv(
                    '..Models/train_val_after_chi/features_data_valid_{}_{}.csv'.format(
                        project_key, label_name[0]), low_memory=False)
                features_data_train_test = pd.read_csv(
                    '..Models/train_test_after_chi/features_data_train_{}_{}.csv'.format(
                        project_key, label_name[0]), low_memory=False)
                features_data_test = pd.read_csv(
                    '..Models/train_test_after_chi/features_data_test_{}_{}.csv'.format(
                        project_key, label_name[0]), low_memory=False)

                # remove features by chi square:
                if project_key == 'DEVELOPER': # all but a
                    features_data_train_valid.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                                                    'dominant_topic'], axis=1, inplace=True)
                    features_data_valid.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                                              'dominant_topic'], axis=1, inplace=True)
                    features_data_train_test.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                                                   'dominant_topic'], axis=1, inplace=True)
                    features_data_test.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                                             'dominant_topic'], axis=1, inplace=True)
                if project_key == 'REPO': # c + d
                    features_data_train_valid.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
                                                    '11', '12', '13', '14', 'dominant_topic', 'num_headlines',
                                                    'num_question_marks', 'has_template', 'len_sum_desc',
                                                    'len_description', 'if_description_empty_tbd',
                                                    'num_sentences', 'num_words', 'avg_word_len',
                                                    'avg_num_word_in_sentence',
                                                    'has_acceptance_criteria', 'noun_count', 'verb_count', 'adj_count',
                                                    'adv_count', 'pron_count', 'num_stopwords'], axis=1, inplace=True)
                    features_data_valid.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
                                              '11', '12', '13', '14', 'dominant_topic', 'num_headlines',
                                              'num_question_marks', 'has_template', 'len_sum_desc',
                                              'len_description', 'if_description_empty_tbd',
                                              'num_sentences', 'num_words', 'avg_word_len',
                                              'avg_num_word_in_sentence',
                                              'has_acceptance_criteria', 'noun_count', 'verb_count', 'adj_count',
                                              'adv_count', 'pron_count', 'num_stopwords'], axis=1, inplace=True)
                    features_data_train_test.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
                                                   '11', '12', '13', '14', 'dominant_topic', 'num_headlines',
                                                   'num_question_marks', 'has_template', 'len_sum_desc',
                                                   'len_description', 'if_description_empty_tbd',
                                                   'num_sentences', 'num_words', 'avg_word_len',
                                                   'avg_num_word_in_sentence',
                                                   'has_acceptance_criteria', 'noun_count', 'verb_count', 'adj_count',
                                                   'adv_count', 'pron_count', 'num_stopwords'], axis=1, inplace=True)
                    features_data_test.drop(['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
                                             '11', '12', '13', '14', 'dominant_topic', 'num_headlines',
                                             'num_question_marks', 'has_template', 'len_sum_desc',
                                             'len_description', 'if_description_empty_tbd',
                                             'num_sentences', 'num_words', 'avg_word_len',
                                             'avg_num_word_in_sentence',
                                             'has_acceptance_criteria', 'noun_count', 'verb_count', 'adj_count',
                                             'adv_count', 'pron_count', 'num_stopwords'], axis=1, inplace=True)
                if project_key == 'XD': # c + d
                    features_data_train_valid.drop(['0', '1', '2', '3', '4',
                                                    'dominant_topic', 'num_headlines', 'num_question_marks',
                                                    'has_template', 'len_sum_desc', 'len_description', 'len_acceptance',
                                                    'num_sentences', 'num_words', 'avg_word_len',
                                                    'avg_num_word_in_sentence', 'has_tbd', 'has_acceptance_criteria',
                                                    'noun_count', 'verb_count', 'adj_count', 'adv_count', 'pron_count',
                                                    'num_stopwords'], axis=1, inplace=True)
                    features_data_valid.drop(['0', '1', '2', '3', '4',
                                              'dominant_topic', 'num_headlines', 'num_question_marks',
                                              'has_template', 'len_sum_desc', 'len_description', 'len_acceptance',
                                              'num_sentences', 'num_words', 'avg_word_len',
                                              'avg_num_word_in_sentence', 'has_tbd', 'has_acceptance_criteria',
                                              'noun_count', 'verb_count', 'adj_count', 'adv_count', 'pron_count',
                                              'num_stopwords'], axis=1, inplace=True)
                    features_data_train_test.drop(['0', '1', '2', '3', '4',
                                                   'dominant_topic', 'num_headlines', 'num_question_marks',
                                                   'has_template', 'len_sum_desc', 'len_description', 'len_acceptance',
                                                   'num_sentences', 'num_words', 'avg_word_len',
                                                   'avg_num_word_in_sentence', 'has_tbd', 'has_acceptance_criteria',
                                                   'noun_count', 'verb_count', 'adj_count', 'adv_count', 'pron_count',
                                                   'num_stopwords'], axis=1, inplace=True)
                    features_data_test.drop(['0', '1', '2', '3', '4',
                                             'dominant_topic', 'num_headlines', 'num_question_marks',
                                             'has_template', 'len_sum_desc', 'len_description', 'len_acceptance',
                                             'num_sentences', 'num_words', 'avg_word_len',
                                             'avg_num_word_in_sentence', 'has_tbd', 'has_acceptance_criteria',
                                             'noun_count', 'verb_count', 'adj_count', 'adv_count', 'pron_count',
                                             'num_stopwords'], axis=1, inplace=True)
                # update the new data
                # DM - all
                # write train val
                features_data_train_valid.to_csv(
                    '..Models/train_val_after_all_but/features_data_train_{}_{}.csv'.format(
                        project_key, label_name[0]), index=False)
                features_data_valid.to_csv(
                    '..Models/train_val_after_all_but/features_data_valid_{}_{}.csv'.format(
                        project_key, label_name[0]), index=False)
                # write train test
                features_data_train_test.to_csv(
                    '..Models/train_test_after_all_but/features_data_train_{}_{}.csv'.format(
                        project_key, label_name[0]), index=False)
                features_data_test.to_csv(
                    '..Models/train_test_after_all_but/features_data_test_{}_{}.csv'.format(
                        project_key, label_name[0]), index=False)


