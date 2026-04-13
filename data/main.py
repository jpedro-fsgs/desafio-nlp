import json

with open("dados_grupo_estudos_new/biblioteca_aneel_gov_br_legislacao_2016_metadados.json", "r") as f:
	dados_2016 = json.load(f)

with open("dados_grupo_estudos_new/biblioteca_aneel_gov_br_legislacao_2021_metadados.json", "r") as f:
	dados_2021 = json.load(f)

with open("dados_grupo_estudos_new/biblioteca_aneel_gov_br_legislacao_2022_metadados.json", "r") as f:
	dados_2022 = json.load(f)