# coding: utf-8
"""
Fichier pour tester les développements en cours
"""
import json
import logging

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from src.modules import cmd_sqlite

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
    cats = list(schema.keys())
    client = cmd_sqlite.connect(conf.infra['sqlite']['file'])
    for cat in cats:
        output = cmd_sqlite.get_data(client, cat)
        for row in output:
            keys = list(schema[cat].keys())
            row_info = dict(zip(keys, row))
            row_info['categorie'] = cat
            data.append(row_info)

    stats_df = pd.DataFrame(data)
    fields = ['categorie', 'mails', 'mots', 'mots_uniques']
    for etape in stats_df['etape'].unique():
        etape_df = stats_df[stats_df['etape'] == etape][fields]
        logger.info("Statistiques %s:\n%s", etape, etape_df.to_string(index=False))

    fig, axes = plt.subplots(1, 3, figsize=(17, 5))
    fig.suptitle('Statistiques de la récolte')
    fig.subplots_adjust(wspace=0.4)

    index = 0
    for key, titre in [('mails', 'Documents conservés'), ('mots', 'Nombre de mots'),
                       ('mots_uniques', 'Nombre de mots uniques')]:
        sns.barplot(data=stats_df[[key, 'etape', 'categorie']], x='etape', y=key,
                    hue='categorie', ax=axes[index], hue_order=['globales', 'ham', 'spam'])
        axes[index].set_title(titre)
        axes[index].get_legend().set_visible(False)
        index += 1

    handles, labels = plt.gca().get_legend_handles_labels()
    fig.legend(handles, labels, ncols=3, loc='upper left')

    plt.show()
