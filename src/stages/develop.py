# coding: utf-8
"""
Fichier pour le développement
"""
import os.path
import sys
import tempfile

import logging
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


def main(conf):
    """
    Fonction principale
    """
    logger.info("DEVELOPPEMENT")

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
                mail_eval(ticket, conf)

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


def mail_eval(ticket, conf):
    """
    Process pour le traitement des demandes d'évaluation.
    :param ticket: <dict>
    :param conf: <Settings>
    :return: <None>
    """
    logger.info('Evaluation des mails du ticket %s', ticket['key'])

    if not ticket['attachment']:
        logger.info("Ticket sans attachement valide - %s")
        comment = ("Bonjour,\n"
                   "Merci de nous avoir contacter.\n"
                   "Malheureusement, les pièces jointes fournies ne semblent pas répondre aux "
                   "critère de traitement.\n"
                   "Merci de vérifier que vous nous avez bien transmis des fichier email au "
                   "format .eml")
        reply(conf, ticket['self'], comment, 'Cancel')
        return

    if not os.path.isdir(conf.infra['mails']):
        os.makedirs(conf.infra['mails'])
    tempfile.tempdir = conf.infra['mails']

    logger.info('Téléchargement des mails de %s', ticket['key'])
    for attached in ticket['attachment']:
        print(attached['content_link'])
        resp = requests.request('GET', attached['content_link'], timeout=30)
        if resp.status_code == 200:
            with tempfile.NamedTemporaryFile(prefix='errol_', suffix='.eml') as tmp_file:
                tmp_file.write(resp.content)
                attached['local_path'] = tmp_file.name
                logger.info("%s - mail téléchargé - %s", ticket['key'], tmp_file.name)
        else:
            logger.error(" %s Echec de téléchargement du mail %s - %s %s",
                         ticket['key'], attached['filename'],
                         resp.status_code, resp.text)
            attached['local_path'] = None
            attached['reason'] = "Echec de téléchargement"

    # reply(conf, ticket, 'test', 'Traité')


def reply(conf, ticket, comment, transition=None):
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
    logger.info("Commentaire posté sur le ticket %s", ticket['key'])

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

    logger.info("Nouvel état pour le ticket %s - %s", ticket['key'], transition)
