SELECT COUNT(id_message) total_documents FROM controle WHERE nlp_status LIKE 'OK';

SELECT ca.nom categorie, COUNT(co.id_message) documents
FROM controle co
JOIN messages me ON co.id_message = me.id_message
JOIN categories ca ON me.id_categorie = ca.id_categorie
WHERE co.nlp_status LIKE 'OK'
GROUP BY categorie;

SELECT COUNT(id_mot) corpus_mots_uniques, SUM(freq_corpus) corpus_mots FROM nlp_mots_corpus;

SELECT ca.nom categorie, COUNT(DISTINCT(nd.id_mot)) mots_uniques, SUM(nd.occurrence) mots
FROM nlp_mots_documents nd
JOIN messages me ON nd.id_message = me.id_message
JOIN categories ca ON me.id_categorie = ca.id_categorie
GROUP BY categorie;