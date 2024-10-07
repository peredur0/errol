# coding: utf-8
"""
Fichier pour le développement
"""
import hashlib
import logging
import imaplib
import email
import email.header
import re

import langdetect

from src.modules import importation, cmd_mongo
from src.modules import nettoyage
from src.stages.kaamelott import previous_eval, features_process, nlp_process, vecteur_process, \
    ai_eval

logger = logging.getLogger(__name__)


def move(imap, mail_id, folder):
    """
    Déplace un mail dans un fichier
    :param imap: <imaplib>
    :param mail_id: <byte>
    :param folder: <str>
    """
    status, folders = imap.list()
    if status != 'OK':
        logger.error("Echec de la récupération des dossier imap - %s", status)

    if folder.encode() not in [exist.split()[-1].replace(b'"', b'') for exist in folders]:
        imap.create(folder)
        logger.info("Dossier imap créé - %s", folder)

    imap.copy(mail_id, folder)
    imap.store(mail_id, '+FLAGS', '\\Deleted')
    imap.expunge()
    logger.info("Mail %s déplacé dans %s", mail_id, folder)


def main(conf):
    """
    Fonction principale
    """
    logger.info("DEVELOPPEMENT")
    logger.info("Developping the new feature - %s", conf)

    imap = imaplib.IMAP4_SSL(conf.infra['mail']['imap_srv'], conf.infra['mail']['imap_port'])
    imap.login(conf.infra['mail']['user'], conf.infra['mail']['password'])
    imap.select('inbox')
    status, messages = imap.search(None, "ALL") # todo: UNSEEN for production
    if status != 'OK':
        logger.error("Erreur inattendue lors de la récupération des mails - %s", status)
        return

    to_process = []
    for mail_id in messages[0].split():
        mail_data = preprocess_mail(conf, imap, mail_id)
        if not mail_data:
            continue
        to_process.append(mail_data)
        # move(imap, mail_id, 'Processed') # todo: restore for production

    imap.close()
    imap.logout()

    for mail in to_process:
        if (not mail['target']) or ('errol@mail.fr' in mail['target']['document']['message']):
            continue

        if 'result' in mail['target']:
            logger.warning("Problème survenu lors du traitement de %s - %s",
                           mail['source']['subject'], mail['target']['result'])
            # todo: Répondre au mail
            continue

        direct_mail_eval(conf, mail)
        print(mail)


        # todo: ouvrir un ticket pour le compte de l'expéditeur
        # todo: répondre au mails en précisant le numéro de ticket ouvert et le résultat de l'IA


def preprocess_mail(conf, imap, mail_id):
    """
    Prétraitement de l'email
    :param conf: <Settings>
    :param imap: <imap>
    :param mail_id: <byte>
    :return: <dict>
    """
    dft_lang = 'en'
    status, data = imap.fetch(mail_id, '(RFC822)')
    if status != 'OK':
        logger.error('Echec de récupération du mail %s', mail_id)
        move(imap, mail_id, 'Failed')
        return {}

    mail_data = {'source': {}, 'target': {}}
    mail_data['source']['mail_id'] = mail_id

    for part in data:
        if not isinstance(part, tuple):
            continue

        msg = email.message_from_bytes(part[1])
        mail_data['source']['requester'] = msg.get('From')
        subject, encoding = email.header.decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding if encoding else "utf-8")
        mail_data['source']['subject'] = subject

        body = importation.extract_mail_body(msg)
        if re.search(f'{conf.infra["mail"]["user"]}', body):
            logger.info("Réponse potentielle sur le mail %s", subject)
            move(imap, mail_id, 'Ignore')
            break

        body = importation.keep_forwarded(body)
        msg = importation.format_forwarded(body)

        sujet, expediteur = importation.extract_mail_meta(msg)
        body = importation.extract_mail_body(msg)
        body, liens = nettoyage.clear_texte_init(body)

        if not body:
            logger.warning("Echec de récupération du corps de %s", sujet)
            mail_data['target']['success'] = False
            mail_data['target']['result'] = conf.infra['comments']['empty_body'][dft_lang]
            break

        try:
            lang = langdetect.detect(body).split()[0]
        except langdetect.lang_detect_exception.LangDetectException as err:
            logger.error("Echec de détection de la langue pour %s %s", sujet, err)
            mail_data['target']['success'] = False
            mail_data['target']['result'] = conf.infra['comments']['lang_detect_failed'][dft_lang]
            break

        mail_data['target']['document'] = {
            'hash': hashlib.md5(body.encode()).hexdigest(),
            'sujet': sujet if sujet else 'null',
            'expediteur': expediteur,
            'message': body,
            'langue': lang,
            'liens': liens
        }

    return mail_data


def direct_mail_eval(conf, mail):
    """
    Réaliser l'analyse d'un mail envoyé directement
    :param conf: <Settings>
    :param mail: <dict>
    :return: <None>
    """
    dft_lang = 'en'
    client = cmd_mongo.connect(conf)
    collection = client[conf.infra['mongo']['db']][conf.infra['mongo']['models']]
    models = cmd_mongo.get_all_documents(collection,
                                         d_filter={'langue': mail['target']['document']['langue']})
    client.close()

    if not models:
        logger.warning('Pas de modèle IA disponibles pour %s', mail['source']['subject'])
        mail['target']['success'] = False
        mail['target']['result'] = (f"{mail['target']['document']['hash']} - "
                                    f"{conf.infra['comments']['no_model'][dft_lang]} - "
                                    f"{mail['target']['document']['langue']}")
        return

    models = previous_eval(conf, models, mail['target']['document'], mail['target'])
    if not models:
        logger.info("Aucun nouveau traitement à effectuer pour %s", mail['source']['subject'])
        return

    feats = features_process(mail['target']['document'])
    bag = nlp_process(conf, mail['target']['document'], mail['target'])
    vecteur = vecteur_process(conf, bag, mail['target']['document'], mail['target'])
    if not vecteur:
        mail['target']['success'] = False
        mail['target']['result'] = (f"{mail['target']['document']['hash']} - "
                                    f"{conf.infra['comments']['tfidf_failed'][dft_lang]}")
        return

    ai_eval(models, mail['target']['document'], feats, vecteur, mail['target'], conf=conf)
