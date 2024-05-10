# coding: utf-8
"""
Code pour l'affichage des graph
"""

import logging
import seaborn as sns
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)
sns.set()


def fouille_dash(stats_df, zipf_data):
    """
    Affiche la reduction des données lors des étapes de la fouille
    :param stats_df: <DataFrame>
    :param zipf_data: <dict>
    :return: <None>
    """
    logger.info("Affichage du graphe d'évolution des données lors de la fouille")
    palette = {'globales': '#1f77b4', 'ham': '#2ca02c', 'spam': '#d62728'}
    fig, axes = plt.subplots(2, 3, figsize=(20, 10))
    plt.subplots_adjust(top=0.922, bottom=0.073, left=0.049, right=0.984, hspace=0.180,
                        wspace=0.215)
    fig.suptitle('Statistiques de la récolte')
    fig.subplots_adjust(wspace=0.4)

    row = 0
    index = 0
    for key, titre in [('mails', 'Documents conservés'), ('mots', 'Nombre de mots'),
                       ('mots_uniques', 'Nombre de mots uniques')]:
        axe = sns.barplot(data=stats_df[[key, 'etape', 'categorie']], x='etape', y=key,
                          hue='categorie', ax=axes[row, index],
                          hue_order=['globales', 'ham', 'spam'],
                          palette=palette)
        axe.set_title(titre)
        axe.legend(ncol=3, loc='best')
        axe.set_xlabel(None)
        axe.set_ylim(0, stats_df[key].max() * 1.2)
        for cont in axe.containers:
            axe.bar_label(cont)
        index += 1

    row += 1
    index = 0
    tmp_data = stats_df[(stats_df['etape'] == 'mise_en_base')
                        & (stats_df['categorie'] != 'globales')][['categorie', 'mails']]
    axes[row, index].pie(tmp_data['mails'], labels=tmp_data['categorie'],
                         colors=[palette[key] for key in tmp_data['categorie']],
                         autopct='%1.1f%%')
    axes[row, index].set_title("Répartition finale (ham/spam)")
    index += 1

    axes[row, index].scatter(zipf_data['rang'], zipf_data['freq_reel'], label="réel",
                             marker='+', c="black")
    axes[row, index].plot(zipf_data['rang'], zipf_data['freq_theorique'], label="théorique",
                          c='blue')
    axes[row, index].set_title("Distribution de Zipf (ham+spam)")
    axes[row, index].set_ylabel('fréquence')
    axes[row, index].set_xlabel('rang')
    axes[row, index].set_yscale('log')
    axes[row, index].set_xscale('log')
    axes[row, index].legend()
    zipf_text = f"Constante: {zipf_data['const_moy']:.2f}\nCoefficient: {zipf_data['coef_min']:.2f}"
    axes[row, index].text(1, 1, zipf_text)

    plt.show()
