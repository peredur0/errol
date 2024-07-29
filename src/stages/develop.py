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
    me_cols = ['id_message']
    ca_cols = ['nom']
    ha_cols = ['ratio_mots_uniques', 'ratio_texte', 'nombre_hapax']
    mo_cols = ['char_minuscules', 'char_majuscules', 'mots', 'mots_uniques', 'mots_majuscules',
               'mots_capitalizes']
    po_cols = ['point', 'virgule', 'exclamation', 'interrogation', 'tabulation', 'espace',
               'ligne', 'ligne_vide']
    zi_cols = ['constante', 'coefficient', 'taux_erreur']

    query = f'''
    SELECT 
        {','.join([f'me.{field}' for field in me_cols])}, 
        {','.join([f'ca.{field}' for field in ca_cols])}, 
        {','.join([f'ha.{field}' for field in ha_cols])}, 
        {','.join([f'mo.{field}' for field in mo_cols])}, 
        {','.join([f'po.{field}' for field in po_cols])}, 
        {','.join([f'zi.{field}' for field in zi_cols])} 
    FROM messages me
    JOIN categories ca ON ca.id_categorie = me.id_categorie 
    JOIN features_hapax ha ON ha.id_message = me.id_message 
    JOIN features_mots mo ON mo.id_message = me.id_message 
    JOIN features_ponctuations po ON po.id_message = me.id_message 
    JOIN features_zipf zi ON zi.id_message = me.id_message 
    JOIN controle co ON co.id_message = me.id_message
    WHERE co.features IS NOT NULL
    '''
    full_df = pd.read_sql_query(query, client)
    replace_cols = {name: name.replace('_', '-') for name in list(full_df.columns)}
    full_df = full_df.rename(columns=replace_cols)
    client.dispose()

    print_stats = {
        'char': [col.replace('_', '-') for col in mo_cols[:2]],
        'mots': [col.replace('_', '-') for col in mo_cols[2:4]],
        'format-mots': [col.replace('_', '-') for col in mo_cols[4:]],
        'ponctuation': [col.replace('_', '-') for col in po_cols[:4]],
        'espace': [col.replace('_', '-') for col in po_cols[4:]],
        'zipf': [col.replace('_', '-') for col in zi_cols],
        'hapax': [col.replace('_', '-') for col in ha_cols]
    }

    for categorie, fields in print_stats.items():
        data = full_df.pivot_table(
            index='nom',
            values=fields,
            aggfunc=['mean', graph.q50, graph.q90, 'max']
        ).unstack().unstack()
        latex_data = data.round(2).astype(str)
        latex_data.style.to_latex(
            buf=f'{conf.rapport["features"]}/tab_{categorie}.tex',
            caption=f"Statistiques sur les données {categorie}",
            label=f'tab:f_{categorie}',
            position='H',
            position_float='centering',
            clines='skip-last;data',
            column_format='ll|rr',
            hrules=True
        )
        logger.info("Statistiques %s\n%s", categorie, data)

    if conf.args['graph']:
        excluded = ['nom', 'id-message', 'ligne-vide', 'tabulation', 'interrogation',
                    'exclamation', 'virgule', 'mots-majuscules']
        df_corr = full_df.drop(excluded, axis=1)
        graph.feature_correlation(df_corr, conf)
