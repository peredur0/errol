print("Ajout de l'utilisateur de service");
db.getSiblingDB("errol").runCommand({
  createUser: "mongo_errol",
  pwd: "<CHANGE ME>",
  roles: [
    { role: "readWrite", db: "errol" },
  ],
});
