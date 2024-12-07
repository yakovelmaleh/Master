import logging


def get_logger():
    logger = logging.getLogger()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(filename)s:%(lineno)d:%(funcName)s - %(levelname)s - %(message)s',
                        filename=f'Master\\Using_CSV_files\\app.log',  # Specify the filename
                        filemode='a')
    return logger


def get_logger_with_path(path):
    logger = logging.getLogger()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(filename)s:%(lineno)d:%(funcName)s - %(levelname)s - %(message)s',
                        filename=f'{path}/app.log',  # Specify the filename
                        filemode='a')
    return logger


def get_logger_with_path_and_name(path, name):
    logger = logging.getLogger()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(filename)s:%(lineno)d:%(funcName)s - %(levelname)s - %(message)s',
                        filename=f'{path}/{name}.log',  # Specify the filename
                        filemode='a')
    return logger
