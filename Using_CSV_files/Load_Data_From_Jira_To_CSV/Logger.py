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
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    logger.handlers = []

    if not logger.handlers:  # Avoid duplicate handlers on repeated calls

        file_handler = logging.FileHandler(f"{path}/{name}.log", mode='a')
        formatter = logging.Formatter(
            '%(asctime)s - %(filename)s:%(lineno)d:%(funcName)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.propagate = False  # Important: prevent logs from bubbling up to the root logger

    return logger
