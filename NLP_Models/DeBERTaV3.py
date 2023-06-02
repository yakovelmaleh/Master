from transformers import DebertaForSequenceClassification, DebertaTokenizer
from torch.utils.data import DataLoader, TensorDataset
import torch
import matplotlib.pyplot as plt
from sklearn import metrics
from funcsigs import signature
import torch.nn.functional as F
import pandas as pd
import Utils.GetNLPData as GetNLPData

def start(jira_name):

    results = pd.DataFrame(columns=['project_key', 'usability_label',
                                       'accuracy', 'confusion_matrix', 'classification_report',
                                       'area_under_pre_recall_curve', 'avg_precision',
                                       'area_under_roc_curve', 'y_pred'])

    for k_unstable in [5, 10, 15, 20]:
        tokenizer = DebertaTokenizer.from_pretrained("microsoft/deberta-base")
        model = DebertaForSequenceClassification.from_pretrained("microsoft/deberta-v3-base",
                                                                 ignore_mismatched_sizes=True)

        data = GetNLPData.get_data_train(jira_name, 'Master/', k_unstable)
        data_texts = data['sentence'].tolist()
        data_labels = data['label'].tolist()

        encoded_inputs = tokenizer(data_texts, padding=True, truncation=True, return_tensors="pt")
        dataset = TensorDataset(encoded_inputs.input_ids, encoded_inputs.attention_mask, torch.tensor(data_labels))

        # Define the batch size and create a DataLoader
        batch_size = 32
        num_epochs = 3
        dataloader = DataLoader(dataset, batch_size=batch_size)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-5)

        # Move the model to the device
        model.to(device)
        if jira_name == 'Apache' and k_unstable == 5:
            model = DebertaForSequenceClassification.from_pretrained(f"YakovElm/{jira_name}{k_unstable}_DeBERTaV3Model")
        else:
            for epoch in range(num_epochs):
                for batch in dataloader:
                    input_ids = batch[0].to(device)
                    attention_mask = batch[1].to(device)
                    labels = batch[2].to(device)

                    optimizer.zero_grad()
                    outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
                    loss = outputs.loss
                    loss.backward()
                    optimizer.step()

            # save model
            model.push_to_hub(f"YakovElm/{jira_name}{k_unstable}_DeBERTaV3Model")

        # Evaluation loop (assuming you have a separate evaluation dataset)
        data = GetNLPData.get_test_data(jira_name, 'Master/', k_unstable)
        eval_texts = data['sentence'].tolist()
        eval_labels = data['label'].tolist()

        encoded_eval_inputs = tokenizer(eval_texts, padding=True, truncation=True, return_tensors="pt")
        eval_dataset = TensorDataset(encoded_eval_inputs.input_ids, encoded_eval_inputs.attention_mask,
                                     torch.tensor(eval_labels))

        eval_dataloader = DataLoader(eval_dataset, batch_size=batch_size)

        model.eval()  # Set the model to evaluation mode

        model.eval()
        with torch.no_grad():
            for batch in eval_dataloader:
                input_ids = batch['input_ids'].to(device)
                attention_mask = batch['attention_mask'].to(device)

                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                predicted_labels = torch.argmax(outputs[0], dim=1)
                probabilities = F.softmax(outputs[0], dim=1)

        y_pred = predicted_labels.tolist()

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc =\
            get_results(y_score=probabilities, y_pred=y_pred, model_name=f'DeBERTaV3{k_unstable}_model',
                          y_test=eval_labels, project_key=jira_name, label=k_unstable)

        d = {'project_key': jira_name, 'usability_label': k_unstable,
             'accuracy': accuracy,
             'confusion_matrix': confusion_matrix,
             'classification_report': classification_report,
             'area_under_pre_recall_curve': area_under_pre_recall_curve,
             'avg_precision': average_precision, 'area_under_roc_curve': auc}

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

    path = f'Master/NLP_Models/Results/{jira_name}'
    results.to_csv(
        f'{path}/Results_DeBERTaV3_{jira_name}_label_{k_unstable}.csv', index=False)


def get_results(y_score, y_pred, model_name, y_test, project_key, label):
    """
    this function predict with the best params per model
    """
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
                                                       label=label,
                                                       algorithm=model_name)
    print(f'area_under_pre_recall_curve {model_name}: {area_under_pre_recall_curve}')

    return [accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc]


def create_pre_rec_curve(y_test, y_score, average_precision, project_key, label, algorithm):
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
    path = f'Master/NLP_Models/Results/{project_key}'
    plt.savefig(
        f'{path}/pre_recall_curve_groups_{project_key}_{label}_{algorithm}.png')
    plt.close()
    return area
