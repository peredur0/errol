# coding: utf-8
"""
Fichier pour le développement
"""

import logging
import sys

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from src.modules import graph
from src.modules import cmd_psql

logger = logging.getLogger(__name__)


def main(conf):
    """
    fonction principale
    """
    logger.info("DEVELOPPEMENT")
    client = cmd_psql.create_engine(user=conf.infra['psql']['user'],
                                    passwd=conf.infra['psql']['pass'],
                                    host=conf.infra['psql']['host'],
                                    port=conf.infra['psql']['port'],
                                    dbname=conf.infra['psql']['db'])

    with open(conf.infra['psql']['nlp']['requetes'], 'r', encoding='utf-8') as file:
        sql_reqs = file.read()

    stats_df = []
    for query in sql_reqs.split(';'):
        if query.startswith('\n'):
            query = query[1:]
        if not query:
            continue

        new_df = pd.read_sql_query(query, client)
        stats_df.append(new_df.to_string(index=False))

    logger.info("Données du traitement - \n%s", '\n'.join(stats_df))

    client.dispose()
