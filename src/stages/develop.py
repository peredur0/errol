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

    with open(conf.infra['psql']['vecteurs']['tfidf']['data'], 'r', encoding='utf-8') as file:
        sql_reqs = file.read()

    queries = sql_reqs.split(';')
    df_1 = pd.read_sql_query(queries[0], client)
    df_1 = df_1.drop(['document'], axis=1)

    df_2 = pd.read_sql_query(queries[1], client)
    df_2 = df_2.drop(['label'], axis=1)
    graph.vecteurs_dash(df_1, df_2, conf)

    client.dispose()
