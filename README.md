# Stream Deck

Este repo ahora incluye dos variantes:

- `Stream_deck_v2.py` → versión original basada en Tkinter/CustomTkinter.
- `Stream_deck_qt.py` → nueva versión simplificada basada en **Qt (PySide6)**, enfocada en fluidez y facilidad de uso.

## Ejecutar versión Qt

1. Instalar dependencia:

```bash
pip install PySide6
```

2. Ejecutar:

```bash
python Stream_deck_qt.py
```

## Qué trae la versión Qt (MVP)

- Grid de 16 botones con selección rápida.
- Editor simple (Nombre + Acción + Valor).
- Acciones disponibles:
  - Abrir programa
  - Abrir sitio web
  - Abrir archivo
  - Pegar texto (al portapapeles)
- Guardado en `streamdeck_qt_profile.json`.
- Botón “Probar” para validar cada acción.

> Nota: esta versión es un primer paso de migración a Qt para reducir lag y simplificar UX. Se pueden portar más funciones avanzadas en iteraciones siguientes.
