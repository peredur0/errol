# coding: utf-8

"""
Fonctions utilisées pour le stockage des informations statistiques.
Stockage dans une base SQLite
"""

import sys
import logging
import sqlite3
import json

logger = logging.getLogger(__name__)


def connect(path):
    """
    Connection avec une base SQLite
    :param path: <str> chemin d'accès au fichier
    :return: <sqlite3.connection>
    """
    return sqlite3.connect(path)


def create_tables(client, schema_file):
    """
    Créer les tables dans la base
    :param client: <sqlite3.connection>
    :param schema_file: <str> fichier json
    :return: None
    """
    with open(schema_file, 'r', encoding='utf-8') as json_file:
        schema = json.load(json_file)

    for table, champs in schema.items():
        try:
            params = ', '.join([f"{k} {' '.join(v)}" for k, v in champs.items()])
            client.execute(f"DROP TABLE IF EXISTS {table};")
            client.execute(f"CREATE TABLE {table} ({params});")
            logger.info("Table SQLite '%s' créée", table)
        except sqlite3.OperationalError as err:
            logger.error("%s - %s", err, table)
            sys.exit(1)


def insert_dict(client, table, data):
    """
    Insère les données dans une table psql
    :param client: <sqlite3.connection>
    :param table: <str>
    :param data: <dict>
    """
    cursor = client.cursor()
    colonnes = ', '.join(data.keys())
    emplacements = ', '.join('?' * len(data))
    request = f"INSERT INTO {table} ({colonnes}) VALUES ({emplacements})"

    cursor.execute(request, tuple(data.values()))
    client.commit()
    logger.info("Données stockées dans la table %s", table)


def get_data(client, table, fields=None):
    """
    Récupère les données d'une table
    :param client: <sqlite3.connection>
    :param table: <str>
    :param fields: <list>
    """
    if fields is None:
        fields = '*'

    if isinstance(fields, list):
        fields = ', '.join(fields)

    query = f"SELECT {fields} FROM {table};"
    cursor = client.execute(query)
    return cursor.fetchall()
