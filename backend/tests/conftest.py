import os

# Ordinary unit tests must never depend on or call the public internet.
os.environ["WIKIDATA_ENABLED"] = "false"
os.environ["CONCEPTNET_ENABLED"] = "false"
os.environ["TENCENT_WORD2VEC_ENABLED"] = "false"
