"""
mirrorCheck.py

Compara cada nodo del lado L con su gemelo del lado R y dice si es un espejo
de verdad o no. No modifica nada: solo lee y escribe un informe.

Uso en Maya:

    import mirrorCheck
    mirrorCheck.report("Character", filter_text="eye")     # solo los ojos
    mirrorCheck.report("Character", filter_text="lip")     # solo la boca
    mirrorCheck.report("Character")                        # todo

Que compara:

    Para cada pareja L/R coge la matriz de MUNDO del nodo de L, la refleja
    sobre el plano YZ (que es el plano de simetria del personaje) y compara
    el resultado con la matriz de mundo del nodo de R.

    Reflejar una matriz sobre YZ es negar la componente X de sus tres ejes y
    de su traslacion. Si el rig esta bien en espejo, esa matriz reflejada y
    la del nodo de R tienen que coincidir.

Como leer el informe:

    OK              el nodo de R es el espejo exacto del de L.
    POS             estan orientados igual pero en sitios distintos.
    X->+X Y->-Y Z->-Z
                    los ejes de R no coinciden con los del espejo de L.
                    Esa linea se lee "el eje X de R apunta al +X del espejo
                    de L, su Y al -Y y su Z al -Z", que es justo un giro de
                    180 grados sobre X.
    SIN GEMELO      existe en L pero no en R (o al reves).

Los nodos que salen con ejes cambiados son los que rompen el espejo. Si el
que falla es un _Local_OFF, la deformacion de ese lado no puede ir en espejo
por muchos grupos con escala negativa que se pongan encima del control: el
sistema lee la matriz LOCAL del control y la reaplica sobre ese OFF.
"""

import maya.cmds as cmds


TOLERANCE = 0.001


# ----------------------------------------------------------------------
# MATEMATICAS MINIMAS
# ----------------------------------------------------------------------
def _world_frame(node):
    """
    Devuelve (ejeX, ejeY, ejeZ, posicion) del nodo en espacio de mundo.

    cmds.xform devuelve 16 floats en convencion de vector fila: las filas
    0, 1 y 2 son los ejes y la 3 es la traslacion.
    """
    matrix = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    return (tuple(matrix[0:3]),
            tuple(matrix[4:7]),
            tuple(matrix[8:11]),
            tuple(matrix[12:15]))


def _mirror_frame(frame):
    """Refleja un marco sobre el plano YZ: se niega la componente X de todo."""
    return tuple((-vector[0], vector[1], vector[2]) for vector in frame)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _distance(a, b):
    return sum((a[index] - b[index]) ** 2 for index in range(3)) ** 0.5


def _match_axis(axis, reference_frame):
    """
    Dice a que eje del marco de referencia se parece `axis`, y con que signo.

    Devuelve algo como ("Y", -1, 0.999): "apunta al -Y, y el parecido es de
    0.999". Un parecido bajo significa que el eje esta girado un angulo raro,
    no volteado.
    """
    names = ("X", "Y", "Z")
    best_name, best_sign, best_value = "?", 1, 0.0

    for index in range(3):
        value = _dot(axis, reference_frame[index])
        if abs(value) > abs(best_value):
            best_value = value
            best_name = names[index]
            best_sign = 1 if value >= 0 else -1

    return best_name, best_sign, abs(best_value)


# ----------------------------------------------------------------------
# COMPARACION DE UNA PAREJA
# ----------------------------------------------------------------------
def compare(left_node, right_node):
    """
    Compara un nodo de L con su gemelo de R.

    Devuelve (estado, detalle). El estado es "OK", "POS" o "EJES".
    """
    mirrored = _mirror_frame(_world_frame(left_node))
    actual = _world_frame(right_node)

    position_error = _distance(mirrored[3], actual[3])

    axis_report = []
    axes_ok = True
    for index, name in enumerate(("X", "Y", "Z")):
        matched, sign, quality = _match_axis(actual[index], mirrored[:3])
        axis_report.append(f"{name}->{'+' if sign > 0 else '-'}{matched}")
        if matched != name or sign < 0 or quality < 0.99:
            axes_ok = False

    if not axes_ok:
        return "EJES", " ".join(axis_report) + f"  (dist {position_error:.3f})"

    if position_error > TOLERANCE:
        return "POS", f"dist {position_error:.3f}"

    return "OK", ""


# ----------------------------------------------------------------------
# INFORME
# ----------------------------------------------------------------------
def report(rig_name="Character", filter_text=None, show_ok=False):
    """
    Recorre todos los transform que empiezan por L_<rig>_ y compara cada uno
    con su gemelo R_<rig>_.

    filter_text: si se pasa, solo mira los nodos que contengan ese texto
                 ("eye", "lip", "eyelid", "Local_OFF"...).
    show_ok:     por defecto solo se listan los que fallan. Ponlo a True para
                 ver tambien los que estan bien.
    """
    left_prefix = f"L_{rig_name}_"
    right_prefix = f"R_{rig_name}_"

    candidates = cmds.ls(f"{left_prefix}*", type="transform") or []
    if filter_text:
        lowered = filter_text.lower()
        candidates = [node for node in candidates if lowered in node.lower()]

    candidates.sort()

    rows = []
    counts = {"OK": 0, "POS": 0, "EJES": 0, "SIN GEMELO": 0}

    for left_node in candidates:
        right_node = right_prefix + left_node[len(left_prefix):]

        if not cmds.objExists(right_node):
            counts["SIN GEMELO"] += 1
            rows.append(("SIN GEMELO", left_node, ""))
            continue

        # Nombre corto duplicado en la escena: mejor avisar que mentir.
        if len(cmds.ls(left_node) or []) > 1 or len(cmds.ls(right_node) or []) > 1:
            rows.append(("DUPLICADO", left_node, "hay mas de un nodo con ese nombre"))
            continue

        status, detail = compare(left_node, right_node)
        counts[status] = counts.get(status, 0) + 1
        if status != "OK" or show_ok:
            rows.append((status, left_node, detail))

    print("")
    print("=" * 78)
    print(f"CHEQUEO DE ESPEJO  rig '{rig_name}'"
          + (f"  filtro '{filter_text}'" if filter_text else ""))
    print("=" * 78)

    for status, node, detail in rows:
        print(f"  [{status:^10}] {node[len(left_prefix):]:<38} {detail}")

    if not rows:
        print("  Todo en espejo.")

    print("-" * 78)
    print("  " + "   ".join(f"{key}: {value}" for key, value in counts.items()))
    print("=" * 78)
    print("")

    return counts