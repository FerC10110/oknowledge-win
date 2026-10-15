"""The interface language: English by default, Spanish opt-in.

The preference lives in the config, as `[web] language`, and the Settings page
writes it there. (On Omarchy it came out of a JSON file shared with my other
plugins; there are no other plugins here, and a machine without Omarchy has no
such file.) The English text is the key, so a missing translation degrades to
English and nothing breaks. This is a separate axis from the language the AI
writes summaries in, `[ai] language`.
"""

from __future__ import annotations

import re

LANGUAGES = ("en", "es")
# Each language written in itself, which is how a language picker names them --
# "Español", never "Spanish". Deliberately not in STRINGS: these are the one
# piece of interface text that must not change with the interface language.
NATIVE_NAMES = {"en": "English", "es": "Español"}

STRINGS = {
    "es": {
        "Library": "Biblioteca",
        "Sections": "Secciones",
        "Filters": "Filtros",
        "Cancel": "Cancelar",
        "CATEGORIES": "CATEGORÍAS",
        "MARKS": "MARCAS",
        "COLLECTIONS": "COLECCIONES",
        "Marks": "Marcas",
        "Collections": "Colecciones",
        "Favorites": "Favoritos",
        "Pinned": "Fijados",
        "Results": "Resultados",
        "Search or paste a link to save it": "Buscá o pegá un link para guardarlo",
        "Layout": "Vista",
        "List": "Lista",
        "Cards": "Tarjetas",
        "Detail": "Detalle",
        "Back to %1": "Volver a %1",
        "Choose a link to read it here.": "Elegí un link para leerlo acá.",
        "Analysing…": "Analizando…",
        "No category": "Sin categoría",
        "Show more": "Ver más",
        "See everything": "Ver todo",
        "Nothing matches “%1”": "Nada coincide con “%1”",
        "Try another word or a tag. If it is a new link, paste it whole with https:// to save it.":
            "Probá con otra palabra o una etiqueta. Si es un link nuevo, pegalo completo con https:// para guardarlo.",
        "There is nothing in %1": "No hay nada en %1",
        "Mark a link from its panel, or move it here from the category chip.":
            "Marcá un link desde su panel, o movelo acá desde el chip de categoría.",
        "Paste a link in the box above to save it.": "Pegá un link en el campo de arriba para guardarlo.",
        # The panel of a link, beside the list.
        "The AI is reading the link…": "La IA está leyendo el link…",
        "New category": "Nueva categoría",
        "%1 min read of the summary": "%1 min de lectura del resumen",
        "IN THREE LINES": "EN TRES LÍNEAS",
        "Remove the tag %1": "Quitar la etiqueta %1",
        "+ tag": "+ etiqueta",
        "To an idea": "A una idea",
        "Favorite": "Favorito",
        "More": "Más",
        "No mark": "Sin marca",
        "Reprocess with AI": "Reprocesar con IA",
        "Search": "Buscar",
        "Categories": "Categorías",
        "Settings": "Ajustes",
        "That is not an emoji the mark can be.": "Eso no es un emoji que pueda ser una marca.",
        "That is not a type a card can have.": "Ese no es un tipo de ficha.",
        "Nothing saved yet": "Todavía no guardaste nada",
        "Open original": "Abrir el original",
        "Close": "Cerrar",
        "Key points": "Puntos clave",
        "Original content": "Contenido original",
        "Saved": "Guardado",
        "Incomplete": "Incompleto",
        "Delete": "Borrar",
        "Reprocess": "Reprocesar",
        "Rename": "Renombrar",
        "Save": "Guardar",
        "Engines": "Motores",
        "Language and saving": "Idioma y guardado",
        "Import": "Importar",
        "Analysing %1 links": "Analizando %1 links",
        "Analysing 1 link": "Analizando 1 link",
        "Interface language": "Idioma de la interfaz",
        "Summary language": "Idioma de los resúmenes",
        "Keep by default": "Guardar por defecto",
        "All": "Todo",
        "1 note could not be read and is not shown":
            "1 nota no se pudo leer y no se muestra",
        "%1 notes could not be read and are not shown":
            "%1 notas no se pudieron leer y no se muestran",
        "Not found": "No encontrado",
        "That link is not in your library.": "Ese link no está en tu biblioteca.",
        "The vault could not be read": "No se pudo leer el vault",
        "Check that the folder exists, is mounted and is readable.":
            "Revisá que la carpeta exista, esté montada y se pueda leer.",
        "Leisure": "Ocio",
        "In progress": "En curso",
        "What you thought of it": "Qué te pareció",
        "Change type": "Cambiar tipo",
        "Open in %1": "Abrir en %1",
        "The card is as the source gave it (in English).":
            "La ficha está como vino de la fuente (en inglés).",
        "Rewrite in Spanish": "Reescribir en español",
        "WHAT IT IS ABOUT": "DE QUÉ TRATA",
        "YOUR NOTE": "TU NOTA",
        "saving…": "guardando…",
        "saved": "guardado",
        "Movies": "Películas",
        "Books": "Libros",
        "Pending": "Pendiente",
        "not rewritten": "sin reescribir",
        "Rewriting the cards one after the other. Reload in a while to read them.":
            "Reescribiendo las fichas, una después de la otra. Recargá en un rato para leerlas.",
        "Every card is already rewritten.": "Todas las fichas ya están reescritas.",
        "Ideas": "Ideas",
        "New idea": "Nueva idea",
        "Untitled idea": "Idea sin título",
        "seed": "semilla",
        "under way": "en marcha",
        "done": "hecha",
        "dropped": "descartada",
        "%1 ideas could not be read and are not shown":
            "%1 ideas no se pudieron leer y no se muestran",
        "Search your ideas": "Buscá en tus ideas",
        "STATE": "ESTADO",
        "TYPE": "TIPO",
        "Series": "Series",
        "Anime": "Anime",
        "Movie": "Película",
        "TV series": "Serie",
        "Book": "Libro",
        "To watch": "Por ver",
        "Watching": "Viendo",
        "Watched": "Vista",
        "To read": "Por leer",
        "Reading": "Leyendo",
        "Read": "Leído",
        "Recent": "Recientes",
        "Year": "Año",
        "Your stars": "Tus estrellas",
        "1 card not rewritten": "1 ficha sin reescribir",
        "%1 cards not rewritten": "%1 fichas sin reescribir",
        "Rewrite": "Reescribir",
        "Rewriting…": "Reescribiendo…",
        "Search Leisure or paste a link from IMDb or Open Library":
            "Buscá en Ocio o pegá un link de IMDb u Open Library",
        "Choose a card to see it here.": "Elegí una ficha para verla acá.",
        "Nothing in Leisure yet": "Todavía no hay nada en Ocio",
        "Type a title in the box above and search the catalogs.":
            "Escribí un título en el campo de arriba y buscalo en los catálogos.",
        "Search the catalogs to add it.": "Buscalo en los catálogos para sumarlo.",
        "1 link": "1 link",
        "%1 links": "%1 links",
        "No ideas yet": "Todavía no hay ideas",
        "Write one in the box above and press “New idea”.":
            "Escribila en el campo de arriba y tocá “Nueva idea”.",
        "No idea matches “%1”": "Ninguna idea coincide con “%1”",
        "Press “New idea” to write it down.": "Tocá “Nueva idea” para anotarla.",
        "Saved. The model is filling in the title and the tags: reload in a moment to see them.":
            "Guardada. El modelo está completando el título y las etiquetas: "
            "recargá en un momento para verlos.",
        "Write the idea first: there is nothing to save yet.":
            "Escribí la idea primero: todavía no hay nada que guardar.",
        "Title": "Título",
        "Your idea": "Tu idea",
        "Ask the model again": "Pedírselo de nuevo al modelo",
        "Thinking it over. Reload in a moment to read it.":
            "Pensándolo. Recargá en un momento para leerlo.",
        "No engine in your chain searches the web: opencode or the Anthropic API do.":
            "Ningún motor de tu cadena busca en internet: opencode o la API de Anthropic sí.",
        "Already out there": "Ya existe",
        "Already out there?": "¿Ya existe?",
        "Improvements": "Mejoras",
        "Improve": "Mejorar",
        "Expansion": "Ampliación",
        "Expand": "Ampliar",
        "Links that may help": "Links que pueden servir",
        "Last time it failed: %1": "La última vez falló: %1",
        "Among": "Entre",
        "already linked": "ya relacionado",
        "Nothing matches": "Nada coincide",
        "Linked": "Vinculados",
        "Use": "Usar",
        "That idea already has 16 links. Take one off before adding another.":
            "Esa idea ya tiene 16 links. Sacale uno antes de sumar otro.",
        "That idea is not there any more.": "Esa idea ya no está.",
        "Write a title: an empty one is not saved.": "Escribí un título: uno vacío no se guarda.",
        "That is not there any more.": "Eso ya no está.",
        "%1 cards could not be read and are not shown":
            "%1 fichas no se pudieron leer y no se muestran",
        "Search the catalogs": "Buscar en catálogos",
        "I found nothing in the catalogs": "No encontré nada en los catálogos",
        "Type": "Tipo",
        "Only an IMDb or Open Library page makes a card. Paste it in the Library to save it as a link.":
            "Sólo una página de IMDb u Open Library arma una ficha. Pegala en la Biblioteca para guardarla como link.",
        "Looking for “%1”": "Buscando “%1”",
        "The catalogue could not be reached. Try again in a moment.":
            "No se pudo consultar el catálogo. Reintentá en un momento.",
        "Full": "Completo",
        "Summary": "Resumen",
        "Saved.": "Guardado.",
        "The note was moved to the trash folder inside your vault. "
        "You can restore it from Obsidian.":
            "La nota se movió a la carpeta trash de tu vault. "
            "La podés recuperar desde Obsidian.",
        "Re-running the analysis. The note stays pending until it finishes.":
            "Reprocesando. La nota queda pendiente hasta que termine.",
        'That name cannot be used as a category: at most 80 characters, no '
        'dots at either end, no control characters, and none of \\ / : * ? " < > |':
            'Ese nombre no sirve como categoría: 80 caracteres como máximo, sin '
            'puntos al principio ni al final, sin caracteres de control y '
            'ninguno de \\ / : * ? " < > |',
        "1 note moved.": "Se movió 1 nota.",
        "%1 notes moved.": "Se movieron %1 notas.",
        "1 note merged into a category that was already there.":
            "1 nota se fusionó con una categoría que ya existía.",
        "%1 notes merged into a category that was already there.":
            "%1 notas se fusionaron con una categoría que ya existía.",
        "An analysis is running on this link. Try again when it finishes.":
            "Hay un análisis corriendo sobre este link. Probá de nuevo cuando termine.",
        "The vault could not be written. Check that the folder exists and "
        "that you can write to it.":
            "No se pudo escribir en el vault. Revisá que la carpeta exista y "
            "que puedas escribir en ella.",
        "The settings could not be saved. Check that the config folder exists "
        "and that you can write to it.":
            "No se pudieron guardar los ajustes. Revisá que la carpeta de "
            "configuración exista y que puedas escribir en ella.",
        "Re-run the analysis? The title, summary, points, category, tags and "
        "mentions are replaced by the new answer.":
            "¿Reprocesar? El título, el resumen, los puntos, la categoría, las "
            "etiquetas y las menciones se reemplazan por la respuesta nueva.",
        "Mentions": "Menciones",
        # Not the same key as "Search" above: that one is the nav label, this
        # is the badge on a mention whose link is a search. Case is the difference.
        "search": "búsqueda",
        "Remove": "Quitar",

        # Analysing a batch of what an import left unanalysed.
        "Add a model": "Agregar un modelo",
        "Add a model…": "Agregar un modelo…",
        "AI activity": "Actividad de IA",
        "In progress": "En curso",
        "History": "Historial",
        "No AI activity since the server started.": "No hubo actividad de IA desde que arrancó el servidor.",
        "Links waiting to be analysed": "Links que esperan análisis",
        "in progress": "en curso",
        "finished": "listo",
        "failed": "falló",
        "Look for the note": "Buscar la nota",
        "Read the page": "Leer la página",
        "Analyse with the model": "Analizar con el modelo",
        "Fetch the picture": "Bajar la imagen",
        "Save the note": "Guardar la nota",
        "Rewrite the card": "Reescribir la ficha",
        "Fill in the idea": "Completar la idea",
        "Look for it out there": "Buscar si ya existe",
        "Improve the idea": "Mejorar la idea",
        "Expand the idea": "Ampliar la idea",
        "Find links for the idea": "Buscar links para la idea",
        "Waiting to be analysed: %1": "Esperando an\u00e1lisis: %1",
        "Analyse 1 link": "Analizar 1 link",

        # On a card whose note was saved but never analysed.
        "Analyse %1 links": "Analizar %1 links",
        # Toasts the library page shows without reloading (shell.js).
        "It could not be saved": "No se pudo guardar",
        "Done: summary written": "Listo: resumen generado",
        "Done: card rewritten": "Listo: ficha reescrita",
        "The card could not be rewritten": "No se pudo reescribir la ficha",
        "The link could not be analysed": "No se pudo analizar el link",
        "Analysed so far: %1 of %2": "Analizados hasta ahora: %1 de %2",
        "Last run: %1 analysed of %2": "\u00daltima corrida: %1 analizados de %2",
        "Could not be finished: %1": "No se pudieron terminar: %1",
        "This page comes back on its own. You can close it: the run keeps "
        "going until it is done or the server stops.":
            "Esta p\u00e1gina vuelve sola. Pod\u00e9s cerrarla: la corrida sigue "
            "hasta terminar o hasta que se apague el servidor.",
        "Each link is one model call, so this takes a while. "
        "How many at a time is in Settings.":
            "Cada link es una llamada al modelo, as\u00ed que tarda un rato. "
            "Cu\u00e1ntos de una vez se configura en Ajustes.",
        "Every link has been analysed.": "Todos los links est\u00e1n analizados.",
        "Links to analyse at a time": "Links a analizar por vez",
        "Reading that link now. It shows up in the library when it is done.":
            "Leyendo ese link. Aparece en la biblioteca cuando termina.",
        "You already have that link.": "Ese link ya lo tenés.",
        "Writing the summary now. Reload in a moment to read it.":
            "Escribiendo el resumen. Recargá en un momento para leerlo.",
        "The catalogue has no card for that one. Try another.":
            "El catálogo no tiene ficha de esa. Probá con otra.",
        "Write what to look for after the colon, like película:Terminator.":
            "Escribí qué buscar después de los dos puntos, como "
            "película:Terminator.",
        "That is not a link: it has to be an address, like "
        "https://example.com/page.":
            "Eso no es un link: tiene que ser una dirección, como "
            "https://example.com/pagina.",
        "That is a page of search results, not a page. Open the result you "
        "want and paste that one.":
            "Esa es una página de resultados de búsqueda, no una página. Abrí "
            "el resultado que querés y pegá ese.",
        "Analysing. This page comes back on its own; you can close it.":
            "Analizando. Esta p\u00e1gina vuelve sola; pod\u00e9s cerrarla.",
        "A batch is already running. This page shows how it is going.":
            "Ya hay una corrida en curso. Esta p\u00e1gina muestra c\u00f3mo va.",
        "Every link has been analysed. Nothing to do.":
            "Todos los links est\u00e1n analizados. No hay nada que hacer.",

        # La línea de tiempo. Los meses son de tres letras porque la tira
        # en la que entran mide cinco caracteres de ancho.
        "Time": "Tiempo",
        "Jan": "ene", "Feb": "feb", "Mar": "mar", "Apr": "abr",
        "May": "may", "Jun": "jun", "Jul": "jul", "Aug": "ago",
        "Sep": "sep", "Oct": "oct", "Nov": "nov", "Dec": "dic",

        # Las colecciones: lo \u00fanico de una nota que escribe el usuario.
        "Add to a collection": "Agregar a una colecci\u00f3n",
        "Collection": "Colecci\u00f3n",
        "Add": "Agregar",
        "Leave the collection %1": "Sacar de la colecci\u00f3n %1",
        "That name cannot be used as a collection: it has to be "
        "something other than spaces, dots and slashes.":
            "Ese nombre no sirve como colecci\u00f3n: tiene que ser algo m\u00e1s "
            "que espacios, puntos y barras.",
        "No cards were selected, so nothing changed.":
            "No hab\u00eda ninguna tarjeta elegida, as\u00ed que no cambi\u00f3 nada.",
        "The note was added to the collection.":
            "La nota qued\u00f3 en la colecci\u00f3n.",
        "%1 notes added to the collection.":
            "%1 notas quedaron en la colecci\u00f3n.",
        "%1 of %2 notes added to the collection. The rest could "
        "not be written; check the folder and try again.":
            "%1 de %2 notas quedaron en la colecci\u00f3n. Las otras no se "
            "pudieron escribir; revis\u00e1 la carpeta y prob\u00e1 de nuevo.",
        "The note was taken out of the collection.":
            "La nota sali\u00f3 de la colecci\u00f3n.",
        "%1 notes taken out of the collection.":
            "%1 notas salieron de la colecci\u00f3n.",
        "%1 of %2 notes taken out of the collection. The rest "
        "could not be written; check the folder and try again.":
            "%1 de %2 notas salieron de la colecci\u00f3n. Las otras no se "
            "pudieron escribir; revis\u00e1 la carpeta y prob\u00e1 de nuevo.",

        # Importing a WhatsApp export from the browser.
        "Import a WhatsApp export": "Importar un export de WhatsApp",
        "In WhatsApp: open the chat, Export chat, Without media. "
        "Give it the .zip or the .txt inside it.":
            "En WhatsApp: abrí el chat, Exportar chat, Sin archivos. "
            "Dale el .zip o el .txt que tiene adentro.",
        "The export file": "El archivo del export",
        "Read it": "Leerlo",
        "This only reads the file and shows what it found. "
        "Nothing is written until you say so.":
            "Esto solo lee el archivo y muestra lo que encontró. "
            "No se escribe nada hasta que lo digas.",
        "Nothing is written yet": "Todavía no se escribió nada",
        "Dates read as %1.": "Fechas leídas como %1.",
        "assumed": "asumido",
        "Written without http:// \u2014 check these":
            "Escritos sin http:// \u2014 revisá estos",
        "A sentence that ends in a word which happens to be a domain ending "
        "looks exactly like a domain. These are the ones to read before importing.":
            "Una frase que termina en una palabra que casualmente es una "
            "terminación de dominio se ve igual que un dominio. Estos son los "
            "que conviene leer antes de importar.",
        "Looked like a link and was not": "Parecían un link y no lo eran",
        "Nothing here is imported. It is listed so you can see what was skipped.":
            "Nada de esto se importa. Está listado para que veas qué se salteó.",
        "Writing a thousand notes takes a few seconds. The page waits for it.":
            "Escribir mil notas tarda unos segundos. La página espera.",
        "Import %1 links": "Importar %1 links",
        "Import 1 link": "Importar 1 link",
        # Counts in label form, never inside a sentence: a sentence carrying
        # three of them needs the singular and the plural of each, and nobody
        # writes eight variants, so it ends up saying "1 links".
        "Links: %1": "Links: %1",
        "Messages: %1": "Mensajes: %1",
        "From %1 to %2": "Del %1 al %2",
        "New notes: up to %1": "Notas nuevas: hasta %1",
        "Repeated in the chat: %1": "Repetidos en el chat: %1",
        "Already in your library: %1": "Ya en tu biblioteca: %1",
        "Notes written: %1 of %2 links": "Notas escritas: %1 de %2 links",
        "Not usable as a URL: %1. Those are reported, not written.":
            "No usables como URL: %1. Se reportan, no se escriben.",
        # The value the sentence above takes, so it is not left in English.
        "day/month": "día/mes",
        "month/day": "mes/día",
        "Choose another file": "Elegir otro archivo",
        "That upload is no longer here. Choose the file again.":
            "Ese archivo ya no está. Elegí el archivo de nuevo.",
        "Imported": "Importado",
        "Not imported": "Sin importar",
        # The trace file one run writes per link. "Prompt" and "Link" are the
        # same word in both languages, so they are not in here: a key with no
        # entry degrades to English, which is where they already are.
        "Engine": "Motor",
        # The step list on the batch page, and the box that writes the files.
        # Choosing a model from a list instead of typing it from memory.
        # Who the api engine talks to, and the key it needs.
        "Who the api engine talks to": "Con quién habla el motor api",
        "Provider": "Proveedor",
        "The api engine is not ticked above, so none of this is in use yet.":
            "El motor api no está tildado arriba, así que todavía nada de esto "
            "se usa.",
        "free key": "key gratis",
        "in use": "en uso",
        "get a key": "sacar una key",
        "The key for %1 is in place.": "La key de %1 está en su lugar.",
        "There is no key yet. Paste %1=… into %2":
            "Todavía no hay key. Pegá %1=… en %2",
        "Create that file": "Crear ese archivo",
        "The key is in %1, which is as private as the folder it sits in.":
            "La key está en %1, que es tan privado como la carpeta donde vive.",
        "Anyone else with an account on this machine can read %1. Make it yours "
        "alone with chmod 600.":
            "Cualquier otra cuenta de esta máquina puede leer %1. Dejalo sólo "
            "para vos con chmod 600.",
        "config.toml names a provider this list does not have: %1. Saving will "
        "not replace it.":
            "config.toml nombra un proveedor que esta lista no tiene: %1. "
            "Guardar no lo va a reemplazar.",
        "config.toml sends this engine to %1 by hand, and that address wins "
        "over the list.":
            "config.toml manda este motor a %1 a mano, y esa dirección gana "
            "sobre la lista.",
        # What each one costs. The rows live in ai/providers.py.
        "Free coding models that rotate, and no card to sign up. Where "
        "the opencode engine already goes, by API instead of by command.":
            "Modelos de código gratis que van rotando, y sin tarjeta para "
            "registrarse. Es donde ya va el motor opencode, pero por API en "
            "lugar de por comando.",
        "The GLM Flash models cost nothing at all, which is not the same "
        "as a trial credit. No published limit.":
            "Los modelos GLM Flash no cuestan nada, que no es lo mismo que un "
            "crédito de prueba. No publican el límite.",
        "A trial key: 20 requests a minute and a thousand calls a month.":
            "Una key de prueba: 20 pedidos por minuto y mil llamadas al mes.",
        "One token for many providers, with ten cents of credit a month: "
        "enough to try one link, not enough for a batch.":
            "Un token para muchos proveedores, con diez centavos de crédito "
            "al mes: alcanza para probar un link, no para una tanda.",
        "Paid from the first token: the API is not the free chat.":
            "Se paga desde el primer token: la API no es el chat gratis.",
        "30 requests a minute, 14,400 a day. They do not train on what you send.":
            "30 pedidos por minuto, 14.400 por día. No entrenan con lo que les mandás.",
        "15 requests a minute, 1,500 a day. What you send on the free tier "
        "may be used to improve their models.":
            "15 pedidos por minuto, 1.500 por día. Lo que mandás en el tier "
            "gratis lo pueden usar para mejorar sus modelos.",
        "A million tokens a day, in a context of 8K: enough for a page, "
        "not for a long video.":
            "Un millón de tokens por día, con contexto de 8K: alcanza para una "
            "página, no para un video largo.",
        "The models whose name ends in :free, 50 a day. One shop front for "
        "many providers.":
            "Los modelos cuyo nombre termina en :free, 50 por día. Un solo "
            "mostrador para muchos proveedores.",
        "A free tier you switch on in the console, which asks for a phone number.":
            "Un tier gratis que se activa en la consola, que pide un teléfono.",
        "A thousand credits when you sign up, and the open models of "
        "everyone else to spend them on.":
            "Mil créditos al registrarte, y los modelos abiertos de todo el "
            "mundo para gastarlos.",
        "Some models are free, with a low limit, and signing up gives you "
        "a small credit.":
            "Algunos modelos son gratis, con un límite bajo, y al registrarte "
            "te dan un crédito chico.",
        # The three answers of the button that makes the .env.
        "The file is there, with the variable ready. Paste the key "
        "after the = sign and save it.":
            "El archivo está, con la variable lista. Pegá la key después del = "
            "y guardalo.",
        "That file already exists, so nothing was touched. Add the "
        "variable to it yourself.":
            "Ese archivo ya existe, así que no se tocó nada. Agregale la "
            "variable a mano.",
        "The file could not be created. Check that its folder can "
        "be written.":
            "No se pudo crear el archivo. Revisá que se pueda escribir en su "
            "carpeta.",
        "Find models": "Buscar modelos",
        "Looked up %1": "Consultado el %1",
        "%1 models found. They are in the list beside each box.":
            "Se encontraron %1 modelos. Están en la lista al lado de cada campo.",
        "No models could be listed. The engine may not be installed, running "
        "or reachable -- you can still type the name by hand.":
            "No se pudo listar ningún modelo. El motor puede no estar "
            "instalado, no estar corriendo o no ser alcanzable: podés escribir "
            "el nombre a mano igual.",
        "Save the prompt and the reply of each link":
            "Guardar el prompt y la respuesta de cada link",
        "The trace files hold the full text of each page. They are written "
        "outside the vault and only the last ten runs are kept.":
            "Los archivos de traza tienen el texto completo de cada página. Se "
            "escriben fuera del vault y sólo se guardan las últimas diez corridas.",
        "Reply": "Respuesta",
        "Parsed": "Interpretado",
        "(%1 characters cut from the middle)":
            "(se recortaron %1 caracteres del medio)",
        "The notes are saved but not analysed yet: each one needs a model call. "
        "Run `oknowledge retry` when you want that to happen.":
            "Las notas están guardadas pero todavía sin analizar: cada una "
            "necesita una llamada al modelo. Corré `oknowledge retry` cuando "
            "quieras que pase.",
        "%1 notes moved, %2 could not be written. "
        "Check the folder and try again.":
            "Se movieron %1 notas; %2 no se pudieron escribir. "
            "Revisá la carpeta y probá de nuevo.",
        "1 note moved, %2 could not be written. "
        "Check the folder and try again.":
            "Se movió 1 nota; %2 no se pudieron escribir. "
            "Revisá la carpeta y probá de nuevo.",
        "%1 notes moved, 1 could not be written. "
        "Check the folder and try again.":
            "Se movieron %1 notas; 1 no se pudo escribir. "
            "Revisá la carpeta y probá de nuevo.",
        "1 note moved, 1 could not be written. "
        "Check the folder and try again.":
            "Se movió 1 nota; 1 no se pudo escribir. "
            "Revisá la carpeta y probá de nuevo.",
        "Saved, but the indexes could not be rebuilt. Run "
        "`oknowledge reindex` once the folder is writable again.":
            "Guardado, pero no se pudieron rehacer los índices. Corré "
            "`oknowledge reindex` cuando la carpeta vuelva a ser escribible.",
        "The note was moved to the trash folder inside your vault, but the "
        "indexes could not be rebuilt. Run `oknowledge reindex` once the "
        "folder is writable again.":
            "La nota se movió a la carpeta trash de tu vault, pero no se "
            "pudieron rehacer los índices. Corré `oknowledge reindex` cuando "
            "la carpeta vuelva a ser escribible.",
        "Saving rewrites %1 from scratch: your comments, your formatting and "
        "any key oknowledge does not read are not kept. The file it replaces "
        "is copied to config.toml.bak first.":
            "Guardar reescribe %1 de cero: tus comentarios, tu formato y "
            "cualquier clave que oknowledge no lea no se conservan. El archivo "
            "que reemplaza se copia antes a config.toml.bak.",
        "Mentions of a video": "Menciones de un video",
        # Settings in panes, and the sidebar's foot (delivery 3, spec §3, §7).
        "The changes save themselves": "Los cambios se guardan solos",
        "They are used in order, top to bottom. You can put several models "
        "separated by commas.":
            "Se usan en orden, de arriba hacia abajo. Podés poner varios modelos "
            "separados por coma.",
        "Where is this saved?": "¿Dónde se guarda esto?",
        "Changing it reloads the page": "Cambiarlo recarga la página",
        "What is marked when you paste a link": "Lo que se marca al pegar un link",
        "Tools": "Herramientas",
        "Which names are pulled out": "Qué nombres se extraen",
        "How many each batch takes": "Cuántos procesa cada tanda",
        "Drop the WhatsApp export here": "Soltá acá el export de WhatsApp",
        "Choose file": "Elegir archivo",
        "Links waiting for analysis: %1": "Links esperando análisis: %1",
        "Analysing: %1/%2": "Analizando: %1/%2",
        "See activity": "Ver actividad",
        "If you rename to one that already exists, they merge.":
            "Si renombrás a una que ya existe, se unen.",
        "Merge «%1» into «%2»?": "¿Unir «%1» con «%2»?",
        "Shortcuts": "Atajos",
        "Only what it discusses": "Sólo lo discutido",
        "created %1": "creada %1",
        "Saving…": "Guardando…",
        "ASK THE AI": "PEDILE A LA IA",
        "using": "usando",
        "Linked links (%1)": "Links vinculados (%1)",
        "The whole library": "Toda la biblioteca",
        "Only my text": "Sólo mi texto",
        "YOUR IDEA": "TU IDEA",
        "Write it however it comes out: the AI puts it in order.":
            "Escribila como te salga: la IA la ordena.",
        "saves itself": "se guarda sola",
        "You have not asked yet.": "Todavía no se lo pediste.",
        "Regenerate everything with the AI": "Regenerar todo con la IA",
        "Delete idea": "Borrar idea",
        "Searching…": "Buscando…",
        # Deleting with Deshacer (delivery 3, spec §6).
        "Deleted": "Borrado",
        # Bulk actions (delivery 3, spec §5.1).
        "That is not a state it can be in.": "Ese no es un estado que pueda tener.",
        "%1 deleted": "%1 borrados",
        "1 moved to %2": "1 movido a %2",
        "%1 moved to %2": "%1 movidos a %2",
        "1 marked as favorite": "1 marcado como favorito",
        "%1 marked as favorites": "%1 marcados como favoritos",
        "Favorite removed from %1": "Se quitó favorito a %1",
        "1 could not be changed": "1 no se pudo cambiar",
        "%1 could not be changed": "%1 no se pudieron cambiar",
        "Undo": "Deshacer",
        "Restored": "Restaurado",
        "%1 restored": "%1 restaurados",
        "It can no longer be undone": "Ya no se puede deshacer",
        "It could not be restored: there is already another note with that link":
            "No se pudo restaurar: ya hay otra nota con ese link",
        "Restored · %2 not: there is already another note with that link":
            "Restaurado · %2 no: ya hay otra nota con ese link",
        "%1 restored · %2 not: there is already another note with that link":
            "%1 restaurados · %2 no: ya hay otra nota con ese link",
        # The shortcuts help (delivery 3, spec §3.2).
        "Keyboard shortcuts": "Atajos de teclado",
        "Search or paste a link": "Buscar o pegar un link",
        "Library · Leisure · Ideas": "Biblioteca · Ocio · Ideas",
        "Previous / next": "Anterior / siguiente",
        "Row up / down": "Fila arriba / abajo",
        "Open the original link": "Abrir original",
        "Add a tag": "Agregar etiqueta",
        "Select": "Seleccionar",
        "Delete the selected": "Borrar seleccionados",
        "List / cards": "Lista / tarjetas",
        "Close / deselect": "Cerrar / deseleccionar",
        # Enter on a list (delivery 3, spec §4).
        "Opening %1…": "Abriendo %1…",
        # Multi-selection (delivery 3, spec §5).
        "Select %1": "Seleccionar %1",
        "1 selected": "1 seleccionado",
        "%1 selected": "%1 seleccionados",
        "Move to": "Mover a",
        "Clear the selection": "Limpiar la selección",
        # The Settings modal (delivery 3, spec §3.1).
        "The settings could not be loaded. Check that oknowledge is still running.":
            "No se pudieron cargar los ajustes. Fijate que oknowledge siga andando.",
        "Restored, but the indexes could not be rebuilt. Run `oknowledge reindex` "
        "once the folder is writable again.":
            "Restaurado, pero no se pudieron rehacer los índices. Corré "
            "`oknowledge reindex` cuando la carpeta vuelva a ser escribible.",
        "Improvements…": "Mejoras…",
        "Expansion…": "Ampliación…",
        "Regenerating…": "Regenerando…",
        "Done: %1": "Listo: %1",
        "Failed: %1": "Falló: %1",
        "Links of this idea": "Links de esta idea",
        "LINKED": "VINCULADOS",
        "MAY HELP": "PUEDEN SERVIR",
        "RESULTS": "RESULTADOS",
        "+ Add": "+ Sumar",
        "No linked links yet": "Todavía no vinculaste links",
        "Nothing in common yet": "Nada en común todavía",
        "Search your %1 links to add": "Buscá en tus %1 links para sumar",
    },
}


def translator(language: str):
    table = STRINGS.get(language, {})

    def t(text: str, *args) -> str:
        out = table.get(text, text)

        def value(match: re.Match) -> str:
            n = int(match.group(1))
            if n == 0 or n > len(args):
                return match.group(0)        # not a marker we were given
            return str(args[n - 1])

        # One pass: a loop would re-scan its own output and substitute a
        # marker that arrived inside an argument.
        return re.sub(r"%(\d+)", value, out)

    return t
