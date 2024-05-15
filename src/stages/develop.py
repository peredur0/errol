# coding: utf-8
"""
Fichier pour tester les développements en cours
"""
import logging
import multiprocessing
import tqdm
from src.stages import fouille
from src.modules import importation


logger = logging.getLogger(__name__)


def main(conf):
    """
    Processus principal
    :param conf: <Settings>
    :return: None
    """
    logger.info("DEVELOPPEMENT")
    # fouille.databases_init(conf)

    ham_test = "./project_data/spamassassin/easy_ham"
    files_stack = {'ham': importation.get_files(ham_test)}
    pool_args = [(file, cat) for cat, f_list in files_stack.items() for file in list(f_list)]
    with multiprocessing.Pool(conf.infra['cpu_available']) as pool:
        result = list(tqdm.tqdm(pool.imap(fouille.fouille_doc, pool_args),
                                desc="Création des documents",
                                leave=False,
                                disable=conf.args['progress_bar']))
    result = [doc for doc in result if doc]
    logger.info("Documents créés - %s", len(result))

    fouille.mise_en_base(result, conf)
    # todo: trouver comment nettoyer un container
