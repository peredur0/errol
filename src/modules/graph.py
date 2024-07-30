# coding: utf-8
"""
Code pour l'affichage des graph
"""

import logging
import os

import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.ticker as tck

logger = logging.getLogger(__name__)
sns.set()


def q50(x):
    """
    Donne la médiane d'une série
    :param x: <Series>
    :return: <float>
    """
    return x.quantile(0.5)


def q90(x):
    """
    Donne la valeur au percentile 90% d'une série
    :param x: <Series>
    :return: <float>
    """
    return x.quantile(0.9)


def compacter(value, pos=None):
    """
    Compact les nombres.
    :param value: <int>
    :param pos: nécessaire pour FuncFormatter
    """
    logger.debug("compacter pos %s", pos)
    if value >= 1000:
        return f'{value/1000:.0f}K'
    return f'{value:.0f}'


def fouille_dash(conf, stats_df, zipf_data, link_df):
    """
    Affiche la reduction des données lors des étapes de la fouille
    :param conf: <Settings>
    :param stats_df: <DataFrame>
    :param zipf_data: <dict>
    :param link_df: <DataFrame>
    :return: <None>
    """
    logger.info("Affichage du graphe d'évolution des données lors de la fouille")
    palette = {'globales': '#1f77b4', 'ham': '#2ca02c', 'spam': '#d62728'}
    fig, axes = plt.subplots(2, 3, figsize=(20, 10))
    fig.figname = "fouilleStats"
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
        axe.set_facecolor('white')
        axe.yaxis.set_major_formatter(tck.FuncFormatter(compacter))
        for cont in axe.containers:
            if key == 'mails':
                axe.bar_label(cont)
            else:
                axe.bar_label(cont, fmt=tck.FuncFormatter(compacter))
        index += 1

    row += 1
    index = 0
    tmp_data = stats_df[(stats_df['etape'] == 'mise_en_base')
                        & (stats_df['categorie'] != 'globales')][['categorie', 'mails']]
    axes[row, index].pie(tmp_data['mails'], labels=tmp_data['categorie'],
                         colors=[palette[key] for key in tmp_data['categorie']],
                         autopct='%1.1f%%')
    axes[row, index].set_title("Répartition finale (ham/spam)")
    axes[row, index].set_facecolor('white')
    index += 1

    axes[row, index].scatter(zipf_data['rang'], zipf_data['freq_reel'], label="réel",
                             marker='+', c="black")
    axes[row, index].plot(zipf_data['rang'], zipf_data['freq_theorique'], label="théorique",
                          c='blue')
    axes[row, index].set_title("Distribution de Zipf (ham+spam)")
    axes[row, index].set_facecolor('white')
    axes[row, index].set_ylabel('fréquence')
    axes[row, index].set_xlabel('rang')
    axes[row, index].set_yscale('log')
    axes[row, index].set_xscale('log')
    axes[row, index].legend()
    zipf_text = f"Constante: {zipf_data['const_moy']:.2f}\nCoefficient: {zipf_data['coef_min']:.2f}"
    axes[row, index].text(1, 1, zipf_text)
    index += 1

    axes[row, index].set_title('Statistiques des liens')
    axes[row, index].set_facecolor('white')
    axes[row, index].get_xaxis().set_visible(False)
    axes[row, index].get_yaxis().set_visible(False)
    text = (f"Adresses mail:\n"
            f"Mean - "
            f"ham: {link_df['ham']['mail']['mean']:.2f} | "
            f"spam: {link_df['spam']['mail']['mean']:.2f}\n"
            f"Q50   - "
            f"ham: {link_df['ham']['mail']['q50']:.2f} | "
            f"spam: {link_df['spam']['mail']['q50']:.2f}\n"
            f"Q90   - "
            f"ham: {link_df['ham']['mail']['q90']:.2f} | "
            f"spam: {link_df['spam']['mail']['q90']:.2f}\n"
            f"Max   - "
            f"ham: {link_df['ham']['mail']['max']:.2f} | "
            f"spam: {link_df['spam']['mail']['max']:.2f}\n"
            f"\n"
            f"url:\n"
            f"Mean - "
            f"ham: {link_df['ham']['url']['mean']:.2f} | "
            f"spam: {link_df['spam']['url']['mean']:.2f}\n"
            f"Q50   - "
            f"ham: {link_df['ham']['url']['q50']:.2f} | "
            f"spam: {link_df['spam']['url']['q50']:.2f}\n"
            f"Q90   - "
            f"ham: {link_df['ham']['url']['q90']:.2f} | "
            f"spam: {link_df['spam']['url']['q90']:.2f}\n"
            f"Max   - "
            f"ham: {link_df['ham']['url']['max']:.2f} | "
            f"spam: {link_df['spam']['url']['max']:.2f}\n"
            f"\n"
            f"Nombres:\n"
            f"Mean - "
            f"ham: {link_df['ham']['nombre']['mean']:.2f} | "
            f"spam: {link_df['spam']['nombre']['mean']:.2f}\n"
            f"Q50   - "
            f"ham: {link_df['ham']['nombre']['q50']:.2f} | "
            f"spam: {link_df['spam']['nombre']['q50']:.2f}\n"
            f"Q90   - "
            f"ham: {link_df['ham']['nombre']['q90']:.2f} | "
            f"spam: {link_df['spam']['nombre']['q90']:.2f}\n"
            f"Max   - "
            f"ham: {link_df['ham']['nombre']['max']:.2f} | "
            f"spam: {link_df['spam']['nombre']['max']:.2f}\n"
            f"\n"
            f"Prix:\n"
            f"Mean - "
            f"ham: {link_df['ham']['prix']['mean']:.2f} | "
            f"spam: {link_df['spam']['prix']['mean']:.2f}\n"
            f"Q50   - "
            f"ham: {link_df['ham']['prix']['q50']:.2f} | "
            f"spam: {link_df['spam']['prix']['q50']:.2f}\n"
            f"Q90   - "
            f"ham: {link_df['ham']['prix']['q90']:.2f} | "
            f"spam: {link_df['spam']['prix']['q90']:.2f}\n"
            f"Max   - "
            f"ham: {link_df['ham']['prix']['max']:.2f} | "
            f"spam: {link_df['spam']['prix']['max']:.2f}\n"
            )
    axes[row, index].text(0.1, -0.05, text, fontsize='small')
    plt.savefig(f'{conf.rapport["images"]}/{fig.figname}.png')
    plt.show()


def feature_correlation(data, conf):
    """
    Génère la matrice de correlation pour les caractéristiques:
    :param data: <dataframe>
    :param conf: <Settings>
    """
    plt.figure(figsize=(17, 10))
    sns.heatmap(data.corr(), annot=True)
    plt.tight_layout()
    plt.savefig(f'{conf.rapport["images"]}/features_corr.png')
    plt.show()


def vecteurs_dash(data_message, data_mot, conf):
    """
    Créé le dashboard après la vectorisation
    :param data_message: <dataframe>
    :param data_mot: <dataframe>
    :param conf: <Settings>
    """
    logger.info("Affichage du tableau de bord de la vectorisation")
    palette = {'ham': '#2ca02c', 'spam': '#d62728'}
    fig, axes = plt.subplots(2, 1, figsize=(10, 5))
    fig.figname = "vectdash"
    dim_df = data_message[data_message['dimensions'] <= 200]
    sns.histplot(data=dim_df[['dimensions', 'categorie']],
                 x='dimensions',
                 hue='categorie',
                 multiple="dodge",
                 shrink=0.8,
                 ax=axes[0],
                 palette=palette,
                 bins=70)
    axes[0].set_title("Répartitions des documents par nombre de dimensions")
    axes[0].set_ylabel("Nombre de documents")

    sum_df = data_message[data_message['somme'] <= 1000]
    sns.histplot(data=sum_df[['somme', 'categorie']],
                 x='somme',
                 hue='categorie',
                 multiple="dodge",
                 shrink=0.8,
                 ax=axes[1],
                 palette=palette,
                 bins=70)
    axes[1].set_title("Répartitions des documents par somme vectorielle")
    axes[1].set_ylabel("Nombre de documents")

    plt.tight_layout()
    plt.subplots_adjust(top=0.918, bottom=0.139, left=0.084, right=0.982, hspace=0.624, wspace=0.2)
    plt.savefig(f'{conf.rapport["images"]}/{fig.figname}.png')
    plt.show()

    max_ham = data_mot['freq_ham'].max()
    max_spam = data_mot['freq_spam'].max()
    maxi = max_ham if max_ham > max_spam else max_spam
    fig, axe = plt.subplots(1, 1, figsize=(10, 10))
    fig.figname = "vectmots"
    fig.tight_layout()
    sns.scatterplot(data=data_mot,
                    x='freq_spam',
                    y='freq_ham',
                    hue='freq_corpus',
                    size='freq_corpus',
                    ax=axe)
    plt.plot([0, maxi], [0, maxi], color='black', linestyle='--')

    axe.set_title("Représentation des mots du vecteurs")
    plt.tight_layout()
    plt.savefig(f'{conf.rapport["images"]}/{fig.figname}.png')
    plt.show()
