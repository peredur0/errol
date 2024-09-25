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
import datetime
import warnings

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

warnings.filterwarnings("ignore", category=FutureWarning)

def main(conf):
    """
    Fonction principale
    """
    logger.info("Traitement automatique des tickets Jira")

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
                eval_ticket(conf, ticket)
                post_eval_report(conf, ticket)
                save_results(conf, ticket)
                save_mail(conf, ticket)

            case 'Populate':
                eval_ticket(conf, ticket)
                save_mail(conf, ticket)
                post_populate_report(conf, ticket)

            case 'Remove':
                suppression_ticket(conf, ticket)
                post_reply(conf, ticket, "Opération de suppression effectuée", "Fermeture")

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
        'attachment': [],
        'storage_auth': 'Autoriser',
        'categorie': 'Inconnu'
    }

    if data['fields']['customfield_10048']:
        extracted_data['storage_auth'] = data['fields']['customfield_10048']['value']

    if data['fields']['customfield_10050']:
        extracted_data['categorie'] = data['fields']['customfield_10050']['value'].lower()

    if data['fields']['customfield_10052']:
        extracted_data['suppr_type'] = data['fields']['customfield_10052']['value']

    if data['fields']['customfield_10053']:
        extracted_data['signatures'] = []
        for content in data['fields']['customfield_10053']['content']:
            for sub_content in  content['content']:
                if 'text' in sub_content:
                    extracted_data['signatures'].append(sub_content['text'])

    if data['fields']['customfield_10054']:
        extracted_data['ticket_key'] = []
        for content in data['fields']['customfield_10054']['content']:
            for sub_content in content['content']:
                if 'text' in sub_content:
                    extracted_data['ticket_key'].append(sub_content['text'])

    extracted_data['request_language'] = data['fields']['customfield_10065']['value'] if (
        data)['fields']['customfield_10065'] else 'en'

    if 'attachment' in data['fields']:
        for attachment in data['fields']['attachment']:
            if attachment['mimeType'] not in ['message/rfc822', 'text/plain']:
                logger.warning('MIME type non supporté - %s %s', attachment['mimeType'],
                               attachment['filename'])
                continue

            extracted_data['attachment'].append({
                'filename': attachment['filename'],
                'content_link': attachment['content']
            })

    return extracted_data


def eval_ticket(conf, ticket):
    """
    Process pour le traitement des demandes d'évaluation.
    :param conf: <Settings>
    :param ticket: <dict>
    :return: <None>
    """
    header = {'Accept': 'application/json'}
    auth = HTTPBasicAuth(conf.infra['jira']['user'], conf.infra['jira']['token'])
    logger.info('Début du traitement du ticket evaluation - %s', ticket['key'])

    if not ticket['attachment']:
        logger.info("Ticket sans attachement valide - %s", ticket['key'])
        comment = conf.infra['comments']['eval_not_attachment'][ticket['request_language']]
        post_reply(conf, ticket, comment, 'Cancel')
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
            document = pre_traitement(conf, ticket, attached)

            if not document:
                continue

            if ticket['ticket_type'] == "Populate":
                attached['document'] = document
                continue

            if ticket['storage_auth'] == 'Autoriser':
                attached['document'] = document
            attachment_eval(conf, ticket, attached, document)


def suppression_ticket(conf, ticket):
    """
    Gestion d'un ticket de suppression
    :param conf: <Settings>
    :param ticket: <dict>
    """
    p_client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                   passwd=conf.infra['psql']['pass'],
                                   host=conf.infra['psql']['host'],
                                   port=conf.infra['psql']['port'],
                                   dbname=conf.infra['psql']['db'])

    m_client = cmd_mongo.connect(conf)

    table = "kaamelott_users"
    id_user = cmd_psql.get_unique_data(p_client, table, 'id_user',
                                       f"email LIKE '{ticket['reporter']}'")
    if not id_user:
        logger.info("%s - l'utilisateur n'est pas présent en base - %s", ticket['key'],
                    ticket['reporter'])
        return

    if 'signatures' not in ticket:
        ticket['signatures'] = []

    if ticket['suppr_type'] == 'Sélection':
        for ticket_key in ticket.get('ticket_key', []):
            attached_mail = cmd_psql.get_data(p_client, 'kaamelott_mail_store', ['id_message'],
                                              f"jira_key LIKE '{ticket_key}' "
                                              f"AND id_user = {id_user}")
            table = 'kaamelott_messages'
            for line in attached_mail:
                ticket['signatures'].append(
                    cmd_psql.get_unique_data(p_client, table, 'hash',
                                             f"id_message = {line['id_message']}")
                )
        ticket['signatures'] = list(set(sign for sign in ticket['signatures'] if sign))
    else:
        provided_mail = cmd_psql.get_data(p_client, 'kaamelott_mail_store', ['id_message'],
                                          f"id_user = {id_user}")
        table = 'kaamelott_messages'
        for line in provided_mail:
            ticket['signatures'].append(
                cmd_psql.get_unique_data(p_client, table, 'hash',
                                         f"id_message = {line['id_message']}")
            )

    if not ticket['signatures']:
        logger.info('Aucun document à retirer')
        return

    ticket['signatures'] = [f"'{sign}'" for sign in ticket['signatures']]
    ticket['signatures'] = cmd_psql.get_data(p_client, 'kaamelott_messages', ['id_message', 'hash'],
                                             f"hash in ({', '.join(ticket['signatures'])})")

    collection = m_client[conf.infra['mongo']['db']]['kaamelott']
    query = ("DELETE FROM kaamelott_mail_store "
             "WHERE id_message = {id_message} AND id_user = {id_user}")
    for entry in ticket['signatures']:
        cmd_psql.exec_query(p_client, query.format(id_message=entry['id_message'],
                                                   id_user=id_user))
        logger.info("Association retirée du magasin - id_message(%s) id_user(%s), si présente",
                    entry['hash'], id_user)

        if not cmd_psql.get_data(p_client, 'kaamelott_mail_store', ['id_user'],
                                 f"id_message = {entry['id_message']}"):
            collection.delete_one({'_id': entry['hash']})
            logger.info("Message retiré de la base mongo - %s", entry['hash'])

    p_client.close()
    m_client.close()


def attachment_eval(conf, ticket, attached, document):
    """
    Evaluer un mail avec les modèles disponibles.
    :param conf: <Settings>
    :param ticket: <dict>
    :param attached: <str>
    :param document: <dict>
    :return: <None>
    """
    client = cmd_mongo.connect(conf)
    collection = client[conf.infra['mongo']['db']][conf.infra['mongo']['models']]
    models = cmd_mongo.get_all_documents(collection, d_filter={'langue': document['langue']})
    client.close()

    req_lang = ticket['request_language']

    if not models:
        logger.warning('%s - Pas de modèles IA disponible pour %s', ticket['key'],
                       attached['filename'])
        attached['success'] = False
        attached['result'] = (f"{document['hash']} - "
                              f"{conf.infra['comments']['no_model'][req_lang]} - "
                              f"{document['langue']}")
        return

    attached['hash'] = document['hash']
    models = previous_eval(conf, models, document, attached)
    if not models:
        logger.info('Aucun nouveau traitement à effectuer pour %s', attached['filename'])
        return

    feats = features_process(document, attached)
    bag = nlp_process(conf, ticket, document, attached)
    vecteur = vecteur_process(conf, bag, document, attached)
    if not vecteur:
        attached['success'] = False
        attached['result'] = (f"{document['hash']} - "
                              f"{conf.infra['comments']['tfidf_failed'][req_lang]}")
        return

    ai_eval(models, document, feats, vecteur, attached, conf=conf, ticket=ticket)


def pre_traitement(conf, ticket, attached):
    """
    Traitement initial de la pièce jointe
    :param conf: <Settings>
    :param ticket: <dict>
    :param attached: <dict>
    :return: <dict>
    """
    logger.debug('%s Traitement initial de %s', ticket['key'], attached['filename'])
    mail = importation.load_mail(attached['tmp_path'])
    sujet, exp = importation.extract_mail_meta(mail)
    body = importation.extract_mail_body(mail)
    body, liens = nettoyage.clear_texte_init(body)
    req_lang = ticket['request_language']

    if not body:
        logger.warning("Echec de récupération du corps de %s", attached['filename'])
        attached['success'] = False
        attached['result'] = conf.infra['comments']['empty_body'][req_lang]
        return {}

    try:
        lang = langdetect.detect(body).split()[0]
        attached['langue'] = lang
    except langdetect.lang_detect_exception.LangDetectException as err:
        logger.error("Echec de détection de la langue pour %s %s", attached['filename'], err)
        attached['success'] = False
        attached['result'] = conf.infra['comments']['lang_detect_failed'][req_lang]
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


def ai_eval(models, document, feats, vecteur, attached, **kwargs):
    """
    Réalise l'évaluation via les modèles
    :param models: <list>
    :param document: <dict>
    :param feats: <dict>
    :param vecteur: <dict>
    :param attached: <dict>
    """
    logger.info("%s - Evaluation des modèles", attached['filename'])
    conf = kwargs['conf']
    ticket = kwargs['ticket']
    req_lang = ticket['request_language']

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
            attached['result'] = (f"{document['hash']} - "
                                  f"{conf.infra['comments']['ai_norm'][req_lang]}"
                                  f"{attached['filename']}")
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
        mot = mot.replace("'", "''")
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


def nlp_process(conf, ticket, document, attached):
    """
    Traitement NLP de la pièce jointe
    :param conf: <Settings>
    :param ticket: <dict>
    :param document: <dict>
    :param attached: <dict>
    :return: <dict>
    """
    logger.info("%s - Traitement du langage naturel", attached['filename'])
    req_lang = ticket['request_language']

    match document['langue']:
        case 'en':
            stopw = set(stopwords.words('english'))
        case 'fr':
            stopw = set(stopwords.words('french'))
        case _:
            logger.info("Langue détectée non supportée - %s", document['langue'])
            attached['success'] = False
            attached['result'] = (f"{document['hash']} - "
                                  f"{conf.infra['comment']['no_nlp'][req_lang]} "
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

    logger.info("%s Nouvel état pour le ticket - %s", ticket['key'], transition)


def post_eval_report(conf, ticket):
    """
    Prépare et poste le retour de l'analyse.
    :param conf: <Settings>
    :param ticket: <dict>
    """
    if not ticket['attachment']:
        return

    req_lang = ticket['request_language']
    comment = conf.infra['comments']['post_eval'][req_lang]
    for attached in ticket['attachment']:
        tmp_cmt = f"\n{attached['filename']} - "
        if not attached['success']:
            tmp_cmt += attached['result']
        else:
            tmp_cmt += (f"\n{conf.infra['comments']['mail_id'][req_lang]}: "
                        f"{attached['hash']}\n\t")
            tmp_cmt += '\n\t'.join([f"{model}\t>\t{pred}"
                                    for model, pred in attached['result'].items()])
        comment += f"{tmp_cmt}\n"

    comment += f"\n\n{conf.infra['comments']['eval_thanks'][req_lang]}"

    post_reply(conf, ticket, comment, 'Traité')


def post_populate_report(conf, ticket):
    """
    Prépare et poste la réponse pour un ticket de population
    :param conf: <Settings>
    :param ticket: <dict>
    """
    req_lang = ticket['request_language']
    comment = (f"{conf.infra['comments']['post_pop'][req_lang]} - "
               f"{ticket['categorie']}\n")

    for attached in ticket['attachment']:
        if ('document' not in attached) or (not attached['document']):
            continue
        tmp_cmt = f"\n{attached['filename']}:\n"
        tmp_cmt += (f"\t{conf.infra['comments']['mail_id'][req_lang]} - "
                    f"{attached['document']['hash']}\n")
        tmp_cmt += (f"\t{conf.infra['comments']['detect_lang'][req_lang]} - "
                    f"{attached['document']['langue']}\n\n")
        comment += tmp_cmt

    comment += f"{conf.infra['comments']['pop_thanks'][req_lang]}"

    post_reply(conf, ticket, comment, 'Fermeture')


def save_results(conf, ticket):
    """
    Sauvegarde les informations
    :param conf: <Settings>
    :param ticket: <dict>
    :return: <None>
    """
    client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])

    now = datetime.datetime.utcnow()
    for attached in ticket['attachment']:
        if not attached['success']:
            continue

        table = 'kaamelott_messages'
        id_message = cmd_psql.get_unique_data(client, table, 'id_message',
                                              f"hash LIKE '{attached['hash']}'")
        if not id_message:
            cmd_psql.insert_data_one(client, table, {'hash': attached['hash']})
            id_message = cmd_psql.get_unique_data(client, table, 'id_message',
                                                  f"hash LIKE '{attached['hash']}'")

        table = 'kaamelott_mail_eval'
        for model, prediction in attached['result'].items():
            id_eval = cmd_psql.get_unique_data(client, table, 'id_eval',
                                               f"id_message = {id_message} "
                                               f"AND model_name LIKE '{model}' "
                                               f"AND langue LIKE '{attached['langue']}'")
            if id_eval:
                data = {
                    "eval_timestamp": now.isoformat(),
                    "result": prediction
                }
                cmd_psql.update(client, table, data, clause=f"id_eval = {id_eval}")
                logger.info("%s %s Résultat mis à jour", attached['filename'], model)
                continue

            data = {
                "id_message": id_message,
                "model_name": model,
                "langue": attached['langue'],
                "eval_timestamp": now.isoformat(),
                "result": prediction
            }
            cmd_psql.insert_data_one(client, table, data)
            logger.info("%s %s Résultat mis en base", attached['filename'], model)

    client.close()


def save_mail(conf, ticket):
    """
    Sauvegarde le mail dans la base mongo.
    Selon autorisation
    :param conf: <Settings>
    :param ticket: <dict>
    :return: <None>
    """
    p_client = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                 passwd=conf.infra['psql']['pass'],
                                 host=conf.infra['psql']['host'],
                                 port=conf.infra['psql']['port'],
                                 dbname=conf.infra['psql']['db'])

    m_client = cmd_mongo.connect(conf)
    collection = m_client[conf.infra['mongo']['db']]['kaamelott']

    if ticket['ticket_type'] == 'Evaluate':
        if ticket['storage_auth'] != 'Autoriser':
            p_client.close()
            m_client.close()
            return
        categorie = 'Inconnu'
    elif ticket['ticket_type'] == 'Populate':
        categorie = ticket['categorie']
    else:
        categorie = 'Inconnu'

    table = "kaamelott_users"
    id_user = cmd_psql.get_unique_data(p_client, table, 'id_user',
                                       f"email LIKE '{ticket['reporter']}'")
    if not id_user:
        cmd_psql.insert_data_one(p_client, table, {'email': ticket['reporter']})
        id_user = cmd_psql.get_unique_data(p_client, table, 'id_user',
                                           f"email LIKE '{ticket['reporter']}'")
        logger.info('Nouvel utilisateur créé dans la base PSQL')

    for attached in ticket['attachment']:
        if ('document' not in attached) or (not attached['document']):
            continue
        table = 'kaamelott_messages'
        id_message = cmd_psql.get_unique_data(p_client, table, 'id_message',
                                              f"hash LIKE '{attached['document']['hash']}'")
        if not id_message:
            cmd_psql.insert_data_one(p_client, table, {'hash': attached['document']['hash']})
            id_message = cmd_psql.get_unique_data(p_client, table, 'id_message',
                                                  f"hash LIKE '{attached['document']['hash']}'")

        table = 'kaamelott_mail_store'
        clause = (f"jira_key LIKE '{ticket['key']}' "
                  f"AND id_message = {id_message} "
                  f"AND id_user = {id_user}")
        if not cmd_psql.get_unique_data(p_client, table, 'jira_key', clause):
            data = {
                'jira_key': ticket['key'],
                'id_message': id_message,
                'id_user': id_user
            }
            cmd_psql.insert_data_one(p_client, table, data)
            logger.info("Metadonnées de %s - %s stockées dans PSQL", ticket['key'],
                        attached['filename'])

        m_document = {key: value for key, value in attached['document'].items()
                      if key not in ['liens']}
        m_document['categorie'] = categorie
        m_document['_id'] = m_document.pop('hash')
        cmd_mongo.insert_document(m_document, collection)

    m_client.close()
    p_client.close()
    logger.info("%s Fin de la sauvegarde des documents", ticket['key'])
