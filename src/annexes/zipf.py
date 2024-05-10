# coding: utf-8
"""
Code utilisé pour l'exploitation de la distribution de Zipf
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


def freq_mot(bag, freq=None):
    """
    Calcule la fréquence de chaque mot dans un sac de mot
    :param bag: <list> - liste de tous les mots d'un texte
    :param freq: <dict> - dict de fréquence avec {<str> mot: <int> frequence} à augmenter
    :return: <dict> - dictionnaire avec la fréquence par mot {mot: frequence}
    """
    if freq is None:
        freq = {}
    for mot in bag:
        freq[mot] = freq.get(mot, 0) + 1
    return freq


def cout(l1, l2, methode):
    """
    Calcul le cout de l'écart entre les éléments de l1 et le l2, place par place
    help : https://www.youtube.com/watch?v=_TE9fDgtOaE
    :param l1: <list> liste d'entier
    :param l2: <liste> liste d'entier
    :param methode: <str> méthode de calcul du cout
    :return: <float> cout selon méthode
    """
    if len(l1) != len(l2):
        logger.error("Erreur, fonction cout: l1 & l2 de taille différente")
        return None

    if len(l1) == 0:
        logger.error("Erreur, fonction cout: liste vide")
        return None

    match methode.lower():
        case 'absolue':
            return np.mean([abs(x-y) for x, y in zip(l1, l2)])
        case 'carre':
            return np.mean([(x-y)**2 for x, y in zip(l1, l2)])
        case 'racine':
            return np.sqrt(np.mean([(x-y)**2 for x, y in zip(l1, l2)]))
        case _:
            logger.error("Erreur, fonction cout - methode '%s' inconnue", methode)
            return None


def classement_zipf(dico):
    """
    Trie un dictionnaire de mots : occurrence et leur assigne un rang en fonction du nombre
    d'occurrences
    :param dico: <dict> dictionnaire de mot: occurrences
    :return: <list> {"rang": <int>, "mot": <str>, "frequence": <int>}
    """
    ranked = []
    for rang, couple in enumerate(sorted(dico.items(), key=lambda item: item[1],
                                         reverse=True), start=1):
        ranked.append({"rang": rang,
                       "mot": couple[0],
                       "frequence": couple[1]})
    return ranked


def zipf_process(bag):
    """
    Récupère une liste de mot et applique les traitements pour l'analyse de la distribution de zipf
    1. calcul de la fréquence
    2. trier les mots par fréquence
    3. calculer la constante moyenne
    4. calculer la fréquence théorique moyenne
    5. déterminer le coefficient avec le cout absolu moyen le plus bas
    :param bag: <list> liste de <str>
    :return: <dict>
    """
    # Trie du sac de mot
    classement = classement_zipf(freq_mot(bag))
    rang, freq_reel = zip(*[(e['rang'], e['frequence']) for e in classement])

    # Déterminer la constante moyenne
    const_moy = np.mean([e['rang'] * e['frequence'] for e in classement])

    # Déterminer le coefficient avec le cout minimum
    coefs = list(np.arange(0.86, 1.3, 0.01))
    freq_theorique = {coef: [zipf_freq_theorique(const_moy, rg, coef) for rg in rang]
                      for coef in coefs}
    cout_p_coef = {coef: cout(freq_reel, freq_theorique[coef], 'absolue')
                   for coef in coefs}
    cout_min = min(cout_p_coef.values())
    coef_min = list(cout_p_coef.keys())[list(cout_p_coef.values()).index(cout_min)]

    return {
        'const_moy': const_moy,
        'cout_min': cout_min,
        'coef_min': coef_min,
        'rang': rang,
        'freq_reel': freq_reel,
        'cout_p_coef': cout_p_coef,
        'freq_theorique': freq_theorique[coef_min]
    }


def zipf_freq_theorique(constante, rang, coef):
    """
    Calcul la fréquence théorique d'un mot selon son rang, la constante du texte et un coefficient
    d'ajustement
    :param constante: <int> constante déterminé par la distribution de Zipf
    :param rang: <int> rang du mot selon sa fréquence
    :param coef: <float> variable d'ajustement
    :return: <float> fréquence théorique zipfienne
    """
    return constante / (rang ** coef)


def hapax(bag):
    """
    Compte le nombre de mots n'ayant qu'une seule occurrence
    :param bag: <list> liste des mots
    :return: <dict> Nombre d'hapax et ratio par rapport à tout le texte et tous les mots
    """
    classement = classement_zipf(freq_mot(bag))
    nb_hapax = len([e['mot'] for e in classement if e['frequence'] == 1])

    hapax_data = {
        'nombres': nb_hapax,
        'ratio_mots_uniques': nb_hapax/len(classement),
        'ratio_texte': nb_hapax/len(bag)
    }

    return hapax_data
