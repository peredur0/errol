# coding: utf-8
"""
Module pour la gestion des importations dans le programme
"""

import os


def get_files(folder):
    """
    Liste tous les fichiers d'un répertoire
    :param folder: <str>
    :return: <list>
    """
    subdir = [d[0] for d in os.walk(folder)]
    files = []

    for sd in subdir:
        for f in os.listdir(sd):
            x = os.path.join(sd, f)
            if os.path.isfile(x):
                files.append(x)

    return files
