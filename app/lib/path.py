import os


def get_app_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def get_data_path():
    return os.path.join(get_app_path(), 'data')
