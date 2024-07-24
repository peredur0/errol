SELECT nd.id_mot, vt.label, nd.occurrence, nc.freq_documents
FROM nlp_mots_documents nd
JOIN vect_tfidf_mots_labels vt ON nd.id_mot = vt.id_mot
JOIN nlp_mots_corpus nc ON nd.id_mot = nc.id_mot
WHERE nd.id_message = 1;
