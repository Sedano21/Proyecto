# Ronda V68 (23-nov-2026): stock sin rotación por almacén

## Qué se hizo
- En Suministro → Stock sin rotación, cada producto muestra ahora **en qué almacén está y cuánto hay en cada uno**,
  debajo de su stock total. Ejemplo: «Por almacén: ALM-01 30 (15 kg) · ALM-02 20 (10 kg)».
- Los almacenes se ordenan de mayor a menor cantidad.
- Los kilos aparecen solo si el producto tiene definido su peso por unidad.
- Si se filtra por uno o varios almacenes, el desglose muestra solo esos almacenes.

## Pruebas
`tests/test_v68.py`: verifica que el desglose suma lo mismo que los lotes de cada almacén y que la pantalla lo
muestra. Usa solo datos ficticios.
