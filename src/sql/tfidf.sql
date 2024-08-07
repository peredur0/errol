SELECT mot FROM nlp_mots_corpus ORDER by freq_corpus DESC;
SELECT mot FROM nlp_mots_corpus ORDER by freq_spam DESC;
SELECT mot FROM nlp_mots_corpus ORDER by freq_ham DESC;
SELECT mot FROM nlp_mots_corpus ORDER by freq_documents DESC;
SELECT mot FROM nlp_mots_corpus ORDER by freq_ham, freq_spam DESC;
SELECT mot FROM nlp_mots_corpus ORDER by freq_spam, freq_ham DESC;
SELECT mot FROM nlp_mots_corpus WHERE freq_ham >= 2*freq_spam ORDER BY freq_ham DESC;
SELECT mot FROM nlp_mots_corpus WHERE freq_spam >= 2*freq_ham ORDER BY freq_spam DESC;
SELECT mot, freq_ham/freq_spam as "ratio ham/spam" FROM nlp_mots_corpus WHERE freq_ham > 0 AND freq_spam > 0 ORDER BY "ratio ham/spam" DESC;
SELECT mot, freq_spam/freq_ham as "ratio spam/ham" FROM nlp_mots_corpus WHERE freq_ham > 0 AND freq_spam > 0 ORDER BY "ratio spam/ham" DESC;