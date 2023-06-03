import ktrain
import sklearn
from ktrain import text
import Utils.GetNLPData as GetNLPData
import pandas as pd
from sklearn import metrics
from sklearn.utils import class_weight
import numpy as np


def start(jira_name):
    results = pd.DataFrame(
        columns=['project_key', 'usability_label', 'accuracy', 'confusion_matrix', 'classification_report',
                 'area_under_pre_recall_curve', 'avg_precision', 'area_under_roc_curve', 'y_pred', 'precision',
                 'recall', 'thresholds'])

    for k_unstable in [5, 10, 15, 20]:

        train = GetNLPData.get_data_train(jira_name, 'Master/', k_unstable)
        test = GetNLPData.get_test_data(jira_name, 'Master/', k_unstable)

        # Pre Processing
        trn, val, preproc = text.texts_from_array(x_train=train['sentence'].tolist(), y_train=train['label'].tolist(),
                                                  x_test=test['sentence'].tolist(), y_test=test['label'].tolist(),
                                                  class_names=np.unique(train['label']),
                                                  val_pct=0.1,
                                                  max_features=30000,
                                                  maxlen=350,
                                                  preprocess_mode='distilbert',
                                                  ngram_range=1)

        # Load the pre-trained DistilBERT model
        model = text.text_classifier('distilbert', train_data=trn, preproc=preproc)

        # Set the class weights
        class_weights = class_weight.compute_class_weight('balanced', np.unique(train['label']), train['label'].tolist())

        # Create a Learner object
        learner = ktrain.get_learner(model, train_data=trn, val_data=val, batch_size=6)
        learner.lr_find(show_plot=True, max_epochs=5)

        learner.autofit(2e-5, 3, class_weight=class_weights)

        # Evaluate the model
        learner.validate()
        learner.push_to_hub(f'YakovElm/{jira_name}_Ktrain_{ktrain}')

        test_labels = test['label'].tolist()

        # Preprocess the test data
        test_preprocessed = preproc.preprocess_test(test['sentence'].tolist())

        # Create a test dataloader
        test_dataloader = preproc.create_dataloader(test_preprocessed, batch_size=32, shuffle=False)

        # Predict on the test data
        y_pred = learner.predict(test_dataloader)
        y_score = learner.predict_proba(test_dataloader=test_dataloader)

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




