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
        prog="errol",
        description="programme pour le projet d'étude Fouille de données et Ingénierie des langues"
    )
    subparsers = parser.add_subparsers(title='stages', dest='stage')

    parser.add_argument(
        '-b', '--progress_bar',
        help='Affiche les barres de progression si disponible',
        action='store_true',
        default=False
    )

    parser.add_argument(
        '-r', '--rapport',
        help='Sauvegarde les données et images pour le rapport',
        action='store_true',
        default=False
    )

    parser_dev = subparsers.add_parser('develop',
                                       help="Lance la partie en cours de développement")

    parser_dev.add_argument('-d', '--debug',
                            help='augmente la verbosité des logs',
                            action='store_true',
                            default=False)

    parser_dev.add_argument("-g", "--graph",
                            help="Affiche les données statistiques sous forme de graph",
                            action='store_true',
                            default=False)

    parser_fouille = subparsers.add_parser('fouille',
                                           help="Réalisation des actions de fouille de données")
    parser_fouille.add_argument("-g", "--graph",
                                help="Affiche les données statistiques sous forme de graph",
                                action='store_true',
                                default=False)

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

    parser_features = subparsers.add_parser('features',
                                            help="Recherche des caractéristiques")
    parser_features.add_argument("-g", "--graph",
                                 help="Affiche les données statistiques sous forme de graph",
                                 action='store_true',
                                 default=False)

    subparsers.add_parser('nlp', help='Traitement du langage naturel')

    parser_vecteurs = subparsers.add_parser('vecteurs',
                                            help="Vectorise les documents")

    parser_vecteurs.add_argument('method',
                                 help="Methode de vectorisation",
                                 nargs=1,
                                 choices=['tfidf'])

    parser_vecteurs.add_argument('-l', '--limit',
                                 help="limiter le nombre mot utilisés dans la base vectorielle",
                                 type=int,
                                 default=200)

    parser_vecteurs.add_argument('-i', '--init',
                                 help="Initialise la base psql",
                                 action='store_true',
                                 default=False)

    parser_vecteurs.add_argument("-g", "--graph",
                                 help="Affiche les données statistiques sous forme de graph",
                                 action='store_true',
                                 default=False)

    parser_train = subparsers.add_parser('train',
                                         help='Entrainement des modèles')
    models = {
        'rtf': 'Random Tree Forest',
        'svm': 'Support Vector Machine'
    }
    model_txt = ' | '.join([f'{abr}({nom})' for abr, nom in models.items()])
    help_text = f"Modèles disponibles: {model_txt}"
    parser_train.add_argument('models',
                              help=help_text,
                              nargs='+',
                              choices=models.keys())
    subparsers.required = True
    return parser.parse_args()
