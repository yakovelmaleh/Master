from sentence_transformers.losses import CosineSimilarityLoss
from datasets import Dataset
import pyarrow as pa
from setfit import SetFitModel, SetFitTrainer, sample_dataset
import pandas as pd


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


def get_dataset_train_with_labels(jira_name, main_path, k_unstable):
    train_data, valid_data = get_data_train_with_labels(jira_name, main_path, k_unstable)

    train_data = Dataset(pa.Table.from_pandas(train_data))
    valid_data = Dataset(pa.Table.from_pandas(valid_data))

    return train_data, valid_data


def start(jira_name, main_path):
    for num in [5, 10, 15, 20]:
        # Load Data and valid
        train, valid = get_dataset_train_with_labels(jira_name, main_path, num)

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

        trainer.push_to_hub(f"YakovElm/{jira_name}{num}SetFitModel")
        print(f"Metrics of {num}:")
        print(metrics)
        print(f'finish {num}')