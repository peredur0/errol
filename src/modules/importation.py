# coding: utf-8
"""
Module pour la gestion des importations dans le programme
"""

import os
import logging
import email
import email.header
import re

from src.modules import nettoyage

logger = logging.getLogger(__name__)


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


def get_text_file(file):
    """
    Récupère le texte d'un fichier
    :param file: <str>
    :return: <str>
    """
    try:
        with open(file, 'r', encoding='utf-8') as f_obj:
            return f_obj.read()
    except UnicodeError as err:
        logger.debug("Fichier %s - %s", file, err)
        return ""


def load_mail(file):
    """
    Lis un fichier dans le format mail
    :param file: <str>
    :return: <EmailMessage>
    """
    with open(file, 'rb') as f_bin:
        return email.message_from_binary_file(f_bin)


def extract_mail_body(msg):
    """ Extraire le corps du mail
    :param msg: <EmailMessage> Mail
    :return: <str>
    """
    refused_charset = ['unknown-8bit', 'default', 'default_charset',
                       'gb2312_charset', 'chinesebig5', 'big5']
    body = ""

    if msg.is_multipart():
        for part in msg.walk():
            if not part.is_multipart():
                body += extract_mail_body(part)
        return body

    if msg.get_content_maintype() != 'text':
        return ""

    if msg.get_content_charset() in refused_charset:
        return ""

    if msg.get_content_subtype() == 'plain':
        payload = msg.get_payload(decode=True)
        body += payload.decode(errors='ignore')

    if msg.get_content_subtype() == 'html':
        payload = msg.get_payload(decode=True)
        body += nettoyage.clear_html(payload.decode(errors='ignore'))

    if msg.get_content_subtype() == 'enriched':
        payload = msg.get_payload(decode=True)
        body += nettoyage.clear_enriched(payload.decode(errors='ignore'))

    return body


def extract_mail_meta(msg):
    """ Extrait les métadonnées d'un message
    :param msg: <EmailMessage>
    :return: <tuple>
    """
    sujet = msg.get('Subject')
    if isinstance(sujet, email.header.Header):
        sujet = email.header.decode_header(sujet)

    if isinstance(sujet, list):
        sujet = sujet[0][0].decode(errors='ignore')

    try:
        expediteur = msg.get('From', 'Inconnu').replace("'", "''")
    except AttributeError:
        data = msg.get('From', 'Inconnu')
        logger.warning("Echec de récupération de l'expéditeur - %s", data)
        expediteur = 'Inconnu'

    if extract := re.search(r"([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+"
                            r"(\.[A-Z|a-z]{2,})+", expediteur):
        expediteur = extract[0]

    return sujet, expediteur
