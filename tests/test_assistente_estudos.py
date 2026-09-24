import unittest
import unicodedata

from backend.processamento import detectar_conteudo_assistente


def normalizar_texto(texto):
    texto = unicodedata.normalize("NFKD", texto)
    return texto.encode("ascii", "ignore").decode("ascii").lower()


class TestAssistenteEstudos(unittest.TestCase):
    def test_descobre_livro_e_descricao_a_partir_do_texto(self):
        texto = '''
        Capítulo 2
        Álgebra Linear
        Matrizes e sistemas lineares
        Exercícios resolvidos
        '''

        resultado = detectar_conteudo_assistente(texto)

        self.assertIn("livro", resultado)
        self.assertIn("descricao", resultado)
        self.assertIn("figuras", resultado)
        self.assertIn("disciplinas", resultado)
        self.assertTrue(any("algebra" in normalizar_texto(item) for item in resultado["disciplinas"]))
        self.assertIn("matematica", normalizar_texto(resultado["descricao"]))
        self.assertTrue(any("algebra" in normalizar_texto(item) for item in resultado["figuras"]))

    def test_gera_resumo_e_exercicios_para_o_fluxo_de_estudo(self):
        texto = '''
        Algoritmos
        Busca em largura
        Complexidade de tempo
        Grafos e caminhos
        '''

        resultado = detectar_conteudo_assistente(texto)
        resumo = resultado["resumo_estudo"]
        exercicios = resultado["exercicios_revisao"]

        self.assertIn("algoritmos", normalizar_texto(resumo))
        self.assertTrue(len(exercicios) >= 2)
        self.assertTrue(any("grafo" in normalizar_texto(item) for item in exercicios))

    def test_identifica_biologia_quando_o_texto_tem_palavras_do_campo(self):
        texto = '''
        Membrana celular
        DNA e genes
        Estruturas internas da célula
        Biologia molecular
        '''

        resultado = detectar_conteudo_assistente(texto)

        self.assertTrue(any("biologia" in normalizar_texto(item) for item in resultado["disciplinas"]))
        self.assertIn("biologia", normalizar_texto(resultado["descricao"]))

    def test_ignora_falsa_positiva_de_termos_genericos(self):
        texto = '''
        Resumo do capítulo
        Tema geral de estudos
        Revisão de conteúdo
        '''

        resultado = detectar_conteudo_assistente(texto)

        self.assertIn("disciplinas", resultado)
        self.assertTrue(len(resultado["disciplinas"]) >= 1)
        self.assertNotIn("Álgebra Linear e Geometria Analítica", resultado["livro"])

    def test_detecta_autor_separado_do_resumo(self):
        texto = '''
        Capítulo 2
        Álgebra Linear
        Professor: Ana Souza
        Matrizes e sistemas lineares
        '''

        resultado = detectar_conteudo_assistente(texto)

        self.assertIn("autor", resultado)
        self.assertIn("ana", normalizar_texto(resultado["autor"]))
        self.assertLess(len(resultado["resumo_estudo"]), 220)
        self.assertNotIn("professor", normalizar_texto(resultado["resumo_estudo"]))


if __name__ == "__main__":
    unittest.main()
