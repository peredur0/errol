# coding: utf-8
"""
Module pour la gestion des transformations dans le programme
"""

import logging

logger = logging.getLogger(__name__)


def create_doc(text, category):
    """
    Créé un document d'une certaine catégorie
    :param text: <str>
    :param category: <str>
    :return: <dict>
    """
    corp =