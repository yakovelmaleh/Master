import torch
from torch.utils.data import TensorDataset, DataLoader
import torch.nn.functional as F
import pandas as pd
import Utils.NLP_Models.Get_Results as Get_Results
from transformers import AutoTokenizer, GPT2ForSequenceClassification


def start(jira_name, train_data_list, test_data_list, model_name, path_to_save):

    results = pd.DataFrame(columns=['project_key', 'usability_label',
                                       'accuracy', 'confusion_matrix', 'classification_report',
                                       'area_under_pre_recall_curve', 'avg_precision',
                                       'area_under_roc_curve', 'y_pred'])

    for k_unstable in [5, 10, 15, 20]:
        tokenizer = AutoTokenizer.from_pretrained('microsoft/DialogRPT-updown')

        train_data = train_data_list[f'{k_unstable}']
        test_data = test_data_list[f'{k_unstable}']

        x_train = list(train_data['sentence'])
        y_train = list(train_data['label'].astype(float))

        x_test = list(test_data['sentence'])
        y_test = list(test_data['label'].astype(float))

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

        model = GPT2ForSequenceClassification.from_pretrained("microsoft/DialogRPT-updown")

        # Step 3: Train the model
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model.to(device)
        batch_size = 32
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

        optimizer = torch.optim.Adam(model.parameters(), lr=1e-5)

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

        model.push_to_hub(f"YakovElm/{jira_name}_{k_unstable}_GPT2_Microsoft_{model_name}")

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
        y_score = [[y, 1-y] for y in y_score]

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc =\
            Get_Results.get_results(y_score=y_score, y_pred=y_pred,
                                    model_name=f'{jira_name}_{k_unstable}_GPT2_Microsoft_{model_name}', y_test=y_test,
                                    path_to_save=path_to_save)

        d = {'project_key': jira_name, 'usability_label': k_unstable,
             'accuracy': accuracy,
             'confusion_matrix': confusion_matrix,
             'classification_report': classification_report,
             'area_under_pre_recall_curve': area_under_pre_recall_curve,
             'avg_precision': average_precision, 'area_under_roc_curve': auc}

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

    results.to_csv(
        f'{path_to_save}/Results_GTP2_Microsoft_{jira_name}_{model_name}.csv', index=False)
