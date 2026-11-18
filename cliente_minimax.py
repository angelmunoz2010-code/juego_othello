"""
Cliente de Othello con IA Minimax mejorada + interfaz gráfica (Tkinter).

Uso:
    python cliente_minimax_gui.py IP [PUERTO] [NOMBRE]
"""

import json
import socket
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

IP = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PUERTO = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
NOMBRE = sys.argv[3] if len(sys.argv) > 3 else "IA_Minimax"

TIEMPO_LIMITE = 10.0
PROFUNDIDAD_MAX = 20
VACIO = 0
NEGRA, BLANCA = 1, 2

DIRECCIONES = [(-1, -1), (-1, 0), (-1, 1), (0, -1),
               (0, 1), (1, -1), (1, 0), (1, 1)]

PESOS = [
    [100, -20, 10,  5,  5, 10, -20, 100],
    [-20, -50, -2, -2, -2, -2, -50, -20],
    [ 10,  -2,  1,  1,  1,  1,  -2,  10],
    [  5,  -2,  1,  0,  0,  1,  -2,   5],
    [  5,  -2,  1,  0,  0,  1,  -2,   5],
    [ 10,  -2,  1,  1,  1,  1,  -2,  10],
    [-20, -50, -2, -2, -2, -2, -50, -20],
    [100, -20, 10,  5,  5, 10, -20, 100],
]
ESQUINAS = [(0, 0), (0, 7), (7, 0), (7, 7)]


class SinTiempo(Exception):
    pass


# ---------------------------------------------------------------- reglas

def rival(color):
    return 3 - color


def fichas_a_voltear(t, fila, col, color):
    if t[fila][col] != VACIO:
        return ()
    otro = rival(color)
    volteadas = []
    for df, dc in DIRECCIONES:
        f, c = fila + df, col + dc
        linea = []
        while 0 <= f < 8 and 0 <= c < 8 and t[f][c] == otro:
            linea.append((f, c))
            f, c = f + df, c + dc
        if linea and 0 <= f < 8 and 0 <= c < 8 and t[f][c] == color:
            volteadas.extend(linea)
    return volteadas


def jugadas_validas(t, color):
    return [(f, c) for f in range(8) for c in range(8)
            if t[f][c] == VACIO and fichas_a_voltear(t, f, c, color)]


def hacer_jugada(t, fila, col, color):
    volteadas = fichas_a_voltear(t, fila, col, color)
    for f, c in volteadas:
        t[f][c] = color
    t[fila][col] = color
    return volteadas


def deshacer_jugada(t, fila, col, volteadas):
    t[fila][col] = VACIO
    for f, c in volteadas:
        t[f][c] = VACIO


def contar(t, color):
    return sum(r.count(color) for r in t)


# ---------------------------------------------------------------- evaluación

def evaluar(t, yo, movs_yo, movs_rival):
    otro = rival(yo)
    mis = contar(t, yo)
    sus = contar(t, otro)
    vacias = 64 - mis - sus

    if vacias == 0:
        return 100000 * (mis - sus)

    posicion = 0
    for f in range(8):
        for c in range(8):
            v = t[f][c]
            if v == yo:
                posicion += PESOS[f][c]
            elif v == otro:
                posicion -= PESOS[f][c]

    mm, sm = len(movs_yo), len(movs_rival)
    movilidad = 100 * (mm - sm) / (mm + sm) if (mm + sm) else 0

    mis_esq = sum(1 for f, c in ESQUINAS if t[f][c] == yo)
    sus_esq = sum(1 for f, c in ESQUINAS if t[f][c] == otro)
    esquinas = 40 * (mis_esq - sus_esq)

    if mis + sus:
        fichas = 100 * (mis - sus) / (mis + sus)
    else:
        fichas = 0
    if vacias > 30:
        peso_fichas = 0.0
    elif vacias > 15:
        peso_fichas = 0.5
    elif vacias > 8:
        peso_fichas = 1.5
    else:
        peso_fichas = 4.0

    return posicion + 3 * movilidad + 10 * esquinas + peso_fichas * fichas


# ---------------------------------------------------------------- buscador

class Buscador:
    def __init__(self, color, limite):
        self.color = color
        self.limite = limite
        self.nodos = 0
        self.check_cada = 4096
        self.tt = {}
        self.history = [[0] * 64 for _ in range(2)]
        self.killer = [[None, None] for _ in range(PROFUNDIDAD_MAX + 2)]

    def _chequear_tiempo(self):
        self.nodos += 1
        if self.nodos % self.check_cada == 0 and time.time() > self.limite:
            raise SinTiempo()

    def _ordenar(self, t, movs, color, prof):
        def key(m):
            f, c = m
            base = PESOS[f][c]
            for (ef, ec) in ESQUINAS:
                if abs(ef - f) <= 1 and abs(ec - c) <= 1 and (ef, ec) != (f, c):
                    if t[ef][ec] == VACIO:
                        base -= 60
            base += self.history[color - 1][f * 8 + c]
            if self.killer[prof][0] == m:
                base += 10000
            elif self.killer[prof][1] == m:
                base += 5000
            return base
        movs.sort(key=key, reverse=True)

    def _clave_tt(self, t, color, prof):
        h = 1469598103934665603
        for f in range(8):
            for c in range(8):
                h = (h ^ t[f][c]) * 1099511628211
        h ^= color
        h ^= prof
        return h & 0xFFFFFFFFFFFFFFFF

    def negamax(self, t, prof, alfa, beta, color, movs_color, movs_rival):
        self._chequear_tiempo()

        if not movs_color:
            if not movs_rival:
                mis = contar(t, color)
                sus = contar(t, rival(color))
                return 100000 * (mis - sus), None
            return -self.negamax(t, prof, -beta, -alfa, rival(color),
                                 movs_rival, movs_color)[0], None

        if prof == 0:
            return evaluar(t, color, movs_color, movs_rival), None

        clave = self._clave_tt(t, color, prof)
        entrada = self.tt.get(clave)
        if entrada is not None:
            prof_tt, val_tt, flag, mejor_tt = entrada
            if prof_tt >= prof:
                if flag == 0:
                    return val_tt, mejor_tt
                elif flag == 1:
                    if val_tt > alfa:
                        alfa = val_tt
                elif flag == 2:
                    if val_tt < beta:
                        beta = val_tt
                if alfa >= beta:
                    return val_tt, mejor_tt

        self._ordenar(t, movs_color, color, prof)

        alfa_orig = alfa
        mejor_val = float("-inf")
        mejor_mov = movs_color[0]
        otro = rival(color)

        for (f, c) in movs_color:
            volteadas = hacer_jugada(t, f, c, color)
            nuevos_movs_rival = jugadas_validas(t, otro)
            nuevos_movs_yo = jugadas_validas(t, color)
            v, _ = self.negamax(t, prof - 1, -beta, -alfa, otro,
                                nuevos_movs_rival, nuevos_movs_yo)
            v = -v
            deshacer_jugada(t, f, c, volteadas)

            if v > mejor_val:
                mejor_val = v
                mejor_mov = (f, c)
            if v > alfa:
                alfa = v
            if alfa >= beta:
                if self.killer[prof][0] != (f, c):
                    self.killer[prof][1] = self.killer[prof][0]
                    self.killer[prof][0] = (f, c)
                self.history[color - 1][f * 8 + c] += prof * prof
                break

        if mejor_val <= alfa_orig:
            flag = 2
        elif mejor_val >= beta:
            flag = 1
        else:
            flag = 0
        self.tt[clave] = (prof, mejor_val, flag, mejor_mov)
        return mejor_val, mejor_mov


# ---------------------------------------------------------------- libro

LIBRO = {}

def _clave_tablero(t):
    return tuple(v for fila in t for v in fila)

def _agregar_libro(tablero, jugadas):
    LIBRO[_clave_tablero(tablero)] = jugadas

_t0 = [[0]*8 for _ in range(8)]
_t0[3][3] = _t0[4][4] = BLANCA
_t0[3][4] = _t0[4][3] = NEGRA
_agregar_libro(_t0, [(2, 3), (3, 2), (4, 5), (5, 4)])

_t1 = [r[:] for r in _t0]
hacer_jugada(_t1, 2, 3, NEGRA)
_agregar_libro(_t1, [(2, 2), (3, 2), (4, 2), (2, 4), (4, 4)])


# ---------------------------------------------------------------- elección

def elegir_jugada(tablero, jugadas, color, excluir=None):
    jugadas = [tuple(m) for m in jugadas]
    if excluir is not None:
        jugadas = [m for m in jugadas if m != tuple(excluir)]
    if not jugadas:
        return (0, 0)
    if len(jugadas) == 1:
        return jugadas[0]

    clave = _clave_tablero(tablero)
    if clave in LIBRO:
        for m in LIBRO[clave]:
            if m in jugadas:
                return m, 0, 0, 0.0

    t = [r[:] for r in tablero]
    otro = rival(color)
    movs_yo = jugadas
    movs_rival = jugadas_validas(t, otro)

    t_inicio = time.time()
    limite = t_inicio + TIEMPO_LIMITE
    buscador = Buscador(color, limite)

    mejor = max(jugadas, key=lambda m: PESOS[m[0]][m[1]])
    prof_alcanzada = 0

    for prof in range(1, PROFUNDIDAD_MAX + 1):
        buscador.limite = limite
        try:
            orden = [mejor] + [m for m in jugadas if m != mejor]
            mejor_iter, mejor_val = None, float("-inf")
            alfa = float("-inf")
            beta = float("inf")
            for (f, c) in orden:
                volteadas = hacer_jugada(t, f, c, color)
                nuevos_movs_rival = jugadas_validas(t, otro)
                nuevos_movs_yo = jugadas_validas(t, color)
                v, _ = buscador.negamax(t, prof - 1, -beta, -alfa, otro,
                                        nuevos_movs_rival, nuevos_movs_yo)
                v = -v
                deshacer_jugada(t, f, c, volteadas)
                if v > mejor_val:
                    mejor_val, mejor_iter = v, (f, c)
                if v > alfa:
                    alfa = v
            mejor = mejor_iter
            prof_alcanzada = prof
        except SinTiempo:
            break
        if abs(mejor_val) > 90000:
            break

    tiempo_usado = time.time() - t_inicio
    return mejor, prof_alcanzada, buscador.nodos, tiempo_usado


# ---------------------------------------------------------------- GUI

class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Othello - {NOMBRE}")
        self.root.configure(bg="#1e1e1e")

        self.tablero = [[0]*8 for _ in range(8)]
        self.color = None
        self.rival_nombre = ""
        self.ultima_propia = None
        self.ultima_rival = None
        self.ultimas_validas = []
        self.socket = None
        self.lector = None
        self.conectado = False

        # ---- Layout
        frame_izq = tk.Frame(root, bg="#1e1e1e")
        frame_izq.pack(side=tk.LEFT, padx=10, pady=10)

        frame_der = tk.Frame(root, bg="#1e1e1e")
        frame_der.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ---- Tablero
        self.canvas = tk.Canvas(frame_izq, width=480, height=480,
                                bg="#0b5d1e", highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.click_tablero)

        # ---- Estado
        self.lbl_color = tk.Label(frame_der, text="Color: -", fg="#ffffff",
                                  bg="#1e1e1e", font=("Consolas", 12, "bold"))
        self.lbl_color.pack(anchor="w")

        self.lbl_turno = tk.Label(frame_der, text="Turno: -", fg="#ffd54f",
                                  bg="#1e1e1e", font=("Consolas", 12))
        self.lbl_turno.pack(anchor="w")

        self.lbl_marcador = tk.Label(frame_der, text="Marcador: X 0 - 0 O", fg="#ffffff",
                                     bg="#1e1e1e", font=("Consolas", 12))
        self.lbl_marcador.pack(anchor="w", pady=(4, 8))

        self.lbl_prof = tk.Label(frame_der, text="Profundidad: -", fg="#b0bec5",
                                 bg="#1e1e1e", font=("Consolas", 10))
        self.lbl_prof.pack(anchor="w")

        self.lbl_nodos = tk.Label(frame_der, text="Nodos: -", fg="#b0bec5",
                                  bg="#1e1e1e", font=("Consolas", 10))
        self.lbl_nodos.pack(anchor="w")

        self.lbl_tiempo = tk.Label(frame_der, text="Tiempo: -", fg="#b0bec5",
                                   bg="#1e1e1e", font=("Consolas", 10))
        self.lbl_tiempo.pack(anchor="w", pady=(0, 6))

        # Barra de progreso del pensamiento
        self.prog = ttk.Progressbar(frame_der, orient="horizontal",
                                    length=300, mode="determinate", maximum=100)
        self.prog.pack(anchor="w", pady=(0, 10))

        # ---- Log
        tk.Label(frame_der, text="Registro:", fg="#ffffff", bg="#1e1e1e",
                 font=("Consolas", 10, "bold")).pack(anchor="w")
        self.log = tk.Text(frame_der, width=42, height=18, bg="#111111",
                           fg="#dcdcdc", font=("Consolas", 9), state="disabled",
                           wrap="word", bd=0)
        self.log.pack(fill=tk.BOTH, expand=True)

        # ---- Botón reconectar
        self.btn_reconectar = tk.Button(frame_der, text="Reconectar",
                                        command=self.reconectar,
                                        bg="#37474f", fg="white",
                                        activebackground="#546e7a",
                                        font=("Consolas", 10, "bold"))
        self.btn_reconectar.pack(pady=(8, 0), fill=tk.X)

        self.dibujar_tablero()
        self.conectar()

    # ------------------------------------------------ dibujo
    def dibujar_tablero(self):
        self.canvas.delete("all")
        celda = 60
        for f in range(8):
            for c in range(8):
                x1, y1 = c * celda, f * celda
                x2, y2 = x1 + celda, y1 + celda
                # Color base tipo tablero
                self.canvas.create_rectangle(x1, y1, x2, y2,
                                             fill="#0b5d1e", outline="#063d14")
                # Resaltar jugada propia (azul)
                if self.ultima_propia == (f, c):
                    self.canvas.create_rectangle(x1+2, y1+2, x2-2, y2-2,
                                                 outline="#42a5f5", width=3)
                # Resaltar jugada rival (rojo)
                if self.ultima_rival == (f, c):
                    self.canvas.create_rectangle(x1+2, y1+2, x2-2, y2-2,
                                                 outline="#ef5350", width=3)
                v = self.tablero[f][c]
                cx, cy = x1 + celda/2, y1 + celda/2
                if v == NEGRA:
                    self.canvas.create_oval(cx-24, cy-24, cx+24, cy+24,
                                            fill="#1a1a1a", outline="#000")
                elif v == BLANCA:
                    self.canvas.create_oval(cx-24, cy-24, cx+24, cy+24,
                                            fill="#f5f5f5", outline="#999")
                else:
                    # Punto guía si es jugada válida (solo si es mi turno)
                    if self.color and (f, c) in self.ultimas_validas \
                            and self.lbl_turno.cget("text").endswith("TÚ"):
                        self.canvas.create_oval(cx-4, cy-4, cx+4, cy+4,
                                                fill="#c8e6c9", outline="")

    def actualizar_marcador(self):
        n = contar(self.tablero, NEGRA)
        b = contar(self.tablero, BLANCA)
        self.lbl_marcador.config(text=f"Marcador: X {n} - {b} O")

    # ------------------------------------------------ red
    def log_msg(self, texto):
        self.log.config(state="normal")
        self.log.insert(tk.END, texto + "\n")
        self.log.see(tk.END)
        self.log.config(state="disabled")

    def enviar(self, msg):
        if not self.conectado:
            return
        try:
            self.socket.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        except OSError as e:
            self.log_msg(f"[error envío] {e}")

    def conectar(self):
        self.log_msg(f"Conectando a {IP}:{PUERTO} ...")
        try:
            self.socket = socket.create_connection((IP, PUERTO), timeout=15)
            self.socket.settimeout(60)
            self.lector = self.socket.makefile("r", encoding="utf-8")
            self.conectado = True
            self.enviar({"tipo": "hola", "nombre": NOMBRE})
            self.log_msg(f"Conectado como {NOMBRE}")
            hilo = threading.Thread(target=self.bucle_lectura, daemon=True)
            hilo.start()
        except Exception as e:
            self.log_msg(f"[error conexión] {e}")
            messagebox.showerror("Error", f"No se pudo conectar:\n{e}")

    def reconectar(self):
        try:
            if self.socket:
                self.socket.close()
        except Exception:
            pass
        self.conectado = False
        self.log_msg("Reconectando...")
        self.conectar()

    def bucle_lectura(self):
        ultimo = None
        ultima_invalida = None
        try:
            for linea in self.lector:
                if not linea.strip():
                    continue
                msg = json.loads(linea)
                tipo = msg["tipo"]

                if tipo == "bienvenida":
                    self.color = msg["color"]
                    self.rival_nombre = msg["rival"]
                    txt = "NEGRAS (X)" if self.color == NEGRA else "BLANCAS (O)"
                    self.root.after(0, lambda t=txt, r=msg["rival"]:
                                    self.lbl_color.config(text=f"Color: {t} vs {r}"))
                    self.root.after(0, self.log_msg,
                                    f"Bienvenida: juegas con {txt} contra {msg['rival']}")

                elif tipo == "tu_turno":
                    ultimo = msg
                    ultima_invalida = None
                    self.tablero = [r[:] for r in msg["tablero"]]
                    self.ultimas_validas = [tuple(m) for m in msg["jugadas_validas"]]
                    self.root.after(0, self.dibujar_tablero)
                    self.root.after(0, self.actualizar_marcador)
                    self.root.after(0, self.lbl_turno.config, {"text": "Turno: TÚ"})
                    self.root.after(0, self.animar_progreso_inicio)

                    # Pensar en hilo aparte para no bloquear la GUI
                    def pensar():
                        jug, prof, nodos, t_usado = elegir_jugada(
                            msg["tablero"], msg["jugadas_validas"], msg["color"])
                        self.root.after(0, self.lbl_prof.config,
                                        {"text": f"Profundidad: {prof}"})
                        self.root.after(0, self.lbl_nodos.config,
                                        {"text": f"Nodos: {nodos:,}"})
                        self.root.after(0, self.lbl_tiempo.config,
                                        {"text": f"Tiempo: {t_usado:.2f}s"})
                        self.root.after(0, self.prog.config, {"value": 100})
                        self.root.after(0, self.log_msg,
                                        f"→ Juego {jug} (prof {prof}, {nodos} nodos, {t_usado:.2f}s)")
                        self.ultima_propia = jug
                        self.ultima_rival = None
                        self.root.after(0, self.dibujar_tablero)
                        self.enviar({"tipo": "jugada", "fila": jug[0], "columna": jug[1]})

                    threading.Thread(target=pensar, daemon=True).start()

                elif tipo == "error":
                    self.root.after(0, self.log_msg,
                                    f"[servidor] {msg.get('mensaje','error')}")
                    if ultimo is None:
                        continue
                    def repensar():
                        f, c = elegir_jugada(ultimo["tablero"], msg["jugadas_validas"],
                                             ultimo["color"], excluir=ultima_invalida)
                        self.enviar({"tipo": "jugada", "fila": f, "columna": c})
                    nonlocal_ultima_invalida = None
                    threading.Thread(target=repensar, daemon=True).start()

                elif tipo == "paso":
                    self.root.after(0, self.log_msg, "Paso de turno (sin jugadas).")

                elif tipo == "jugada_rival":
                    self.tablero = [r[:] for r in msg["tablero"]]
                    self.ultima_rival = (msg["fila"], msg["columna"])
                    self.ultima_propia = None
                    self.root.after(0, self.dibujar_tablero)
                    self.root.after(0, self.actualizar_marcador)
                    self.root.after(0, self.log_msg,
                                    f"Rival juega ({msg['fila']}, {msg['columna']})")

                elif tipo == "fin":
                    self.root.after(0, self.actualizar_marcador)
                    self.root.after(0, self.dibujar_tablero)
                    motivo = msg.get("motivo", "")
                    gan = msg.get("ganador", 0)
                    punt = msg.get("puntaje", {})
                    texto = "EMPATE" if gan == 0 else (
                        "GANASTE" if gan == self.color else "PERDISTE")
                    self.root.after(0, self.log_msg,
                                    f"FIN ({motivo}) → {texto} | {punt}")
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Fin de la partida",
                        f"{texto}\nMotivo: {motivo}\nPuntaje: {punt}"))
                    break
        except Exception as e:
            self.root.after(0, self.log_msg, f"[desconectado] {e}")
        finally:
            self.conectado = False

    # ------------------------------------------------ animación progreso
    def animar_progreso_inicio(self):
        self.prog["value"] = 0
        self._anim_inicio = time.time()
        self._anim_activa = True
        self._anim_step()

    def _anim_step(self):
        if not getattr(self, "_anim_activa", False):
            return
        if not self.conectado:
            return
        pct = min(100, (time.time() - self._anim_inicio) / TIEMPO_LIMITE * 100)
        self.prog["value"] = pct
        if pct < 100:
            self.root.after(80, self._anim_step)
        else:
            self._anim_activa = False

    # ------------------------------------------------ click manual (opcional)
    def click_tablero(self, event):
        # Si quieres jugar manualmente, descomenta. Por defecto la IA juega sola.
        # f = event.y // 60
        # c = event.x // 60
        # if (f, c) in self.ultimas_validas and self.lbl_turno.cget("text").endswith("TÚ"):
        #     self.enviar({"tipo": "jugada", "fila": f, "columna": c})
        pass


def main():
    root = tk.Tk()
    AppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()