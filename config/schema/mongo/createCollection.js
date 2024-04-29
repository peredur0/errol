db = db.getSiblingDB("errol");
db.createCollection("spamassassin", {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["hash", "message"],
            properties: {
                hash: {
                    bsonType: "string",
                    description: "identifiant unique du message"
                },
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
                liens: {
                    bsonType: "object",
                    description: "information sur les liens et nombres"
                },
            }
        }
    }
});
db.spamassassin.createIndex( { hash: 1 }, { unique: true } );