import matplotlib.pyplot as plt
import tensorflow as tf
from funcsigs import signature
from transformers import TFBertForSequenceClassification, BertTokenizer
import BERT.run_fit_setfit_bert as run_fit_setfit_bert
import numpy as np
from sklearn.metrics import classification_report
from sklearn import metrics
import pandas as pd
from scipy.special import softmax
from transformers import TrainingArguments, Trainer
import Utils.GetNLPData as GetNLPData



def predict_proba(model, x_test):
    # Encode the sentences
    embeddings = model.encode(x_test, convert_to_tensor=True)

    # Predict the logits for the sentences
    logits = model.predict(embeddings)

    # Apply softmax to obtain class probabilities
    probabilities = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    probabilities = probabilities.tolist()

    return probabilities


def create_pre_rec_curve(y_test, y_score, auc, algorithm, label, path):
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
    plt.title('Precision-Recall curve')

    plt.savefig(f'{path}/pre_recall_curve_groups_{label}_{algorithm}_Samples_2.png')
    plt.close()
    return area


def get_report(kind_of_bert, main_path, k_unstable, test_predictions, test_labels,
               threshold=None):
    y_score = softmax(test_predictions, axis=1)
    test_predictions = np.where(y_score[:, 1] >= threshold, 1, 0)

    accuracy = metrics.accuracy_score(test_labels, test_predictions)
    print(f"Accuracy {k_unstable}-unstable:", accuracy)

    confusion_matrix = metrics.confusion_matrix(test_labels, test_predictions)
    print(f"confusion_matrix {k_unstable}-unstable: \n {confusion_matrix}")

    classific_report = metrics.classification_report(test_labels, test_predictions)
    print(f"classification_report {k_unstable}-unstable: \n {classific_report}")

    # Create precision, recall curve
    average_precision = metrics.average_precision_score(test_labels, y_score[:, 1])
    print(f'Average precision-recall score {k_unstable}-unstable: {average_precision}')

    auc = metrics.roc_auc_score(test_labels, y_score[:, 1])
    print(f'AUC roc {k_unstable}-unstable: {auc}')

    precision, recall, thresholds = metrics.precision_recall_curve(test_labels, y_score[:, 1])

    area_under_pre_recall_curve = metrics.auc(recall, precision)
    print(f'area_under_pre_recall_curve {k_unstable}-unstable: {area_under_pre_recall_curve}')

    return [accuracy, confusion_matrix, classific_report, area_under_pre_recall_curve, average_precision, auc,
            test_predictions, precision, recall, thresholds]


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


def start():
    results = pd.DataFrame(columns=['usability_label', 'threshold', 'accuracy',
                                    'confusion_matrix', 'classification_report', 'area_under_pre_recall_curve',
                                    'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                                    'recall', 'thresholds'])
    main_path = 'Master/'
    flag = False
    for k_unstable in [5, 10, 15, 20]:

        # Load the BERT model and tokenizer
        tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')

        test = GetNLPData.get_data_all_test(main_path, k_unstable)

        test_sentences = list(test['sentence'])
        test_labels = list(test['label'])

        test_encoded = batch_encode(tokenizer, test_sentences)

        test_input_ids = test_encoded['input_ids']
        test_attention_mask = test_encoded['attention_mask']
        test_labels = tf.convert_to_tensor(test_labels)

        if flag:
            model = TFBertForSequenceClassification.from_pretrained(
                f"YakovElm/Cross_Project_{k_unstable}_Classic_Cross_Entropy_Samples_2")

        else:
            model = TFBertForSequenceClassification.from_pretrained('bert-base-uncased')
            train, valid = GetNLPData.get_data_all_train_valid(main_path, k_unstable)

            train_sentences = list(train['sentence'])
            train_labels = list(train['label'])

            val_sentences = list(valid['sentence'])
            val_labels = list(valid['label'])

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
            class_weights = [(len(train_labels) / (2 * np.bincount(train_labels)))[0],
                             (len(train_labels) / (2 * np.bincount(train_labels)))[1]]
            loss = tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True)
            metric = tf.keras.metrics.SparseCategoricalAccuracy('accuracy')
            model.compile(optimizer=optimizer, loss=loss, metrics=[metric], loss_weights=class_weights)

            # Train the model with validation data
            model.fit(
                [train_input_ids, train_attention_mask],
                train_labels,
                epochs=3,
                batch_size=32,
                validation_data=([val_input_ids, val_attention_mask], val_labels)
            )

            model.push_to_hub(f"YakovElm/Cross_Project_{k_unstable}_Classic_Cross_Entropy_Samples_2")

        # Assuming you have predictions for the test data
        predictions = model.predict([test_input_ids, test_attention_mask])
        predictions = predictions[0]

        results = add_new_threshold(results, main_path, k_unstable, predictions, test_labels, 0.05)
        results = add_new_threshold(results, main_path, k_unstable, predictions, test_labels, 0.25)
        results = add_new_threshold(results, main_path, k_unstable, predictions, test_labels, 0.5)
        results = add_new_threshold(results, main_path, k_unstable, predictions, test_labels, 0.75)
        results = add_new_threshold(results, main_path, k_unstable, predictions, test_labels, 0.9)
        results = add_new_threshold(results, main_path, k_unstable, predictions, test_labels, 0.998)

        results.to_csv(f'{main_path}Cross_Projects/Results/Cross_Projects_Classic_result_{k_unstable}'
                       f'_Cross_Entropy_Samples_2.csv', index=False)
        results = pd.DataFrame(columns=['usability_label', 'threshold', 'accuracy',
                                        'confusion_matrix', 'classification_report', 'area_under_pre_recall_curve',
                                        'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                                        'recall', 'thresholds'])


def add_new_threshold(results, main_path, k_unstable, predictions, test_labels, threshold):
    accuracy, confusion_matrix, classific_report, area_under_pre_recall_curve, average_precision, auc, \
        y_pred, precision, recall, thresholds = \
        get_report(kind_of_bert="Classic_Samples_2", main_path=main_path, k_unstable=k_unstable, test_predictions=predictions,
                   test_labels=test_labels, threshold=threshold)

    d = {
        'usability_label': k_unstable, 'threshold': threshold,
        'accuracy': accuracy, 'confusion_matrix': confusion_matrix, 'classification_report': classific_report,
        'area_under_pre_recall_curve': area_under_pre_recall_curve, 'avg_precision': average_precision,
        'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision, 'recall': recall,
        'thresholds': thresholds
    }

    results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)
    return results
