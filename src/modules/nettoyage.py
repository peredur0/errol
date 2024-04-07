# coding: utf-8
"""
Module pour la gestion des nettoyages dans le programme
"""
import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def clear_html(texte):
    """ Supprime les balises des textes.
            - html
    :param texte: <str>
    :return: <str>
    """
    brut = BeautifulSoup(texte, "lxml").text
    return brut


def clear_enriched(texte):
    """ Supprime les balises des textes enrichis
    :param texte: <str>
    :return: <str>
    """
    pattern = re.compile('<.*>')
    return re.sub(pattern, '', texte)
