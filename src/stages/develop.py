# coding: utf-8
"""
Fichier pour le développement
"""
import re
import sys
import math
import hashlib
import os.path
import logging
import tempfile
import json
import joblib
import requests
import langdetect
import stanza
import pandas as pd
from nltk.corpus import stopwords
from requests.auth import HTTPBasicAuth

from src.modules import cmd_psql
from src.modules import cmd_mongo
from src.modules import nettoyage
from src.modules import importation
from src.annexes import zipf
from src.stages.nlp import lemmatise
from src.stages.train import normalize
from src.stages.features import features_ponctuations, features_mots, features_zipf, features_hapax


logger = logging.getLogger(__name__)
logging.getLogger('stanza').setLevel(logging.ERROR)


def main(conf):
    """
    Fonction principale
    """
    logger.info("DEVELOPPEMENT")

    if conf.args['init']:
        logger.info("Mise à jour de la base psql")
        cmd_psql.apply_databases_updates(conf, conf.infra['psql']['schema']['kaamelott'])

    header = {'Accept': 'application/json'}
    auth = HTTPBasicAuth(conf.infra['jira']['user'], conf.infra['jira']['token'])
    url = conf.infra['jira']['api']['search']
    query = {'jql': f'''project = "{conf.infra['jira']['project']}" AND status = New'''}

    resp = requests.request('GET', url, headers=header, params=query, auth=auth, timeout=30)

    if resp.status_code != 200:
        logger.error("Echec de la récupération des tickets - %s %s", resp.status_code, resp.text)
        sys.exit(1)

    issues = resp.json()['issues']
    if not issues:
        logger.info("Aucun ticket à traiter")
        return

    to_process = []
    for issue in issues:
        if t_data:= get_issue_data(conf, issue):
            to_process.append(t_data)

    for ticket in to_process:
        match ticket['ticket_type']:
            case 'Evaluate':
                eval_ticket(ticket, conf)
                post_report(conf, ticket)

            case _:
                logger.warning('Type de ticket inconnu - %s', ticket['ticket_type'])


def get_issue_data(conf, issue):
    """
    Récupère les informations d'un ticket
    :param conf: <Settings>
    :param issue: <dict>
    :return: <dict>
    """
    header = {'Accept': 'application/json'}
    auth = HTTPBasicAuth(conf.infra['jira']['user'], conf.infra['jira']['token'])
    url = issue['self']

    resp = requests.request('GET', url, headers=header, auth=auth, timeout=30)

    if resp.status_code != 200:
        logger.error("Echec de la récupération des tickets - %s %s", resp.status_code, resp.text)
        return None

    data = resp.json()
    extracted_data = {
        'self': data['self'],
        'key': data['key'],
        'ticket_type': data['fields']['issuetype']['name'],
        'reporter': data['fields']['reporter']['emailAddress'],
        'storage_auth': data['fields']['customfield_10048']['value'],
        'attachment': []
    }

    if 'attachment' in data['fields']:
        for attachment in data['fields']['attachment']:
            if attachment['mimeType'] != 'message/rfc822':
                logger.warning('MIME type non supporté - %s %s', attachment['mimeType'],
                               attachment['filename'])
                continue

            extracted_data['attachment'].append({
                'filename': attachment['filename'],
                'content_link': attachment['content']
            })

    return extracted_data

def eval_ticket(ticket, conf):
    """
    Process pour le traitement des demandes d'évaluation.
    :param ticket: <dict>
    :param conf: <Settings>
    :return: <None>
    """
    header = {'Accept': 'application/json'}
    auth = HTTPBasicAuth(conf.infra['jira']['user'], conf.infra['jira']['token'])
    logger.info('Début du traitement du ticket evaluation - %s', ticket['key'])

    if not ticket['attachment']:
        logger.info("Ticket sans attachement valide - %s")
        comment = ("Bonjour,\n"
                   "Merci de nous avoir contacter.\n"
                   "Malheureusement, les pièces jointes fournies ne semblent pas répondre aux "
                   "critères de traitement.\n"
                   "Merci de vérifier que vous nous avez bien transmis des fichiers email au "
                   "format .eml")
        post_reply(conf, ticket['self'], comment, 'Cancel')
        return

    if not os.path.isdir(conf.infra['mails']):
        os.makedirs(conf.infra['mails'])
    tempfile.tempdir = conf.infra['mails']

    logger.debug('Téléchargement des mails de %s', ticket['key'])

    for attached in ticket['attachment']:
        logger.info('%s Traitement - %s', ticket['key'], attached['filename'])
        resp = requests.request('GET', attached['content_link'], auth=auth, headers=header,
                                timeout=30)

        if resp.status_code != 200:
            logger.error(" %s Echec de téléchargement du mail %s - %s %s",
                         ticket['key'], attached['filename'],
                         resp.status_code, resp.text)
            attached['success'] = False
            attached['result'] = "Echec de téléchargement"
            continue

        with tempfile.NamedTemporaryFile(prefix='errol_', suffix='.eml') as tmp_file:
            tmp_file.write(resp.content)
            logger.debug("%s mail téléchargé - %s", ticket['key'],
                         os.path.split(tmp_file.name)[-1])
            attached['tmp_path'] = tmp_file.name
            attachment_eval(conf, ticket['key'], attached)

def attachment_eval(conf, ticket_key, attached):
    """
    Evaluer un mail avec les modèles disponibles.
    :param conf: <Settings>
    :param ticket_key: <dict>
    :param attached: <str>
    :return: <None>
    """
    document = pre_traitement(ticket_key, attached)
    client = cmd_mongo.connect(conf)
    collection = client[conf.infra['mongo']['db']][conf.infra['mongo']['models']]
    models = cmd_mongo.get_all_documents(collection, d_filter={'langue': document['langue']})
    client.close()

    if not models:
        logger.warning('%s - Pas de modèles IA disponible pour %s', ticket_key,
                       attached['filename'])
        attached['success'] = False
        attached['result'] = (f"{document['hash']} - Aucun modèle n'est disponible pour la langue "
                              f"détectée - {document['langue']}")
        return

    attached['hash'] = document['hash']
    models = previous_eval(conf, models, document, attached)
    if not models:
        logger.info('Aucun nouveau traitement à effectuer pour %s', attached['filename'])
        return

    feats = features_process(document, attached)
    bag = nlp_process(document, attached)
    vecteur = vecteur_process(conf, bag, document, attached)
    if not vecteur:
        attached['success'] = False
        attached['result'] = (f"{document['hash']} - La vectorisation tfidf à échoué probablement "
                              f"due à un vecteur vide")
        return

    ai_eval(models, document, feats, vecteur, attached)

def pre_traitement(ticket_key, attached):
    """
    Traitement initial de la pièce jointe
    :param ticket_key: <str>
    :param attached: <dict>
    :return: <dict>
    """
    logger.debug('%s Traitement initial de %s', ticket_key, attached['filename'])
    mail = importation.load_mail(attached['tmp_path'])
    sujet, exp = importation.extract_mail_meta(mail)
    body = importation.extract_mail_body(mail)
    body, liens = nettoyage.clear_texte_init(body)

    if not body:
        logger.warning("Echec de récupération du corps de %s", attached['filename'])
        attached['success'] = False
        attached['result'] = "Echec de récupération du corps de mail - probablement vide"
        return {}

    try:
        lang = langdetect.detect(body).split()[0]
    except langdetect.lang_detect_exception.LangDetectException as err:
        logger.error("Echec de détection de la langue pour %s %s", attached['filename'], err)
        attached['success'] = False
        attached['result'] = "Echec de la détection de la langue"
        return {}

    document = {
        'hash': hashlib.md5(body.encode()).hexdigest(),
        'sujet': sujet if sujet else 'null',
        'expediteur': exp,
        'message': body,
        'langue': lang,
        'liens': liens
    }

    return document

def ai_eval(models, document, feats, vecteur, attached):
    """
    Réalise l'évaluation via les modèles
    :param models: <list>
    :param document: <dict>
    :param feats: <dict>
    :param vecteur: <dict>
    :param attached: <dict>
    """
    logger.info("%s - Evaluation des modèles", attached['filename'])

    logger.debug("Préparations des datasets")
    dataset = vecteur
    dataset.update(feats)
    dataset.update(document['liens'])

    for key in list(dataset.keys()):
        if key == 'nombre_hapax':
            dataset['hapax'] = dataset.pop(key)
            continue
        if key == 'ratio_mots_uniques':
            dataset['hapax_uniques'] = dataset.pop(key)
            continue
        dataset[key.lower()] = dataset.pop(key)

    base_df = pd.DataFrame(dataset, index=[0])
    scaler = None

    for model in models:

        if type(scaler).__name__ != model['scaler']:
            logger.error("La méthode de normalisation ne correspond pas %s <> %s",
                         type(scaler).__name__, model['scaler'])
            attached['success'] = False
            attached['result'] = (f"{document['hash']} - Problème de normalisation avec"
                                  f" {attached['filename']} - contactez l'équipe support")
            continue

        colonne_to_add = {colonne: [0.0]*len(base_df)
                          for colonne in model['colonnes'] if colonne not in base_df}
        colonne_to_add = pd.DataFrame(colonne_to_add)
        tmp_df = pd.concat([base_df, colonne_to_add], axis=1)
        tmp_df = tmp_df[model['colonnes']]

        if scaler is not None:
            normalize(tmp_df, scaler)

        model_bin = joblib.load(model['chemin'])
        prediction = model_bin.predict(tmp_df)[0]

        if 'result' not in attached:
            attached['result'] = {}

        attached['success'] = True
        attached['result'][model['name']] = 'ham' if prediction == model['ham_id'] else 'spam'
        logger.info('%s %s %s > %s', model['name'], attached['filename'],
                    document['hash'], attached['result'][model['name']])

def previous_eval(conf, models, document, attached):
    """
    Vérifie la présence d'évaluation précédente pour ce document
    :param conf: <Settings>
    :param models: <list>
    :param document: <dict>
    :param attached: <dict>
    :return: <list>
    """
    client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])
    id_message = cmd_psql.get_unique_data(client, 'kaamelott_messages', 'id_message',
                                          f"hash LIKE '{document['hash']}'")

    if not id_message:
        logger.debug("Message %s non présent en base", attached['filename'])
        return models

    eval_table = 'kaamelott_mail_eval'
    to_process = []
    for model in models:
        clause = (f"id_message = {id_message} AND model_name LIKE '{model['name']}' "
                  f"AND langue LIKE '{model['langue']}'")
        eval_ts = cmd_psql.get_unique_data(client, eval_table, 'eval_timestamp', clause)
        if (not eval_ts) or (eval_ts < model['creation']):
            to_process.append(model)
            continue

        attached['success'] = True
        if 'result' not in attached:
            attached['result'] = {}
        attached['result'][model['name']] = cmd_psql.get_unique_data(client, eval_table, 'result',
                                                                  clause)

    client.close()
    return to_process

def vecteur_process(conf, bag, document, attached):
    """
    Vectorise le document avec la méthode tfidf
    :param conf: <Settings>
    :param bag: <dict>
    :param document: <dict>
    :param attached: <dict>
    :return: <dict>
    """
    logger.info("%s - Vectorisation", attached['filename'])
    client_psql = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                      passwd=conf.infra['psql']['pass'],
                                      host=conf.infra['psql']['host'],
                                      port=conf.infra['psql']['port'],
                                      dbname=conf.infra['psql']['db'])
    with open(conf.infra['psql']['queries'], 'r', encoding='utf-8') as file:
        queries = json.load(file)

    total_docs = cmd_psql.exec_query(client_psql, queries['check_nb_docs'].format(
        langue=document['langue']))[0][0]

    vecteur = {}
    for mot, occurrence in bag.items():
        data = cmd_psql.exec_query(client_psql, queries['check_label'].format(
            mot=mot, algo='tfidf', langue=document['langue']))
        if not data:
            continue
        label, freq_doc = data[0]
        vecteur[label] = occurrence * math.log(total_docs / freq_doc)
    client_psql.close()

    if not vecteur:
        logger.error("Vecteur null pour le message %s", attached['filename'])

    return vecteur

def nlp_process(document, attached):
    """
    Traitement NLP de la pièce jointe
    :param document: <dict>
    :param attached: <dict>
    :return: <dict>
    """
    logger.info("%s -Traitement du langage naturel", attached['filename'])
    match document['langue']:
        case 'en':
            stopw = set(stopwords.words('english'))
        case 'fr':
            stopw = set(stopwords.words('french'))
        case _:
            logger.info("Langue détectée non supportée - %s", document['langue'])
            attached['success'] = False
            attached['result'] = (f"{document['hash']} - Pas de processus du langage naturel pour "
                                  f"{document['langue']}")
            return None

    pattern = re.compile(r'\w+')
    stz_pipe = stanza.Pipeline(lang=document['langue'], processors='tokenize,mwt,pos,lemma')
    bag = zipf.freq_mot(lemmatise(document['message'], stopw, stz_pipe, pattern))

    return bag

def features_process(document, attached):
    """
    Récupération des caractéristiques
    :param document: <dict>
    :param attached: <dict>
    :return: <dict>
    """
    logger.info("%s - Recherche des caractéristiques", attached['filename'])
    feats = {}
    for fonction in [features_ponctuations, features_mots, features_zipf, features_hapax]:
        feats.update(fonction(document['message']))
    return feats


def post_reply(conf, ticket, comment, transition=None):
    """
    Poste une réponse dans le ticket et change le status
    :param conf: <Settings>
    :param ticket: <dict>
    :param comment: <str>
    :param transition: <str>
    """
    header = {'Accept': 'application/json'}
    auth = HTTPBasicAuth(conf.infra['jira']['user'], conf.infra['jira']['token'])
    url = f"{ticket['self']}/comment"
    comment = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                'type': 'paragraph',
                'content': [
                    {'type': 'text', 'text': comment}
                ]
            }
        ]
    }
    body = {'body': comment}
    resp = requests.request('post', url, headers=header, auth=auth, json=body, timeout=30)

    if resp.status_code != 201:
        logger.error('Echec de post du commentaire pour %s - %s %s', ticket['key'],
                     resp.status_code, resp.text)
        return
    logger.info("%s Commentaire posté sur le ticket", ticket['key'])

    if not transition:
        return

    url = f"{ticket['self']}/transitions"
    resp = requests.request('GET', url, auth=auth, headers=header, timeout=30)
    if resp.status_code != 200:
        logger.error("Echec de la récupération de l'id de transition - %s %s",
                     resp.status_code, resp.text)
        return

    status_id = None
    for state in resp.json()['transitions']:
        if state['name'].lower() == transition.lower():
            status_id = state['id']
            break

    if not status_id:
        logger.error("L'état souhaité ne possède pas d'id, vérifier le workflow - %s", transition)
        return

    data = {
        'transition': {'id': status_id},
    }

    resp = requests.request('POST', url, headers=header, auth=auth, json=data, timeout=30)
    if resp.status_code != 204:
        logger.error("Echec de réponse au ticket %s - %s %s", ticket['key'], resp.status_code,
                     resp.text)
        return

    logger.info("%s Nouvel état pour le ticket- %s", ticket['key'], transition)


def post_report(conf, ticket):
    """
    Prépare et poste le retour de l'analyse.
    :param conf: <Settings>
    :param ticket: <dict>
    """
    comment = "Résultat des évaluations:\n"
    for attached in ticket['attachment']:
        tmp_cmt = f"\n{attached['filename']} - "
        if not attached['success']:
            tmp_cmt += attached['result']
        else:
            tmp_cmt += f"{attached['hash']}\n\t"
            tmp_cmt += '\n\t'.join([f"{model} > {pred}"
                                    for model, pred in attached['result'].items()])
        comment += f"{tmp_cmt}\n"

    comment += ("\n\n"
                "rtf = Random Tree Forest, svm = Support Vector Machine\n\n"
                "Merci pour votre confiance.\n"
                "Pensez à vérifier le résultat de ces analyses - Les modèles peuvent se tromper.\n")

    post_reply(conf, ticket, comment, 'Traité')
