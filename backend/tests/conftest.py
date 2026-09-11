import os

# API tests exercise the explicit local-model fallback; provider tests inject tiny models.
os.environ["TENCENT_WORD2VEC_ENABLED"] = "false"
