SELECT sq.document, ca.nom categorie, sq.dimensions, sq.somme
FROM (SELECT id_message document, COUNT(label) dimensions, SUM(value) somme
        FROM vect_messages
        WHERE vecteur_algo LIKE 'tfidf'
        GROUP BY document) as sq
JOIN messages me ON me.id_message = sq.document
JOIN categories ca ON me.id_categorie = ca.id_categorie;
SELECT vml.label, nmc.freq_corpus, nmc.freq_ham, nmc.freq_spam
FROM vect_mots_labels vml
JOIN nlp_mots_corpus nmc ON vml.id_mot = nmc.id_mot
WHERE vml.vecteur_algo LIKE 'tfidf';