"""Guarda-roupa: chapéus, cores do corpo, rastros e o creeper carregado.

Só dados (sem Qt), pra o progresso também saber o que cada nível desbloqueia.
Os desenhos usam a resolução "fina" do sprite (16 de largura = a cabeça toda).
"""

# Chapéus: grade em pixels finos, coluna onde a grade começa (negativa = passa da cabeça)
# e quantas linhas de baixo ficam por cima da cabeça.
HATS = {
    "abobora": {
        "nome": "Abóbora esculpida", "nivel": 5, "x": 3, "sobre": 1,
        "grade": [
            "....gG....",
            ".....G....",
            ".ooOooOoo.",
            "ooOyooyOoo",
            "ooOooooOoo",
            "ooOoyyoOoo",
            ".ooOooOoo.",
        ],
        "cores": {"o": "#F28C1E", "O": "#C8650E", "y": "#FFD54F", "g": "#5D8A2E", "G": "#3E6B1E"},
    },
    "cartola": {
        "nome": "Cartola", "nivel": 12, "x": 2, "sobre": 1,
        "grade": [
            "..kkkkkkkk..",
            "..kKKkkkkk..",
            "..kKkkkkkk..",
            "..kkkkkkkk..",
            "..rrrrrrrr..",
            "kkkkkkkkkkkk",
        ],
        "cores": {"k": "#141414", "K": "#3A3A3A", "r": "#C62828"},
    },
    "coroa": {
        "nome": "Coroa", "nivel": 21, "x": 2, "sobre": 1,
        "grade": [
            ".y...yy...y.",
            ".yy..yy..yy.",
            ".yyyyyyyyyy.",
            ".yRyyBByyRy.",
            ".YYYYYYYYYY.",
        ],
        "cores": {"y": "#FFD54F", "Y": "#C79100", "R": "#E53935", "B": "#42A5F5"},
    },
    "capacete": {
        "nome": "Capacete de diamante", "nivel": 28, "x": -1, "sobre": 4,
        "grade": [
            "...dddddddddddd...",
            ".ddDDDDDDDDDDDDdd.",
            "dDDLLDDDDDDDDDDDDd",
            "dDDDDDDDDDDDDDDDDd",
            "dDd............dDd",
            "dDd............dDd",
            "dd..............dd",
        ],
        "cores": {"d": "#1E9C8C", "D": "#4AEDD9", "L": "#C8FFF6"},
    },
}

# Cores do corpo: os 7 tons do verde original, do mais escuro ao mais claro, trocados.
SKINS = {
    "neve": {
        "nome": "Neve", "nivel": 8,
        "tons": ["#5C7A99", "#8FAACC", "#B7CDE6", "#D3E3F3", "#E8F1FA", "#F7FBFF", "#FFFFFF"],
    },
    "outono": {
        "nome": "Outono", "nivel": 15,
        "tons": ["#6B2E0F", "#8E3F12", "#B5541A", "#D2701F", "#E8902E", "#F2B45A", "#F9D9A0"],
    },
    "noturno": {
        "nome": "Noturno", "nivel": 23,
        "tons": ["#14081F", "#24103A", "#371A55", "#4B2A73", "#6A3F99", "#9465C7", "#C9A6EE"],
        "rosto": "#E079FA",   # no corpo escuro, o rosto brilha
    },
}

TRAILS = {
    "folhas": {"nome": "Folhas", "nivel": 10},
    "faiscas": {"nome": "Faíscas", "nivel": 19},
    "coracoes": {"nome": "Corações", "nivel": 27},
}

CHARGED = {"id": "carregado", "nome": "Creeper carregado", "nivel": 30}

# Tudo que um nível pode desbloquear, no formato dos itens (id, nome, nivel) + o tipo.
UNLOCKS = (
    [{"id": k, "nome": v["nome"], "nivel": v["nivel"], "tipo": "chapeu"} for k, v in HATS.items()]
    + [{"id": k, "nome": v["nome"], "nivel": v["nivel"], "tipo": "cor"} for k, v in SKINS.items()]
    + [{"id": k, "nome": v["nome"], "nivel": v["nivel"], "tipo": "rastro"} for k, v in TRAILS.items()]
    + [{**CHARGED, "tipo": "carregado"}]
)
