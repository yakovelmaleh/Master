import ktrain
import sklearn
from ktrain import text
import Utils.GetNLPData as GetNLPData
import pandas as pd
from sklearn import metrics
from sklearn.utils import class_weight


def start(jira_name):
    results = pd.DataFrame(
        columns=['project_key', 'usability_label', 'accuracy', 'confusion_matrix', 'classification_report',
                 'area_under_pre_recall_curve', 'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                 'recall', 'thresholds'])

    for k_unstable in [5, 10, 15, 20]:

        train, valid = GetNLPData.get_data_train_with_labels(jira_name, 'Master/', k_unstable)
        train_texts = train['sentence'].tolist()
        val_texts = valid['sentence'].tolist()
        train_labels = train['label'].tolist()
        val_labels = valid['label'].tolist()

        trn = text.texts_from_array(train_texts, train_labels)
        val = text.texts_from_array(val_texts, val_texts)

        # Create a TextDataBunch
        data = text.TransformerTextDataBunch.from_datasets(trn_dataset=trn, val_dataset=val, classes=[0, 1],
                                                           preprocess_mode='distilbert')

        # Load the pre-trained DistilBERT model
        model_name = 'distilbert-base-uncased'
        model = text.text_classifier(name='distilbert', train_data=data, preproc=data.preprocess)

        # Set the class weights
        class_weights = class_weight.compute_class_weight('balanced', [1, 0], train_labels)

        # Create a Learner object
        learner = ktrain.get_learner(model, train_data=data, val_data=val, batch_size=6)  # Use separate validation data

        # Fit the model with class weights
        learner.fit_onecycle(3e-5, 3, class_weight=class_weights)  # Adjust the learning rate and epochs as needed

        # Evaluate the model
        learner.validate(class_names=[0, 1])
        learner.push_to_hub(f'YakovElm/{jira_name}_Ktrain_{ktrain}')

        test = GetNLPData.get_test_data(jira_name, 'Master/', k_unstable)
        test_texts = test['sentence'].tolist()
        test_labels = test['label'].tolist()

        test_preprocessed = data.preprocess_test(test_texts)
        # Create a test dataloader
        test_dataloader = data.test_dl(test_preprocessed)

        # Predict on the test data
        y_pred = learner.predict(test_dataloader)
        y_score = learner.predict_proba(test_dataloader=test_dataloader)

        # Get the predicted labels
        predicted_labels = [data.classes[prediction] for prediction in y_pred]

        precision, recall, thresholds = metrics.precision_recall_curve(test_labels, y_score[:, 1])
        d = {
            'project_key': jira_name,
            'usability_label': k_unstable,
            'accuracy': metrics.accuracy_score(test_labels, y_pred),
            'confusion_matrix': metrics.confusion_matrix(test_labels, y_pred),
            'classification_report': metrics.classification_report(test_labels, y_pred),
            'area_under_pre_recall_curve': metrics.auc(test_labels, precision),
            'avg_precision': metrics.average_precision_score(test_labels, y_score[:, 1]),
            'area_under_roc_curve': metrics.roc_auc_score(test_labels, y_score[:, 1]),
            'y_pred': y_pred,
            'precision': precision,
            'recall': recall,
            'thresholds': thresholds,
        }
        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

    results.to_csv(f'Master/Balancing_Data/Results/{jira_name}/Ktrain.csv')




