# coding: utf-8
"""
Fichier pour tester les développements en cours
"""
import json
import logging

import seaborn as sns
import pandas as pd
import numpy as np
from src.modules import cmd_sqlite
from src.modules import cmd_mongo
from src.modules import graph
from src.annexes import zipf


logger = logging.getLogger(__name__)

sns.set()


def main(conf):
    """
    Processus principal
    :param conf: <Settings>
    :return: None
    """
    logger.info("DEVELOPPEMENT")

    with open(conf.infra['sqlite']['schema_stats'], 'r', encoding='utf-8') as json_file:
        schema = json.load(json_file)

    data = []
    client = cmd_sqlite.connect(conf.infra['sqlite']['file'])
    for cat in list(schema.keys()):
        for row in cmd_sqlite.get_data(client, cat):
            keys = list(schema[cat].keys())
            row_info = dict(zip(keys, row))
            row_info['categorie'] = cat
            data.append(row_info)

    stats_df = pd.DataFrame(data)
    for etape in stats_df['etape'].unique():
        etape_df = stats_df[stats_df['etape'] == etape][
            ['categorie', 'mails', 'mots', 'mots_uniques']]
        logger.info("Statistiques %s\n%s", etape, etape_df.to_string(index=False))

    client = cmd_mongo.connect(conf)
    collection = client[conf.infra['mongo']['db']][conf.infra['mongo']['collection']]
    bag = cmd_mongo.get_all_documents(collection, include='message')
    bag = [doc['message'].split() for doc in bag]
    bag = [mot for doc in bag for mot in doc]

    zipf_data = zipf.zipf_process(bag)
    logger.info("Distribution de zipf\n\tconstante: %.2f\n\tcoefficient k: %.2f",
                zipf_data['const_moy'], zipf_data['coef_min'])

    link_data = cmd_mongo.get_all_documents(collection, ['categorie', 'liens'])
    link_data = [{'categorie': entry['categorie'], 'liens': key, 'value': value}
                 for entry in link_data
                 for key, value in entry['liens'].items()]
    link_data = pd.DataFrame(link_data)
    link_data = link_data.pivot_table(
        index='liens',
        values='value',
        columns='categorie',
        aggfunc=['mean', graph.q50, graph.q90, 'max']
    )
    logger.info("Statistiques des liens\n%s", link_data)

    graph.fouille_dash(stats_df, zipf_data, link_data)

    client.close()
