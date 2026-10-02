"""Pré-processamento de páginas e reconhecimento óptico de caracteres."""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from .classificador import classificar_materia
from .perspectiva import corrigir_perspectiva
from .exercicios import montar_exercicios
from .resumo import resumir

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
        "palavras_chave": ("sql", "database", "consulta sql", "join", "normalizacao", "banco de dados", "relacional", "transacao", "chave estrangeira"),
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
        "palavras_chave": ("inteligencia artificial", "machine learning", "deep learning", "rede neural", "redes neurais", "aprendizado supervisionado", "aprendizado de maquina", "ia generativa"),
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
    "programacao": {
        "titulo": "Programação e Desenvolvimento de Software",
        "palavras_chave": ("programacao", "linguagem de programacao", "codigo fonte", "python", "javascript", "java", "variavel", "funcao recursiva", "orientacao a objetos", "heranca", "encapsulamento", "compilador"),
        "descricao": "O conteúdo aborda programação, linguagens e construção de soluções por meio de código.",
        "capitulo": "Fundamentos de programação e desenvolvimento de software",
        "conceito": "Relacionar instruções, dados e estruturas de controle para construir programas que resolvem problemas.",
    },
    "engenharia_software": {
        "titulo": "Engenharia de Software",
        "palavras_chave": ("engenharia de software", "requisito funcional", "requisito nao funcional", "caso de uso", "historia de usuario", "ciclo de vida do software", "teste unitario", "integracao continua", "arquitetura de software", "metodologia agil"),
        "descricao": "O material trata de requisitos, arquitetura, testes ou qualidade no desenvolvimento de software.",
        "capitulo": "Requisitos, projeto e qualidade de software",
        "conceito": "Compreender como requisitos, projeto, implementação e testes se conectam no ciclo de vida de um sistema.",
    },
    "seguranca": {
        "titulo": "Segurança da Informação",
        "palavras_chave": ("seguranca da informacao", "criptografia", "criptografico", "autenticacao multifator", "controle de acesso", "vulnerabilidade", "ransomware", "phishing", "firewall", "ataque cibernetico"),
        "descricao": "A página aborda proteção de sistemas e dados, ameaças digitais ou mecanismos de segurança.",
        "capitulo": "Proteção de sistemas, dados e redes",
        "conceito": "Identificar ameaças e relacionar controles de segurança à confidencialidade, integridade e disponibilidade.",
    },
    "sistemas_operacionais": {
        "titulo": "Sistemas Operacionais",
        "palavras_chave": ("sistemas operacionais", "kernel", "gerenciamento de memoria", "sistema de arquivos", "escalonamento de processos", "memoria virtual", "chamada de sistema", "sistema operacional"),
        "descricao": "O conteúdo aborda o funcionamento do sistema operacional, processos, memória ou arquivos.",
        "capitulo": "Processos, memória e sistemas de arquivos",
        "conceito": "Entender como o sistema operacional administra recursos e oferece serviços aos programas.",
    },
    "geografia": {
        "titulo": "Geografia",
        "palavras_chave": ("geografia", "cartografia", "latitude", "longitude", "coordenadas geograficas", "relevo", "bioma", "clima", "urbanizacao", "globalizacao", "territorio", "placas tectonicas"),
        "descricao": "A página aborda geografia, espaço geográfico, cartografia, ambiente, população ou relações territoriais.",
        "capitulo": "Espaço geográfico e relações socioambientais",
        "conceito": "Analisar como fenômenos naturais e ações humanas organizam e transformam o espaço geográfico.",
    },
    "portugues": {
        "titulo": "Língua Portuguesa",
        "palavras_chave": ("lingua portuguesa", "gramatica", "ortografia", "sintaxe", "semantica", "classe gramatical", "interpretacao de texto", "figura de linguagem", "redacao", "analise sintatica"),
        "descricao": "O material apresenta conteúdos de língua portuguesa, leitura, gramática ou produção textual.",
        "capitulo": "Leitura, gramática e produção textual",
        "conceito": "Relacionar recursos da língua à construção de sentido e à comunicação clara em diferentes textos.",
    },
    "literatura": {
        "titulo": "Literatura",
        "palavras_chave": ("literatura", "romantismo", "realismo", "modernismo", "narrador", "eu lirico", "genero literario", "escola literaria", "poema", "poesia", "cronica"),
        "descricao": "O conteúdo trata de textos literários, gêneros, autores ou movimentos literários.",
        "capitulo": "Gêneros e movimentos literários",
        "conceito": "Interpretar escolhas narrativas e recursos de linguagem considerando o contexto e o gênero da obra.",
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
    perspectiva_corrigida: bool = False


def _normalizar_texto_para_busca(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return texto.lower()


def detectar_conteudo_assistente(texto: str) -> dict[str, object]:
    linhas = [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]
    texto_normalizado = re.sub(r"[^a-z0-9]+", " ", _normalizar_texto_para_busca(" ".join(linhas))).strip()

    if not linhas:
        disciplina_padrao = {
            "titulo": "Material didático genérico",
            "capitulo": "Tema não identificado",
            "conceito": "O texto reconhecido não foi suficiente para identificar o assunto com confiança.",
        }
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
        score = sum(
            1 for termo in dados["palavras_chave"]
            if f" {termo} " in f" {texto_normalizado} "
        )
        if score > 0:
            scores[nome_disciplina] = score

    if not scores:
        palavras_chave_gerais = {
            "matematica": ("algebra", "matriz", "geometria", "equacao", "integral", "derivada", "calculo"),
            "biologia": ("biologia", "celula", "genetica", "dna", "organelo", "membrana", "genoma"),
            "quimica": ("quimica", "atomo", "molecula", "reacao", "elemento", "ligacao", "solucao", "composto"),
            "historia": ("historia", "imperio", "republica", "colonial", "revolucao", "brasil"),
            "fisica": ("fisica", "forca", "energia", "movimento", "velocidade", "eletricidade", "onda"),
        }
        for nome_disciplina, termos in palavras_chave_gerais.items():
            if any(f" {termo} " in f" {texto_normalizado} " for termo in termos):
                scores[nome_disciplina] = 1

    disciplinas_ordenadas = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    # Classificador treinado (backend/classificador.py): quando confiante, a matéria dele vem primeiro.
    previsao = classificar_materia(texto)
    metodo_materia, confianca_materia = "regras", None
    if previsao and previsao[0] in DISCIPLINAS:
        materia_prevista, confianca_materia = previsao
        disciplinas_ordenadas = [(materia_prevista, float("inf"))] + [d for d in disciplinas_ordenadas if d[0] != materia_prevista]
        metodo_materia = "modelo"
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
    # Lacunas tiradas do próprio texto (backend/exercicios.py) + pergunta discursiva da matéria.
    exercicios_revisao, gabarito_exercicios = montar_exercicios(texto, livro_melhor, gerar_exercicios_revisao(texto, livro_melhor))

    return {
        "livro": livro_melhor["titulo"],
        "descricao": livro_melhor["descricao"],
        "figuras": figuras[:4],
        "disciplinas": disciplinas or ["Material didático genérico"],
        "metodo_materia": metodo_materia,
        "confianca_materia": round(confianca_materia, 3) if confianca_materia is not None else None,
        "capitulo": livro_melhor.get("capitulo", "Tema principal do conteúdo"),
        "conceito": livro_melhor.get("conceito", "Esse material contribui para o entendimento do tema central."),
        "autor": autor,
        "resumo_estudo": resumo_estudo,
        "exercicios_revisao": exercicios_revisao,
        "gabarito_exercicios": gabarito_exercicios,
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
    # Resumo extrativo (backend/resumo.py): as frases mais representativas do texto, inteiras e na ordem original.
    frases = resumir(texto, tuple(disciplina.get("palavras_chave", ())))
    if frases:
        return f"{titulo}. " + " ".join(frases)
    cabecalho = f"{titulo} — {capitulo}."
    return f"{cabecalho} {conceito[:110].rstrip()}." if conceito else cabecalho


def gerar_exercicios_revisao(texto: str, disciplina: dict[str, str]) -> list[str]:
    titulo = _normalizar_texto_para_busca(disciplina.get("titulo", "material de estudo"))

    if "algoritmo" in titulo:
        return [
            "Explique a diferença entre busca em largura e busca em profundidade com um exemplo simples.",
            "Descreva como um grafo pode representar um problema prático e indique o caminho mínimo entre dois nós.",
            "Analise a complexidade de tempo de um algoritmo e compare com uma solução alternativa.",
        ]
    if "banco" in titulo:
        return [
            "Escreva uma consulta SQL que recupere dados de duas tabelas relacionadas por chave estrangeira.",
            "Explique por que a normalização melhora o armazenamento e evita redundância de informações.",
            "Descreva a diferença entre SELECT, JOIN e GROUP BY em um contexto prático.",
        ]
    if "rede" in titulo:
        return [
            "Explique a função dos protocolos TCP e IP na comunicação entre computadores.",
            "Descreva como o DNS resolve nomes de domínio e por que isso é fundamental para a internet.",
            "Compare as camadas da arquitetura de redes e seu papel na transmissão de dados.",
        ]
    if "intelig" in titulo:
        return [
            "Defina o que é treinamento de modelo e explique a diferença entre dados de treino e teste.",
            "Descreva como a classificação funciona em um problema de aprendizado supervisionado.",
            "Explique por que a qualidade dos dados impacta diretamente o desempenho de um modelo.",
        ]
    if "programacao" in titulo:
        return [
            "Explique como variáveis, condições e repetições ajudam a construir um programa.",
            "Escreva um exemplo curto de código que resolva um problema descrito no material.",
            "Descreva como funções ou classes ajudam a organizar e reutilizar código.",
        ]
    if "engenharia de software" in titulo:
        return [
            "Diferencie um requisito funcional de um requisito não funcional usando exemplos.",
            "Descreva como testes unitários ajudam a verificar o comportamento de um componente.",
            "Explique como uma história de usuário pode orientar a implementação de uma funcionalidade.",
        ]
    if "seguranca" in titulo:
        return [
            "Explique como a criptografia protege a confidencialidade de uma informação.",
            "Identifique um risco de segurança apresentado no material e proponha uma mitigação.",
            "Diferencie autenticação de controle de acesso em um sistema.",
        ]
    if "sistemas operacionais" in titulo:
        return [
            "Explique como o sistema operacional distribui recursos entre processos.",
            "Descreva a função da memória virtual ou do sistema de arquivos.",
            "Compare processo e thread com base no conteúdo estudado.",
        ]
    if "matemat" in titulo:
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


INCLINACAO_MAXIMA = 15.0
LADO_MINIMO_OCR = 2000


def _ampliar_para_ocr(tons_cinza: np.ndarray) -> np.ndarray:
    """Amplia imagens pequenas: o Tesseract erra muito quando as letras têm poucos pixels de altura."""
    maior_lado = max(tons_cinza.shape[:2])
    if maior_lado >= LADO_MINIMO_OCR:
        return tons_cinza
    fator = min(2.0, LIMITE_LADO / maior_lado)
    return cv2.resize(tons_cinza, None, fx=fator, fy=fator, interpolation=cv2.INTER_CUBIC)


def _normalizar_iluminacao(tons_cinza: np.ndarray) -> np.ndarray:
    """Divide a imagem pelo próprio fundo estimado, removendo sombras e luz desigual.

    A dilatação apaga as letras (escuras) e o mediano grande suaviza o que sobra:
    o resultado aproxima o papel sem texto. Dividir por ele deixa o fundo uniforme.
    """
    fundo = cv2.medianBlur(cv2.dilate(tons_cinza, np.ones((7, 7), np.uint8)), 31)
    return cv2.divide(tons_cinza, fundo, scale=255)


def _medir_inclinacao(binaria: np.ndarray) -> float:
    """Ângulo em que as linhas de texto ficam mais "nítidas" na projeção horizontal.

    Para cada ângulo testado, soma a tinta de cada linha de pixels: com o texto alinhado,
    linhas de texto e entrelinhas alternam entre somas altas e baixas, e a variância é máxima.
    Diferente do retângulo mínimo, bordas, linhas de formulário e sujeira quase não pesam.
    """
    tinta = 255 - binaria
    escala = 1000 / max(tinta.shape)
    if escala < 1:
        tinta = cv2.resize(tinta, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    altura, largura = tinta.shape
    centro = (largura / 2, altura / 2)

    def nitidez(angulo: float) -> float:
        matriz = cv2.getRotationMatrix2D(centro, angulo, 1.0)
        girada = cv2.warpAffine(tinta, matriz, (largura, altura), flags=cv2.INTER_NEAREST, borderValue=0)
        return float(np.var(girada.sum(axis=1, dtype=np.float64)))

    grosso = max(np.arange(-INCLINACAO_MAXIMA, INCLINACAO_MAXIMA + 0.01, 1.0), key=nitidez)
    return float(max(np.arange(grosso - 1, grosso + 1.01, 0.1), key=nitidez))


def _corrigir_inclinacao(binaria: np.ndarray) -> tuple[np.ndarray, float]:
    if cv2.countNonZero(255 - binaria) < 20:
        return binaria, 0.0
    correcao = round(_medir_inclinacao(binaria), 2)
    if abs(correcao) < 0.2:
        return binaria, 0.0
    altura, largura = binaria.shape[:2]
    matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), correcao, 1.0)
    alinhada = cv2.warpAffine(
        binaria, matriz, (largura, altura), flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=255,
    )
    return alinhada, correcao


def processar(imagem: np.ndarray) -> ResultadoProcessamento:
    # Parâmetros escolhidos com o conjunto de treino do FUNSD; ver docs/AVALIACAO.md.
    # Foto tirada de lado: recorta e endireita a folha antes de tudo (backend/perspectiva.py).
    folha, perspectiva_corrigida = corrigir_perspectiva(imagem)
    tons_cinza = cv2.cvtColor(folha, cv2.COLOR_BGR2GRAY)
    ampliada = _ampliar_para_ocr(tons_cinza)
    iluminacao_uniforme = _normalizar_iluminacao(ampliada)
    sem_ruido = cv2.medianBlur(iluminacao_uniforme, 3)
    _, binaria = cv2.threshold(sem_ruido, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
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
        perspectiva_corrigida=perspectiva_corrigida,
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
