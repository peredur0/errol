# coding: utf-8
"""
Fichier pour le développement
"""
import re
import hashlib
import logging
import imaplib
import smtplib
import email
import email.header
import socket
import sys
import requests.exceptions
import langdetect

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from requests.auth import HTTPBasicAuth

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

    try:
        imap = imaplib.IMAP4_SSL(conf.infra['mail']['imap_srv'], conf.infra['mail']['imap_port'])
    except socket.gaierror as err:
        logger.error("Echec de connexino au serveur IMAP - %s", err)
        sys.exit(1)

    try:
        imap.login(conf.infra['mail']['user'], conf.infra['mail']['password'])
    except imaplib.IMAP4.abort as err:
        logger.error('Echec de connexion au serveur IMAP - %s', err)
        sys.exit(1)

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
            reply_mail(conf, mail)
            continue

        direct_mail_eval(conf, mail)
        create_ticket(conf, mail)
        # todo: ouvrir un ticket pour le compte de l'expéditeur
        # todo: répondre au mails en précisant le numéro de ticket ouvert et le résultat de l'IA
        # reply_mail(conf, mail)


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


def reply_mail(conf, mail):
    """
    Répond à un mail
    :param conf: <Settings>
    :param mail: <dict>
    :return: <None>
    """
    dft_lang = 'en'
    body = f"{conf.infra['reply']['header'][dft_lang]}\n\n"
    body += f"{conf.infra['reply']['success'][dft_lang].format(result=mail['target']['success'])}\n"
    body += f"Message id : {mail['target']['document']['hash']}\n"

    if mail['target']['success']:
        model_return = '\n\t'.join([f"{model}\t>\t{pred}"
                                    for model, pred in mail['target']['result'].items()])
        body += f"\n\t{model_return}\n\n"
    else:
        body += f"{mail['target']['result']}\n\n"

    body += f"{conf.infra['reply']['footer'][dft_lang]}\n"

    message = MIMEMultipart()
    message['From'] = conf.infra['mail']['user']
    message['To'] = mail['source']['requester']
    message['Subject'] = f"Re: {mail['source']['subject']}"
    message.attach(MIMEText(body, 'plain'))

    try:
        smtp_srv = smtplib.SMTP(conf.infra['mail']['smtp_srv'], conf.infra['mail']['smtp_port'])
        smtp_srv.starttls()
        smtp_srv.login(conf.infra['mail']['user'], conf.infra['mail']['password'])
        smtp_srv.sendmail(message['From'], message['To'], message.as_string())
        smtp_srv.quit()
        logger.info("Réponse envoyée à %s pour %s", message['To'], message['Subject'])
    except requests.exceptions.ConnectionError as err:
        logger.error("Echec d'envoi du mail - %s", err)


def create_ticket(conf, mail):
    """
    Ajoute un ticket à l'environnement Jira
    :param conf: <Settings>
    :param mail: <dict>
    """
    header = {'Accept': 'application/json'}
    auth = HTTPBasicAuth(conf.infra['jira']['user'], conf.infra['jira']['token'])
    url = conf.infra['jira']['api']['issue']

    if mail['target']['success']:
        display = '\n\t'.join(f"{model}\t>\t{pred}"
                             for model, pred in mail['target']['result'].items())
        display = f"\n\t{display}"
    else:
        display = mail['target']['result']

    description = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "heading",
                "attrs": {
                    "level": 2
                },
                "content": [
                    {
                        "type": "text",
                        "text": mail['source']['subject']
                    }
                ]
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": mail['target']['document']['message']
                    }
                ]
            },
            {
                "type": "rule",
            },
            {
                "type": "heading",
                "attrs": {
                    "level" : 2
                },
                "content": [
                    {
                        "type": "text",
                        "text": "Result"
                    }
                ]
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"Process success status - {mail['target']['success']}\n"
                                f"Message ID - {mail['target']['document']['hash']}\n\n"
                                f"{display}\n\n"
                    }
                ]
            }
        ]
    }
    # todo search ID by mail
    requester_mail = re.search(r'<([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>',
                               mail['source']['requester']).group(1)
    reporter_id = get_jira_id(conf, requester_mail)
    print(reporter_id)
    payload = {
        "fields": {
            "project": {
                "key": conf.infra['jira']['project_key']
            },
            "summary": f"[mail.fr] - {mail['source']['subject']}",
            "description": description,
            "issuetype": {
                "name": "Evaluate"
            },
            "reporter": {
              "id": reporter_id
            },
            "customfield_10048": {"value": "Autoriser"},
            "customfield_10066": requester_mail
        }
    }
    resp = requests.post(url, json=payload, auth=auth, headers=header, timeout=15)
    if resp.status_code != 201:
        logger.error("Echec de création du ticket pour le mail %s - %s %s",
                     mail['source']['subject'], resp.status_code, resp.text)
        return

    mail['target']['jira'] = resp.json()
    logger.info("Ticket %s créé pour %s", mail['target']['jira']['key'],
                mail['source']['subject'])
    return


def get_jira_id(conf, mail):
    """
    Récupère l'id d'un utilisateur via son adresse mail
    :param conf: <Settings>
    :param mail: <str>
    :return: <str>
    """
    header = {'Accept': 'application/json'}
    auth = HTTPBasicAuth(conf.infra['jira']['user'], conf.infra['jira']['token'])
    url = conf.infra['jira']['api']['user_search']

    resp = requests.get(url, headers=header, auth=auth, params={'query': mail}, timeout=15)

    if resp.status_code != 200:
        logger.warning("Echec de récupération de l'identifiant Jira de %s - %s %s", mail,
                       resp.status_code, resp.text)
        return ""

    if not resp.json():
        url = conf.infra['jira']['api']['user_create']
        resp = requests.post(url, headers=header, auth=auth,
                             json= {"displayName": mail, "email": mail}, timeout=15)
        if resp.status_code != 201:
            logger.error('Echec de création du client %s - %s %s', mail, resp.status_code,
                         resp.text)
            return ""
        return resp.json()['accountId']

    return resp.json()[0]['accountId']
