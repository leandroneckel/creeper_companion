# Creeper Companion

Um creeper de estimação que mora na sua tela. Ele anda em cima da barra de tarefas, sente fome, sede,
cansaço e sono, fala (com bastante humor) e, se for muito cutucado, explode. Depois volta emburrado.

Funciona no **Windows** e no **Linux** (GNOME incluído).

## Como abrir

- **Windows:** dois cliques em `iniciar_windows.bat`. Na primeira vez ele cria o ambiente e instala as dependências.
- **Linux:** `./iniciar_linux.sh`

Ou, manualmente:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip ...
.venv/bin/python main.py                        # Windows: .venv\Scripts\pythonw.exe main.py
```

Só abre uma cópia por vez: rodar de novo apenas traz o creeper de volta da bandeja.

## Como interagir

| Ação | Como |
|---|---|
| Ver como ele está | Passe o mouse em cima: aparece a barra de botões e, logo depois, o painel de status |
| Comer, beber, atividades, dormir | Botões da barra, ou clique direito nele, ou menu do ícone da bandeja |
| Fazer carinho | Passe o mouse de um lado pro outro em cima dele (ou use o botão ❤) |
| Cutucar | Clique nele (cuidado: muitos cutucões em seguida fazem ele chiar e explodir) |
| Carregar | Clique e arraste; ao soltar ele cai. Chacoalhar deixa ele tonto |
| Mandar pra bandeja | Botão de "recolher" na barra; clique no ícone da bandeja pra trazer de volta |
| Acalmar quando estiver chiando | Faça carinho rápido antes de ele explodir |

### Necessidades

Cada uma vai de 0 a 100 (cheio = bem). O painel mostra no estilo da barra de fome do Minecraft.

- **Fome e sede** caem com o tempo e com exercício.
- **Energia** cai com exercício e volta quando ele descansa ou dorme.
- **Sono** cai ao longo do dia (mais rápido à noite) e só volta dormindo.
- **Diversão** cai com o tédio; sobe com atividades, carinho e guloseimas.

Com o app fechado o tempo passa bem mais devagar, e nada cai abaixo de 15. Ele não morre:
no máximo fica de mau humor.

Alguns itens têm efeitos: **café** (tira o sono, mas deixa agitado e atrapalha dormir), **carne podre**
(enjoo), **leite** (cura enjoo e café), **maçã dourada** (fica brilhando, necessidades congeladas por
10 min), **poção de velocidade**. E nunca traga um gato.

### Ele também cuida de você

- Lembra de **beber água** (a cada 60 min de uso).
- Sugere **pausas** depois de 50 min seguidos no computador.
- Depois da meia-noite, manda você **ir dormir**.
- Se você ficar 15 min longe do PC e ele estiver com sono, tira um cochilo e acorda quando você volta.
- Some sozinho quando algum app está em **tela cheia** (jogo, apresentação, vídeo).

Tudo isso pode ser ligado/desligado em **Configurações** (clique direito nele ou no ícone da bandeja).

## Áreas de trabalho virtuais

- **Windows:** a janela é do tipo "tool window". O Windows não a associa a nenhuma área de trabalho
  virtual, então ela aparece em todas, sem precisar de APIs não documentadas.
- **Linux:** a janela é criada fora do controle do gerenciador de janelas (`X11BypassWindowManagerHint`),
  o que a mantém em todas as áreas de trabalho e acima das outras janelas. No GNOME com Wayland o app
  roda via XWayland automaticamente (`QT_QPA_PLATFORM=xcb`), porque o Wayland não permite isso
  para apps comuns.

### Observações para Linux

- No Ubuntu/Debian pode ser preciso: `sudo apt install libxcb-cursor0`.
- O ícone na bandeja no GNOME depende da extensão **AppIndicator** (já vem ativa no Ubuntu).
  Sem ela, o creeper continua funcionando, só não dá pra recolher pra bandeja.
- A detecção de inatividade usa o `org.gnome.Mutter.IdleMonitor` (GNOME) ou `xprintidle`.

## Personalizar

- **Comidas, bebidas e atividades:** `content/itens.yaml`.
- **Falas:** `content/falas.yaml`. Dá pra adicionar quantas quiser em cada situação.
- **Dados salvos:** `%APPDATA%\CreeperCompanion\save.json` (Windows) ou
  `~/.config/creeper-companion/save.json` (Linux).

## Estrutura

```
main.py                 entrada (instância única, Wayland -> XWayland)
creeper/
  app.py                liga tudo: laço principal, lembretes, bandeja, salvamento
  pet.py                comportamento: estados, reações, falas, partículas
  needs.py              necessidades, efeitos, humor
  config.py             configurações e salvamento
  content.py            leitura dos YAML
  art/sprite.py         o creeper em pixel art (gerado por código) e suas expressões
  art/icons.py          ícones 12x12 dos itens e das barras de status
  ui/pet_window.py      janela transparente, balão, barra de botões, painel, mouse
  ui/menus.py           menus estilo Minecraft
  ui/tray.py            ícone da bandeja
  desktop/              integração com o sistema (Windows / Linux)
content/                itens e falas (YAML)
tools/smoke_test.py     teste automático sem tela (python tools/smoke_test.py)
tools/preview_sprites.py  gera uma folha com todas as expressões e ícones
```

## Licença

Código sob a licença [MIT](LICENSE).

## Aviso

Projeto de fã, sem fins comerciais. Não é oficial nem associado à Mojang Studios ou à Microsoft.
"Minecraft" e "Creeper" são marcas da Mojang/Microsoft. Toda a arte deste projeto é desenhada por código;
nenhuma textura do jogo é usada.

## Próximos passos

- Sons (chiado, explosão, mastigar), com opção de mudo.
- XP, níveis e itens desbloqueáveis.
- Executável único (`.exe` no Windows, AppImage no Linux).
- Conversa de verdade com ele via API do Claude (opcional, pago por uso).
