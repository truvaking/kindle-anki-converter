import trace
import traceback
import argparse
import yaml
import sqlite3
import pandas
import requests
import math
import os
import json


def lang_code(c):
    language_code_map = {
        "en": "en-us",
        "de": "de"
    }
    return language_code_map[c]


def get_config():
    # Check if this is a first run or not
    first_run = True
    try:
        with open('data/config.yaml') as f:
            first_run = False
    except:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--app_id", required=first_run,
                        help='Application ID from the Dictionnary')
    parser.add_argument("--app_key", required=first_run,
                        help='Application key from the Dictionnary')
    parser.add_argument("--vocab", required=first_run,
                        help='The absolute path to your vocab.db file')
    parser.add_argument("--clear", action='store_true',
                        help='Whether or not vocab.db should be cleared at the end')
    parser.add_argument("--lang", default="en-us")
    parser.add_argument("--skip", action='store_true',
                        help='Whether or not to skip reading from vocab DB')
    config = vars(parser.parse_args())

    if not first_run:
        with open('data/config.yaml', 'r') as f:
            config_disk = yaml.safe_load(f)

        # Update config
        for k in config:
            if config[k] != None:  # TODO: check if value isn't equal to default
                config_disk[k] = config[k]

        config = config_disk

    with open('data/config.yaml', 'w') as f:
        f.write(yaml.safe_dump(config))

    return config


def read_vocab(path, n=None):
    """
    Read the vocab.db file
    n : maximum number of files to read
    """
    # Create a connection with vocabulary db
    conn = sqlite3.connect(path)
    c = conn.cursor()

    # Select appropriate data
    c.execute(f"""
    SELECT DISTINCT words.stem, max(lookups.usage), lang
        FROM words
        JOIN lookups
        ON words.id = lookups.word_key
        GROUP BY words.stem
        ORDER BY words.stem
        {
            "" if n == None
            else f"LIMIT {n} "
        }
    """)

    # Export to JSON
    export = {"stems": [], "usages": [], "langs": []}
    db = c.fetchall()
    for row in db:
        export["stems"].append(row[0])
        export["usages"].append(row[1])
        export["langs"].append(row[2])

    return export


def fetch_definition(word, usage, lang, cred):
    """
    Contact the Oxford Dictionary API and fetch a definition
    TODO: could be improved if passed a list of word?
    """
    url = "https://od-api.oxforddictionaries.com:443/api/v2/entries/" + \
        lang_code(lang) + "/" + word.lower()
    result = requests.get(url, headers=cred).json()

    try:
        # TODO: look into the documentation of Oxford API to understand the
        # json structure
        # TODO: for now only the first definition is fetched, but it is a
        # possibility that there are others, so it should be accounted for
        # in a future update
        return result["results"][0]["lexicalEntries"][0]["entries"][0]["senses"][0]["definitions"][0]
    except:
        print(f'usage: {usage}')
        res = input(f"Definition not found for ->{word}<-, input your own:\n")
        return res


def split_vocab(vocab, split=30):
    n = len(vocab['stems'])
    assert n == len(vocab['usages'])
    assert n == len(vocab['langs'])
    nb_split = math.ceil(n / split)

    for i in range(nb_split):
        partition = {
            "stems": vocab['stems'][i*split:min(n, (i+1)*split)],
            "usages": vocab['usages'][i*split:min(n, (i+1)*split)],
            "langs": vocab['langs'][i*split:min(n, (i+1)*split)]
        }

        with open(f'data/part{i}.json', 'w') as f:
            json.dump(partition, f)


def populate_def(entry):
    # Populate the definitions list
    definitions = []
    for word, usage, lang in zip(entry["stems"], entry["usages"], entry["langs"]):
        cred = {
            "app_id": cfg["app_id"],
            "app_key": cfg["app_key"]
        }
        definitions.append(fetch_definition(word, usage, lang, cred))

    entry["definitions"] = definitions
    return entry


def merge_csv():
    with open('data/vocab.csv', 'w') as output:
        for file in os.listdir("data"):
            if file.endswith(".csv"):
                with open(os.path.join("data", file)) as input:
                    output.write(input.read())


if __name__ == "__main__":
    # Parse the config
    cfg = get_config()

    if not cfg['skip']:
        # Read the vocab database
        vocab = read_vocab(cfg['vocab'])

        # Split the vocab and write them to disk for future processing
        split_vocab(vocab)

    # Query for each partition of the vocab and write it to disk
    for file in os.listdir("data"):
        if file.endswith(".json"):
            with open(os.path.join("data", file)) as f:
                entry = json.loads(f.read())
                entry = populate_def(entry)

                # Write to disk the anki deck
                pandas.DataFrame.from_dict(entry).to_csv(
                    f'data/{file}vocab.csv')

    merge_csv()
