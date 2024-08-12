db = db.getSiblingDB("errol");
db.createCollection("spamassassin", {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["message"],
            properties: {
                categorie: {
                    bsonType: "string",
                    description: "type de mail"
                },
                sujet: {
                    bsonType: "string",
                    description: "sujet du mail"
                },
                expediteur: {
                    bsonType: "string",
                    description: "source du mail"
                },
                message: {
                    bsonType: "string",
                    description: "corps du message après nettoyage"
                },
                langue: {
                    bsonType: "string",
                    description: "langue principale du mail"
                },
            }
        }
    }
});
db.createCollection("kaamelott", {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["message"],
            properties: {
                categorie: {
                    bsonType: "string",
                    description: "type de mail"
                },
                sujet: {
                    bsonType: "string",
                    description: "sujet du mail"
                },
                expediteur: {
                    bsonType: "string",
                    description: "source du mail"
                },
                message: {
                    bsonType: "string",
                    description: "corps du message après nettoyage"
                },
                langue: {
                    bsonType: "string",
                    description: "langue principale du mail"
                },
            }
        }
    }
});
db.createCollection("trained_models", {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            properties: {
                name: {
                    bsonType: "string",
                    description: "nom du modèle"
                },
                chemin: {
                    bsonType: "string",
                    description: "chemin d'accès au modèle"
                },
                langue: {
                    bsonType: "string",
                    description: "langue du modèle"
                },
                creation: {
                    bsonType: "date",
                    description: "date de création du modèle"
                },
                colonnes: {
                    bsonType: "array",
                    description: "colonnes utilisées pour le modèle"
                }
            }
        }
    }
});