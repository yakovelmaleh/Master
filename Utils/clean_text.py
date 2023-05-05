import re
import pandas as pd
import numpy as np
from textblob import Word
from textblob import TextBlob
from nltk.corpus import stopwords
from nltk.tokenize import RegexpTokenizer
from nltk.stem.porter import PorterStemmer
from nltk.stem import WordNetLemmatizer
import nltk
import warnings
warnings.filterwarnings(action='ignore', category=UserWarning, module='gensim')

nltk.download('stopwords')
nltk.download('omw-1.4')


def clean_text(text2, project_key):
    """
    this function get the text field and the project name, and clean the text from unwanted signs
    output: the clean text
    """

    text = text2
    text = return_text_without_headlines(text)
    # remove text written between double curly braces
    text = re.sub(r"{{code}}.*{{code}}", "code.", text)
    text = re.sub(r"{code.*{code}", "code.", text)
    text = re.sub(r"{code:java}.*{code:java}", "code.", text)
    text = re.sub(r"{noformat}.*{noformat}", "code.", text)
    text = re.sub(r"{{monospaced}}.*{{monospaced}}", "code.", text)
    text = re.sub(r'<script type="text/javascript">.*</noscript>', 'code.', text)
    text = re.sub(r"'''.*'''", "code", text)
    text = text.replace('<p>&nbsp;</p>', "")
    text = text.replace('<div>&nbsp;</div>', "")
    text = text.replace('&nbsp;', " ")
    # remove URLs link
    text = re.sub(r"<a href=.*</a>", "url. ", text)
    text = re.sub(r"http\S+", "url. ", text)
    text = re.sub(r"hdfs://\S+", "url. ", text)
    text = re.sub(r"tcp://\S+", "url. ", text)
    text = re.sub(r"webhdfs://\S+", "url. ", text)
    text = re.sub(r":/\S+", "url. ", text)
    text = re.sub(r"\S+.com ", "url. ", text)
    text = re.sub(r"N/A]", " ", text)
    text = " ".join(x for x in text.split() if not x.endswith('.com'))
    text = " ".join(x for x in text.split() if not x.endswith('.com*'))
    text = " ".join(x for x in text.split() if not x.endswith('.org'))
    text = " ".join(x for x in text.split() if not x.endswith('.xml'))
    text = " ".join(x for x in text.split() if not x.startswith('*javax.xml.'))
    text = " ".join(x for x in text.split() if not x.startswith('javax.xml.'))
    # remove Image attachments
    text = re.sub(r"<p><img alt=.></p>", "image.", text)
    text = re.sub(r"{}-\d+".format(project_key), "issue", text)
    # remove date
    text = re.sub(r'(\w{4})-(\d{1,2})-(\d{1,2}) ', 'date.', text)
    text = re.sub(r'(\w{3,4,5})-(\d{1,2})-(\d{4})', 'date.', text)
    text = re.sub(r'(\d{1,2})/(\d{1,2})/(\d{4})', 'date.', text)
    text = re.sub(r'(\w{3}). (\d{1,2}), (\d{4})', 'date.', text)
    text = re.sub(r'(\w{3}). (\d{1,2}) (\d{4})', 'date.', text)
    text = re.sub(r'&lt;= Today’s Date AND', 'date.', text)
    text = re.sub(r'yyyy-mm-dd', 'date', text)
    # remove text written between small braces
    text = re.sub(r'<.+?>', "", text)
    text = text.replace("e.g.,", " ")
    text = text.replace("e.g.", " ")
    text = text.replace("i.e.,", " ")
    text = text.replace("i.e.", " ")
    # replace non-breaking space with regular space
    text = text.replace(u'\xa0', u' ')
    # replace all punctuations with space
    text = text.replace('-->', " ")
    text = text.replace('--', " ")
    text = text.replace('-', " ")
    text = text.replace('/', " ")
    text = text.replace('&amp;', " ")
    text = text.replace(' * ', ". ")
    text = re.sub(r"\"|\#|\“|\*|\'|\]|\^|\`|\(|\)|\~", "", text)
    text = re.sub(r"\"|\$|\%|\&|\/|\|\=|\>|\<|\@|\[|\\|\]|\{|\||\}", " ", text)
    text = text.replace('$', "")
    text = text.replace('?', ".")
    text = text.replace('+', " ")
    text = re.sub(r" \d\.\d\.N ", " ", text)
    text = re.sub(r" \d\.\d\.b.", " ", text)
    text = re.sub(r" \d\.\d\.b ", " ", text)
    text = re.sub(r"\d\.\d\.N", " ", text)
    text = re.sub(r"\d\.\d\.X", " ", text)
    text = re.sub(r"v\d\.\d\.\d+", " ", text)
    text = re.sub(r"V\d\.\d\.\d+", " ", text)
    text = re.sub(r"v\d\.\d+", " ", text)
    text = re.sub(r"V\d\.\d+", " ", text)
    text = re.sub(r"\d\.\d+", " ", text)
    text = re.sub(r"\d\.\d\.\d+", " ", text)
    text = text.replace("V1", " ")
    text = text.replace("v1", " ")
    # remove digits from text
    text = re.sub(r"\d+", "", text)
    text = text.replace('lt;=', " ")
    text = text.replace('.!', ".")
    text = text.replace('!.', ".")
    text = text.replace('!', ".")
    text = text.replace('... ', ". ")
    text = text.replace('.. ', ". ")
    text = text.replace('..', ".")
    text = text.replace('. . . ', ". ")
    text = text.replace('. . ', ". ")
    text = text.replace('. . ', ". ")
    text = text.replace(' .', ".")
    text = text.replace('. . ', ". ")
    text = text.replace('. . ', ". ")
    text = text.replace(':.', ".")
    text = text.replace(' :', " ")
    text = text.lower()
    text = text.replace('..', ".")
    text = ' '.join(text.split())

    return text


def return_text_without_headlines(text):
    """
    this function get the text field and the project name, and clean the text from unwanted headlines signs
    output: the clean text
    """

    text = text.replace('\\n', '\n')
    text = text.replace('\\r', '\r')
    text = re.sub('h1. (.*)\r', '', text)
    text = re.sub('h2. (.*)\r', '', text)
    text = re.sub('h2. (.*)', '', text)
    text = re.sub('h3. (.*)\r', '', text)
    text = re.sub('h4. (.*)\r', '', text)
    text = text.replace('*acceptance criteria:*', "")
    text = text.replace('*acceptance criteria*:', "")
    text = text.replace('*acceptance criteria*', "")
    text = text.replace('*story:*', "")
    text = text.replace('*story*:', "")
    text = text.replace('*story*', "")
    text = text.replace('*stories:*', "")
    text = text.replace('*questions:*', "")
    text = text.replace('*questions*:', "")
    text = text.replace('*questions*', "")
    text = text.replace('*implementation notes:*', "")
    text = text.replace('*implementation notes*:', "")
    text = text.replace('*implementation notes*', "")
    text = text.replace('*notes:*', "")
    text = text.replace('*notes*:', "")
    text = text.replace('*notes*', "")
    text = text.replace('*Acceptance Criteria:*', "")
    text = text.replace('*Acceptance Criteria*:', "")
    text = text.replace('*Acceptance Criteria*', "")
    text = text.replace('*Story:*', "")
    text = text.replace('*Story*:', "")
    text = text.replace('*Story*', "")
    text = text.replace('*Stories:*', "")
    text = text.replace('*Questions:*', "")
    text = text.replace('*Questions*:', "")
    text = text.replace('*Questions*', "")
    text = text.replace('*Implementation Notes:*', "")
    text = text.replace('*Implementation Notes*:', "")
    text = text.replace('*Implementation Notes*', "")
    text = text.replace('*Notes:*', "")
    text = text.replace('*Notes*:', "")
    text = text.replace('*Notes*', "")
    text = text.replace('*Acceptance criteria:*', "")
    text = text.replace('*Acceptance criteria*:', "")
    text = text.replace('*Acceptance criteria*', "")
    text = text.replace('*Implementation notes:*', "")
    text = text.replace('*Implementation notes*:', "")
    text = text.replace('*Implementation notes*', "")
    text = text.replace('*Acceptance Criteria:*', "")
    text = text.replace('*Acceptance Criteria*:', "")
    text = text.replace('*Acceptance Criteria*', "")
    text = text.replace('*Implementation Notes:*', "")
    text = text.replace('*Implementation Notes*:', "")
    text = text.replace('*Implementation Notes*', "")
    text = text.replace(':\r\n****', " ")
    text = text.replace('\r\n****', ". ")
    text = text.replace(':\n****', " ")
    text = text.replace('\n****', ". ")
    text = text.replace(':\r\n***', " ")
    text = text.replace('\r\n***', ". ")
    text = text.replace(':\n***', " ")
    text = text.replace('\n***', ". ")
    text = text.replace(':\r\n**', " ")
    text = text.replace('\r\n**', ". ")
    text = text.replace(':\n**', " ")
    text = text.replace('\n**', ". ")
    text = text.replace(':\r\n*', " ")
    text = text.replace('\r\n*', ". ")
    text = text.replace(':\n*', " ")
    text = text.replace('\n*', ". ")
    text = text.replace(':\r\n\r\n', " ")
    text = text.replace('\r\n\r\n', ". ")
    text = text.replace(':\r\n', " ")
    text = text.replace('\r\n', ". ")
    text = text.replace('.\n', ". ")
    text = text.replace('\n', " ")
    text = text.replace('.\r', ". ")
    text = text.replace('\r', " ")
    text = text.replace('\\n', '\n')
    text = text.replace('\\t', '\t')
    text = text.replace('\\r', '\r')
    text = text.replace('\n', " ")
    text = text.replace('\r', " ")
    text = text.replace('\t', " ")
    text = ' '.join(text.split())
    return text


# function to check and get the part of speech tag count of a words in a given sentence
def check_pos_tag(x, flag):
    pos_family = {'noun': ['NN', 'NNS', 'NNP', 'NNPS'], 'pron': ['PRP', 'PRP$', 'WP', 'WP$'],
                  'verb': ['VB', 'VBD', 'VBG', 'VBN', 'VBP', 'VBZ'], 'adj': ['JJ', 'JJR', 'JJS'],
                  'adv': ['RB', 'RBR', 'RBS', 'WRB']}
    cnt = 0
    try:
        text = nltk.word_tokenize(x)
        pos = nltk.pos_tag(text)
        for k, v in pos:
            if v in pos_family[flag]:
                cnt += 1
    except:
        pass
    return cnt



def basic_pre_processing(data):
    # function which is doing preprocess to the text field and create clean text field
    stop = stopwords.words('english')
    # Removing Punctuation
    data['clean_text_new'] = data['clean_text']
    # Removal of Stop Words
    data['clean_text_new'] = data['clean_text_new'].apply(lambda x: " ".join(x for x in x.split() if x not in stop))
    # filter out short tokens
    data['clean_text_new'] = data['clean_text_new'].apply(lambda x: " ".join(x for x in x.split() if len(x) > 1))
    # filter out long tokens
    data['clean_text_new'] = data['clean_text_new'].apply(lambda x: " ".join(x for x in x.split() if len(x) < 20))
    # Lemmatization
    data['clean_text_new'] = data['clean_text_new'].apply(lambda x: x.lower())
    data['clean_text_new'] = data['clean_text_new'].apply(
        lambda x: " ".join([Word(word).lemmatize() for word in x.split()]))
    # initialize regex tokenizer
    tokenizer = RegexpTokenizer(r'\w+')
    data['clean_text_new'] = data['clean_text_new'].apply(lambda x: tokenizer.tokenize(x))
    data['clean_text_new'] = data['clean_text_new'].apply(lambda x: [a for a in x if len(a) > 1])


def create_clean_text(data, text_type):
    """
    this function run all the cleaning text function that details above
    """
    stop = stopwords.words('english')
    data['{}'.format(text_type)] = data['{}'.format(text_type)].apply(lambda x: x.replace(' $end$', "."))
    data['{}'.format(text_type)] = data['{}'.format(text_type)].apply(
        lambda x: x.replace(' $acceptance criteria:$', "."))
    data['clean_text'] = data.apply(lambda x: clean_text(x['{}'.format(text_type)], x['project_key']), axis=1)
    basic_pre_processing(data)


