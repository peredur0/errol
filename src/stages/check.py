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
import joblib

import stanza
from nltk.corpus import stopwords
import pandas as pd

from src.modules import importation
from src.modules import nettoyage
from src.modules import cmd_psql
from src.modules import cmd_mongo
from src.annexes import zipf
from src.stages.features import features_ponctuations, features_mots, features_zipf, features_hapax
from src.stages.nlp import lemmatise
from src.stages.train import normalize

logger = logging.getLogger(__name__)

logging.getLogger('stanza').setLevel(logging.ERROR)


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
    nltk.download("stopwords", quiet=True)
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
    data = vecteur
    data.update(new_doc['liens'])
    data.update(features)

    for key in list(data.keys()):
        if key == 'nombre_hapax':
            data['hapax'] = data.pop(key)
            continue
        if key == 'ratio_mots_uniques':
            data['hapax_uniques'] = data.pop(key)
            continue
        data[key.lower()] = data.pop(key)

    base_df = pd.DataFrame(data, index=[0])

    mgo_client = cmd_mongo.connect(conf)
    m_collection = mgo_client[conf.infra['mongo']['db']][conf.infra['mongo']['models']]

    logger.info("Evaluation")
    scaler = None
    models = {name: f"{conf.infra['storage']}/{name}.pkl" for name in conf.args['models']}
    for model_name, path in models.items():
        m_doc = list(m_collection.find({'name': model_name}))[0]
        if path != m_doc['chemin']:
            logger.error('Les chemins pour le modèle %s ne correspondent pas %s <> %s', model_name,
                         path, m_doc['chemin'])
            continue

        if type(scaler).__name__ != m_doc['scaler']:
            logger.error("La méthode de normalisation ne correspond pas %s <> %s",
                         type(scaler).__name__, m_doc['scaler'])
            continue

        m_cols = m_doc['colonnes']
        add_cols = {col: [0.0]*len(base_df) for col in m_cols if col not in base_df}
        add_cols = pd.DataFrame(add_cols)
        tmp_df = pd.concat([base_df, add_cols], axis=1)
        tmp_df = tmp_df[m_cols]
        if scaler is not None:
            normalize(tmp_df, scaler)

        model_bin = joblib.load(path)
        prediction = model_bin.predict(tmp_df)[0]
        ham_id = m_doc['ham_id']
        logger.info("%s - %s > %s",
                    conf.args['mail'], model_name, 'ham' if prediction == ham_id else 'spam')

    mgo_client.close()
