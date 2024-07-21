# coding: utf-8
"""
Fichier pour tester les développements en cours
"""
import logging
import pandas as pd
from src.modules import cmd_psql
from src.modules import graph

logger = logging.getLogger(__name__)


def main(conf):
    """
    Processus principal
    :param conf: <Settings>
    :return: None
    """
    logger.info("DEVELOPMENT")
    client = cmd_psql.create_engine(user=conf.infra['psql']['user'],
                                    passwd=conf.infra['psql']['pass'],
                                    host=conf.infra['psql']['host'],
                                    port=conf.infra['psql']['port'],
                                    dbname=conf.infra['psql']['db'])

    query = '''SELECT
            c.nom, l.url, l.mail, l.tel, l.nombre, l.prix
            FROM liens l 
            JOIN messages m ON l.id_message = m.id_message
            JOIN categories c ON m.id_categorie = c.id_categorie;
            '''

    link_data = pd.read_sql_query(query, client)
    client.dispose()

    link_data.columns = ['categorie', 'url', 'mail', 'tel', 'nombre', 'prix']
    aggfunc=['mean', graph.q50, graph.q90, 'max']
    link_data = link_data.groupby('categorie')[link_data.columns[1:]].agg(
        aggfunc).unstack().unstack()

    link_data = link_data.round(2).astype(str)
    link_data.style.to_latex(
        buf=f'{conf.rapport["fouille"]}/liens.tex',
        caption="Statistiques sur les liens et informations numériques",
        label='tab:p1liens',
        position='H',
        position_float='centering',
        clines=';index',
        column_format='ll|rrr',
    )
    # with open(f'{conf.rapport["fouille"]}/liens.tex', 'w', encoding='utf-8') as file:
    #     file.write(link_latex)

    logger.info("Statistiques des liens\n%s", link_data)
