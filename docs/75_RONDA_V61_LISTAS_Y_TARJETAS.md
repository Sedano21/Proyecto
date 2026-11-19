# Ronda V61 (19-nov-2026): parámetros de lista y tarjetas responsivas

## Observaciones
- Al guardar «abastecimiento_almacenes_utilizables» con `[ALM-001, ALM-003, …]` salía «Valor inválido … Expecting
  value»: el campo exigía JSON estricto, con comillas.
- En «Proyección de demanda», con una descripción larga el código del producto se partía letra por letra.

## Qué cambió
- **Parámetros de tipo lista.** Aceptan JSON (`["ALM-001", "ALM-003"]`) y también una lista escrita a mano:
  - con o sin corchetes y con o sin comillas;
  - separada por comas, punto y coma o una por línea.

  Los números se guardan como números.
- **Tarjetas.** El título de la tarjeta (`xcard-head`) ya no aprieta el código. Si el código y la descripción no caben
  en una línea, la descripción baja a la siguiente. La descripción muestra hasta 70 caracteres y la completa al pasar
  el cursor. Se revisó en escritorio (1400 px) y en celular (390 px).

**Pruebas:** `tests/test_v61.py`.
