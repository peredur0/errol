#! /usr/bin/env python3
# coding: utf-8

"""
Travaille de recherche sur la distribution de zipf.

Recherche de la méthode pour trouver les paramètres avec un cout minimum entre la théorie et
la pratique

Corpus utilisés : ntlk brown, stopwords
utilisation d'un grand dataset préformaté correct avant de l'employer sur mon nettoyage de mail


Après analyse j'obtiens de meilleurs résultats sans retirer les stopswords anglais
et en utilisant une constante moyenne plutôt que médiane
"""
import sys
import re
import nltk
import matplotlib.pyplot as plt
import numpy as np
from nltk.corpus import brown, stopwords
from src.annexes import zipf


if __name__ == '__main__':
    nltk.download("brown")
    nltk.download("stopwords")

    # Récolte
    datas_brown = brown.words()
    stopw = set(stopwords.words('english'))

    # Nettoyage + frequence
    print("-- Récupération du dataset...", end=' ')
    brown_freq = zipf.freq_mot([w.lower() for w in datas_brown if re.match(r'\w+', w)])
    brown_stop_freq = zipf.freq_mot([w.lower() for w in datas_brown if
                                     (re.match(r'\w+', w) and w not in stopw)])
    print("ok")

    print(f"Nombre de mots dans brown:\t"
          f"mots: {len(brown_freq.keys())}\t"
          f"occurences: {sum(list(brown_freq.values()))}")
    print(f"Nombre de mots dans brown stop:\t"
          f"mots: {len(brown_stop_freq.keys())}\t"
          f"occurences: {sum(list(brown_stop_freq.values()))}")

    # Classement zipf
    print("-- Classement selon fréquence...", end=' ')
    zipf_brown = zipf.classement_zipf(brown_freq)
    zipf_brown_s = zipf.classement_zipf(brown_stop_freq)

    zb_rang, zb_freq = zip(*[(e['rang'], e['frequence']) for e in zipf_brown])
    zbs_rang, zbs_freq = zip(*[(e['rang'], e['frequence']) for e in zipf_brown_s])
    print("ok")

    # Détermination des constantes
    print("-- Recherche des constantes...", end=' ')
    zb_const = [e['rang'] * e['frequence'] for e in zipf_brown]

    # Stats
    zb_const_moyen = np.mean(zb_const)
    zb_const_median = np.median(zb_const)

    zbs_const = [e['rang'] * e['frequence'] for e in zipf_brown_s]

    # Stats
    zbs_const_moyen = np.mean(zbs_const)
    zbs_const_median = np.median(zbs_const)
    print("ok")
    print(f"Brown moyenne: {zb_const_moyen:.2f}, mediane: {zb_const_median:.2f}")
    print(f"Brown (- stopwords) moyenne: {zbs_const_moyen:.2f}, mediane: {zbs_const_median:.2f}")

    # Recherche du coefficiant
    print("-- Recherche du coefficiant...", end=' ')
    ls_coef = list(np.arange(0.86, 1.3, 0.01))
    zbmo_th = {coef: [zipf.zipf_freq_theorique(zb_const_moyen, r, coef) for r in zb_rang]
               for coef in ls_coef}
    zbme_th = {coef: [zipf.zipf_freq_theorique(zb_const_median, r, coef) for r in zb_rang]
               for coef in ls_coef}
    zbmoth_cmoy = [zipf.cout(zb_freq, zbmo_th[coef], 'absolue') for coef in ls_coef]
    zbmeth_cmoy = [zipf.cout(zb_freq, zbme_th[coef], 'absolue') for coef in ls_coef]

    zbsmo_th = {coef: [zipf.zipf_freq_theorique(zbs_const_moyen, r, coef) for r in zbs_rang]
                for coef in ls_coef}
    zbsme_th = {coef: [zipf.zipf_freq_theorique(zbs_const_median, r, coef) for r in zbs_rang]
                for coef in ls_coef}
    zbsmoth_cmoy = [zipf.cout(zbs_freq, zbsmo_th[coef], 'absolue') for coef in ls_coef]
    zbsmeth_cmoy = [zipf.cout(zbs_freq, zbsme_th[coef], 'absolue') for coef in ls_coef]
    print("ok")

    print(f"cout min brown moyenne: {min(zbmoth_cmoy):.2f}, median: {min(zbmeth_cmoy):.2f}")
    print(f"cout min brown (- stopwords) moyenne: {min(zbsmoth_cmoy):.2f}, "
          f"median: {min(zbsmeth_cmoy):.2f}")
    zbmot_coef_cmin = list(zbmo_th.keys())[zbmoth_cmoy.index(min(zbmoth_cmoy))]
    zbmet_coef_cmin = list(zbme_th.keys())[zbmeth_cmoy.index(min(zbmeth_cmoy))]

    zbsmot_coef_cmin = list(zbsmo_th.keys())[zbsmoth_cmoy.index(min(zbsmoth_cmoy))]
    zbsmet_coef_cmin = list(zbsme_th.keys())[zbsmeth_cmoy.index(min(zbsmeth_cmoy))]

    print(f"Coefficient min brown moyenne: {zbmot_coef_cmin:.2f}, median: {zbmet_coef_cmin:.2f}")
    print(f"Coefficient min brown (- stopwords) moyenne: {zbsmot_coef_cmin:.2f}, "
          f"median: {zbsmet_coef_cmin:.2f}")

    # Affichage simple
    plt.figure("Distribution de Zipf", figsize=(10, 10))
    plt.subplot(1, 2, 1, title="Distribution de BROWN")
    plt.scatter(zb_rang, zb_freq, label="réel", marker='+', c="black")
    plt.ylabel('fréquence')
    plt.xscale('log')
    plt.yscale('log')
    plt.legend()
    plt.subplot(1, 2, 2, title="Distribution de BROWN sans stop")
    plt.scatter(zbs_rang, zbs_freq, label="réel", marker='+', c='black')
    plt.xlabel('rang')
    plt.ylabel('fréquence')
    plt.xscale('log')
    plt.yscale('log')
    plt.legend()
    plt.show()

    # distribution des constantes
    plt.figure("Distribution des constantes théoriques", figsize=(10, 10))
    plt.subplot(1, 2, 1, title="Distribution constante estimée BROWN")
    plt.hist(zb_const, label='constante', bins=10, color='black')
    plt.axvline(zb_const_moyen, label='moyenne', c="blue")
    plt.axvline(zb_const_median, label='mediane', c="green")
    plt.xlabel("constante théorique")
    plt.ylabel("nombre")
    plt.legend()
    plt.subplot(1, 2, 2, title="Distribution constante estimée BROWN sans stop")
    plt.hist(zbs_const, label='distribution', bins=10, color='black')
    plt.axvline(zbs_const_moyen, label='moyenne', c="blue")
    plt.axvline(zbs_const_median, label='mediane', c="green")
    plt.xlabel('constante theorique')
    plt.ylabel("nombre")
    plt.legend()
    plt.show()

    # Affichage du coup
    plt.figure("Cout moyen par coef et constante", figsize=(10, 10))
    plt.subplot(1, 2, 1, title="Moyenne cout BROWN")
    plt.plot(ls_coef, zbmoth_cmoy, label="constante moyenne", c='blue')
    plt.plot(ls_coef, zbmeth_cmoy, label="constante mediane", c='green')
    plt.xlabel('coefficient')
    plt.ylabel('cout')
    plt.legend()
    plt.subplot(1, 2, 2, title="Moyenne cout BROWN sans stop")
    plt.plot(ls_coef, zbsmoth_cmoy, label="constante moyenne", c='blue')
    plt.plot(ls_coef, zbsmeth_cmoy, label="constante mediane", c='green')
    plt.xlabel('coefficient')
    plt.ylabel('cout')
    plt.legend()
    plt.show()

    # Réel et théorique
    plt.figure("Distribution réelle et théorique", figsize=(10, 10))
    plt.subplot(1, 2, 1, title="BROWN avec estimation")
    plt.scatter(zb_rang, zb_freq, label="réel", marker='+', c="black")
    plt.plot(zb_rang, zbmo_th[zbmot_coef_cmin], label=f'théo avg, coef {zbmot_coef_cmin:.2f}',
             c="blue")
    plt.plot(zb_rang, zbme_th[zbmet_coef_cmin], label=f'théo med, coef {zbmet_coef_cmin:.2f}',
             c="green")
    plt.ylabel('fréquence')
    plt.xscale('log')
    plt.yscale('log')
    plt.legend()
    plt.subplot(1, 2, 2, title="BROWN sans stop avec estimation")
    plt.scatter(zbs_rang, zbs_freq, label="réel", marker='+', c='black')
    plt.plot(zbs_rang, zbsmo_th[zbsmot_coef_cmin],
             label=f'théo avg, coef {zbsmot_coef_cmin:.2f}', c="blue")
    plt.plot(zbs_rang, zbsme_th[zbsmet_coef_cmin],
             label=f'théo med, coef {zbsmet_coef_cmin:.2f}', c="green")
    plt.xlabel('rang')
    plt.ylabel('fréquence')
    plt.xscale('log')
    plt.yscale('log')
    plt.legend()
    plt.show()

    # Process graphique complet
    LIGNE = 2
    COLONNE = 4
    POSITION = 1
    plt.figure("Analyse des données pour zipf", figsize=(10, 10))
    # == Brown
    # Zipf brut
    plt.subplot(LIGNE, COLONNE, POSITION, title="Distribution brown")
    plt.scatter(zb_rang, zb_freq, label="réel", marker='+', c="black")
    plt.ylabel('fréquence')
    plt.xscale('log')
    plt.yscale('log')
    plt.legend()
    # Estimation de la constante
    POSITION += 1
    plt.subplot(LIGNE, COLONNE, POSITION, title="Distribution constante estimée")
    plt.hist(zb_const, label='constante', bins=10, color='black')
    plt.axvline(zb_const_moyen, label='moyenne', c="blue")
    plt.axvline(zb_const_median, label='mediane', c="green")
    plt.xlabel("constante théorique")
    plt.ylabel("nombre")
    plt.legend()
    # cout
    POSITION += 1
    plt.subplot(LIGNE, COLONNE, POSITION, title="Moyenne cout brown")
    plt.plot(ls_coef, zbmoth_cmoy, label="constante moyenne, absolue", c='blue')
    plt.plot(ls_coef, zbmeth_cmoy, label="constante mediane, absolue", c='green')
    plt.ylabel('cout')
    plt.legend()
    # estimation freq
    POSITION += 1
    plt.subplot(LIGNE, COLONNE, POSITION, title="Distribution brown avec estimation")
    plt.scatter(zb_rang, zb_freq, label="réel", marker='+', c="black")
    plt.plot(zb_rang, zbmo_th[zbmot_coef_cmin], label=f'théo avg, coef {zbmot_coef_cmin:.2f}',
             c="blue")
    plt.plot(zb_rang, zbme_th[zbmet_coef_cmin], label=f'théo med, coef {zbmet_coef_cmin:.2f}',
             c="green")
    plt.ylabel('fréquence')
    plt.xscale('log')
    plt.yscale('log')
    plt.legend()

    # == Brown sans stopwords
    # zipf brut
    POSITION += 1
    plt.subplot(LIGNE, COLONNE, POSITION, title="Distribution brown (-stopwords)")
    plt.scatter(zbs_rang, zbs_freq, label="réel", marker='+', c='black')
    plt.xlabel('rang')
    plt.ylabel('fréquence')
    plt.xscale('log')
    plt.yscale('log')
    plt.legend()
    # Estimation de la constante
    POSITION += 1
    plt.subplot(LIGNE, COLONNE, POSITION, title="Distribution constante estimée")
    plt.hist(zbs_const, label='distribution', bins=10, color='black')
    plt.axvline(zbs_const_moyen, label='moyenne', c="blue")
    plt.axvline(zbs_const_median, label='mediane', c="green")
    plt.xlabel('constante theorique')
    plt.ylabel("nombre")
    plt.legend()
    # cout
    POSITION += 1
    plt.subplot(LIGNE, COLONNE, POSITION, title="Moyenne cout brown (-stopwords)")
    plt.plot(ls_coef, zbsmoth_cmoy, label="constante moyenne", c='blue')
    plt.plot(ls_coef, zbsmeth_cmoy, label="constante mediane", c='green')
    plt.ylabel('cout')
    plt.xlabel('coefficient')
    plt.legend()
    # estimation freq
    POSITION += 1
    plt.subplot(LIGNE, COLONNE, POSITION, title="Distribution brown (-stopwords) avec estimation")
    plt.scatter(zbs_rang, zbs_freq, label="réel", marker='+', c='black')
    plt.plot(zbs_rang, zbsmo_th[zbsmot_coef_cmin], label=f'théo avg, coef {zbsmot_coef_cmin:.2f}', c="blue")
    plt.plot(zbs_rang, zbsme_th[zbsmet_coef_cmin], label=f'théo med, coef {zbsmet_coef_cmin:.2f}', c="green")
    plt.xlabel('rang')
    plt.ylabel('fréquence')
    plt.xscale('log')
    plt.yscale('log')
    plt.legend()

    plt.show()

    sys.exit(0)
