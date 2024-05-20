# coding: utf-8
"""
Fichier pour tester les développements en cours
"""
import logging
import pandas as pd
import sqlalchemy
from src.modules import graph
from src.modules import cmd_psql


logger = logging.getLogger(__name__)


def main(conf):
    """
    Processus principal
    :param conf: <Settings>
    :return: None
    """
    logger.info("DEVELOPPEMENT")

    psql_uri = (f"postgresql://{conf.infra['psql']['user']}:{conf.infra['psql']['pass']}@"
                f"{conf.infra['psql']['host']}:{conf.infra['psql']['port']}/"
                f"{conf.infra['psql']['db']}")
    engine = sqlalchemy.create_engine(psql_uri)

    query = '''SELECT
    c.nom, l.url, l.mail, l.tel, l.nombre, l.prix
    FROM liens l 
    JOIN messages m ON l.id_message = m.id_message
    JOIN categories c ON m.id_categorie = c.id_categorie;
    '''
    colonnes = ['categorie', 'url', 'mail', 'tel', 'nombre', 'prix']
    df = pd.read_sql_query(query, engine)
    engine.dispose()
    df.columns = colonnes
    print(df[df['categorie']=='ham'].describe())
    print(df[df['categorie']=='spam'].describe())
    pivot = df.pivot_table(
        index='categorie',
        values=['url', 'mail', 'tel', 'nombre', 'prix'],
        aggfunc=['mean', graph.q50, graph.q90,'max']
    )
    print(pivot)
