# Línea de tiempo vertical

**Fecha:** 2026-10-07 · **Rama:** `feat/mentions-search`

## Contexto

El diseño del importador de WhatsApp dejó esto anotado y afuera:

> *"Lo que no entra acá: la línea de tiempo vertical de la biblioteca. Es el
> otro subsistema de la misma idea, es mucho más chico y tiene su propio
> diseño. Este documento es la condición previa: sin links fechados no hay
> nada que recorrer."*
> — `docs/2026-10-05-importar-whatsapp-design.md:15`

La condición previa está cumplida. Hoy la biblioteca tiene **1181 notas
fechadas entre el 5 de abril de 2019 y hoy**, repartidas en **8 años y 86
meses**, y muy desparejas:

| año | notas | | año | notas |
|---|---|---|---|---|
| 2026 | 178 | | 2022 | 97 |
| 2025 | 54 | | 2021 | **258** |
| 2024 | 192 | | 2020 | 116 |
| 2023 | 121 | | 2019 | 165 |

Noviembre de 2021 solo tiene 65 notas; hay meses con una. Esa desigualdad es
el dato que manda sobre todo lo demás: una tira con los 86 meses a la vez, en
una pantalla de 900 px, son diez píxeles por renglón.

Y el problema que resuelve: hoy la única forma de llegar a 2019 es paginar de
a 100, doce veces.

## Decisión

Una tira fija al borde derecho de la biblioteca que **filtra**. Cada año es un
enlace; al entrar a uno se abren sus meses debajo. Es un filtro más, del mismo
tipo que la categoría, la etiqueta y la colección, y se combina con los tres.

Esto no es el scrubber de Google Fotos, que arrastra y hace scroll. Es lo que
pidió el pedido original — *"que filtre las notas al viajar en el tiempo"* — y
tiene tres ventajas concretas sobre arrastrar:

* **Anda sin JavaScript**, como todo lo demás de esta aplicación.
* **Se combina con los filtros que ya hay.** `/?when=2021&collection=Casa` es
  "lo de ese proyecto, en 2021", y no hay otra forma de preguntar eso hoy.
* **No hay que inventar scroll infinito.** La biblioteca pagina de a 100 y
  saltar a un mes sería aterrizar a mitad de una página.

## La URL

Un parámetro, `when`, que es un año (`2021`), un mes (`2021-11`) o la palabra
`undated`:

```
/?when=2021                    los 258 links de 2021
/?when=2021-11                 los 65 de noviembre
/?when=2021&collection=Casa    los de ese proyecto, ese año
/?when=2021-11&page=2          pagina como cualquier otra vista
```

`when` sólo vale si nombra un período que la biblioteca tiene. Un `?when=2017`
o un `?when=hola` no se ignoran: filtran a nada y la página lo dice, igual que
hace hoy un `?category=zzz`. Un filtro que se descarta en silencio muestra
todo y hace creer que eso es la respuesta.

## Lo que cuenta la tira

**Los años salen del índice; los números salen de lo que estás mirando.**

La lista de años es siempre la misma — los 8 que la biblioteca tiene — para
que la forma del tiempo no cambie de página a página. Los números de al lado
se cuentan sobre las notas que pasaron los *otros* filtros (categoría,
etiqueta, colección) y antes de aplicar `when`. Así, con una colección puesta,
la tira muestra **en qué años vive ese proyecto**, y los años donde no hay
nada quedan apagados y sin enlace.

Es una pasada más sobre las notas ya filtradas, por pedido. Son 1181 notas y
una comparación de prefijo por cada una.

```
      Todo  1181          Todo  12        <- con collection=Casa puesta
      2026   178          2026   4
      2025    54          2025   —
      2024   192          2024   8
      2023   121          2023   —
      2022    97          2022   —
    > 2021   258          2021   —
        nov   65          2020   —
        oct   30          2019   —
        sep   32
        ...
      2020   116
      2019   165
```

## El índice

`Library._refresh()` ya recorre todas las notas una vez. En esa pasada acumula
dos cosas más, igual que `categories` y `collections`:

```python
self._years  = {"2026": 178, "2025": 54, ...}     # de mayor a menor
self._months = {"2026-10": 5, "2026-09": 39, ...}
```

Se limpian en la rama de `OSError` con los demás, y se exponen con
`periods()`, que devuelve las claves válidas para `when`.

**Una nota cuya fecha no se puede leer no desaparece.** `saved` es un texto
que se puede editar a mano en Obsidian, así que una nota cuyo `saved` no sea
`AAAA-MM-DD` cae en un período `undated`, que aparece al final de la tira sólo
cuando hay alguna. La regla del proyecto es que un link no se pierde nunca, y
un link invisible en todos los filtros está perdido. El vault ya tiene este
concepto: `vault.note_stem()` nombra `undated-<título>.md` a una nota así.

`filter()` suma un parámetro:

```python
def filter(self, category=None, tag=None, collection=None, when=None):
    ...
    if when:
        if when not in self.periods():
            return []          # nombra un período que esta biblioteca no tiene
        found = [n for n in found if period_of(n.saved, len(when)) == when]
```

donde `period_of(saved, n)` es `saved[:n]` si la fecha tiene la forma que
tiene que tener, y `"undated"` si no.

La pertenencia se chequea y no alcanza con comparar el prefijo: un
`?when=2021-1`, que no es un mes, se comería octubre, noviembre y diciembre
de 2021 y mostraría ese amontonamiento como si fuera un período.

## La interfaz

### Dónde va

Al lado de la grilla, no encima: la grilla y la tira son dos columnas de un
flex, y la tira es `position: sticky` arriba, así que acompaña el scroll sin
taparle nada a las tarjetas. Ancho fijo de unos 5.5 rem, que es lo que miden
"2026" y un número de tres cifras.

En pantallas angostas la columna no entra. Ahí el flex pasa a columna, la tira
va arriba de las tarjetas con `order: -1` y se vuelve una fila horizontal con
scroll propio. Mismos enlaces, otra forma.

### Sólo en la biblioteca

En los resultados de búsqueda no va. Esa lista está ordenada por relevancia, y
una tira de tiempo al costado de una lista que no está ordenada por tiempo
miente sobre el orden en que están las cosas.

### Cómo se abre un año

El año de `when` es el que está abierto. Sin `when`, ninguno: ocho renglones y
nada más. `/?when=2021` abre 2021 y muestra sus meses debajo; `/?when=2021-11`
abre 2021 y marca noviembre.

Un "Todo" arriba de todo que saca `when` y deja los demás filtros donde
estaban.

### Los meses tienen nombre

`ene feb mar abr may jun jul ago sep oct nov dic` en español, los mismos tres
caracteres en inglés. Doce textos nuevos por idioma. Un `2021-11` en la
pantalla es una fecha para una base de datos, no para una persona.

### Los chips llevan el período

Los enlaces de la tira arrastran la categoría, la etiqueta y la colección que
estén puestas, y los chips de esas tres arrastran `when`. Sin eso el feature
anda a medias: elegís 2021, hacés click en una categoría y perdiste el año.

Lo que **no** cambia es que los chips sigan siendo excluyentes entre ellos —
hacer click en una etiqueta sigue sacando la categoría, como hoy. El tiempo es
otro eje: se cruza con el "qué", no compite con él.

## Qué se prueba

Con mutación sobre cada cosa nueva, como el resto del proyecto.

**`tests/test_web_read.py`**
* `years()` y `months()` cuentan bien y vienen del más nuevo al más viejo;
* una nota con `saved` roto cae en `undated` y no en un año inventado;
* `undated` no aparece en la tira cuando no hay ninguna;
* `filter(when="2021")` trae el año entero y `filter(when="2021-11")` el mes;
* `when` combinado con categoría, etiqueta y colección;
* un `when` que no nombra ningún período trae cero notas, no todas;
* los números de la tira se cuentan **después** de los otros filtros: con una
  colección puesta, un año sin nada de esa colección sale en cero;
* la lista de años no se achica al filtrar: los ocho siguen estando;
* el año de `when` es el único abierto, y sin `when` no hay ninguno;
* los enlaces de la tira llevan la categoría puesta, y los chips llevan `when`;
* la tira no está en `/search`;
* el vault que desaparece deja `years()` y `months()` vacíos.

**`tests/test_web_retry.py`**
* la tarjeta de reprocesar dentro de un período vuelve a ese período (campo
  oculto `when`, como ya hacen `category`, `tag` y `collection`).

**`tests/test_i18n.py`** — los doce meses y los textos nuevos, en los dos
idiomas.

## Lo que no entra

* **Arrastrar.** El tirador de Google Fotos, con el globito de la fecha
  siguiendo al dedo, necesita que la lista sea una sola y que el scroll la
  cargue sola. Es otro feature y empieza por cambiar la paginación.
* **Scroll infinito**, por lo mismo.
* **Semanas y días.** El mes es el grano más chico que tiene sentido acá: hay
  meses con una sola nota.
* **Un gráfico de barras** al costado de los años. Los números alcanzan.
* **Filtrar por rango** (`de 2020 a 2022`). Un período por vez.

Nada de eso le cambia la forma a lo de arriba el día que haga falta.

## Dónde vive hoy (2026-10-17)

El rediseño se la llevó: la entrega 1 borró `library.html`, donde estaba la
tira, y con ella el índice de años y el parámetro `when`
(`docs/2026-10-14-rediseno-biblioteca-design.md`, tabla de decisiones: *"¿Tira
de etiquetas y filtro año/mes? Se van"*). El motivo era que las tres columnas
del handoff no tienen un costado libre a la derecha: ahí va el panel del link.

Vuelve en la barra lateral izquierda, como un grupo **FECHAS** debajo de
CATEGORÍAS, MARCAS y COLECCIONES, que es donde viven todos los filtros desde
el rediseño. Lo de arriba sigue valiendo entero —`when`, los períodos, los
contadores sobre lo que dejaron los otros filtros, `undated`, los meses del
año abierto, que el tiempo cruce a los demás filtros en vez de competir con
ellos— y sólo cambia la forma: renglones de la barra en vez de una tira
pegada al borde, y los mismos años como chips en el celular.
