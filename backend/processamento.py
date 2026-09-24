"""Pré-processamento de páginas e reconhecimento óptico de caracteres."""
from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract

IDIOMAS_OCR = os.getenv("OCR_LANGUAGES", "por+eng")
LIMITE_LADO = 4000
DISCIPLINAS = {
    "algoritmos": {
        "titulo": "Algoritmos e Estruturas de Dados",
        "palavras_chave": ("algoritmo", "algoritmos", "grafo", "grafos", "busca", "ordenacao", "complexidade", "estrutura", "pilha", "fila", "arvore", "hash"),
        "descricao": "A imagem parece tratar de algoritmos, grafos e análise de eficiência de soluções computacionais.",
        "capitulo": "Busca, grafos e complexidade de algoritmos",
        "conceito": "Entender como as estruturas de dados organizam a informação e como a escolha do algoritmo impacta tempo e memória.",
    },
    "banco_de_dados": {
        "titulo": "Banco de Dados",
        "palavras_chave": ("sql", "database", "dados", "consulta", "join", "normalizacao", "modelo", "relacional", "transacao"),
        "descricao": "A imagem parece abordar modelagem de dados, consultas e organização de informações em sistemas de banco de dados.",
        "capitulo": "Modelagem e consultas em banco de dados",
        "conceito": "Estruturar dados de forma consistente e recuperar informações com consultas eficientes.",
    },
    "redes": {
        "titulo": "Redes de Computadores",
        "palavras_chave": ("rede", "redes", "tcp", "ip", "protocolos", "dns", "router", "camada", "osi", "internet"),
        "descricao": "A imagem parece estar relacionada a redes, protocolos e comunicação entre dispositivos.",
        "capitulo": "Protocolos e comunicação em redes",
        "conceito": "Compreender como os protocolos organizam a troca de dados entre computadores e serviços.",
    },
    "ia": {
        "titulo": "Inteligência Artificial",
        "palavras_chave": ("ia", "inteligencia", "artificial", "machine", "learning", "rede", "neuronal", "classificacao", "treinamento", "modelo"),
        "descricao": "A imagem parece contextualizar inteligência artificial, treinamento de modelos e aprendizado de máquina.",
        "capitulo": "Modelos e treinamento de aprendizado de máquina",
        "conceito": "Observar como o modelo aprende padrões a partir de dados e como isso se aplica a classificação e previsão.",
    },
    "matematica": {
        "titulo": "Álgebra Linear e Geometria Analítica",
        "palavras_chave": ("algebra", "linear", "geometria", "matriz", "matrizes", "vetores", "sistemas", "equacao", "funcao", "integral", "derivada", "calculo"),
        "descricao": "A imagem parece representar material didático de matemática, com foco em álgebra linear, matrizes, vetores e resolução de sistemas.",
        "capitulo": "Matrizes, vetores e sistemas lineares",
        "conceito": "Relacionar estruturas matemáticas e operações lineares para resolver problemas e representar dados.",
    },
    "biologia": {
        "titulo": "Biologia Celular e Molecular",
        "palavras_chave": ("biologia", "celula", "genetica", "dna", "rna", "membrana", "biomoleculas", "organelo", "tecido", "organismo"),
        "descricao": "A imagem parece ser de um material de biologia, com destaque para células, estruturas internas e fundamentos da genética.",
        "capitulo": "Estruturas celulares e genética",
        "conceito": "Reforçar a relação entre a estrutura celular e os mecanismos de hereditariedade e funcionamento do organismo.",
    },
    "quimica": {
        "titulo": "Química Geral",
        "palavras_chave": ("quimica", "atomos", "moleculas", "reacao", "tabela", "elementos", "ligacao", "solucao", "ph", "composto"),
        "descricao": "A imagem parece abordar conceitos de química geral, com atenção para átomos, ligações e reações químicas.",
        "capitulo": "Estrutura e reações químicas",
        "conceito": "Relacionar átomos, moléculas e transformações químicas para interpretar fenômenos e processos.",
    },
    "historia": {
        "titulo": "História do Brasil",
        "palavras_chave": ("historia", "brasil", "imperio", "republica", "colonial", "contexto", "revolucao", "governo", "sociedade"),
        "descricao": "A imagem parece ter foco em história e contexto social, com elementos de estudo sobre períodos históricos e acontecimentos relevantes.",
        "capitulo": "Contexto histórico e formação social",
        "conceito": "Reconhecer eventos e transformações históricas que moldaram a sociedade e o país.",
    },
    "fisica": {
        "titulo": "Física Geral",
        "palavras_chave": ("fisica", "forca", "energia", "movimento", "velocidade", "mecanica", "eletricidade", "onda", "campo"),
        "descricao": "A imagem parece ser de física, abordando conceitos de movimento, força, energia e fenômenos físicos.",
        "capitulo": "Movimento e energia",
        "conceito": "Estabelecer a relação entre força, movimento e energia em sistemas físicos.",
    },
}


@dataclass
class ResultadoProcessamento:
    original: np.ndarray
    tons_cinza: np.ndarray
    tratada: np.ndarray
    texto: str
    inclinacao_corrigida_graus: float
    ocr_disponivel: bool
    aviso: str | None = None
    assistente_estudos: dict | None = None
    descricao_processo: str = ""


def _normalizar_texto_para_busca(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return texto.lower()


def detectar_conteudo_assistente(texto: str) -> dict[str, object]:
    linhas = [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]
    texto_normalizado = _normalizar_texto_para_busca(" ".join(linhas))

    if not linhas:
        disciplina_padrao = DISCIPLINAS["algoritmos"]
        autor = _extrair_autor(texto)
        return {
            "livro": "Material didático genérico",
            "descricao": "A imagem parece conter material de estudo, mas ainda não foi possível identificar um livro com clareza.",
            "figuras": ["Resumo visual", "Ilustração de apoio", "Tema do conteúdo"],
            "disciplinas": ["Material didático genérico"],
            "capitulo": disciplina_padrao["capitulo"],
            "conceito": disciplina_padrao["conceito"],
            "autor": autor,
            "resumo_estudo": gerar_resumo_estudo("", disciplina_padrao),
            "exercicios_revisao": gerar_exercicios_revisao("", disciplina_padrao),
        }

    scores = {}
    for nome_disciplina, dados in DISCIPLINAS.items():
        score = sum(1 for termo in dados["palavras_chave"] if termo in texto_normalizado)
        if score > 0:
            scores[nome_disciplina] = score

    if not scores:
        palavras_chave_gerais = {
            "matematica": ("algebra", "matriz", "geometria", "equacao", "sistema", "funcao", "integral", "derivada", "calculo"),
            "biologia": ("biologia", "celula", "genetica", "dna", "organelo", "tecido", "membrana", "genoma"),
            "quimica": ("quimica", "atomo", "molecula", "reacao", "elemento", "ligacao", "solucao", "composto"),
            "historia": ("historia", "imperio", "republica", "colonial", "revolucao", "brasil", "sociedade"),
            "fisica": ("fisica", "forca", "energia", "movimento", "velocidade", "eletricidade", "onda", "campo"),
        }
        for nome_disciplina, termos in palavras_chave_gerais.items():
            if any(termo in texto_normalizado for termo in termos):
                scores[nome_disciplina] = 1

    disciplinas_ordenadas = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    disciplinas = [DISCIPLINAS[nome]["titulo"] for nome, _ in disciplinas_ordenadas[:2]]

    livro_melhor = None
    if disciplinas_ordenadas:
        melhor_disciplina = disciplinas_ordenadas[0][0]
        livro_melhor = DISCIPLINAS[melhor_disciplina]
    else:
        livro_melhor = {
            "titulo": "Material didático generalista",
            "descricao": "A imagem parece ser um material de apoio ao estudo, com conceitos organizados para leitura e revisão.",
            "capitulo": "Tema geral de revisão",
            "conceito": "Esse conteúdo pode ser revisado por meio de leitura guiada e organização dos tópicos centrais.",
        }

    figuras = []
    vistos = set()
    for linha in linhas:
        texto_linha = _normalizar_texto_para_busca(linha)
        if len(linha) <= 3:
            continue
        if any(token in texto_linha for token in ("capitulo", "algebra", "biologia", "quimica", "historia", "geografia", "fisica", "algoritmos", "programacao", "matrizes", "exercicios", "tema", "sistema", "equacao", "dna")):
            chave = linha.lower()
            if chave not in vistos:
                figuras.append(linha)
                vistos.add(chave)

    if not figuras:
        for linha in linhas[:4]:
            palavras = linha.split()
            if 2 <= len(palavras) <= 8:
                chave = linha.lower()
                if chave not in vistos:
                    figuras.append(linha)
                    vistos.add(chave)

    if not figuras:
        figuras = ["Resumo visual", "Tema principal", "Exercícios de revisão"]

    autor = _extrair_autor(texto)
    resumo_estudo = gerar_resumo_estudo(texto, livro_melhor)
    exercicios_revisao = gerar_exercicios_revisao(texto, livro_melhor)

    return {
        "livro": livro_melhor["titulo"],
        "descricao": livro_melhor["descricao"],
        "figuras": figuras[:4],
        "disciplinas": disciplinas or ["Material didático genérico"],
        "capitulo": livro_melhor.get("capitulo", "Tema principal do conteúdo"),
        "conceito": livro_melhor.get("conceito", "Esse material contribui para o entendimento do tema central."),
        "autor": autor,
        "resumo_estudo": resumo_estudo,
        "exercicios_revisao": exercicios_revisao,
    }


def _extrair_autor(texto: str) -> str:
    linhas = [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]
    padroes = (
        "professor",
        "professora",
        "autor",
        "autora",
        "elaborado por",
        "revisado por",
        "created by",
        "by",
    )

    for linha in linhas:
        linha_normalizada = _normalizar_texto_para_busca(linha)
        if any(padrao in linha_normalizada for padrao in padroes):
            if any(termo in linha_normalizada for termo in ("professor", "professora", "autor", "autora", "created by", "by")):
                candidato = linha.split(":")[-1].strip() if ":" in linha else linha
                candidat = candidato.strip(" -—–")
                if candidat and len(candidat) > 2:
                    return candidat

    for linha in linhas:
        if len(linha.split()) <= 5 and any(token.isalpha() for token in linha.split()):
            if not any(token in _normalizar_texto_para_busca(linha) for token in ("capitulo", "algoritmo", "biologia", "quimica", "historia", "fisica", "matriz", "sistema", "equacao", "resumo", "tema", "revisao")):
                return linha

    return "Autor não identificado"


def gerar_resumo_estudo(texto: str, disciplina: dict[str, str]) -> str:
    conceito = disciplina.get("conceito", "Esse material é útil para revisão e consolidação de ideias principais.")
    capitulo = disciplina.get("capitulo", "Tema principal do conteúdo")
    titulo = disciplina.get("titulo", "Material de estudo")
    resumo = f"{titulo} — {capitulo}."
    if conceito:
        resumo = f"{resumo} {conceito[:110].rstrip()}."
    return resumo


def gerar_exercicios_revisao(texto: str, disciplina: dict[str, str]) -> list[str]:
    texto_normalizado = _normalizar_texto_para_busca(texto)
    titulo = disciplina.get("titulo", "material de estudo").lower()

    if "algoritmo" in titulo or any(token in texto_normalizado for token in ("algoritmo", "grafo", "busca", "ordenacao", "complexidade")):
        return [
            "Explique a diferença entre busca em largura e busca em profundidade com um exemplo simples.",
            "Descreva como um grafo pode representar um problema prático e indique o caminho mínimo entre dois nós.",
            "Analise a complexidade de tempo de um algoritmo e compare com uma solução alternativa.",
        ]
    if "banco" in titulo or any(token in texto_normalizado for token in ("sql", "dados", "consulta", "join", "normalizacao")):
        return [
            "Escreva uma consulta SQL que recupere dados de duas tabelas relacionadas por chave estrangeira.",
            "Explique por que a normalização melhora o armazenamento e evita redundância de informações.",
            "Descreva a diferença entre SELECT, JOIN e GROUP BY em um contexto prático.",
        ]
    if "rede" in titulo or any(token in texto_normalizado for token in ("tcp", "ip", "dns", "protocolo", "router", "internet")):
        return [
            "Explique a função dos protocolos TCP e IP na comunicação entre computadores.",
            "Descreva como o DNS resolve nomes de domínio e por que isso é fundamental para a internet.",
            "Compare as camadas da arquitetura de redes e seu papel na transmissão de dados.",
        ]
    if "intelig" in titulo or any(token in texto_normalizado for token in ("machine", "learning", "modelo", "treinamento", "classificacao", "neuronal")):
        return [
            "Defina o que é treinamento de modelo e explique a diferença entre dados de treino e teste.",
            "Descreva como a classificação funciona em um problema de aprendizado supervisionado.",
            "Explique por que a qualidade dos dados impacta diretamente o desempenho de um modelo.",
        ]
    if "matemat" in titulo or any(token in texto_normalizado for token in ("matriz", "vetor", "equacao", "sistema", "geometria")):
        return [
            "Resolva um sistema linear simples e identifique o significado geométrico da solução.",
            "Explique como uma matriz pode representar transformações e dados em problemas práticos.",
            "Compare duas operações lineares e descreva seu efeito sobre o vetor de entrada.",
        ]
    return [
        "Resuma o tema principal da imagem em duas ou três frases usando linguagem própria do estudo.",
        "Liste os conceitos-chave apresentados e explique como eles se relacionam entre si.",
        "Crie um exemplo simples que ilustre o tema central do conteúdo visualizado.",
    ]


def gerar_descricao_processo(texto: str, assistente: dict | None = None) -> str:
    disciplina = (assistente or {}).get("livro") or "material didático geral"
    contexto = (assistente or {}).get("descricao") or "A imagem contém conteúdo de estudo para consulta e revisão."
    texto_base = texto.strip()
    if not texto_base:
        texto_base = "Nenhum texto OCR foi identificado com clareza na imagem."

    return (
        "A imagem foi processada em sequência para melhorar a leitura: primeiro foi convertida para tons de cinza, "
        "depois houve ajuste de contraste e redução de ruído, em seguida a página foi alinhada para corrigir inclinação "
        "e, por fim, aplicada binarização para separar melhor o texto do fundo. "
        f"{contexto} O conteúdo identificado sugere estudo relacionado a {disciplina}. "
        f"Como parte do reconhecimento, o sistema extraiu: \"{texto_base[:280]}\"."
    )


def _configurar_tesseract() -> str:
    executavel = os.getenv("TESSERACT_CMD")
    if not executavel:
        instalacao_padrao = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if instalacao_padrao.is_file():
            executavel = str(instalacao_padrao)
    if executavel:
        pytesseract.pytesseract.tesseract_cmd = executavel
    diretorios_modelos = []
    dados_locais = os.getenv("LOCALAPPDATA")
    if dados_locais:
        diretorios_modelos.append(Path(dados_locais) / "Tesseract-OCR" / "tessdata")
    diretorios_modelos.append(Path(__file__).resolve().parent.parent / ".tessdata")
    for diretorio_modelos in diretorios_modelos:
        if (diretorio_modelos / "por.traineddata").is_file() and (diretorio_modelos / "eng.traineddata").is_file():
            return f'--tessdata-dir "{diretorio_modelos}"'
    return ""


def tesseract_disponivel() -> tuple[bool, str | None]:
    config_dados = _configurar_tesseract()
    try:
        pytesseract.get_tesseract_version()
        idiomas = set(pytesseract.get_languages(config=config_dados))
        ausentes = {idioma for idioma in IDIOMAS_OCR.split("+") if idioma not in idiomas}
        if ausentes:
            return False, "Pacote(s) de idioma ausente(s) no Tesseract: " + ", ".join(sorted(ausentes)) + "."
        return True, None
    except (pytesseract.TesseractNotFoundError, OSError):
        return False, "Tesseract não encontrado. Instale o programa e os idiomas configurados para habilitar OCR."


def decodificar_imagem(conteudo: bytes) -> np.ndarray:
    imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        raise ValueError("O arquivo não parece ser uma imagem válida ou usa um formato não suportado.")
    altura, largura = imagem.shape[:2]
    if largura > LIMITE_LADO or altura > LIMITE_LADO:
        escala = LIMITE_LADO / max(largura, altura)
        imagem = cv2.resize(imagem, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    return imagem


def _corrigir_inclinacao(binaria: np.ndarray) -> tuple[np.ndarray, float]:
    pontos = cv2.findNonZero(255 - binaria)
    if pontos is None or len(pontos) < 20:
        return binaria, 0.0
    angulo = cv2.minAreaRect(pontos)[-1]
    if angulo < -45:
        angulo = 90 + angulo
    if abs(angulo) > 15:
        return binaria, 0.0
    correcao = -float(angulo)
    altura, largura = binaria.shape[:2]
    matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), correcao, 1.0)
    alinhada = cv2.warpAffine(
        binaria, matriz, (largura, altura), flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=255,
    )
    return alinhada, correcao


def processar(imagem: np.ndarray) -> ResultadoProcessamento:
    tons_cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
    contraste = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(tons_cinza)
    sem_ruido = cv2.medianBlur(contraste, 3)
    binaria = cv2.adaptiveThreshold(
        sem_ruido, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 11,
    )
    alinhada, inclinacao = _corrigir_inclinacao(binaria)
    config_dados = _configurar_tesseract()
    disponivel, aviso = tesseract_disponivel()
    texto = ""
    if disponivel:
        try:
            texto = pytesseract.image_to_string(
                alinhada, lang=IDIOMAS_OCR, config=f"--psm 6 {config_dados}".strip(),
            ).strip()
        except pytesseract.TesseractError as erro:
            disponivel = False
            aviso = "O Tesseract não conseguiu processar esta imagem: " + str(erro)
    assistente_estudos = detectar_conteudo_assistente(texto)
    descricao_processo = gerar_descricao_processo(texto, assistente_estudos)
    return ResultadoProcessamento(
        original=imagem, tons_cinza=tons_cinza, tratada=alinhada, texto=texto,
        inclinacao_corrigida_graus=round(inclinacao, 2),
        ocr_disponivel=disponivel, aviso=aviso,
        assistente_estudos=assistente_estudos,
        descricao_processo=descricao_processo,
    )


def codificar_png(imagem: np.ndarray) -> str:
    import base64
    sucesso, buffer = cv2.imencode(".png", imagem)
    if not sucesso:
        raise RuntimeError("Não foi possível gerar a imagem de visualização.")
    return base64.b64encode(buffer.tobytes()).decode("ascii")
