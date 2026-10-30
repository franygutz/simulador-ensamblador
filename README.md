# Simulador educativo de ensamblador

Programa en Python con interfaz Tkinter para escribir ensamblador, ejecutarlo
paso a paso y observar los registros, las variables, las banderas y los saltos.
Toda la aplicación está en **[simulador.py](simulador.py)**. No utiliza paquetes externos.

## Cómo abrirlo

Necesitas Python 3 con Tkinter. En Windows, abre PowerShell en esta carpeta:

```powershell
python simulador.py
```

Si tu instalación usa el lanzador de Windows, también puedes ejecutar
`py simulador.py`. No es necesario compilar ni instalar dependencias con `pip`.

## Uso de la interfaz

1. Escribe tu programa en **Tu código**, o pulsa **Ejemplos** y elige uno del glosario.
2. Pulsa **Ejecutar instrucción** para avanzar una instrucción y leer su explicación.
3. Observa **Registros y banderas**, la pestaña **Variables** y **Resultado de PRINT**.
4. Si avanzaste demasiado, pulsa **Paso anterior** para recuperar el estado y la explicación anteriores.

| Control | Función | Atajo |
| --- | --- | --- |
| Ejecutar instrucción | Avanza un paso | F10 |
| Paso anterior | Deshace un paso, incluidos saltos y salida | F9 |
| Ejecutar todo / Pausar | Ejecuta automáticamente o pausa | F5 |
| Reiniciar | Limpia la ejecución y permite editar el mismo código | — |
| Ejemplos | Abre el glosario dentro del área del editor | — |
| Volver al código | Cierra el glosario conservando el programa y su estado | — |
| Velocidad | Selecciona ejecución lenta, normal o rápida | — |

La línea **amarilla** es la próxima instrucción; la **verde**, la última ejecutada.
Los registros modificados muestran su cambio, por ejemplo `0 → 5`. Debajo del
editor se explica qué ocurrió en cada paso.

Durante la ejecución, el editor queda bloqueado. Usa **Reiniciar** para modificarlo.
**Paso anterior** también funciona después de finalizar; si se pulsa durante la
ejecución automática, primero la pausa. El reinicio elimina el historial.

El panel de la CPU y el glosario tienen desplazamiento para acceder a todo su
contenido. Al abrir el glosario se ocultan el título del editor y la instrucción
amarilla. Su cabecera se desplaza con la lista. Elegir un ejemplo reemplaza el
código y reinicia la simulación; volver sin elegir conserva lo que tenías.

## Instrucciones disponibles

Escribe una instrucción por línea. Separa los operandos con coma y usa `;` para
comentarios. Los nombres no distinguen entre mayúsculas y minúsculas.

| Instrucción | Significado | Ejemplo |
| --- | --- | --- |
| MOV | Copia el valor de la fuente al destino | `MOV AX, 5` |
| ADD | Suma la fuente al destino | `ADD AX, BX` |
| SUB | Resta la fuente al destino | `SUB total, 2` |
| INC | Incrementa el destino en uno | `INC contador` |
| DEC | Reduce el destino en uno | `DEC CX` |
| CMP | Compara mediante una resta; solo modifica banderas | `CMP contador, 0` |
| JMP | Salta siempre a una etiqueta | `JMP bucle` |
| JZ | Salta si ZF vale 1 | `JZ fin` |
| JNZ | Salta si ZF vale 0 | `JNZ bucle` |
| PRINT | Muestra un valor en la consola | `PRINT total` |
| HLT | Detiene el programa | `HLT` |

El destino puede ser un registro o una variable declarada. La fuente puede ser
un registro, una variable o un literal. Las etiquetas se escriben con `:` y no
cuentan como instrucciones. Si el programa llega al final sin `HLT`, también termina.

## Variables y registros

La CPU tiene cuatro registros: **AX, BX, CX y DX**, inicialmente en cero. Puedes
declarar variables en memoria sin un límite fijo de cantidad:

```asm
INT precio = 10
VAR extra, 3
INT total            ; Sin inicializador, comienza en cero
MOV total, precio
ADD total, extra
PRINT total          ; Imprime 13
HLT
```

`INT` y `VAR` son declaraciones educativas equivalentes. **Aquí `INT` no representa
la interrupción de x86 ni convierte el lenguaje en C**. Los inicializadores deben
ser literales, no expresiones ni otras variables.

Las declaraciones reservan e inicializan memoria al cargar el programa; no son
pasos ejecutables. Los nombres admiten letras ASCII, números y guion bajo, pero
no pueden comenzar con un número, repetirse ni coincidir con registros,
instrucciones o etiquetas. La pestaña **Variables** muestra sus nombres en mayúsculas.

Los registros y las variables guardan enteros **con signo de 16 bits**:

- Decimales: de `-32768` a `32767`.
- Hexadecimales: de `0x0000` a `0xFFFF`; `0xFFFF` representa `-1`.
- Las operaciones conservan los 16 bits inferiores: `32767 + 1` produce `-32768`.

## PC y banderas

**PC** es el índice de la próxima instrucción, comenzando en cero. No es el número
de línea del editor: los comentarios, las líneas vacías y las declaraciones no
incrementan ese índice. Un salto modifica PC.

| Bandera | Cuándo vale 1 |
| --- | --- |
| ZF | El resultado es cero |
| SF | El resultado es negativo |
| OF | La operación desborda el rango con signo de 16 bits |
| CF | Hay acarreo en suma o préstamo en resta |

`ADD`, `SUB` y `CMP` actualizan las cuatro banderas. `INC` y `DEC` actualizan
ZF, SF y OF, conservando CF. Las demás instrucciones conservan las banderas.
`CMP` no cambia el valor del destino; después de comparar valores iguales, ZF vale 1.

## Ejemplo con un bucle

```asm
INT total = 0
INT contador = 5

bucle:
    ADD total, contador
    DEC contador
    JNZ bucle

PRINT total
HLT
```

Imprime **15**. `DEC` activa ZF al llegar a cero y entonces `JNZ` deja de saltar.
El glosario incluye 11 ejemplos con títulos descriptivos, comentarios y salida
esperada: operaciones básicas, variables, comparaciones, saltos y desbordamiento.

## Pruebas

```powershell
python -B simulador.py --test
```

Las pruebas están incorporadas en el mismo archivo y no abren la interfaz.
Comprueban operaciones, banderas, PC, saltos, errores, los ejemplos del glosario
y un programa con 1500 variables.

## Organización y alcance

En `simulador.py`, **CPU** analiza y ejecuta las instrucciones; **Ventana** presenta
el editor y el depurador; **EJEMPLOS** contiene el glosario y **pruebas()** verifica
el comportamiento. No hay carpetas ni módulos adicionales.

Es una arquitectura simulada para aprender. No ejecuta código máquina x86 ni
admite interrupciones, pila, multiplicación, división o instrucciones ajenas a
la tabla anterior. Los errores de sintaxis indican la línea problemática antes
de empezar la ejecución. Los programas se escriben o pegan en el editor; no hay
botones de abrir o guardar archivos.
