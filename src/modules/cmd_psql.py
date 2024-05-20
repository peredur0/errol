# coding: utf-8

"""
Module de liaison avec une base postgresSQL
"""

import logging
import psycopg2
import sqlalchemy

logger = logging.getLogger(__name__)


def create_engine(user, passwd, host, port, dbname):
    """
    Connexion a la base de donnees Postgres pour pandas
    Penser à fermer la connexion
    :param user: <str> utilisateur autoriser à pusher les données
    :param passwd: <str> mot de passe
    :param host: <str> localisation réseau de la bdd
    :param port: <str> port de connexion
    :param dbname: <str> nom de la base de donnees
    :return: <psycopg2.extension.connection> objet connexion à la bdd
    """
    uri = f"postgresql://{user}:{passwd}@{host}:{port}/{dbname}"
    engine = sqlalchemy.create_engine(uri)
    return engine


def connect_db(user, passwd, host, port, dbname=""):
    """
    Connexion a la base de donnees Postgres.
    Penser à fermer la connexion
    :param user: <str> utilisateur autoriser à pusher les données
    :param passwd: <str> mot de passe
    :param host: <str> localisation réseau de la bdd
    :param port: <str> port de connexion
    :param dbname: <str> nom de la base de donnees
    :return: <psycopg2.extension.connection> objet connexion à la bdd
    """
    try:
        client_psql = psycopg2.connect(dbname=dbname,
                                       user=user,
                                       password=passwd,
                                       host=host,
                                       port=port)
    except psycopg2.Error as err:
        logger.error("Erreur de connexion : %s", err)
        return None

    client_psql.autocommit = True
    return client_psql


def create_table(client_psql, schema):
    """
    Créé une nouvelle table dans la base de donnees
    :param client_psql: <psycopg2.extension.connection> object connexion vers une base de donnee
    :param schema: <dict>
    :return:
    """
    instr = []
    for field in schema['fields']:
        instr.append(f"{field['name']} {' '.join(field['type'])}")

    if 'primary_key' in schema and schema['primary_key']:
        instr.append(f"PRIMARY KEY ({','.join(schema['primary_key'])}")

    if "foreign_keys" in schema and schema['foreign_keys']:
        for key in schema['foreign_keys']:
            constr = (f"CONSTRAINT {key['name']} FOREIGN KEY({key['field']}) REFERENCES "
                      f"{key['reference']}")
            if 'on_delete' in key and key['on_delete']:
                constr += f" ON DELETE {key['on_delete']}"
            instr.append(constr)

    cursor = client_psql.cursor()
    query = f"CREATE TABLE {schema['name']} ({', '.join(instr)})"
    try:
        cursor.execute(query)
    except psycopg2.Error as err:
        logger.error(err)
    else:
        logger.info("Table '%s' créée", schema['name'])


def create_index(client_psql, nom, table, colonne):
    """
    Index sur les hash des messages
    :param client_psql: <psycopg2.extension.connection> object connexion vers une base de donnee
    :param nom: <str> nom de l'index
    :param table: <str> table sur laquelle creer l'index
    :param colonne: <str> colonne cible
    :return:
    """
    query = f"CREATE UNIQUE INDEX {nom} ON {table}({colonne})"
    exec_query(client_psql, query)


def insert_data_one(client_psql, table, data):
    """
    Insérer les données d'un dictionnaire dans une table de la base de donnees PSQL
    Les clés du dictionnaire doivent correspondre aux colonnes de la table.
    :param client_psql: <psycopg2.extension.connection> object connexion vers une base de donnee
    :param table: <str> La table dans à remplir
    :param data: <dict> {colonne : valeur}
    :return: None
    """
    cols = ','.join([str(c) for c in data.keys()])
    vals = ','.join([str(v) if not isinstance(v, str) else f"'{v}'" for v in data.values()])
    query = f"INSERT INTO {table}({cols}) VALUES ({vals})"

    exec_query(client_psql, query)


def insert_data_many(client_psql, table, data):
    """
    Insérer les données sur plusieurs lignes
    :param client_psql: <psycopg2.extension.connection> object connexion vers une base de donnee
    :param table: <str> La table dans à remplir
    :param data: <list> [{col1 : val1, col2 : val2}, ...]
    """
    if len(data) == 1:
        insert_data_one(client_psql, table, data[0])
        return

    data = [dict(sorted(line.items())) for line in data]
    keys = data[0].keys()
    for line in data[1:]:
        if keys != line.keys():
            logger.error("Impossible d'insérer les données dans la table %s les clés entre les"
                         " lignes ne sont pas identiques", table)
            return

    lines_values = []
    for line in data:
        vals = ','.join([str(v) if not isinstance(v, str) else f"'{v}'" for v in line.values()])
        vals = f"({vals})"
        lines_values.append(vals)

    query = f"INSERT INTO {table} ({','.join(list(keys))}) VALUES {', '.join(lines_values)}"
    exec_query(client_psql, query)


def get_data(client_psql, table, champs, clause=None):
    """
    Récupère les données de la base.
    :param client_psql: <psycopg2.extension.connection> object connexion vers une base de donnee.
    :param table: <str> table à scroller.
    :param champs: <list> champs à récupérer.
    :param clause: <str> Clause WHERE
    :return: <list> dict par ligne
    """
    query = f"SELECT {','.join(champs)} FROM {table}"
    if clause:
        query += f" WHERE {clause}"

    result = exec_query(client_psql, query)
    return [dict(zip(champs, ligne)) for ligne in result]


def exec_query(client_psql, query):
    """ Execute une query dans la base PSQL
    :param client_psql: <psycopg2.extension.connection> object connexion vers une base de donnee
    :param query: <str> query à appliquer
    :return: <list> vide ou sortie du select
    """
    cursor = client_psql.cursor()

    try:
        cursor.execute(query)
        if query.upper().find("SELECT", 0, 6) >= 0:
            return cursor.fetchall()
        return []
    except psycopg2.Error as err:
        logger.error("Erreur d'execution de la requete : %s\n%s", err, query)
        return []
