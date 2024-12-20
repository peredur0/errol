![Errol logo](./ressources/readme/errol_logo.png)
# Errol - Spam detector project
Project illustrating all steps necessary to generate AI models to detect spam.

### Data sources
- Source email are .eml type gathered from the Apache SpamAssassin project - [Datasets](https://spamassassin.apache.org/old/publiccorpus/) | [Project link](https://spamassassin.apache.org/).
- Some ressources could come from the dedicated Jira project [Jira Portal](https://kaamelott.atlassian.net/servicedesk/customer/portal/2)

### Steps or stages
1. *fouille* - Import .eml files, perform text cleaning and store the content in databases
2. *features* - Process the content to extract statistical information
3. *nlp* - Natural language processing to prepare the vectorization
4. *vecteurs* - Vectorization of all the email content
    - Methods available: TFIDF
5. *train* - Generate AI models based on vectors and features
    - Methods available: Random tree forest, Support vector machine
6. *check* - Use to check simple mail directly from CLI

#### Other commands
- *develop* - Use to develop new feature or to fix bug before insert inside the other steps
- *kaamelott* - Interface with the jira project.

## Installation
### External packages
* libpq-dev
* python3-dev
```bash
sudo apt update && sudo apt install libpq-dev python3-dev -y
```
* Docker engine - [Docker documentation](https://docs.docker.com/engine/install/)

### Instructions
1. Pull the project directly from GitHub.
2. Go to the project root directory
3. Create the python virtual environment
    ```bash
   make venv
    ```
4. Set up the passwords
   - Databases
     - mongo - rename `./config/schema/mongo/template_createUser.js` to `./config/schema/mongo/createUser.js` and set up the *pwd* variable.
     - psql - rename `./config/schema/postgres/template_init.sql` to `./config/schema/postgres/init.sql` and set up the password for user *psql_errol*.
   - Docker
     - rename `./src/infra/.env_template` to `./src/infra/.env` and set up the admin password for mongo and psql containter
   - Program
     - rename `./config/template_errol.ini` to `./config/errol.ini` and provide passwords for mongo and psql service users.
   ```
   NOTE: The jira configuration part is not mandatory
   ```
5. Initialize the docker infrastructure
   ```bash
   make docker_start
   ```

## Usage example
Full process from zero to model creation based on spamassassin data.
Only mail in english (en) will be processed
```bash
make docker_prune
make docker_start
source .venv/bin/activate
./errol.py fouille spamassassin -a ./spamassassin_data/ham1/ ./spamassassin_data/ham2/ -p ./spamassassin_data/spam1/ ./spamassassin_data/spam2/
./errol.py -b features spamassassin -l en
./errol.py -b nlp spamassassin -l en
./errol.py -b vecteurs tfidf -l en -t 500 -i
./errol.py -b train rtf svm -l en
deactivate
```

Check an email file locally
```bash
source .venv/bin/activate
./errol.py check ./test_data/file1.eml
deactivate
```

Run the automatic jira process
```bash
source .venv/bin/activate
./errol.py kaamelott -i
deactivate
```

### Maintenance
#### PSQL database backup
```bash
pg_dump -h localhost -p 5432 -U psql_errol -W -d errol | gzip > "./project_backup/$(date -I)_errol_psql_backup.gz"
```

#### PSQL database restore
```bash
DATE="YYYY-MM-DD"
gunzip -c ./project_backup/$(DATE)_errol_psql_backup.gz | psql -h localhost -p 5432 -U psql_errol -W errol
```

#### Mongo database backup
```bash
mongodump --host=localhost --port=5432 --username=mongo_errol --password=PASWWORD --db=errol --archive="./project_backup/$(date -I)_errol_mongo_backup.gz" --gzip
```

#### Mongo database restore
```bash
DATE="YYYY-MM-DD"
mongorestore --host=localhost --port=5432 --username=mongo_errol --password=PASWWORD --db=errol --archive="./project_backup/$(DATE)_errol_mongo_backup.gz" --gzip
```


## Documentation
Full report and references (FR) : [https://github.com/peredur0/errol/blob/master/rapport/IED_lang_fouille_ia.pdf](https://github.com/peredur0/errol/blob/master/rapport/IED_lang_fouille_ia.pdf)

## Next steps
1. Manage mail forwarded directly to errol
2. Handle database desaster (documents still on mongo but disappeared from psql)

## Contributing
As this project is part of my course of study, any direct external contribution must be avoided.
However, you are welcome to submit your comments by creating an issue or opening a ticket on the [Jira Portal](https://kaamelott.atlassian.net/servicedesk/customer/portal/2).
