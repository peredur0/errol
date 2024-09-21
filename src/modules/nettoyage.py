# coding: utf-8
"""
Module pour la gestion des nettoyages dans le programme
"""
import re
import warnings
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def clear_html(texte):
    """ Supprime les balises des textes.
            - html
    :param texte: <str>
    :return: <str>
    """
    with warnings.catch_warnings(record=True) as warn:
        brut = BeautifulSoup(texte, "lxml").text
        if warn:
            logger.warning("%s - %s", warn[-1].category.__name__, warn[-1].message)
    return brut


pattern_enriched = re.compile('<.*>')


def clear_enriched(texte):
    """ Supprime les balises des textes enrichis
    :param texte: <str>
    :return: <str>
    """
    return re.sub(pattern_enriched, '', texte)


def clear_texte_init(texte):
    """ Fonction principale de traitement du texte
    :param texte: <str>
    :return: <str>
    """
    liens = {'URL': 0, 'MAIL': 0, 'TEL': 0, 'NOMBRE': 0, 'PRIX': 0}
    temp = clear_reply(texte)
    temp = change_lien(temp, liens)
    temp = change_nombres(temp, liens)
    temp = clear_ponctuation(temp)

    return temp, liens


def clear_reply(texte):
    """ Supprime les parties correspondantes au mail precedent
    :param texte: <str>
    :return: <str>
    """
    pattern = re.compile('^>.*$', flags=re.MULTILINE)
    return re.sub(pattern, '', texte)


pattern_mail = re.compile('[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+')
pattern_url1 = re.compile(r'(http|ftp|https)?://([\w\-_]+(?:(?:\.[\w\-_]+)+))'
                          r'([\w\-.,@?^=%&:/~+#]*[\w\-@?^=%&/~+#])?', flags=re.MULTILINE)
pattern_url2 = re.compile(r'(\w+\.)+\w+', flags=re.MULTILINE)
pattern_tel1 = re.compile(r'\(\d{3}\)\d+-\d+')  # (359)1234-1000
pattern_tel2 = re.compile(r'\+\d+([ .-]?\d)+')    # +34 936 00 23 23


def change_lien(texte, liens):
    """
    Sauvegarde les liens dans un dictionnaire séparé et les supprime du texte
    :param texte: <str>
    :param liens: <dict> dictionnaire des liens
    :return: <str> - texte nettoyé
    """
    temp, liens['MAIL'] = re.subn(pattern_mail, '', texte)

    temp, liens['URL'] = re.subn(pattern_url1, '', temp)
    temp, nb = re.subn(pattern_url2, '', temp)
    liens['URL'] += nb

    temp, liens['TEL'] = re.subn(pattern_tel1, '', temp)
    temp, nb = re.subn(pattern_tel2, '', temp)
    liens['TEL'] += nb

    return temp


MONNAIE = '$£€'
pattern_prix1 = re.compile(f'[{MONNAIE}]( )?\\d+([.,]\\d+)? ', flags=re.MULTILINE)
pattern_prix2 = re.compile(f' \\d+([.,]\\d+)?( )?[{MONNAIE}]', flags=re.MULTILINE)
pattern_nb = re.compile('\\d+')


def change_nombres(texte, liens):
    """ Retire les données numéraires et stocke le nombre de substitutions
    :param texte: <str>
    :param liens: <dict> dictonnaire des liens
    :return: <str>
    """
    temp, liens['PRIX'] = re.subn(pattern_prix1, '', texte)
    temp, nb = re.subn(pattern_prix2, '', temp)
    liens['PRIX'] += nb

    temp, liens['NOMBRE'] = re.subn(pattern_nb, '', temp)

    return temp


pattern_ponct = re.compile(r'[*#\\-_=:;<>\[\]"~)(|/$+}{@%&\\]', flags=re.MULTILINE)


def clear_ponctuation(texte):
    """
    Supprimer les ponctuations non grammaticales
    :param texte: <str>
    :return: <str>
    """
    return re.sub(pattern_ponct, '', texte)
