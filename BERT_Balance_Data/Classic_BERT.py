import matplotlib.pyplot as plt
import tensorflow as tf
from funcsigs import signature
from transformers import TFBertForSequenceClassification, BertTokenizer
import BERT.run_fit_setfit_bert as run_fit_setfit_bert
import numpy as np
from sklearn import metrics
import pandas as pd
from scipy.special import softmax
from sklearn.model_selection import train_test_split


def create_pre_rec_curve(y_test, y_score, auc, algorithm, jira_name, label, path):
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
    plt.title('Precision-Recall curve {0}: Area under Curve={1:0.2f}'.format(jira_name, auc))

    plt.savefig(f'{path}/pre_recall_curve_groups_{jira_name}_{label}_{algorithm}.png')
    plt.close()
    return area


def get_report(model, kind_of_bert, jira_name, main_path, k_unstable, test_predictions, x_test, test_labels,
               threshold=None):

    y_score = softmax(test_predictions, axis=1)
    test_predictions = np.where(y_score[:, 1] >= threshold, 1, 0)

    accuracy = metrics.accuracy_score(test_labels, test_predictions)
    print(f"Accuracy {jira_name} {k_unstable}-unstable:", accuracy)

    confusion_matrix = metrics.confusion_matrix(test_labels, test_predictions)
    print(f"confusion_matrix {jira_name} {k_unstable}-unstable: \n {confusion_matrix}")

    classific_report = metrics.classification_report(test_labels, test_predictions)
    print(f"classification_report {jira_name} {k_unstable}-unstable: \n {classific_report}")

    # Create precision, recall curve
    average_precision = metrics.average_precision_score(test_labels, y_score[:, 1])
    print(f'Average precision-recall score {jira_name} {k_unstable}-unstable: {average_precision}')

    auc = metrics.roc_auc_score(test_labels, y_score[:, 1])
    print(f'AUC roc {jira_name} {k_unstable}-unstable: {auc}')

    precision, recall, thresholds = metrics.precision_recall_curve(test_labels, y_score[:, 1])

    area_under_pre_recall_curve = metrics.auc(recall, precision)
    print(f'area_under_pre_recall_curve {jira_name} {k_unstable}-unstable: {area_under_pre_recall_curve}')

    if threshold is None or threshold == 0.5:
        path = f'{main_path}BERT_Balance_Data/Results/{jira_name}'
        create_pre_rec_curve(test_labels, y_score[:, 1],
                             average_precision, kind_of_bert, jira_name, k_unstable, path)

    return [accuracy, confusion_matrix, classific_report, area_under_pre_recall_curve, average_precision, auc,
            test_predictions, precision, recall, thresholds]


def get_balance_data(jira_name, main_path, k_unstable, ratio):
    path = f"{main_path}Data/{jira_name}/features_labels_table_os.csv"
    all_features = pd.read_csv(path)
    all_features = all_features[
        ['original_summary_description_acceptance_sprint', f'is_change_text_num_words_{k_unstable}']]

    all_features = all_features.rename(
        columns={'original_summary_description_acceptance_sprint': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})

    label_1 = all_features[all_features['label'] == 1]
    label_0 = all_features[all_features['label'] == 0]
    label_0 = label_0.sample(n=int(len(label_1)*ratio))

    all_data = pd.concat([label_1, label_0], ignore_index=True)
    shuffled_all_data = all_data.sample(frac=1, random_state=42)

    train, temp = train_test_split(shuffled_all_data, test_size=0.4, random_state=42)
    validation, test = train_test_split(temp, test_size=0.5, random_state=42)

    return train, validation, test, len(shuffled_all_data)


def get_ratio(jira_name, main_path, k_unstable):
    path = f"{main_path}Data/{jira_name}/features_labels_table_os.csv"
    all_features = pd.read_csv(path)
    all_features = all_features[
        ['original_summary_description_acceptance_sprint', f'is_change_text_num_words_{k_unstable}']]

    all_features = all_features.rename(
        columns={'original_summary_description_acceptance_sprint': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})

    len_total = len(all_features)
    len_label_1 = len(all_features[all_features['label'] == 1])

    ratio_list = [0.5, 1, 2, 3, 4]
    output = []
    for num in ratio_list:
        if len_label_1 + (len_label_1*num) <= len_total:
            output.append(num)

    return output


def batch_encode(tokenizer, data):
    return tokenizer.batch_encode_plus(
        data,
        add_special_tokens=True,
        max_length=128,
        padding='max_length',
        truncation=True,
        return_attention_mask=True,
        return_tensors='tf'
    )


def start(jira_name, main_path):
    results = pd.DataFrame(columns=['jira_name', 'usability_label', 'size', 'threshold', 'accuracy',
                                    'confusion_matrix', 'classification_report', 'area_under_pre_recall_curve',
                                    'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                                    'recall', 'thresholds'])

    for k_unstable in [5,10,15,20]:

        ratio_lst = get_ratio(jira_name, main_path, k_unstable)
        for ratio in ratio_lst:
            if ratio == 0.5:
                ratio_name = 'Half'
            else:
                ratio_name = ratio

            # Load the BERT model and tokenizer
            tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')

            train, validation, test, size = get_balance_data(jira_name=jira_name,
                                                             main_path=main_path, k_unstable=k_unstable, ratio=ratio)

            train_sentences = list(train['sentence'])
            train_labels = list(train['label'])

            val_sentences = list(validation['sentence'])
            val_labels = list(validation['label'])

            test_sentences = list(test['sentence'])
            test_labels = list(test['label'])

            test_encoded = batch_encode(tokenizer, test_sentences)

            test_input_ids = test_encoded['input_ids']
            test_attention_mask = test_encoded['attention_mask']
            test_labels = tf.convert_to_tensor(test_labels)

            if jira_name == 'Nothing':
                model = TFBertForSequenceClassification.\
                    from_pretrained(f'YakovElm/{jira_name}{k_unstable}Classic_Balance_DATA_ratio_{ratio_name}')

            else:
                model = TFBertForSequenceClassification.from_pretrained('bert-base-uncased')

                train_encoded = batch_encode(tokenizer, train_sentences)
                val_encoded = batch_encode(tokenizer, val_sentences)

                train_input_ids = train_encoded['input_ids']
                train_attention_mask = train_encoded['attention_mask']
                train_labels = tf.convert_to_tensor(train_labels)

                val_input_ids = val_encoded['input_ids']
                val_attention_mask = val_encoded['attention_mask']
                val_labels = tf.convert_to_tensor(val_labels)

                # Compile the BERT classification model
                optimizer = tf.keras.optimizers.Adam(learning_rate=3e-5, epsilon=1e-08, clipnorm=1.0)
                loss = tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True)
                metric = tf.keras.metrics.SparseCategoricalAccuracy('accuracy')
                model.compile(optimizer=optimizer, loss=loss, metrics=[metric])

                # Train the model with validation data
                model.fit(
                    [train_input_ids, train_attention_mask],
                    train_labels,
                    epochs=3,
                    batch_size=32,
                    validation_data=([val_input_ids, val_attention_mask], val_labels)
                )

                model.push_to_hub(f"YakovElm/{jira_name}{k_unstable}Classic_Balance_DATA_ratio_{ratio_name}")

            # Assuming you have predictions for the test data
            predictions = model.predict([test_input_ids, test_attention_mask])
            predictions = predictions[0]

            results = add_new_threshold(results, model, jira_name, main_path, k_unstable, predictions, test_input_ids,
                                        test_attention_mask, test_labels, 0.05, size)

            results = add_new_threshold(results, model, jira_name, main_path, k_unstable, predictions, test_input_ids,
                                        test_attention_mask, test_labels, 0.25, size)

            results = add_new_threshold(results, model, jira_name, main_path, k_unstable, predictions, test_input_ids,
                                        test_attention_mask, test_labels, 0.5, size)

            results = add_new_threshold(results, model, jira_name, main_path, k_unstable, predictions, test_input_ids,
                                        test_attention_mask, test_labels, 0.75, size)

            results = add_new_threshold(results, model, jira_name, main_path, k_unstable, predictions, test_input_ids,
                                        test_attention_mask, test_labels, 0.9, size)

            print('start to save')
            print(f'path: {main_path}BERT_Balance_Data/'
                  f'Results/{jira_name}/Classic_result_{k_unstable}_ratio_{ratio_name}.csv')
            results.to_csv(f'{main_path}BERT_Balance_Data/'
                           f'Results/{jira_name}/Classic_result_{k_unstable}_ratio_{ratio_name}.csv', index=False)
            print('ended to save')

            results = pd.DataFrame(columns=['jira_name', 'usability_label', 'threshold', 'accuracy',
                                            'confusion_matrix', 'classification_report', 'area_under_pre_recall_curve',
                                            'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                                            'recall', 'thresholds'])


def add_new_threshold(results, model, jira_name, main_path, k_unstable, predictions, test_input_ids,
                      test_attention_mask, test_labels, threshold, size, ratio_name):

    accuracy, confusion_matrix, classific_report, area_under_pre_recall_curve, average_precision, auc, \
        y_pred, precision, recall, thresholds = \
        get_report(model=model, kind_of_bert=f"Classic_ratio_{ratio_name}", jira_name=jira_name, main_path=main_path,
                   k_unstable=k_unstable, test_predictions=predictions,
                   x_test=[test_input_ids, test_attention_mask], test_labels=test_labels, threshold=threshold)

    d = {
        'jira_name': jira_name, 'usability_label': k_unstable, 'threshold': threshold,
        'accuracy': accuracy, 'confusion_matrix': confusion_matrix, 'classification_report': classific_report,
        'area_under_pre_recall_curve': area_under_pre_recall_curve, 'avg_precision': average_precision,
        'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision, 'recall': recall,
        'thresholds': thresholds, 'size': size
    }

    results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)
    return results





