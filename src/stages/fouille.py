# coding: utf-8
"""
Code pour la phase de fouille de données
"""
import hashlib
import logging
import multiprocessing

import langdetect
import tqdm

from src.modules import cmd_sqlite
from src.modules import importation
from src.modules import word_count
from src.modules import nettoyage

logger = logging.getLogger(__name__)


def main(conf):
    """
    Fonction principale pour la fouille
    :param conf: <Settings>
    :return: <None>
    """
    logger.info("Collecte des mails et mise en base")
    logger.info("Création de la base SQLITE")
    cli_sqlite = cmd_sqlite.connect(conf.infra['sqlite']['file'])
    cmd_sqlite.create_tables(cli_sqlite, conf.infra['sqlite']['schema_stats'])
    cli_sqlite.close()

    logger.info("Récolte")
    files_stack = {'ham': [], 'spam': []}

    for cat in ['ham', 'spam']:
        try:
            for folder in conf.args[cat]:
                files_stack[cat] += importation.get_files(folder)
        except TypeError:
            logger.warning("%s - aucun dossier donné en argument", cat)
            continue
    word_count.fouille_wc(files_stack, conf, 'récolte')

    logger.info("Création des documents")
    pool_args = [(file, cat) for cat, f_list in files_stack.items() for file in list(f_list)]
    with multiprocessing.Pool(conf.infra['cpu_available']) as pool:
        result = list(tqdm.tqdm(pool.imap(fouille_doc, pool_args),
                                desc="Création des documents",
                                leave=False,
                                disable=conf.args['progress_bar']))
    logger.info("Documents créés - %s", len([doc for doc in result if doc]))
    word_count.fouille_wc([doc for doc in result if doc], conf, 'création')

    logger.info("Mise en base des documents")
    mise_en_base(result)

def fouille_doc(pool_args):
    """
    Processus de création des documents
    :param pool_args: <tuple>
    :return: <dict>
    """
    cat = pool_args[1]
    file = pool_args[0]

    mail = importation.load_mail(file)
    sujet, exp = importation.extract_mail_meta(mail)
    body = importation.extract_mail_body(mail)
    body, liens = nettoyage.clear_texte_init(body)

    if not body:
        logger.warning("Echec de récupération du corps de %s", file)
        return None

    try:
        lang = langdetect.detect(body)
    except langdetect.lang_detect_exception.LangDetectException:
        logger.warning("Echec de détection de la langue pour %s", file)
        return None

    if lang != 'en':
        logger.warning('Langue détectée pour %s - %s', file, lang)
        return None

    new_doc = {
        'hash': hashlib.md5(body.encode()).hexdigest(),
        'categorie': cat.lower(),
        'sujet': sujet,
        'expediteur': exp,
        'message': body,
        'langue': lang,
        'liens': liens
    }

    return new_doc

def mise_en_base(result):
    """
    Mise en base de documents
    :param result: <list> [<dict>, ...]
    """
