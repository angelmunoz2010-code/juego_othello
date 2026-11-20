"""Cliente Othello/Reversi mejorado: Negamax + alfa-beta + TT + iteracion.
Compatible con servidor_othello.py del usuario.
Uso: python cliente_othello_mejorado.py IP [PUERTO] [NOMBRE]
"""
import json
import socket
import sys
import time

IP = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PUERTO = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
NOMBRE = sys.argv[3] if len(sys.argv) > 3 else "EquipoMinimaxPlus"

# El servidor permite 30 segundos. Dejamos margen para enviar la respuesta.
TIEMPO_LIMITE = 20.0
PROFUNDIDAD_MAX = 64
VACIO, NEGRA, BLANCA = 0, 1, 2
DIRECCIONES = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
ESQUINAS = [(0,0),(0,7),(7,0),(7,7)]
ADYACENTES_ESQUINA = {
    (0,0): [(0,1),(1,0),(1,1)], (0,7): [(0,6),(1,7),(1,6)],
    (7,0): [(7,1),(6,0),(6,1)], (7,7): [(7,6),(6,7),(6,6)]
}
PESOS = [
 [120,-35,18,8,8,18,-35,120],
 [-35,-55,-8,-5,-5,-8,-55,-35],
 [18,-8,12,3,3,12,-8,18],
 [8,-5,3,2,2,3,-5,8],
 [8,-5,3,2,2,3,-5,8],
 [18,-8,12,3,3,12,-8,18],
 [-35,-55,-8,-5,-5,-8,-55,-35],
 [120,-35,18,8,8,18,-35,120]
]
INF = 10**9
MATE = 10**7

class TiempoAgotado(Exception):
    pass

def rival(color):
    return 3 - color

def contar(t, color):
    return sum(row.count(color) for row in t)

def fichas_a_voltear(t, f, c, color):
    if not (0 <= f < 8 and 0 <= c < 8) or t[f][c] != VACIO:
        return []
    enemigo = rival(color)
    resultado = []
    for df, dc in DIRECCIONES:
        nf, nc = f + df, c + dc
        linea = []
        while 0 <= nf < 8 and 0 <= nc < 8 and t[nf][nc] == enemigo:
            linea.append((nf, nc))
            nf += df; nc += dc
        if linea and 0 <= nf < 8 and 0 <= nc < 8 and t[nf][nc] == color:
            resultado.extend(linea)
    return resultado

def jugadas_validas(t, color):
    return [(f,c) for f in range(8) for c in range(8)
            if t[f][c] == VACIO and fichas_a_voltear(t,f,c,color)]

def hacer_jugada(t, f, c, color):
    volteadas = fichas_a_voltear(t, f, c, color)
    t[f][c] = color
    for vf, vc in volteadas:
        t[vf][vc] = color
    return volteadas

def deshacer_jugada(t, f, c, color, volteadas):
    t[f][c] = VACIO
    enemigo = rival(color)
    for vf, vc in volteadas:
        t[vf][vc] = enemigo

class Buscador:
    def __init__(self, limite):
        self.limite = limite
        self.nodos = 0
        self.tabla = {}
        self.historial = [[0]*64 for _ in range(2)]
        self.killers = [[None, None] for _ in range(66)]

    def revisar_tiempo(self):
        self.nodos += 1
        if (self.nodos & 127) == 0 and time.monotonic() >= self.limite:
            raise TiempoAgotado

    def clave(self, t, color):
        return (tuple(v for fila in t for v in fila), color)

    def evaluar(self, t, color):
        enemigo = rival(color)
        mis = contar(t, color); suyas = contar(t, enemigo)
        vacias = 64 - mis - suyas
        if vacias == 0:
            return MATE * (mis - suyas)

        # La importancia de la posición cambia a medida que avanza la partida.
        fase = (64 - vacias) / 64.0
        pos = 0
        for f in range(8):
            for c in range(8):
                v = t[f][c]
                if v == color: pos += PESOS[f][c]
                elif v == enemigo: pos -= PESOS[f][c]

        # Penaliza casillas peligrosas junto a esquinas aún vacías.
        peligro = 0
        for esquina, vecinos in ADYACENTES_ESQUINA.items():
            ef, ec = esquina
            if t[ef][ec] == VACIO:
                for f, c in vecinos:
                    if t[f][c] == color: peligro -= 22
                    elif t[f][c] == enemigo: peligro += 22

        mis_esquinas = sum(t[f][c] == color for f,c in ESQUINAS)
        sus_esquinas = sum(t[f][c] == enemigo for f,c in ESQUINAS)
        corner_score = 900 * (mis_esquinas - sus_esquinas)

        mis_mov = len(jugadas_validas(t, color))
        sus_mov = len(jugadas_validas(t, enemigo))
        movilidad = 0 if mis_mov + sus_mov == 0 else 100 * (mis_mov - sus_mov) / (mis_mov + sus_mov)

        # Conteo de fichas poco importante al inicio, decisivo al final.
        diferencia = mis - suyas
        peso_fichas = 2 if vacias > 40 else 8 if vacias > 20 else 25 if vacias > 10 else 100
        fichas = peso_fichas * diferencia

        # Aproximación a estabilidad: fichas en bordes conectadas a una esquina propia.
        estable = 0
        for f, c in ESQUINAS:
            if t[f][c] == color:
                # Cuenta tramos continuos del borde desde una esquina controlada.
                for df, dc in [(0,1),(0,-1),(1,0),(-1,0)]:
                    nf, nc = f+df, c+dc
                    while 0 <= nf < 8 and 0 <= nc < 8 and t[nf][nc] == color:
                        estable += 12
                        nf += df; nc += dc
            elif t[f][c] == enemigo:
                for df, dc in [(0,1),(0,-1),(1,0),(-1,0)]:
                    nf, nc = f+df, c+dc
                    while 0 <= nf < 8 and 0 <= nc < 8 and t[nf][nc] == enemigo:
                        estable -= 12
                        nf += df; nc += dc

        # La movilidad domina al principio; el material domina al final.
        return pos + 5*movilidad + corner_score + peligro + fichas + estable


    def ordenar(self, t, color, movs, mejor_tt=None, prof=0):
        def valor(m):
            f,c = m
            score = PESOS[f][c] * 8
            if m == mejor_tt: score += 2_000_000
            if self.killers[prof][0] == m: score += 500_000
            elif self.killers[prof][1] == m: score += 250_000
            score += self.historial[color-1][f*8+c]
            # Preferir esquinas y capturar más solo como desempate moderado.
            if m in ESQUINAS: score += 100_000
            score += len(fichas_a_voltear(t,f,c,color))
            return score
        return sorted(movs, key=valor, reverse=True)


    def negamax(self, t, prof, alfa, beta, color):
        self.revisar_tiempo()
        movs = jugadas_validas(t, color)
        rival_movs = None
        if not movs:
            rival_movs = jugadas_validas(t, rival(color))
            if not rival_movs:
                return MATE * (contar(t,color) - contar(t,rival(color)))
            # Pasar turno no consume profundidad.
            return -self.negamax(t, prof, -beta, -alfa, rival(color))
        if prof <= 0:
            return self.evaluar(t, color)

        key = self.clave(t, color)
        entrada = self.tabla.get(key)
        mejor_tt = None
        alfa_original = alfa
        beta_original = beta
        if entrada:
            d, val, flag, mov = entrada
            mejor_tt = mov
            if d >= prof:
                if flag == 0: return val
                if flag == 1: alfa = max(alfa, val)
                elif flag == 2: beta = min(beta, val)
                if alfa >= beta: return val

        mejor_val = -INF
        mejor_mov = None
        for m in self.ordenar(t, color, movs, mejor_tt, min(prof,65)):
            f,c = m
            flips = hacer_jugada(t,f,c,color)
            val = -self.negamax(t, prof-1, -beta, -alfa, rival(color))
            deshacer_jugada(t,f,c,color,flips)
            if val > mejor_val:
                mejor_val, mejor_mov = val, m
            alfa = max(alfa, val)
            if alfa >= beta:
                self.killers[min(prof,65)][1] = self.killers[min(prof,65)][0]
                self.killers[min(prof,65)][0] = m
                self.historial[color-1][f*8+c] += prof*prof
                break

        flag = 1 if mejor_val <= alfa_original else 2 if mejor_val >= beta_original else 0
        self.tabla[key] = (prof, mejor_val, flag, mejor_mov)
        return mejor_val


def elegir_jugada(tablero, jugadas, color):
    jugadas = [tuple(m) for m in jugadas]
    if not jugadas:
        return (0,0)
    if len(jugadas) == 1:
        return jugadas[0]

    inicio = time.monotonic()
    limite = inicio + TIEMPO_LIMITE
    buscador = Buscador(limite)
    t = [row[:] for row in tablero]
    # Primera jugada razonable si no termina ninguna iteración.
    mejor = max(jugadas, key=lambda m: (PESOS[m[0]][m[1]], m in ESQUINAS))
    profundidad_completa = 0
    valor_final = None

    for prof in range(1, PROFUNDIDAD_MAX+1):
        try:
            orden = [mejor] + [m for m in jugadas if m != mejor]
            alfa = -INF
            mejor_iter = mejor
            mejor_val_iter = -INF
            for f,c in orden:
                buscador.revisar_tiempo()
                flips = hacer_jugada(t,f,c,color)
                val = -buscador.negamax(t, prof-1, -INF, -alfa, rival(color))
                deshacer_jugada(t,f,c,color,flips)
                if val > mejor_val_iter:
                    mejor_val_iter, mejor_iter = val, (f,c)
                alfa = max(alfa,val)
            # Solo se guarda si la iteración se completó totalmente.
            mejor = mejor_iter
            valor_final = mejor_val_iter
            profundidad_completa = prof
        except TiempoAgotado:
            break

    print(f"Jugada {mejor} | profundidad {profundidad_completa} | nodos {buscador.nodos} | {time.monotonic()-inicio:.2f}s")
    return mejor


def main():
    with socket.create_connection((IP, PUERTO), timeout=10) as s:
        s.settimeout(None)
        lector = s.makefile("r", encoding="utf-8")
        def enviar(msg):
            s.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        enviar({"tipo":"hola", "nombre":NOMBRE})
        print(f"Conectado a {IP}:{PUERTO} como {NOMBRE}")
        ultimo = None
        for linea in lector:
            if not linea.strip():
                continue
            msg = json.loads(linea)
            tipo = msg.get("tipo")
            if tipo == "bienvenida":
                print(f"Juegas con {'negras' if msg['color']==1 else 'blancas'} contra {msg['rival']}")
            elif tipo == "tu_turno":
                ultimo = msg
                f,c = elegir_jugada(msg["tablero"], msg["jugadas_validas"], msg["color"])
                enviar({"tipo":"jugada", "fila":f, "columna":c})
            elif tipo == "error":
                print("Servidor rechazó la jugada:", msg.get("mensaje", "error"))
                if ultimo and msg.get("jugadas_validas"):
                    f,c = tuple(msg["jugadas_validas"][0])
                    enviar({"tipo":"jugada", "fila":f, "columna":c})
            elif tipo == "paso":
                print("Pasas turno (sin movimientos válidos).")
            elif tipo == "jugada_rival":
                pass
            elif tipo == "fin":
                print(f"Fin: {msg.get('motivo')} | ganador={msg.get('ganador')} | puntaje={msg.get('puntaje')}")
                break

if __name__ == "__main__":
    main()
