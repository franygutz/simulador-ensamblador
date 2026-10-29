"""Simulador educativo: un archivo, Python y Tkinter (sin paquetes externos).

Ejecutar: python simulador.py       Pruebas: python simulador.py --test

CPU simulada de 16 bits: AX/BX/CX/DX se muestran como enteros con signo.
Literales decimales [-32768,32767] o hexadecimales [0x0000,0xFFFF].
La aritmetica desborda envolviendo a 16 bits, como un registro fisico.
ZF: resultado cero; SF: negativo; OF: desbordamiento con signo;
CF: acarreo en suma o prestamo en resta. INC/DEC conservan CF.
CMP calcula las banderas de una resta sin cambiar registros.
MOV, PRINT, los saltos y HLT no modifican las banderas.
PC cuenta instrucciones desde cero; etiquetas y comentarios no cuentan.
Variables sin cantidad fija: VAR nombre, 5 o INT nombre = 5 (declaracion
educativa, no la interrupcion INT de x86). Sin inicializador comienzan en cero.
Las declaraciones reservan memoria al cargar; no son pasos ejecutables.
Los nombres no distinguen mayusculas; toda variable tambien guarda 16 bits.
MOV/ADD/SUB/INC/DEC/CMP/PRINT admiten variables igual que registros.
No es ensamblador x86 real. No hay pila ni instrucciones nativas.
"""

import re
import sys
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


EJEMPLO = """; Sumar 5 + 4 + 3 + 2 + 1, paso a paso.
; Esperado en consola: 15
INT total = 0      ; Variable en memoria, no un registro
INT cantidad = 5
MOV AX, 0          ; Acumulador
MOV CX, cantidad   ; Leer una variable

bucle:
    ADD AX, CX
    DEC CX
    CMP CX, 0      ; ZF = 1 cuando CX llega a cero
    JNZ bucle      ; Volver mientras ZF sea 0

MOV total, AX      ; Guardar el resultado en memoria
PRINT total
HLT
"""

# Titulo, explicacion, codigo y salida esperada de cada opcion del glosario.
EJEMPLOS = (
    ("Primer programa: guardar y mostrar un valor", "MOV copia un valor y PRINT lo muestra.",
     "; Resultado esperado: 42\nMOV AX, 42\nPRINT AX\nHLT\n", ("42",)),
    ("Sumar dos registros con ADD", "Suma 5 y 3; el resultado queda en AX.",
     "; Resultado esperado: 8\nMOV AX, 5\nMOV BX, 3\nADD AX, BX\nPRINT AX\nHLT\n", ("8",)),
    ("Restar y obtener un número negativo", "SUB resta 8 a 3 y activa la bandera de signo.",
     "; Resultado esperado: -5\nMOV AX, 3\nSUB AX, 8\nPRINT AX\nHLT\n", ("-5",)),
    ("Contar hacia arriba con INC y JNZ", "Incrementa una variable hasta llegar a 3.",
     "; Resultado esperado: 1, 2, 3\nINT contador = 0\nbucle:\nINC contador\nPRINT contador\nCMP contador, 3\nJNZ bucle\nHLT\n", ("1", "2", "3")),
    ("Cuenta regresiva con DEC", "DEC reduce CX; JNZ repite mientras no sea cero.",
     "; Resultado esperado: 3, 2, 1\nMOV CX, 3\nbucle:\nPRINT CX\nDEC CX\nJNZ bucle\nHLT\n", ("3", "2", "1")),
    ("Comparar valores y saltar si son iguales", "CMP actualiza ZF y JZ decide qué línea ejecutar.",
     "; Resultado esperado: 1\nMOV AX, 7\nCMP AX, 7\nJZ iguales\nPRINT 0\nJMP fin\niguales:\nPRINT 1\nfin:\nHLT\n", ("1",)),
    ("Saltar instrucciones con JMP", "Un salto incondicional evita imprimir el valor 99.",
     "; Resultado esperado: 10\nJMP salida\nPRINT 99\nsalida:\nPRINT 10\nHLT\n", ("10",)),
    ("Declarar y sumar variables con INT y VAR", "Las variables guardan datos en memoria, fuera de los registros.",
     "; Resultado esperado: 13\nINT a = 10\nVAR b, 3\nINT total\nMOV total, a\nADD total, b\nPRINT total\nHLT\n", ("13",)),
    ("Usar más variables que registros", "Suma seis variables sin limitarse a AX, BX, CX y DX.",
     "; Resultado esperado: 21\nINT a=1\nINT b=2\nINT c=3\nINT d=4\nINT e=5\nINT f=6\nINT total\nADD total,a\nADD total,b\nADD total,c\nADD total,d\nADD total,e\nADD total,f\nPRINT total\nHLT\n", ("21",)),
    ("Sumar del 1 al 5 con un bucle", "Combina variables, registros, comparación y saltos.",
     EJEMPLO, ("15",)),
    ("Entender el desbordamiento de 16 bits", "Al pasar de 32767 a -32768 se activan OF y SF.",
     "; Resultado esperado: -32768\nMOV AX, 32767\nINC AX\nPRINT AX\nHLT\n", ("-32768",)),
)


class ErrorASM(ValueError):
    """Un error de codigo guarda la linea para resaltarla en el editor."""

    def __init__(self, linea, mensaje):
        super().__init__(f"Línea {linea}: {mensaje}")
        self.linea = linea


class CPU:
    """El analizador y la CPU no dependen de la ventana; se prueban por separado."""

    REGISTROS = ("AX", "BX", "CX", "DX")
    ARIDAD = {"MOV": 2, "ADD": 2, "SUB": 2, "INC": 1, "DEC": 1,
              "CMP": 2, "JMP": 1, "JZ": 1, "JNZ": 1, "PRINT": 1, "HLT": 0}

    def __init__(self, codigo=""):
        self.registros = dict.fromkeys(self.REGISTROS, 0)
        self.variables = {}             # Memoria simbolica: no depende de los cuatro registros.
        self.banderas = dict.fromkeys(("ZF", "SF", "OF", "CF"), 0)
        self.pc = 0
        self.terminada = False
        self.instrucciones = []
        self.etiquetas = {}
        self.analizar(codigo)

    @staticmethod
    def firmado(valor):
        """Conservar 16 bits e interpretar el bit superior como signo."""
        return ((valor + 32768) & 0xFFFF) - 32768

    def literal(self, texto, linea):
        if re.fullmatch(r"[+-]?\d+", texto):
            # Rechazar entradas enormes antes de convertirlas a entero.
            if len(texto.lstrip("+-")) > 6:
                raise ErrorASM(linea, "literal decimal fuera de rango")
            numero = int(texto, 10)
            if -32768 <= numero <= 32767:
                return numero
        elif re.fullmatch(r"0X[0-9A-F]{1,4}", texto):
            return self.firmado(int(texto, 16))
        raise ErrorASM(linea, f"operando inválido o fuera de rango: {texto}")

    def analizar(self, codigo):
        """Primera pasada: instrucciones y etiquetas. Segunda: validar operandos."""
        for linea, original in enumerate(codigo.splitlines(), 1):
            texto = original.split(";", 1)[0].strip().upper()
            while ":" in texto:
                etiqueta, texto = texto.split(":", 1)
                etiqueta, texto = etiqueta.strip(), texto.strip()
                if not re.fullmatch(r"[A-Z_][A-Z_0-9]*", etiqueta):
                    raise ErrorASM(linea, "nombre de etiqueta inválido")
                if etiqueta in self.etiquetas:
                    raise ErrorASM(linea, f"etiqueta duplicada: {etiqueta}")
                if etiqueta in self.variables:
                    raise ErrorASM(linea, f"el nombre ya pertenece a una variable: {etiqueta}")
                self.etiquetas[etiqueta] = len(self.instrucciones)
            if not texto:
                continue
            partes = texto.split(None, 1)
            op = partes[0]
            if op in ("VAR", "INT"):
                declaracion = re.fullmatch(r"(?:VAR|INT)\s+([A-Z_][A-Z_0-9]*)(?:\s*[,=]\s*(\S+))?", texto)
                if not declaracion:
                    raise ErrorASM(linea, "use INT nombre = 5 o VAR nombre, 5; no se simulan interrupciones x86")
                nombre, valor = declaracion.groups()
                if nombre in self.variables or nombre in self.etiquetas or nombre in self.REGISTROS or nombre in self.ARIDAD or nombre in ("INT", "VAR"):
                    raise ErrorASM(linea, f"variable duplicada o nombre reservado: {nombre}")
                self.variables[nombre] = self.literal(valor, linea) if valor is not None else 0
                continue
            if op not in self.ARIDAD:
                raise ErrorASM(linea, f"instrucción desconocida: {op}")
            args = [a.strip() for a in partes[1].split(",")] if len(partes) == 2 else []
            if len(args) != self.ARIDAD[op] or any(not a for a in args):
                raise ErrorASM(linea, f"{op} requiere {self.ARIDAD[op]} operando(s); sepárelos con coma")
            self.instrucciones.append((linea, op, args, texto))

        for linea, op, args, _ in self.instrucciones:
            if op in ("JMP", "JZ", "JNZ"):
                if args[0] not in self.etiquetas:
                    raise ErrorASM(linea, f"etiqueta inexistente: {args[0]}")
            elif args:
                if op != "PRINT" and args[0] not in self.REGISTROS and args[0] not in self.variables:
                    raise ErrorASM(linea, "el destino debe ser un registro o una variable declarada con INT/VAR o las contempladas: AX, BX, CX, DX.")
                if op == "PRINT" or len(args) == 2:
                    fuente = args[-1]
                    if fuente not in self.REGISTROS and fuente not in self.variables:
                        self.literal(fuente, linea)
        self.terminada = not self.instrucciones

    def leer(self, nombre, linea):
        if nombre in self.registros:
            return self.registros[nombre]
        if nombre in self.variables:
            return self.variables[nombre]
        return self.literal(nombre, linea)

    def guardar(self, nombre, valor):
        destino = self.registros if nombre in self.registros else self.variables
        destino[nombre] = valor

    def paso(self):
        """Ejecutar exactamente una instruccion; devolver linea y posible salida."""
        if self.terminada:
            return None, None
        linea, op, args, _ = self.instrucciones[self.pc]
        siguiente, salida = self.pc + 1, None
        fuente = None
        if op in ("MOV", "ADD", "SUB", "CMP", "PRINT"):
            nombre = args[-1]
            fuente = self.leer(nombre, linea)
        if op == "MOV":
            self.guardar(args[0], fuente)
        elif op in ("ADD", "SUB", "INC", "DEC", "CMP"):
            anterior = self.leer(args[0], linea)
            fuente = 1 if op in ("INC", "DEC") else fuente
            suma = op in ("ADD", "INC")
            resultado = anterior + fuente if suma else anterior - fuente
            envuelto = self.firmado(resultado)
            self.banderas["ZF"] = int(envuelto == 0)
            self.banderas["SF"] = int(envuelto < 0)
            self.banderas["OF"] = int(not -32768 <= resultado <= 32767)
            if op not in ("INC", "DEC"):
                a, b = anterior & 0xFFFF, fuente & 0xFFFF
                self.banderas["CF"] = int(a + b > 0xFFFF) if suma else int(a < b)
            if op != "CMP":
                self.guardar(args[0], envuelto)
        elif op in ("JMP", "JZ", "JNZ"):
            if op == "JMP" or (op == "JZ" and self.banderas["ZF"]) or (op == "JNZ" and not self.banderas["ZF"]):
                siguiente = self.etiquetas[args[0]]
        elif op == "PRINT":
            salida = str(fuente)
        elif op == "HLT":
            self.terminada = True
        self.pc = siguiente
        self.terminada = self.terminada or self.pc >= len(self.instrucciones)
        return linea, salida


class Ventana:
    """Una ventana: editor, CPU y salida. La simulacion sigue en la clase CPU."""

    FONDO, TINTA, VERDE = "#f3f6f5", "#182e2b", "#087c65"

    def __init__(self, raiz):
        self.raiz, self.cpu, self.temporizador = raiz, None, None
        self.ejecutando, self.pasos = False, 0
        self.historial = []              # Guardar cada estado permite deshacer incluso saltos.
        self.catalogo_visible = False
        raiz.title("Simulador de ensamblador")
        raiz.geometry("1120x820")
        raiz.minsize(960, 740)
        raiz.configure(bg=self.FONDO)
        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure("TButton", font=("Segoe UI", 9), padding=(9, 4),
                         background="white", foreground=self.TINTA, bordercolor="#cbd7d3")
        estilo.map("TButton", background=[("active", "#e4eeea")],
                   foreground=[("disabled", "#8b9995")])
        estilo.configure("Principal.TButton", background=self.VERDE, foreground="white",
                         font=("Segoe UI", 9, "bold"))
        estilo.map("Principal.TButton", background=[("disabled", "#baccc5"), ("active", "#05614e")],
                   foreground=[("disabled", "white")])
        base = tk.Frame(raiz, bg=self.FONDO, padx=18, pady=10)
        base.pack(fill="both", expand=True)
        base.columnconfigure(0, weight=1)
        base.rowconfigure(2, weight=1)
        cabecera = tk.Frame(base, bg=self.FONDO)
        cabecera.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.rotulo(cabecera, "Simulador de ensamblador", 16, True, bg=self.FONDO).pack(anchor="w")
        self.rotulo(cabecera, "Escribe código, ejecuta una instrucción y observa qué cambia", 9, color="#536d65", bg=self.FONDO).pack(anchor="w")
        self.insignia = self.rotulo(cabecera, "Listo para empezar", 9, color=self.VERDE, bg="#dff2e9")
        self.insignia.place(relx=1, x=0, y=4, anchor="ne")

        barra = tk.Frame(base, bg=self.FONDO)
        barra.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.boton_anterior = ttk.Button(barra, text="← Paso anterior", command=self.retroceder, state="disabled")
        self.boton_anterior.pack(side="left", padx=(0, 5))
        self.boton_paso = ttk.Button(barra, text="Ejecutar instrucción", style="Principal.TButton", command=self.avanzar)
        self.boton_paso.pack(side="left")
        self.boton_ejecutar = ttk.Button(barra, text="Ejecutar todo", command=self.ejecutar)
        self.boton_ejecutar.pack(side="left", padx=5)
        ttk.Button(barra, text="Reiniciar", command=self.reiniciar).pack(side="left")
        self.boton_ejemplos = ttk.Button(barra, text="Ejemplos", command=self.mostrar_ejemplos)
        self.boton_ejemplos.pack(side="left", padx=5)
        self.velocidad = tk.StringVar(value="Normal")
        ttk.Combobox(barra, textvariable=self.velocidad, values=("Lento", "Normal", "Rápido"),
                     state="readonly", width=8, font=("Segoe UI", 9)).pack(side="right", padx=(5, 0))
        self.rotulo(barra, "Velocidad", 9, bg=self.FONDO, color="#536d65").pack(side="right")

        centro = tk.Frame(base, bg=self.FONDO)
        centro.grid(row=2, column=0, sticky="nsew")
        centro.columnconfigure(0, weight=1)
        centro.rowconfigure(0, weight=1)
        codigo = self.tarjeta(centro)
        codigo.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        codigo.columnconfigure(0, weight=1)
        codigo.rowconfigure(2, weight=1)
        self.titulo_codigo = self.rotulo(codigo, "⌨   Tu código", 12, True)
        self.titulo_codigo.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        self.proxima = tk.StringVar()
        self.indicador_proxima = self.rotulo(codigo, variable=self.proxima, color="#806017", bg="#fff7dd")
        self.indicador_proxima.grid(row=1, column=0, sticky="ew", padx=10, pady=(3, 8))
        edicion = tk.Frame(codigo, bg="white")
        edicion.grid(row=2, column=0, sticky="nsew")
        edicion.columnconfigure(1, weight=1)
        edicion.rowconfigure(0, weight=1)
        self.numeros = tk.Canvas(edicion, width=42, bg="#f6f8f7", highlightthickness=0)
        self.numeros.grid(row=0, column=0, sticky="ns")
        self.editor = ScrolledText(edicion, width=40, height=10, font=("Consolas", 12),
                                   bg="white", fg=self.TINTA, insertbackground=self.VERDE,
                                   undo=True, wrap="none", relief="flat", padx=8, pady=8)
        self.editor.grid(row=0, column=1, sticky="nsew")
        horizontal = ttk.Scrollbar(codigo, orient="horizontal", command=self.editor.xview)
        horizontal.grid(row=3, column=0, sticky="ew")
        self.editor.configure(xscrollcommand=horizontal.set, yscrollcommand=self.desplazar)
        self.editor.tag_configure("instruccion", foreground="#1465a0")
        self.editor.tag_configure("comentario", foreground="#6d8177")
        self.editor.tag_configure("actual", background="#e0f1e9")
        self.editor.tag_configure("siguiente", background="#fff0bd")
        self.editor.tag_configure("error", background="#ffe0e0", foreground="#991b1b")
        self.editor.bind("<<Modified>>", self.editar)
        self.editor.bind("<Configure>", lambda event: self.dibujar_numeros())
        leyenda = tk.Frame(codigo, bg="white")
        self.leyenda = leyenda
        leyenda.grid(row=4, column=0, sticky="w", padx=14, pady=8)
        self.rotulo(leyenda, "Amarillo", bold=True, color="#b88600").pack(side="left")
        self.rotulo(leyenda, ": próxima instrucción     ", color="#536d65").pack(side="left")
        self.rotulo(leyenda, "Verde", bold=True, color=self.VERDE).pack(side="left")
        self.rotulo(leyenda, ": última ejecutada", color="#536d65").pack(side="left")

        # El glosario ocupa el mismo lugar del editor, sin abrir otra ventana.
        self.catalogo = tk.Frame(codigo, bg="white")
        self.catalogo.grid(row=0, column=0, rowspan=5, sticky="nsew")
        self.catalogo.columnconfigure(0, weight=1)
        self.catalogo.rowconfigure(0, weight=1)
        self.lista_ejemplos = tk.Canvas(self.catalogo, bg="white", highlightthickness=0, height=100, width=200)
        self.lista_ejemplos.grid(row=0, column=0, sticky="nsew")
        scroll_ejemplos = ttk.Scrollbar(self.catalogo, orient="vertical", command=self.lista_ejemplos.yview)
        scroll_ejemplos.grid(row=0, column=1, sticky="ns")
        self.lista_ejemplos.configure(yscrollcommand=scroll_ejemplos.set)
        opciones = tk.Frame(self.lista_ejemplos, bg="white")
        ventana_opciones = self.lista_ejemplos.create_window((0, 0), window=opciones, anchor="nw")
        opciones.bind("<Configure>", lambda event: self.lista_ejemplos.configure(scrollregion=self.lista_ejemplos.bbox("all")))
        self.lista_ejemplos.bind("<Configure>", lambda event: self.lista_ejemplos.itemconfigure(ventana_opciones, width=event.width))
        # La cabecera pertenece a la lista: desaparece al bajar, como los ejemplos.
        cabecera_ejemplos = tk.Frame(opciones, bg="white")
        cabecera_ejemplos.pack(fill="x", padx=12, pady=(8, 4))
        self.rotulo(cabecera_ejemplos, "Glosario de ejemplos", 12, True).pack(side="left")
        self.rotulo(opciones, "Elige un título para cargarlo y probarlo.", 9, color="#536d65").pack(anchor="w", padx=12, pady=(0, 8))
        for indice, (titulo, descripcion, _, _) in enumerate(EJEMPLOS):
            opcion = tk.Frame(opciones, bg="white")
            opcion.pack(fill="x", padx=12, pady=(0, 10))
            boton = tk.Button(opcion, text=titulo, command=lambda n=indice: self.cargar_ejemplo(n),
                              font=("Segoe UI", 10, "bold"), fg=self.VERDE, bg="#eef6f2",
                              activebackground="#dff2e9", activeforeground=self.VERDE,
                              relief="flat", anchor="w", padx=10, pady=7, cursor="hand2", wraplength=420)
            boton.pack(fill="x")
            self.rotulo(opcion, descripcion, 9, color="#536d65", wrap=420).pack(anchor="w", pady=(2, 0))
        pendientes_ejemplos = [opciones, self.lista_ejemplos]
        while pendientes_ejemplos:
            widget = pendientes_ejemplos.pop()
            widget.bind("<MouseWheel>", lambda event: self.lista_ejemplos.yview_scroll(-1 if event.delta > 0 else 1, "units"))
            pendientes_ejemplos.extend(widget.winfo_children())
        self.catalogo.grid_remove()
        
        contenedor_cpu = self.tarjeta(centro)
        contenedor_cpu.grid(row=0, column=1, sticky="nsew")
        contenedor_cpu.rowconfigure(0, weight=1)
        contenedor_cpu.columnconfigure(0, weight=1)
        self.pestanas = ttk.Notebook(contenedor_cpu)
        self.pestanas.grid(row=0, column=0, sticky="nsew")
        tab_cpu = tk.Frame(self.pestanas, bg="white")
        tab_cpu.rowconfigure(0, weight=1)
        tab_cpu.columnconfigure(0, weight=1)
        self.pestanas.add(tab_cpu, text="Registros y banderas")
        # El panel puede desplazarse si la explicación o la escala de Windows
        # reducen el espacio; pack ya no deja las banderas fuera de la vista.
        self.vista_cpu = tk.Canvas(tab_cpu, width=320, height=280,
                                   bg="white", highlightthickness=0)
        self.vista_cpu.grid(row=0, column=0, sticky="nsew")
        scroll_cpu = ttk.Scrollbar(tab_cpu, orient="vertical", command=self.vista_cpu.yview)
        scroll_cpu.grid(row=0, column=1, sticky="ns")
        self.vista_cpu.configure(yscrollcommand=scroll_cpu.set)
        panel = tk.Frame(self.vista_cpu, bg="white")
        ventana_cpu = self.vista_cpu.create_window((0, 0), window=panel, anchor="nw")
        panel.bind("<Configure>", lambda event: self.vista_cpu.configure(scrollregion=self.vista_cpu.bbox("all")))
        self.vista_cpu.bind("<Configure>", lambda event: self.vista_cpu.itemconfigure(ventana_cpu, width=event.width))
        self.rotulo(panel, "⚙   Observa la CPU", 12, True).pack(anchor="w", padx=14, pady=(8, 3))
        tabla = tk.Frame(panel, bg="white")
        tabla.pack(fill="x", padx=14)
        for col, texto in enumerate(("Registro", "Valor", "Último cambio")):
            self.rotulo(tabla, texto, 9, color="#536d65").grid(row=0, column=col, sticky="w", padx=(0, 16), pady=2)
        self.datos, self.cambios, self.valores = {}, {}, {}
        for fila, nombre in enumerate(CPU.REGISTROS, 1):
            self.rotulo(tabla, nombre, 11, True).grid(row=fila, column=0, sticky="w", pady=2)
            self.datos[nombre], self.cambios[nombre] = tk.StringVar(), tk.StringVar()
            valor = self.rotulo(tabla, variable=self.datos[nombre], size=15, bold=True, mono=True)
            valor.grid(row=fila, column=1, sticky="w", padx=(0, 14))
            self.valores[nombre] = valor
            self.rotulo(tabla, variable=self.cambios[nombre], size=9, color="#536d65").grid(row=fila, column=2, sticky="w")
        self.datos["PC"] = tk.StringVar()
        self.rotulo(panel, variable=self.datos["PC"], bold=True, bg="#eef4f1").pack(fill="x", padx=14, pady=(5, 5))
        self.rotulo(panel, "Banderas · 1 = activa, 0 = inactiva", 9, True).pack(anchor="w", padx=14)
        flags = tk.Frame(panel, bg="white")
        flags.pack(fill="x", padx=14, pady=(3, 7))
        self.flags = {}
        for n, (clave, nombre) in enumerate((("ZF", "Cero"), ("SF", "Negativo"), ("OF", "Desborde"), ("CF", "Acarreo"))):
            etiqueta = self.rotulo(flags, size=9)
            etiqueta.grid(row=n // 2, column=n % 2, sticky="ew", padx=(0, 8), pady=0)
            self.flags[clave] = (etiqueta, nombre)
        # La rueda funciona solamente sobre la CPU, sin afectar al editor.
        pendientes = [panel, self.vista_cpu]
        while pendientes:
            widget = pendientes.pop()
            widget.bind("<MouseWheel>", lambda event: self.vista_cpu.yview_scroll(-1 if event.delta > 0 else 1, "units"))
            pendientes.extend(widget.winfo_children())

        self.tab_memoria = tk.Frame(self.pestanas, bg="white")
        self.pestanas.add(self.tab_memoria, text="Variables (0)")
        self.tab_memoria.columnconfigure(0, weight=1)
        self.tab_memoria.rowconfigure(1, weight=1)
        self.rotulo(self.tab_memoria, "INT contador = 5\nVAR total, 0", size=10, mono=True).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=8)
        self.tabla_variables = ttk.Treeview(self.tab_memoria, columns=("nombre", "valor"), show="headings", height=5)
        self.tabla_variables.heading("nombre", text="Variable")
        self.tabla_variables.heading("valor", text="Valor")
        self.tabla_variables.column("nombre", width=180, minwidth=80)
        self.tabla_variables.column("valor", width=90, minwidth=65, stretch=False, anchor="e")
        self.tabla_variables.tag_configure("cambio", background="#dff2e9", foreground=self.VERDE)
        self.tabla_variables.grid(row=1, column=0, sticky="nsew")
        scroll_memoria = ttk.Scrollbar(self.tab_memoria, orient="vertical", command=self.tabla_variables.yview)
        scroll_memoria.grid(row=1, column=1, sticky="ns")
        self.tabla_variables.configure(yscrollcommand=scroll_memoria.set)
        self.cambios_variables = set()

        explicacion = self.tarjeta(base)
        explicacion.grid(row=3, column=0, sticky="ew", pady=(12, 10))
        self.rotulo(explicacion, "QUÉ OCURRIÓ EN ESTE PASO", 9, True, color=self.VERDE).pack(anchor="w", padx=12, pady=(8, 2))
        self.detalle = tk.StringVar()
        self.rotulo(explicacion, variable=self.detalle, wrap=850).pack(anchor="w", padx=12, pady=(0, 9))
        resultados = self.tarjeta(base)
        resultados.grid(row=4, column=0, sticky="ew")
        titulo_salida = tk.Frame(resultados, bg="white")
        titulo_salida.pack(fill="x", padx=12, pady=(8, 4))
        self.rotulo(titulo_salida, "▤   Resultado de PRINT", 11, True).pack(side="left")
        self.salida_estado = tk.StringVar(value="Sin salida todavía")
        self.rotulo(titulo_salida, variable=self.salida_estado, size=9, color="#536d65").pack(side="right")
        self.consola = ScrolledText(resultados, height=3, state="disabled", font=("Consolas", 12),
                                    bg="#f8faf9", fg=self.TINTA, relief="flat", padx=12, pady=5)
        self.consola.pack(fill="x", padx=8, pady=(0, 8))
        self.estado = tk.StringVar()
        self.rotulo(base, variable=self.estado, size=9, color="#536d65", bg=self.FONDO).grid(row=5, column=0, sticky="w", pady=(8, 0))
        raiz.bind("<F10>", lambda event: self.avanzar())
        raiz.bind("<F9>", lambda event: self.retroceder())
        raiz.bind("<F5>", lambda event: self.ejecutar())
        raiz.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.ejemplo()

    def rotulo(self, padre, texto="", size=10, bold=False, color=None, bg="white", variable=None, mono=False, wrap=0):
        return tk.Label(padre, text=texto, textvariable=variable, bg=bg, fg=color or self.TINTA,
                        font=("Consolas" if mono else "Segoe UI", size, "bold" if bold else "normal"),
                        anchor="w", justify="left", wraplength=wrap, padx=4, pady=2)

    @staticmethod
    def tarjeta(padre):
        return tk.Frame(padre, bg="white", highlightbackground="#d8e2dd", highlightthickness=1)

    def desplazar(self, inicio, fin):
        self.editor.vbar.set(inicio, fin)
        self.numeros.after_idle(self.dibujar_numeros)

    def dibujar_numeros(self):
        self.numeros.delete("all")
        indice = self.editor.index("@0,0")
        while True:
            posicion = self.editor.dlineinfo(indice)
            if posicion is None:
                break
            self.numeros.create_text(31, posicion[1] + 2, anchor="ne", text=indice.split(".")[0],
                                     font=("Consolas", 12), fill="#7c9186")
            indice = self.editor.index(f"{indice}+1line")

    def editar(self, event=None):
        if not self.editor.edit_modified():
            return
        self.editor.edit_modified(False)
        for etiqueta in ("instruccion", "comentario"):
            self.editor.tag_remove(etiqueta, "1.0", "end")
        texto = self.editor.get("1.0", "end-1c")
        for numero, contenido in enumerate(texto.splitlines(), 1):
            codigo, separador, _ = contenido.partition(";")
            for palabra in re.finditer(r"\b(?:MOV|ADD|SUB|INC|DEC|CMP|JMP|JZ|JNZ|PRINT|HLT|INT|VAR)\b", codigo, re.I):
                self.editor.tag_add("instruccion", f"{numero}.{palabra.start()}", f"{numero}.{palabra.end()}")
            if separador:
                self.editor.tag_add("comentario", f"{numero}.{len(codigo)}", f"{numero}.end")
        self.dibujar_numeros()

    def escribir(self, texto):
        self.consola.configure(state="normal")
        self.consola.insert("end", texto + "\n")
        self.consola.see("end")
        self.consola.configure(state="disabled")
        self.salida_estado.set("Salida del programa")

    def resaltar(self, etiqueta, linea):
        self.editor.tag_add(etiqueta, f"{linea}.0", f"{linea}.end+1c")
        self.editor.see(f"{linea}.0")

    def actualizar(self, anteriores=None):
        registros = self.cpu.registros if self.cpu else dict.fromkeys(CPU.REGISTROS, 0)
        for nombre, valor in registros.items():
            cambio = anteriores is not None and valor != anteriores[nombre]
            self.datos[nombre].set(str(valor))
            self.cambios[nombre].set(f"{anteriores[nombre]} → {valor}" if cambio else "—")
            self.valores[nombre].configure(bg="#dff2e9" if cambio else "white", fg=self.VERDE if cambio else self.TINTA)
        self.mostrar_variables(anteriores)
        pc = self.cpu.pc if self.cpu else 0
        self.datos["PC"].set(f"PC: {pc}   ·   Pasos ejecutados: {self.pasos}")
        banderas = self.cpu.banderas if self.cpu else dict.fromkeys(self.flags, 0)
        for clave, (etiqueta, nombre) in self.flags.items():
            activa = banderas[clave]
            etiqueta.configure(text=f"{nombre} ({clave}): {activa}", bg="#dff2e9" if activa else "#f3f6f5",
                               fg=self.VERDE if activa else "#647970")
        self.editor.tag_remove("siguiente", "1.0", "end")
        if self.cpu and not self.cpu.terminada:
            linea, _, _, texto = self.cpu.instrucciones[self.cpu.pc]
            self.proxima.set(f"Siguiente -> Línea {linea}: {texto}")
            self.resaltar("siguiente", linea)
        else:
            self.proxima.set("Programa finalizado" if self.cpu else "Pulsa «Ejecutar instrucción» para empezar")

    def mostrar_variables(self, anteriores=None, cambios=None):
        memoria = self.cpu.variables if self.cpu else {}
        self.cambios_variables = set(cambios) if cambios is not None else {
            n for n, v in memoria.items() if anteriores is not None and anteriores.get(n) != v}
        for nombre in self.tabla_variables.get_children():
            if nombre not in memoria:
                self.tabla_variables.delete(nombre)
        for nombre, valor in memoria.items():
            opciones = {"values": (nombre, valor), "tags": ("cambio",) if nombre in self.cambios_variables else ()}
            if self.tabla_variables.exists(nombre):
                self.tabla_variables.item(nombre, **opciones)
            else:
                self.tabla_variables.insert("", "end", iid=nombre, **opciones)
        self.pestanas.tab(self.tab_memoria, text=f"Variables ({len(memoria)})")

    def preparar(self):
        if self.catalogo_visible:
            return False
        if self.cpu is not None:
            return not self.cpu.terminada
        self.editor.tag_remove("error", "1.0", "end")
        try:
            self.cpu = CPU(self.editor.get("1.0", "end-1c"))
        except ErrorASM as error:
            self.escribir(f"ERROR · {error}")
            self.resaltar("error", error.linea)
            self.insignia.configure(text="Revisa tu código", bg="#ffe0e0", fg="#991b1b")
            self.detalle.set(str(error))
            self.estado.set("Corrige la línea roja y vuelve a ejecutar. Puedes seguir editando.")
            return False
        self.editor.configure(state="disabled")
        self.actualizar()
        if self.cpu.variables:
            self.pestanas.select(self.tab_memoria)
        if self.cpu.terminada:
            self.detalle.set("No hay instrucciones para ejecutar. Reinicia y escribe tu código.")
            self.finalizar()
            return False
        self.leyenda.grid_remove()
        return True

    def explicar(self, op, args, anterior, flags, salida):
        actuales = {**self.cpu.registros, **self.cpu.variables}
        cambios = [f"{r}: {anterior[r]} → {v}" for r, v in actuales.items() if anterior[r] != v]
        if op in ("JMP", "JZ", "JNZ"):
            salto = op == "JMP" or (op == "JZ" and flags["ZF"] == 1) or (op == "JNZ" and flags["ZF"] == 0)
            return f"Salto a «{args[0]}»." if salto else f"No se salta a «{args[0]}»: ZF={flags['ZF']}. Continúa la siguiente instrucción."
        if op == "PRINT":
            return f"PRINT muestra {salida} en la consola. Los registros conservan sus valores."
        if op == "HLT":
            return "HLT detuvo el programa. Los registros y la salida quedan visibles."
        if op == "CMP":
            return f"Se comparó {args[0]} con {args[1]} sin cambiar registros. ZF={self.cpu.banderas['ZF']} (1 significa iguales)."
        accion = {"MOV": "Se copió el valor", "ADD": "Se sumó", "SUB": "Se restó",
                  "INC": "Se incrementó en 1", "DEC": "Se redujo en 1"}[op]
        return f"{accion}. " + ("; ".join(cambios) if cambios else "El valor no cambió.")

    def avanzar(self):
        if self.ejecutando:
            return
        self.paso()

    def paso(self):
        if not self.preparar():
            return
        self.historial.append({         # Copiar el estado ANTES de modificar la CPU.
            "registros": self.cpu.registros.copy(),
            "variables": self.cpu.variables.copy(),
            "banderas": self.cpu.banderas.copy(),
            "pc": self.cpu.pc,
            "terminada": self.cpu.terminada,
            "pasos": self.pasos,
            "detalle": self.detalle.get(),
            "linea": tuple(map(str, self.editor.tag_ranges("actual"))),
            "consola": self.consola.index("end-1c"),
            "salida_estado": self.salida_estado.get(),
            "cambios": {r: v.get() for r, v in self.cambios.items()},
            "cambios_variables": self.cambios_variables.copy(),
        })
        self.boton_anterior.configure(state="normal")
        anterior = {**self.cpu.registros, **self.cpu.variables}
        flags = self.cpu.banderas.copy()
        _, op, args, texto = self.cpu.instrucciones[self.cpu.pc]
        linea, salida = self.cpu.paso()
        self.pasos += 1
        self.editor.tag_remove("actual", "1.0", "end")
        self.resaltar("actual", linea)
        if salida is not None:
            self.escribir(salida)
        self.actualizar(anterior)
        self.detalle.set(f"Línea {linea} · {texto} — {self.explicar(op, args, anterior, flags, salida)}")
        self.insignia.configure(text="Ejecutando" if self.ejecutando else "Paso completado", bg="#dff2e9", fg=self.VERDE)
        self.estado.set("El código está bloqueado durante la simulación. «Reiniciar / editar» permite modificarlo.")
        if self.cpu.terminada:
            self.finalizar()

    def retroceder(self):
        """Restaurar el estado anterior real; restar uno al PC no deshace un salto."""
        if self.catalogo_visible or not self.historial:
            return
        self.pausar()                   # Cancelar la ejecución automática antes de retroceder.
        anterior = self.historial.pop()
        self.cpu.registros = anterior["registros"]
        self.cpu.variables = anterior["variables"]
        self.cpu.banderas = anterior["banderas"]
        self.cpu.pc = anterior["pc"]
        self.cpu.terminada = anterior["terminada"]
        self.pasos = anterior["pasos"]
        self.consola.configure(state="normal")
        self.consola.delete(anterior["consola"], "end-1c")  # Quitar los PRINT deshechos sin borrar el salto final de Tk.
        self.consola.configure(state="disabled")
        self.salida_estado.set(anterior["salida_estado"])
        self.editor.tag_remove("actual", "1.0", "end")
        if anterior["linea"]:
            self.editor.tag_add("actual", *anterior["linea"])
        self.actualizar()
        self.mostrar_variables(cambios=anterior["cambios_variables"])
        for registro, texto in anterior["cambios"].items():
            self.cambios[registro].set(texto)
            cambio = texto != "—"
            self.valores[registro].configure(bg="#dff2e9" if cambio else "white", fg=self.VERDE if cambio else self.TINTA)
        self.detalle.set(anterior["detalle"])
        if anterior["linea"]:
            self.editor.see(anterior["linea"][0])
        self.boton_ejecutar.configure(state="normal")  # También permite volver desde HLT.
        self.boton_anterior.configure(state="normal" if self.historial else "disabled")
        self.insignia.configure(text="Paso anterior", bg="#fff0bd", fg="#806017")
        self.estado.set(f"Volviste al paso {self.pasos}. Puedes seguir retrocediendo (F9) o avanzar (F10).")

    def finalizar(self):
        self.ejecutando = False
        self.boton_paso.configure(state="disabled")
        self.boton_ejecutar.configure(state="disabled", text="Ejecutar todo")
        self.insignia.configure(text="Finalizado", bg="#dff2e9", fg=self.VERDE)
        self.proxima.set("No hay más instrucciones por ejecutar")
        self.estado.set("Programa terminado. Pulsa «Reiniciar» para empezar de nuevo.")

    def ejecutar(self):
        if self.ejecutando:
            self.pausar()
        elif self.preparar():
            self.ejecutando = True
            self.boton_ejecutar.configure(text="Pausar")
            self.boton_paso.configure(state="disabled")
            self.tick()

    def tick(self):
        self.temporizador = None
        self.paso()
        if self.ejecutando:
            demora = {"Lento": 700, "Normal": 250, "Rápido": 40}[self.velocidad.get()]
            self.temporizador = self.raiz.after(demora, self.tick)

    def pausar(self):
        if self.temporizador is not None:
            self.raiz.after_cancel(self.temporizador)
        self.temporizador, self.ejecutando = None, False
        self.boton_ejecutar.configure(text="Ejecutar todo")
        self.boton_paso.configure(state="normal")
        self.insignia.configure(text="En pausa", bg="#fff0bd", fg="#806017")
        self.estado.set("En pausa: ejecuta una instrucción o pulsa «Ejecutar todo» para continuar.")

    def reiniciar(self):
        if self.catalogo_visible:
            self.cerrar_ejemplos()
        self.pausar()
        self.leyenda.grid()
        self.cpu, self.pasos = None, 0
        self.historial.clear()
        self.boton_anterior.configure(state="disabled")
        self.editor.configure(state="normal")
        for etiqueta in ("actual", "siguiente", "error"):
            self.editor.tag_remove(etiqueta, "1.0", "end")
        self.consola.configure(state="normal")
        self.consola.delete("1.0", "end")
        self.consola.configure(state="disabled")
        self.boton_ejecutar.configure(state="normal")
        self.actualizar()
        self.salida_estado.set("Aquí aparecerán los números de PRINT")
        self.insignia.configure(text="Listo para empezar", bg="#dff2e9", fg=self.VERDE)
        self.detalle.set("Pulsa «Ejecutar instrucción». Aquí verás una explicación de lo que hace cada paso.")
        self.estado.set("CPU educativa de 16 bits · PC cuenta instrucciones desde 0 · ; inicia un comentario")

    def ejemplo(self):
        self.reiniciar()
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", EJEMPLO)

    def mostrar_ejemplos(self):
        if self.catalogo_visible:
            self.cerrar_ejemplos()
            return
        if self.ejecutando:
            self.pausar()
        self.estado_antes_catalogo = self.estado.get()
        self.catalogo_visible = True
        self.titulo_codigo.grid_remove()
        self.indicador_proxima.grid_remove()
        self.boton_ejemplos.configure(text="Volver al código")
        self.catalogo.grid()
        self.catalogo.tkraise()
        self.catalogo.focus_set()
        for boton in (self.boton_paso, self.boton_anterior, self.boton_ejecutar):
            boton.configure(state="disabled")
        self.estado.set("Elige un ejemplo para cargarlo. «Volver al código» conserva tu programa y su estado.")

    def cerrar_ejemplos(self):
        self.catalogo.grid_remove()
        self.titulo_codigo.grid()
        self.indicador_proxima.grid()
        self.boton_ejemplos.configure(text="Ejemplos")
        self.catalogo_visible = False
        finalizado = self.cpu is not None and self.cpu.terminada
        self.boton_paso.configure(state="disabled" if finalizado else "normal")
        self.boton_ejecutar.configure(state="disabled" if finalizado else "normal")
        self.boton_anterior.configure(state="normal" if self.historial else "disabled")
        self.estado.set(self.estado_antes_catalogo)

    def cargar_ejemplo(self, indice):
        titulo, descripcion, codigo, salida = EJEMPLOS[indice]
        self.reiniciar()
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", codigo)
        self.editor.see("1.0")
        self.proxima.set(titulo)
        self.detalle.set(f"{descripcion} Salida esperada: {', '.join(salida)}.")
        self.estado.set("Ejemplo cargado. Pulsa «Ejecutar instrucción» o «Ejecutar todo».")

    def cerrar(self):
        if self.temporizador is not None:
            self.raiz.after_cancel(self.temporizador)
        self.raiz.destroy()


def pruebas():
    """Pruebas incorporadas; no crean carpetas ni requieren instalar paquetes."""
    import unittest

    class PruebasCPU(unittest.TestCase):
        def ejecutar(self, codigo):
            cpu, salida = CPU(codigo), []
            for _ in range(1000):
                if cpu.terminada:
                    return cpu, salida
                _, valor = cpu.paso()
                if valor is not None:
                    salida.append(valor)
            self.fail("El programa de prueba no terminó")

        def test_ejemplo(self):
            cpu, salida = self.ejecutar(EJEMPLO)
            self.assertEqual(salida, ["15"])
            self.assertEqual(cpu.registros["CX"], 0)

        def test_operaciones(self):
            cpu, salida = self.ejecutar("MOV AX, -2\nINC AX\nDEC AX\nMOV BX, 4\nADD AX, BX\nSUB BX, AX\nPRINT AX\nPRINT BX\nHLT")
            self.assertEqual(salida, ["2", "2"])
            self.assertEqual(cpu.registros["AX"], 2)

        def test_saltos_y_cmp(self):
            _, salida = self.ejecutar("MOV AX, 4\nCMP AX, 4\nJZ igual\nPRINT 99\nigual: PRINT AX\nJMP fin\nPRINT 88\nfin: HLT")
            self.assertEqual(salida, ["4"])
            _, salida = self.ejecutar("MOV AX, 2\nbucle: DEC AX\nJNZ bucle\nJZ fin\nPRINT 99\nfin: PRINT AX")
            self.assertEqual(salida, ["0"])

        def test_banderas(self):
            cpu, _ = self.ejecutar("MOV AX, 32767\nADD AX, 1")
            self.assertEqual(cpu.registros["AX"], -32768)
            self.assertEqual(cpu.banderas, {"ZF": 0, "SF": 1, "OF": 1, "CF": 0})
            cpu, _ = self.ejecutar("MOV AX, 0xFFFF\nADD AX, 1\nINC BX")
            self.assertEqual(cpu.banderas["CF"], 1)
            cpu, _ = self.ejecutar("MOV AX, 0\nCMP AX, 1")
            self.assertEqual(cpu.registros["AX"], 0)
            self.assertEqual(cpu.banderas, {"ZF": 0, "SF": 1, "OF": 0, "CF": 1})

        def test_paso_pc_y_hlt(self):
            cpu = CPU("; comentario\ninicio:\nMOV AX, 3\nHLT\nPRINT 9")
            self.assertEqual(cpu.paso(), (3, None))
            self.assertEqual(cpu.pc, 1)
            cpu.paso()
            self.assertTrue(cpu.terminada)
            self.assertEqual(cpu.paso(), (None, None))

        def test_errores(self):
            for codigo in ("MOV EX, 1", "MOV AX 2", "ADD AX,", "NOP", "HLT AX",
                           "JMP perdida", "a: HLT\na: HLT", "PRINT 32768", "MOV AX, BX, CX",
                           "MOV AX, 0x10000", "PRINT " + "9" * 5000, "MOV 1, AX"):
                with self.subTest(codigo=codigo[:40]):
                    with self.assertRaises(ErrorASM):
                        CPU(codigo)

        def test_reinicio(self):
            cpu, _ = self.ejecutar("MOV AX, 8\nHLT")
            nuevo = CPU("MOV AX, 8\nHLT")
            self.assertEqual(nuevo.pc, 0)
            self.assertTrue(all(v == 0 for v in nuevo.registros.values()))
            self.assertNotEqual(cpu.registros, nuevo.registros)

        def test_variables_y_operaciones(self):
            cpu, salida = self.ejecutar("int a = 5;\nVAR b, 3\nINT total\nMOV total, a\nADD total, b\nSUB total, 1\nINC total\nDEC b\nMOV AX, total\nCMP total, AX\nJNZ fallo\nPRINT total\nPRINT b\nHLT\nfallo: PRINT 99")
            self.assertEqual(salida, ["8", "2"])
            self.assertEqual(cpu.variables, {"A": 5, "B": 2, "TOTAL": 8})
            self.assertEqual(cpu.registros["AX"], 8)

        def test_muchas_variables(self):
            declaraciones = "\n".join(f"INT dato_{n} = {n % 100}" for n in range(1500))
            cpu, salida = self.ejecutar(declaraciones + "\nMOV dato_1499, 12\nADD dato_1499, dato_0\nPRINT dato_1499\nHLT")
            self.assertEqual(len(cpu.variables), 1500)
            self.assertEqual(salida, ["12"])
            self.assertEqual(cpu.pc, 4)  # Las declaraciones no son instrucciones de CPU.

        def test_bucle_con_variables(self):
            cpu, salida = self.ejecutar("INT total=0\nINT contador=5\nbucle: ADD total, contador\nDEC contador\nJNZ bucle\nPRINT total\nHLT")
            self.assertEqual(salida, ["15"])
            self.assertEqual(cpu.variables["CONTADOR"], 0)

        def test_desborde_en_memoria(self):
            cpu, salida = self.ejecutar("INT x = 32767\nINC x\nPRINT x")
            self.assertEqual(salida, ["-32768"])
            self.assertEqual(cpu.banderas["OF"], 1)
            cpu, _ = self.ejecutar("VAR x, 0xFFFF\nADD x, 1")
            self.assertEqual(cpu.variables["X"], 0)
            self.assertEqual(cpu.banderas["CF"], 1)

        def test_errores_de_variables(self):
            for codigo in ("INT AX=1", "INT a=1\nVAR a,2", "INT 21h", "INT 2x=3",
                           "INT a=40000", "INT a=b", "INT a=1+2", "PRINT desconocida",
                           "MOV desconocida, 1", "INT MOV=3", "INT a=0\na: HLT",
                           "a: HLT\nINT a=0"):
                with self.subTest(codigo=codigo):
                    with self.assertRaises(ErrorASM):
                        CPU(codigo)

        def test_solo_declaraciones(self):
            cpu = CPU("INT a\nVAR b, -4")
            self.assertEqual(cpu.variables, {"A": 0, "B": -4})
            self.assertTrue(cpu.terminada)

        def test_glosario_completo(self):
            for titulo, _, codigo, esperado in EJEMPLOS:
                with self.subTest(ejemplo=titulo):
                    _, salida = self.ejecutar(codigo)
                    self.assertEqual(salida, list(esperado))

    resultado = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PruebasCPU))
    return 0 if resultado.wasSuccessful() else 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(pruebas())
    raiz = tk.Tk()
    Ventana(raiz)
    raiz.mainloop()
