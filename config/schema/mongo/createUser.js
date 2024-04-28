print("Ajout de l'utilisateur de service");
db.getSiblingDB("errol").runCommand({
  createUser: "mongo_errol",
  pwd: "Azerty1234",
  roles: [
    { role: "readWrite", db: "errol" },
  ],
});
