-- O backend grava o processamento, envia a miniatura ao Storage e então registra o caminho dela.
-- Libera o UPDATE apenas dessa coluna; as demais continuam imutáveis para o papel nexo_app.
grant update (miniatura_caminho) on nexo.processamentos to nexo_app;
