import matplotlib.pyplot as plt
import tensorflow as tf
from funcsigs import signature
from transformers import TFBertForSequenceClassification, BertTokenizer
import numpy as np
from sklearn import metrics
import pandas as pd
from scipy.special import softmax
import json


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


def start(jira_name, main_path):

    text_column = 'original_summary_description_acceptance_sprint'
    all_data = pd.read_csv(f'{main_path}Data/{jira_name}/features_labels_table_os.csv')
    all_data = all_data[['issue_key', text_column]]

    for k_unstable in [5, 10, 15, 20]:

        # get relevant model
        model = TFBertForSequenceClassification.from_pretrained(f'YakovElm/{jira_name}{k_unstable}Classic')
        tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')

        # get embedding values per User story
        sentences = list(all_data[text_column])
        encoded = batch_encode(tokenizer, sentences)
        data_input_ids = encoded['input_ids']
        data_attention_mask = encoded['attention_mask']

        # get BERT model predictions
        predictions = model.predict([data_input_ids, data_attention_mask])
        predictions = predictions[0]

        # get probability to be k_unstable
        predictions = softmax(predictions, axis=1)[:, 1]

        all_data[f'BERT_{k_unstable}_instability'] = predictions

    all_data = all_data.drop(text_column, axis=1)

    def add_bert_predictions(data, data_name, k_unstable):
        data = data.join(all_data.set_index('issue_key'), on='issue_key')
        data.to_csv(f'Master/Instability_With_BERT/Data/{jira_name}/{data_name}_{k_unstable}'
                    f'_features_with_bert_instability.csv')

        return data

    return add_bert_predictions


