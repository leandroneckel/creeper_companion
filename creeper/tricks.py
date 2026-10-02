"""Comportamentos que o creeper aprende subindo de nível (só dados, sem Qt)."""

TRICKS = {
    "chamar": {"nome": "Vir quando chamado", "nivel": 3},
    "bolinha": {"nome": "Brincar de bolinha", "nivel": 11},
    "sozinho": {"nome": "Brincar sozinho", "nivel": 17},
    "esconde": {"nome": "Esconde-esconde", "nivel": 25},
    "janelas": {"nome": "Subir nas janelas", "nivel": 29},
}

UNLOCKS = [{"id": k, "nome": v["nome"], "nivel": v["nivel"], "tipo": "truque"} for k, v in TRICKS.items()]
