# coding: utf-8
"""
Code pour la phase de fouille de données
"""

import logging

from src.modules import cmd_sqlite
from src.modules import importation

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
    raw_stack = {'ham': [], 'spam': [], 'csv': conf.args['csv']}

    for cat in ['ham', 'spam']:
        for folder in conf.args[cat]:
            raw_stack[cat] += importation.get_files(folder)
