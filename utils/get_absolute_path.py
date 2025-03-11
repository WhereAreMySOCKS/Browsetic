import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)


def get_absolute_path(_path):
    return project_root + _path
