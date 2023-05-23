from setfit import SetFitModel
import pandas as pd
import Classic_BERT_with_clean as Classic_BERT_with_clean
import numpy as np


def start(jira_name, main_path):
    results = pd.DataFrame(columns=['project_key', 'usability_label', 'accuracy',
                                    'confusion_matrix', 'classification_report', 'area_under_pre_recall_curve',
                                    'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                                    'recall', 'thresholds'])

    for k_unstable in [5, 10, 15, 20]:
        model = SetFitModel.from_pretrained(f"YakovElm/{jira_name}{k_unstable}SetFitModel_clean_data")

        # get test data
        test = Classic_BERT_with_clean.get_test_data(jira_name, main_path, k_unstable)
        test = Classic_BERT_with_clean.clean_data(test)

        test_sentence = list(test['sentence'])
        test_labels = list(test['label'])

        test_predictions = model(test_sentence)
        test_predictions = np.array(test_predictions)

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc, \
            y_pred, precision, recall, thresholds = \
            Classic_BERT_with_clean.get_report(model=model, kind_of_bert="SetFit", jira_name=jira_name,
                                               main_path=main_path,
                                               k_unstable=k_unstable, test_predictions=test_predictions,
                                               x_test=test_sentence,
                                               test_labels=test_labels)

        d = {
            'jira_name': jira_name, 'usability_label': k_unstable,
            'accuracy': accuracy, 'confusion_matrix': confusion_matrix, 'classification_report': classification_report,
            'area_under_pre_recall_curve': area_under_pre_recall_curve, 'avg_precision': average_precision,
            'area_under_roc_curve': auc, 'y_pred': y_pred, 'precision': precision, 'recall': recall,
            'thresholds': thresholds
        }

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

    results.to_csv(f'{main_path}BERT_With_Cleaning/Results/{jira_name}/SetFit_With_Cleaning_result.csv', index=False)
