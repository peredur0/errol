# coding: utf-8
"""
Programme de vérification d'un message
"""
import json
import math
import re
import nltk
import logging
import hashlib
import langdetect

from nltk.corpus import stopwords
import stanza

from src.modules import importation
from src.modules import nettoyage
from src.modules import cmd_psql
from src.annexes import zipf
from src.stages.features import features_ponctuations, features_mots, features_zipf, features_hapax
from src.stages.nlp import lemmatise

logger = logging.getLogger(__name__)


def main(conf):
    """
    Fonction principale
    """
    logger.info("Check d'un message")

    logger.info("Traitement initial du message")
    mail = importation.load_mail(conf.args['mail'])
    sujet, exp = importation.extract_mail_meta(mail)
    body = importation.extract_mail_body(mail)
    body, liens = nettoyage.clear_texte_init(body)
    if not body:
        logger.warning("Echec de récupération du corps de %s", conf.args['mail'])
        return

    try:
        lang = langdetect.detect(body).split()[0]
    except langdetect.lang_detect_exception.LangDetectException as err:
        logger.error("Echec de détection de la langue pour %s %s", conf.args['mail'], err)
        return

    new_doc = {
        'hash': hashlib.md5(body.encode()).hexdigest(),
        'sujet': sujet if sujet else 'null',
        'expediteur': exp,
        'message': body,
        'langue': lang,
        'liens': liens
    }

    logger.info("Recherche des caractéristiques")
    fonctions = [features_ponctuations, features_mots, features_zipf, features_hapax]
    features = {}
    for fonction in fonctions:
        features.update(fonction(body))

    logger.info("Traitement NLP")
    nltk.download("stopwords")
    match new_doc['langue']:
        case 'en':
            stopw = set(stopwords.words('english'))
        case 'fr':
            stopw = set(stopwords.words('french'))
        case _:
            logger.info("Langue détectée non supportée - %s", new_doc['langue'])
            return

    pattern = re.compile(r'\w+')
    stz_pipe = stanza.Pipeline(lang=new_doc['langue'], processors='tokenize,mwt,pos,lemma')
    bag = zipf.freq_mot(lemmatise(body, stopw, stz_pipe, pattern))

    logger.info("Vectorisation")
    client_psql = cmd_psql.connect_db(user=conf.infra['psql']['user'],
                                      passwd=conf.infra['psql']['pass'],
                                      host=conf.infra['psql']['host'],
                                      port=conf.infra['psql']['port'],
                                      dbname=conf.infra['psql']['db'])
    with open(conf.infra['psql']['queries'], 'r', encoding='utf-8') as file:
        queries = json.load(file)

    total_docs = cmd_psql.exec_query(client_psql, queries['check_nb_docs'].format(
        langue=new_doc['langue']))[0][0]

    vecteur = {}
    for mot, occurrence in bag.items():
        data = cmd_psql.exec_query(client_psql, queries['check_label'].format(
            mot=mot, algo='tfidf', langue=new_doc['langue']))
        if not data:
            continue
        label, freq_doc = data[0]
        vecteur[label] = occurrence * math.log(total_docs/freq_doc)
    client_psql.close()

    if not vecteur:
        logger.error("Vecteur null pour le message - abandon")
        return

    logger.info("Préparation des datasets")

    # models = {name: f"{conf.infra['storage']}/{name}.pkl" for name in conf.args['models']}


