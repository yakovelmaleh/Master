from sentence_transformers.losses import CosineSimilarityLoss
from datasets import Dataset
import pyarrow as pa
from setfit import SetFitModel, SetFitTrainer, sample_dataset
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn import metrics
import matplotlib.pyplot as plt
from funcsigs import signature


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

    y_score = model.predict_proba(x_test)

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


def get_data_train_with_labels(jira_name, main_path, k_unstable):
    path = f"{main_path}Data/{jira_name}/features_labels_table_os.csv"
    all_features = pd.read_csv(path)

    path = f"{main_path}Models/train_val/{jira_name}"
    train_keys = pd.read_csv(f'{path}/features_data_train_{jira_name}_is_change_text_num_words_{k_unstable}.csv')
    valid_keys = pd.read_csv(f'{path}/features_data_valid_{jira_name}_is_change_text_num_words_{k_unstable}.csv')

    train_keys = train_keys[['issue_key']]
    valid_keys = valid_keys[['issue_key']]

    all_features = all_features[
        ['issue_key', 'original_summary_description_acceptance_sprint', f'is_change_text_num_words_{k_unstable}']]

    train_data = train_keys.join(all_features.set_index('issue_key'), on='issue_key')
    valid_data = valid_keys.join(all_features.set_index('issue_key'), on='issue_key')

    train_data = train_data.reset_index()
    valid_data = valid_data.reset_index()

    train_data = train_data.rename(
        columns={'index': 'idx', 'original_summary_description_acceptance_sprint': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})
    valid_data = valid_data.rename(
        columns={'index': 'idx', 'original_summary_description_acceptance_sprint': 'sentence',
                 f'is_change_text_num_words_{k_unstable}': 'label'})

    train_data = train_data.drop('issue_key', axis=1)
    valid_data = valid_data.drop('issue_key', axis=1)

    return train_data, valid_data


def get_datasets(jira_name, main_path, k_unstable, ratio):

    train_data, valid_data, test_data, size = get_balance_data(jira_name, main_path, k_unstable, ratio)

    train_data = Dataset(pa.Table.from_pandas(train_data))
    valid_data = Dataset(pa.Table.from_pandas(valid_data))
    test_data = Dataset(pa.Table.from_pandas(test_data))

    return train_data, valid_data, test_data, size


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


def start(jira_name, main_path):

    results = pd.DataFrame(columns=['project_key', 'usability_label', 'size', 'ratio', 'accuracy',
                                    'confusion_matrix', 'classification_report', 'area_under_pre_recall_curve',
                                    'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                                    'recall', 'thresholds'])

    for k_unstable in [5, 10, 15, 20]:

        ratio_lst = get_ratio(jira_name, main_path, k_unstable)
        for ratio in ratio_lst:
            if ratio == 0.5:
                ratio_name = 'Half'
            else:
                ratio_name = ratio

            # Load Data and valid
            train, valid, test, size = get_datasets(jira_name, main_path, k_unstable, ratio)

            # Simulate the few-shot regime by sampling 8 examples per class
            train_dataset = sample_dataset(train, label_column="label", num_samples=8)

            # Load a SetFit model from Hub
            model = SetFitModel.from_pretrained("sentence-transformers/paraphrase-mpnet-base-v2")

            # Create trainer
            trainer = SetFitTrainer(
                model=model,
                train_dataset=train_dataset,
                eval_dataset=valid,
                loss_class=CosineSimilarityLoss,
                metric="accuracy",
                batch_size=16,
                num_iterations=20,  # The number of text pairs to generate for contrastive learning
                num_epochs=3,  # The number of epochs to use for contrastive learning
                column_mapping={"sentence": "text", "label": "label"}
                # Map dataset columns to text/label expected by trainer
            )

            # Train and evaluate
            trainer.train()
            metrics = trainer.evaluate()

            trainer.push_to_hub(f"YakovElm/{jira_name}{k_unstable}SetFitModel_balance_ratio_{ratio_name}")
            print(f'finish {k_unstable}')

            test_sentence = list(test['sentence'])
            test_labels = list(test['label'])

            test_predictions = model(test_sentence)
            test_predictions = np.array(test_predictions)

            accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc, \
                y_pred, precision, recall, thresholds = \
                get_report(model=model, kind_of_bert=f"SetFit__ratio_{ratio_name}", jira_name=jira_name, main_path=main_path,
                                        k_unstable=k_unstable, test_predictions=test_predictions, x_test=test_sentence,
                                        test_labels=test_labels)

            d = {
                'jira_name': jira_name, 'usability_label': k_unstable,
                'accuracy': accuracy, 'confusion_matrix': confusion_matrix,
                'classification_report': classification_report,
                'area_under_pre_recall_curve': area_under_pre_recall_curve, 'avg_precision': average_precision,
                'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision, 'recall': recall,
                'thresholds': thresholds, 'size': size, 'ratio': ratio_name
            }

            results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

        results.to_csv(f'{main_path}BERT_Balance_Data/'
                       f'Results/{jira_name}/SetFit_result_{k_unstable}.csv', index=False)