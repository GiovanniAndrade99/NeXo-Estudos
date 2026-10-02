import unittest

from backend.resumo import extrair_frases, resumir

TEXTO_BIOLOGIA = """
Capítulo 4
A Célula
Professora: Marina Lopes
A célula é a unidade básica da vida. Todos os seres
vivos são formados por uma ou mais células, que
realizam funções como nutrição, respiração e reprodução.
A membrana plasmática controla a entrada e a saída de
substâncias, permitindo que a célula mantenha seu
equilíbrio interno.
No núcleo fica o DNA, molécula que guarda as informações
genéticas e coordena a produção de proteínas.
42
"""


class TestExtrairFrases(unittest.TestCase):
    def test_junta_linhas_quebradas_em_frases_completas(self):
        frases = extrair_frases(TEXTO_BIOLOGIA)
        self.assertIn("A membrana plasmática controla a entrada e a saída de substâncias, "
                      "permitindo que a célula mantenha seu equilíbrio interno.", frases)

    def test_descarta_titulo_autor_e_numero_de_pagina(self):
        texto = " ".join(extrair_frases(TEXTO_BIOLOGIA))
        for intruso in ("Capítulo 4", "Marina", "Professora", "42"):
            self.assertNotIn(intruso, texto)

    def test_descarta_ruido_do_ocr(self):
        frases = extrair_frases("~~ ;;; ## 1 |\nA fotossíntese transforma a luz do sol em energia química nas plantas.")
        self.assertEqual(frases, ["A fotossíntese transforma a luz do sol em energia química nas plantas."])

    def test_desfaz_hifenizacao_do_fim_de_linha(self):
        frases = extrair_frases("O pré-proces-\nsamento melhora muito a leitura feita pelo OCR.")
        self.assertEqual(frases, ["O pré-processamento melhora muito a leitura feita pelo OCR."])

    def test_texto_vazio(self):
        self.assertEqual(extrair_frases(""), [])
        self.assertEqual(resumir(""), [])


class TestResumir(unittest.TestCase):
    def test_respeita_limite_e_quantidade(self):
        frases = resumir(TEXTO_BIOLOGIA, max_frases=2, limite=200)
        self.assertLessEqual(len(frases), 2)
        self.assertLessEqual(len(" ".join(frases)), 200)

    def test_mantem_a_ordem_original(self):
        frases = resumir(TEXTO_BIOLOGIA)
        posicoes = [TEXTO_BIOLOGIA.replace("\n", " ").find(f[:25]) for f in frases]
        self.assertEqual(posicoes, sorted(posicoes))

    def test_frases_inteiras_sem_corte_no_meio(self):
        for frase in resumir(TEXTO_BIOLOGIA):
            self.assertRegex(frase, r"[.!?]$")
            self.assertTrue(frase[0].isupper(), frase)

    def test_prefere_frases_com_termos_centrais(self):
        texto = (
            "O DNA guarda as informações genéticas de cada célula do organismo.\n"
            "Nesta aula, vamos começar com uma pequena revisão do semestre anterior.\n"
            "A célula usa o DNA como molde para produzir proteínas no ribossomo.\n"
        )
        frases = resumir(texto, termos_destaque=("dna", "celula"), max_frases=2)
        self.assertNotIn("Nesta aula", " ".join(frases))


if __name__ == "__main__":
    unittest.main()
