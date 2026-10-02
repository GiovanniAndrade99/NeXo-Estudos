import unittest

from backend.classificador import classificar_materia
from backend.exercicios import LACUNA, gerar_lacunas, montar_exercicios, perguntas_mais_relacionadas
from backend.processamento import DISCIPLINAS, detectar_conteudo_assistente

BIOLOGIA = """A célula é a unidade básica da vida. Todos os seres vivos são formados por uma ou mais células,
que realizam funções como nutrição, respiração e reprodução. A membrana plasmática controla a entrada e
a saída de substâncias, permitindo que a célula mantenha seu equilíbrio interno. No núcleo fica o DNA,
molécula que guarda as informações genéticas e coordena a produção de proteínas."""

HISTORIA = """A economia colonial brasileira foi baseada na produção de açúcar nos engenhos do Nordeste,
que dependiam do trabalho escravizado. Portugal mantinha o monopólio comercial sobre a colônia, o que
limitava o comércio com outras nações europeias. No século XVIII, a descoberta de ouro em Minas Gerais
deslocou o centro econômico para o Sudeste e fez crescer as cidades."""


class TestExercicios(unittest.TestCase):
    def test_lacuna_esconde_termo_que_esta_no_gabarito(self):
        exercicios, respostas = gerar_lacunas(BIOLOGIA, DISCIPLINAS["biologia"]["palavras_chave"])
        self.assertTrue(exercicios)
        for exercicio, resposta in zip(exercicios, respostas):
            self.assertIn(LACUNA, exercicio)
            frase = exercicio.split("“", 1)[1].rstrip("”")
            self.assertIn(frase.replace(LACUNA, resposta), BIOLOGIA.replace("\n", " "))

    def test_nao_esconde_palavras_vazias_nem_a_primeira_palavra(self):
        _, respostas = gerar_lacunas(BIOLOGIA)
        for resposta in respostas:
            self.assertNotIn(resposta.lower(), {"a", "o", "que", "de", "uma"})

    def test_monta_tres_exercicios_com_gabarito_alinhado(self):
        exercicios, gabarito = montar_exercicios(BIOLOGIA, DISCIPLINAS["biologia"], ["Pergunta A.", "Pergunta B."])
        self.assertEqual(len(exercicios), 3)
        self.assertEqual(len(gabarito), 3)
        self.assertEqual(gabarito[-1], "Resposta pessoal.")

    def test_texto_sem_frases_usa_so_perguntas_da_materia(self):
        exercicios, gabarito = montar_exercicios("Capítulo 2", DISCIPLINAS["biologia"], ["P1.", "P2.", "P3."])
        self.assertEqual(exercicios, ["P1.", "P2.", "P3."])
        self.assertEqual(set(gabarito), {"Resposta pessoal."})

    def test_escolhe_a_pergunta_mais_ligada_a_pagina(self):
        perguntas = ["Explique variáveis e repetições.", "Explique como classes organizam objetos."]
        texto = "Em Python, uma classe define atributos e métodos para criar objetos."
        self.assertEqual(perguntas_mais_relacionadas(texto, perguntas, 1), ["Explique como classes organizam objetos."])


class TestClassificador(unittest.TestCase):
    def test_classifica_textos_de_materias_diferentes(self):
        self.assertEqual(classificar_materia(BIOLOGIA)[0], "biologia")
        self.assertEqual(classificar_materia(HISTORIA)[0], "historia")

    def test_texto_curto_nao_e_classificado(self):
        self.assertIsNone(classificar_materia("Capítulo 2"))

    def test_assistente_informa_quando_o_modelo_decidiu(self):
        resultado = detectar_conteudo_assistente(HISTORIA)
        self.assertEqual(resultado["metodo_materia"], "modelo")
        self.assertEqual(resultado["livro"], DISCIPLINAS["historia"]["titulo"])
        self.assertGreaterEqual(resultado["confianca_materia"], 0.4)

    def test_tolera_erros_tipicos_de_ocr(self):
        com_erros = BIOLOGIA.replace("o", "0", 6).replace("ç", "c").replace("ã", "a").replace(" a ", " o ")
        self.assertEqual(classificar_materia(com_erros)[0], "biologia")


if __name__ == "__main__":
    unittest.main()
