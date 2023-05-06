import re
import pandas as pd
import numpy as np
from textblob import Word
from textblob import TextBlob
from nltk.corpus import stopwords
from nltk.tokenize import RegexpTokenizer
from nltk.stem.porter import PorterStemmer
from nltk.stem import WordNetLemmatizer
import warnings
warnings.filterwarnings(action='ignore', category=UserWarning, module='gensim')
import nltk
from string import punctuation


"""
    this function get the text field and the project name, and clean the text from unwanted signs
    output: the clean text
"""
def clean_text2(text2, project_key):
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

"""
    this function get the text field and the project name, and clean the text from unwanted headlines signs
    output: the clean text
"""
def return_text_without_headlines(text):
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


def check_if_in_head(name_head, headlines_list):
    """
    function that return 1 if the text contain headline, 0 else
    """
    try:
        headlines_list = headlines_list()
        if name_head in headlines_list:
            is_headline = 1
        else:
            is_headline = 0
        return is_headline

    except Exception as e:
        return 0


def clean_text(text):
    """
    this function get the text field and the project name, and clean the text from unwanted signs
    output: the clean text
    """
    text = text.replace('\\n', '\n')
    text = text.replace('\\r', '\r')
    text = text.replace('\\t', '\t')
    text = text.replace('\n', " ")
    text = text.replace('\r', " ")
    text = text.replace('\t', " ")
    text = ' '.join(text.split())
    return text


def get_headlines(issue_description2):
    """ function gets description, split it by the headlines and return list of headlines in this description
    :param issue_description:
    :return: list of headlines
    """
    heads = []
    issue_description = issue_description2
    if issue_description is not None:
        issue_description = issue_description.replace('\\n', '\n')
        issue_description = issue_description.replace('\\r', '\r')
        info_description_changes = issue_description.split('\n')
        for index, value in enumerate(info_description_changes):
            result = re.search('h1. (.*)\r', value)
            if result is not None:
                heads.append(clean_text(result.group(1)).replace(":", "").lower())
            result = re.search('h2. (.*)\r', value)
            if result is not None:
                heads.append(clean_text(result.group(1)).replace(":", "").lower())
            else:
                result = re.search('h2. (.*)', value)
                if result is not None:
                    heads.append(clean_text(result.group(1)).replace(":", "").lower())
            result = re.search('h3. (.*)\r', value)
            if result is not None:
                heads.append(clean_text(result.group(1)).replace(":", "").lower())
            result = re.search('h4. (.*)\r', value)
            if result is not None:
                heads.append(clean_text(result.group(1)).replace(":", "").lower())
            if value is not None:
                if '*story*' in value.lower() or '*story:*' in value.lower():
                    heads.append('story')
                if '*acceptance criteria*' in value.lower() or '*acceptance criteria:*' in value.lower():
                    heads.append('acceptance criteria')
                if '*requirements*' in value.lower() or '*requirements:*' in value.lower():
                    heads.append('requirements')
                if '*definition of done*' in value.lower() or '*definition of done:*' in value.lower():
                    heads.append('definition of done')
                if '*design*' in value.lower() or '*design:*' in value.lower():
                    heads.append('design')
                if '*stakeholders*' in value.lower() or '*stakeholders:*' in value.lower():
                    heads.append('stakeholders')
                if '*review steps*' in value.lower() or '*review steps:*' in value.lower():
                    heads.append('review steps')
                if '*questions*' in value.lower() or '*questions:*' in value.lower():
                    heads.append('questions')
                if '*implementation notes*' in value.lower() or '*implementation notes:*' in value.lower():
                    heads.append('implementation notes')
                if '*notes*' in value.lower() or '*notes:*' in value.lower():
                    heads.append('notes')

    return heads

def check_if_has_code(text):
    """
    this function get the text field, and return 1 if the text contains code, 0 else
    """
    text1 = re.sub(r"'''.*'''", "code", text)
    text2 = re.sub(r"{{code}}.*{{code}}", "code", text)
    text3 = re.sub(r"{code.*{code}", "code", text)
    text4 = re.sub(r"{noformat}.*{noformat}", "code", text)
    text5 = re.sub(r'<script type="text/javascript">.*</noscript>', 'code', text)
    text6 = re.sub(r"{code:java}.*{code:java}", "code", text)
    if text == text1 == text2 == text3 == text4 == text5 == text6:
        return 0
    else:
        return 1


def check_if_has_date(text):
    """
    this function get the text field, and return 1 if the text contains dates, 0 else
    """
    text1 = re.sub(r'(\w{3,4,5})-(\d{1,2})-(\d{4})', 'date', text)
    text2 = re.sub(r'(\d{1,2})/(\d{1,2})/(\d{4})', 'date', text)
    text3 = re.sub(r'(\w{3}). (\d{1,2}), (\d{4})', 'date', text)
    text4 = re.sub(r'(\w{3}). (\d{1,2}) (\d{4})', 'date', text)
    text5 = re.sub(r'(\w{4})-(\d{1,2})-(\d{1,2}) ', 'date', text)
    text6 = re.sub(r'&lt;= Today’s Date AND', 'date', text)
    text7 = re.sub(r'yyyy-mm-dd', 'date', text)
    if text == text1 == text2 == text3 == text4 == text5 == text6 == text7:
        return 0
    else:
        return 1


def check_if_has_url(text):
    """
    this function get the text field, and return 1 if the text contains url address, 0 else
    """
    text1 = re.sub(r"<a href=.*</a>", "url ", text)
    text2 = re.sub(r"http\S+", "url ", text)
    text3 = re.sub(r"hdfs://\S+", "url ", text)
    text4 = re.sub(r"tcp://\S+", "url ", text)
    text5 = re.sub(r"webhdfs://\S+", "url ", text)
    text6 = re.sub(r":/\S+", "url ", text)
    text7 = re.sub(r"\S+.com ", "url ", text)
    if text == text1 == text2 == text3 == text4 == text5 == text6 == text7:
        return 0
    else:
        return 1


def get_priority(priority, project_k):
    """
    this function return the priority number of the USI
    """

    if priority == 'Nice to have':
        return 1
    elif priority == 'Important':
        return 4
    elif priority == 'Urgent':
        return 5
    elif priority == 'Minor':
        return 2
    elif priority == 'Trivial':
        return 3
    elif priority == 'Major':
        return 4
    elif priority == 'Blocker':
        return 6
    elif priority == 'Critical':
        return 5
    else:
        # 'Undefined' or empty
        return 0



def check_if_has_template(description):
    """
    the function get the description and return if it contains the template as a, I want so that,
    :param description:
    :return: true if has, false if not
    """
    try:
        if description is not None:
            description = description.replace("*Story*: \r\n", "")
            description = description.replace("*Story*: ", "")
            description = description.replace("*Story*:\r\n", "")
            description = description.replace("*Story*:", "")
            description = description.replace("*Story:* \r\n", "")
            description = description.replace("*Story:* ", "")
            description = description.replace("*Story:*\r\n", "")
            description = description.replace("*Story:*", "")
            description = description.replace("*Story* \r\n", "")
            description = description.replace("*Story* ", "")
            description = description.replace("*Story*\r\n", "")
            description = description.replace("*Story*", "")
            description = re.sub(r'<.+?>', "", description)
            description = re.sub(r'h2.+?\r\n', "", description)
            if description.startswith('as a minimum'):
                return 0
            if description.lower().startswith('as a') or description.lower().startswith('as an') or \
                description.lower().startswith('<p>as a ') or description.lower().startswith('scenario:\r\nas a') or \
                description.lower().startswith('scenario:\r\n\r\nas a') or \
                description.lower().startswith('scenario:\r\nas release stakeholder') or \
                description.lower().startswith('h3. as a') or description.lower().startswith('h3.  narrative\nas a') \
                    or description.lower().startswith('h2. narrative\nas a'):
                return 1
    except TypeError:
        return 0
    except Exception as e:
        return 0
    return 0


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


def avg_word(text):
    words = text.split()
    try:
        average = sum(len(word) for word in words) / len(words)
    except ZeroDivisionError:
        average = 0
    return average


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


def list_num_word_in_sen(text):
    """
    this function return the number of words in the sentence
    """
    sentences = nltk.tokenize.sent_tokenize(text)
    sentences = [sent for sent in sentences if len(sent.split()) > 1]
    list_num_word_in_sen = list(
        map(lambda x: len([word for word in nltk.tokenize.word_tokenize(x) if word.isalnum()]), sentences))
    try:
        avg_num_word_in_sentence = sum(list_num_word_in_sen) / float(len(list_num_word_in_sen))
    except ZeroDivisionError:
        avg_num_word_in_sentence = 0

    return avg_num_word_in_sentence


def is_description_empty_tbd(text):
    """
    this function return 1 if the description is empty, 0 else
    """
    try:
        if text == 'TBD' or text == 'TODO' or text == '<p>TBD</p>\r\n' or text == '<p>c</p>\r\n' or \
                text == '<p>...</p>\r\n' or text is None or text.lower() == 'tbd' or text.lower() == 'todo':
            return 1
        else:
            return 0
    except Exception as e:
        return 0


def is_acceptance_empty_tbd(text):
    """
    this function return 1 if the acceptance criteria is empty, 0 else
    """
    if type(text) is not str:
        return 0

    if text == 'TBD' or text == 'TBD - Placeholder\n\n' or text == '\r\n\r\n' or text == '.\r\n' or text == '- a' or \
            text == '/' or text == '.' or text == '-' or text == '..' or text == '--' or text == '...' or text == 'NA' \
            or text == '?' or text is None or text.lower() == 'tbd':
        return 1
    else:
        return 0


def len_description(text):
    try:
        if text is None:
            return 0
        else:
            return len(text)
    except Exception as e:
        return 0

def create_feature_data(data, text_type, project_key):
    nltk.download('punkt')
    """
    this function get the data and add it features that we can extract from the text, by the help of the functions that details above
    """
    stop = stopwords.words('english')
    features_data = pd.DataFrame()
    data['{}'.format(text_type)] = data['{}'.format(text_type)].apply(lambda x: x.replace(' $end$', "."))
    data['{}'.format(text_type)] = data['{}'.format(text_type)].apply(
        lambda x: x.replace(' $acceptance criteria:$', "."))

    data['num_headlines'] = data['{}'.format(text_type)].apply(lambda x: len(get_headlines(x)))
    features_data['num_headlines'] = data['num_headlines']

    features_data['issue_key'] = data['issue_key'].copy()
    features_data['has_code'] = data['{}'.format(text_type)].apply(lambda x: check_if_has_code(x))
    features_data['has_url'] = data['{}'.format(text_type)].apply(lambda x: check_if_has_url(x))
    features_data['num_question_marks'] = data['{}'.format(text_type)].apply(lambda x: x.count("?"))
    features_data['created'] = data['created'].copy()
    data['clean_text'] = data.apply(lambda x: clean_text2(x['{}'.format(text_type)], x['project_key']), axis=1)
    features_data['has_template'] = data['original_description_sprint'].apply(lambda x: check_if_has_template(x))
    features_data['len_sum_desc'] = data['clean_text'].apply(lambda x: len(x))
    features_data['num_sentences'] = data['clean_text'].apply(
        lambda x: len([sent for sent in nltk.tokenize.sent_tokenize(x) if len(sent.split()) > 1]))
    features_data['num_words'] = data['clean_text'].apply(
        lambda x: len([word for word in nltk.tokenize.word_tokenize(x) if word.isalnum()]))

    features_data['has_acceptance_criteria'] = data['original_description_sprint'].apply(
        lambda x: check_if_in_head('acceptance criteria', lambda:get_headlines(x)))

    features_data['if_acceptance_empty_tbd'] = data['original_acceptance_criteria_sprint'].apply(
         lambda x: is_acceptance_empty_tbd(x))

    features_data['len_acceptance'] = data['original_acceptance_criteria_sprint'].apply(
            lambda x: len_description(x))

    features_data['avg_word_len'] = data['clean_text'].apply(lambda x: avg_word(x))
    features_data['avg_num_word_in_sentence'] = data['clean_text'].apply(lambda x: list_num_word_in_sen(x))
    features_data['has_tbd'] = data['{}'.format(text_type)].apply(lambda x: 1 if (x.lower().count("tbd") or
                                                                                  x.lower().count("todo")) > 0 else 0)
    features_data['has_please'] = data['{}'.format(text_type)].apply(
        lambda x: 1 if x.lower().count("please") > 0 else 0)
    features_data['len_description'] = data['original_description_sprint'].apply(lambda x: len_description(x))
    features_data['if_description_empty_tbd'] = data['original_description_sprint'].apply(
        lambda x: is_description_empty_tbd(x))
    features_data['num_stopwords'] = data['clean_text'].apply(lambda x: len([x for x in x.split() if x in stop]))
    features_data['num_issues_cretor_prev'] = data['num_issues_cretor_prev'].copy()

    features_data['priority'] = data.apply(lambda x: get_priority(x['priority'], x['project_key']), axis=1)

    features_data['num_comments_before_sprint'] = data['num_comments_before_sprint'].copy()
    features_data['num_changes_text_before_sprint'] = data['num_changes_text_before_sprint'].copy()
    features_data['num_changes_story_point_before_sprint'] = data['num_changes_story_point_before_sprint'].copy()
    features_data['original_story_points_sprint'] = data['original_story_points_sprint'].apply(
        lambda x: x if x == x else -1)
    features_data['time_until_add_sprint'] = data['time_until_add_to_sprint'].copy()
    features_data['noun_count'] = data['clean_text'].apply(lambda x: check_pos_tag(x, 'noun'))
    features_data['verb_count'] = data['clean_text'].apply(lambda x: check_pos_tag(x, 'verb'))
    features_data['adj_count'] = data['clean_text'].apply(lambda x: check_pos_tag(x, 'adj'))
    features_data['adv_count'] = data['clean_text'].apply(lambda x: check_pos_tag(x, 'adv'))
    features_data['pron_count'] = data['clean_text'].apply(lambda x: check_pos_tag(x, 'pron'))
    features_data['block'] = data['block']
    features_data['block_by'] = data['block_by']
    features_data['duplicate'] = data['duplicate']
    features_data['relates'] = data['relates']
    features_data['duplicate_by'] = data['duplicate_by']

    basic_pre_processing(data)

    return features_data
