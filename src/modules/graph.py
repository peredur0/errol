# coding: utf-8
"""
Code pour l'affichage des graph
"""

import logging
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
    :param pos: <?> nécessaire pour FuncFormatter
    """
    logger.debug("compacter pos %s", pos)
    if value >= 1000:
        return f'{value/1000:.0f}K'
    return f'{value:.0f}'


def fouille_dash(stats_df, zipf_data, link_df):
    """
    Affiche la reduction des données lors des étapes de la fouille
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
            f"ham: {link_df['mean', 'ham']['MAIL']:.2f} | "
            f"spam: {link_df['mean', 'spam']['MAIL']:.2f}\n"
            f"Q50   - "
            f"ham: {link_df['q50', 'ham']['MAIL']:.2f} | "
            f"spam: {link_df['q50', 'spam']['MAIL']:.2f}\n"
            f"Q90   - "
            f"ham: {link_df['q90', 'ham']['MAIL']:.2f} | "
            f"spam: {link_df['q90', 'spam']['MAIL']:.2f}\n"
            f"Max   - "
            f"ham: {link_df['max', 'ham']['MAIL']:.2f} | "
            f"spam: {link_df['max', 'spam']['MAIL']:.2f}\n"
            f"\n"
            f"URL:\n"
            f"Mean - "
            f"ham: {link_df['mean', 'ham']['URL']:.2f} | "
            f"spam: {link_df['mean', 'spam']['URL']:.2f}\n"
            f"Q50   - "
            f"ham: {link_df['q50', 'ham']['URL']:.2f} | "
            f"spam: {link_df['q50', 'spam']['URL']:.2f}\n"
            f"Q90   - "
            f"ham: {link_df['q90', 'ham']['URL']:.2f} | "
            f"spam: {link_df['q90', 'spam']['URL']:.2f}\n"
            f"Max   - "
            f"ham: {link_df['max', 'ham']['URL']:.2f} | "
            f"spam: {link_df['max', 'spam']['URL']:.2f}\n"
            f"\n"
            f"Nombres:\n"
            f"Mean - "
            f"ham: {link_df['mean', 'ham']['NOMBRE']:.2f} | "
            f"spam: {link_df['mean', 'spam']['NOMBRE']:.2f}\n"
            f"Q50   - "
            f"ham: {link_df['q50', 'ham']['NOMBRE']:.2f} | "
            f"spam: {link_df['q50', 'spam']['NOMBRE']:.2f}\n"
            f"Q90   - "
            f"ham: {link_df['q90', 'ham']['NOMBRE']:.2f} | "
            f"spam: {link_df['q90', 'spam']['NOMBRE']:.2f}\n"
            f"Max   - "
            f"ham: {link_df['max', 'ham']['NOMBRE']:.2f} | "
            f"spam: {link_df['max', 'spam']['NOMBRE']:.2f}\n"
            f"\n"
            f"Prix:\n"
            f"Mean - "
            f"ham: {link_df['mean', 'ham']['PRIX']:.2f} | "
            f"spam: {link_df['mean', 'spam']['PRIX']:.2f}\n"
            f"Q50   - "
            f"ham: {link_df['q50', 'ham']['PRIX']:.2f} | "
            f"spam: {link_df['q50', 'spam']['PRIX']:.2f}\n"
            f"Q90   - "
            f"ham: {link_df['q90', 'ham']['PRIX']:.2f} | "
            f"spam: {link_df['q90', 'spam']['PRIX']:.2f}\n"
            f"Max   - "
            f"ham: {link_df['max', 'ham']['PRIX']:.2f} | "
            f"spam: {link_df['max', 'spam']['PRIX']:.2f}\n"
            )
    axes[row, index].text(0.1, -0.05, text, fontsize='small')
    plt.savefig(f'./rapport/img/{fig.figname}.png')
    plt.show()
