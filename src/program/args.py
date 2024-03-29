# coding: utf-8
"""
Gestion des paramètres en ligne de commande
"""
import argparse


def args_handler():
    """
    Gestion des arguments
    :return: <argparse.Namespace>
    """
    parser = argparse.ArgumentParser(
        prog="main_project",
        description="programme pour le projet d'étude Fouille de données et Ingénierie des langues"
    )
    subparsers = parser.add_subparsers(title='stages', dest='stage')

    parser_fouille = subparsers.add_parser('fouille', help="Réalisation des actions de fouille de données")
    source = parser_fouille.add_argument_group("source de données")
    source.add_argument(
        "-a", "--ham",
        dest='ham',
        help="Dossier contenant les mails légitimes",
        metavar="DOSSIER_HAM",
        nargs='*'
    )
    source.add_argument(
        "-p", "--spam",
        dest="spam",
        help="Dossier contenant les mails frauduleux",
        metavar="DOSSIER_SPAM",
        nargs='*'
    )
    source.add_argument(
        "-s", "--fichier_csv",
        dest="fichier_csv",
        help="fichier CSV contenant les emails stockés dans un fichier CSV",
        metavar="FICHIER_CSV",
        nargs='*'
    )

    subparsers.required = True
    return parser.parse_args()
