import ktrain
from ktrain import text
import Utils.NLP_Models.Get_Results as Get_Results
import pandas as pd
from sklearn.utils import class_weight
import numpy as np


def start(jira_name, train_data_list, test_data_list, model_name, path_to_save):
    results = pd.DataFrame(columns=['project_key', 'usability_label',
                                       'accuracy', 'confusion_matrix', 'classification_report',
                                       'area_under_pre_recall_curve', 'avg_precision',
                                       'area_under_roc_curve', 'y_pred'])

    for k_unstable in [5, 10, 15, 20]:

        train = train_data_list[f'{k_unstable}']
        test = test_data_list[f'{k_unstable}']

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
        class_weights = class_weight.compute_class_weight(class_weight='balanced', classes=np.unique(train['label']),
                                                          y=train['label'].tolist())

        weights = {}
        for index, weight in enumerate(class_weights):
            weights[index] = weight

        # Create a Learner object
        learner = ktrain.get_learner(model, train_data=trn, val_data=val, batch_size=6)
        learner.lr_find(show_plot=True, max_epochs=5)

        learner.autofit(2e-5, 3, class_weight=weights)

        # Evaluate the model
        learner.validate()

        test_labels = test['label'].tolist()

        predictor = ktrain.get_predictor(learner.model, preproc)
        y_pred = predictor.predict(test['sentence'].tolist())
        y_score = predictor.predict_proba(test['sentence'].tolist())

        accuracy, confusion_matrix, classification_report, area_under_pre_recall_curve, average_precision, auc = \
            Get_Results.get_results(y_score=y_score, y_pred=y_pred,
                                    model_name=f'{jira_name}_{k_unstable}_RoBERTaV2_{model_name}', y_test=test_labels,
                                    path_to_save=path_to_save)

        d = {'project_key': jira_name, 'usability_label': k_unstable,
             'accuracy': accuracy,
             'confusion_matrix': confusion_matrix,
             'classification_report': classification_report,
             'area_under_pre_recall_curve': area_under_pre_recall_curve,
             'avg_precision': average_precision, 'area_under_roc_curve': auc}

        results = pd.concat([results, pd.DataFrame([d.values()], columns=d.keys())], ignore_index=True)

    results.to_csv(f'{path_to_save}/Results_ktrain_{jira_name}_{model_name}.csv')




