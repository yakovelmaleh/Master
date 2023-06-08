from transformers import RobertaTokenizer, RobertaForSequenceClassification
import torch
from torch.utils.data import TensorDataset, DataLoader
import Utils.GetNLPData as GetNLPData
import torch.nn.functional as F
from sklearn import metrics
from funcsigs import signature
import matplotlib.pyplot as plt
import pandas as pd


def start(jira_name):

    results = pd.DataFrame(columns=['project_key', 'usability_label',
                                       'accuracy', 'confusion_matrix', 'classification_report',
                                       'area_under_pre_recall_curve', 'avg_precision',
                                       'area_under_pre_recall_curve', 'avg_precision',
                                       'area_under_roc_curve', 'y_pred'])

    for k_unstable in [5, 10, 15, 20]:
        tokenizer = RobertaTokenizer.from_pretrained('roberta-base')

        train_data = GetNLPData.get_data_train(jira_name, "Master/", k_unstable)
        test_data = GetNLPData.get_test_data(jira_name, "Master/", k_unstable)

        x_train = train_data['sentence']
        y_train = train_data['label']

        x_test = test_data['sentence']
        y_test = test_data['label']

        x_train_tokenized = tokenizer.batch_encode_plus(
            x_train,
            max_length=128,
            padding='max_length',
            truncation=True,
            return_tensors='pt'
        )

        x_test_tokenized = tokenizer.batch_encode_plus(
            x_test,
            max_length=128,
            padding='max_length',
            truncation=True,
            return_tensors='pt'
        )
        train_dataset = TensorDataset(x_train_tokenized['input_ids'], x_train_tokenized['attention_mask'],
                                      torch.tensor(y_train))
        test_dataset = TensorDataset(x_test_tokenized['input_ids'], x_test_tokenized['attention_mask'],
                                     torch.tensor(y_test))

        model = RobertaForSequenceClassification.from_pretrained('roberta-base', num_labels=2)

        # Step 3: Train the model
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model.to(device)
        batch_size = 32
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

        optimizer = torch.optim.Adam(model.parameters(), lr=1e-5)
        loss_fn = torch.nn.CrossEntropyLoss()

        model.train()
        epochs = 3
        for epoch in range(epochs):  # Train for 5 epochs
            total_loss = 0
            for batch in train_loader:
                input_ids, attention_mask, labels = batch
                input_ids, attention_mask, labels = input_ids.to(device), attention_mask.to(device), labels.to(device)

                optimizer.zero_grad()

                outputs = model(input_ids, attention_mask=attention_mask, labels=labels)
                loss = outputs.loss
                logits = outputs.logits

                total_loss += loss.item()

                loss.backward()
                optimizer.step()

            average_loss = total_loss / len(train_loader)
            print(f"Epoch {epoch + 1}/{5}, Average Loss: {average_loss}")

        model.push_to_hub(f"YakovElm/{jira_name}_RoBERTa_{k_unstable}")

        model.eval()  # Set the model to evaluation mode

        test_loader = DataLoader(test_dataset, batch_size=32, shuffle=False)

        all_predicted_labels = []
        all_probabilities = []

        for batch in test_loader:
            input_ids, attention_mask, labels = batch
            input_ids, attention_mask, labels = input_ids.to(device), attention_mask.to(device), labels.to(device)

            with torch.no_grad():
                outputs = model(input_ids, attention_mask=attention_mask)
                logits = outputs.logits

                _, predicted_labels = torch.max(outputs.logits, dim=1)
                probabilities = F.softmax(outputs.logits, dim=1)

                all_predicted_labels.extend(predicted_labels.tolist())
                all_probabilities.extend(probabilities.tolist())

        y_pred = all_predicted_labels
        y_score = torch.tensor(all_probabilities)

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc =\
            get_results(y_score=y_score, y_pred=y_pred, model_name=f'RoBERTa_{k_unstable}_model',
                        y_test=y_test, project_key=jira_name, label=k_unstable)

        d = {'project_key': jira_name, 'usability_label': k_unstable,
             'accuracy': accuracy,
             'confusion_matrix': confusion_matrix,
             'classification_report': classification_report,
             'area_under_pre_recall_curve': area_under_pre_recall_curve,
             'avg_precision': average_precision, 'area_under_roc_curve': auc}

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

    path = f'Master/NLP_Models/Results/{jira_name}'
    results.to_csv(
        f'{path}/Results_RoBERTa_{jira_name}_label_{k_unstable}.csv', index=False)


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
