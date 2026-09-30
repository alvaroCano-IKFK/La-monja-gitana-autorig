import maya.cmds as cmds


# ---------------------------------------------------------------------------
# COLORES OFICIALES DE MAYA
#
# Los drawing overrides de Maya van por INDICE (0-31), no por RGB. El indice es
# lo unico que se escribe en el nodo; los RGB de esta tabla son solo para
# pintar los botones de la ventana.
#
# Se usan como respaldo: si Maya esta disponible, swatch_rgb() le pregunta a el
# con cmds.colorIndex(), que es la fuente real y no se queda desfasada si
# Autodesk retoca la paleta.
# ---------------------------------------------------------------------------
FALLBACK_RGB = {
    1:  (0.000, 0.000, 0.000),  2:  (0.250, 0.250, 0.250),
    3:  (0.600, 0.600, 0.600),  4:  (0.608, 0.000, 0.157),
    5:  (0.000, 0.016, 0.373),  6:  (0.000, 0.000, 1.000),
    7:  (0.000, 0.275, 0.098),  8:  (0.149, 0.000, 0.263),
    9:  (0.784, 0.000, 0.784),  10: (0.541, 0.282, 0.200),
    11: (0.247, 0.137, 0.122),  12: (0.600, 0.149, 0.000),
    13: (1.000, 0.000, 0.000),  14: (0.000, 1.000, 0.000),
    15: (0.000, 0.255, 0.600),  16: (1.000, 1.000, 1.000),
    17: (1.000, 1.000, 0.000),  18: (0.392, 0.863, 1.000),
    19: (0.263, 1.000, 0.639),  20: (1.000, 0.690, 0.690),
    21: (0.894, 0.675, 0.475),  22: (1.000, 1.000, 0.388),
    23: (0.000, 0.600, 0.325),  24: (0.630, 0.414, 0.189),
    25: (0.620, 0.627, 0.188),  26: (0.408, 0.627, 0.188),
    27: (0.188, 0.627, 0.365),  28: (0.188, 0.627, 0.627),
    29: (0.188, 0.404, 0.627),  30: (0.435, 0.188, 0.627),
    31: (0.627, 0.188, 0.404),
}

COLOR_INDICES = sorted(FALLBACK_RGB.keys())

#: Canales que se pueden bloquear, en el orden del channel box.
CHANNELS = [
    ("translateX", "TX"), ("translateY", "TY"), ("translateZ", "TZ"),
    ("rotateX", "RX"), ("rotateY", "RY"), ("rotateZ", "RZ"),
    ("scaleX", "SX"), ("scaleY", "SY"), ("scaleZ", "SZ"),
    ("visibility", "Vis"),
]

CHANNEL_NAMES = [name for name, _ in CHANNELS]


def swatch_rgb(index):
    """RGB del indice, preguntandoselo a Maya y tirando de tabla si falla."""
    try:
        color = cmds.colorIndex(index, q=True)
        if color:
            return tuple(color[:3])
    except Exception:
        pass

    return FALLBACK_RGB.get(index, (0.5, 0.5, 0.5))


# ---------------------------------------------------------------------------
# QUE NODOS SE TOCAN
# ---------------------------------------------------------------------------
def is_control(node):
    """
    True si el transform tiene alguna shape de curva.

    Es el filtro que distingue un control de un grupo. Sin el, aplicar "en
    jerarquia" desde la raiz del rig pintaria y bloquearia tambien los _GRP,
    _SPC, _OFF y _SDK, que el animador no ve pero el rig si usa.
    """
    if cmds.nodeType(node) != "transform":
        return False

    shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                type="nurbsCurve") or []

    return bool(shapes)


def collect_targets(nodes=None, hierarchy=False, only_controls=True):
    """
    Nodos sobre los que actuar.

    Args:
        nodes (list): de donde partir. None = lo que este seleccionado.
        hierarchy (bool): incluir tambien todo lo que cuelga por debajo.
        only_controls (bool): quedarse solo con transforms que tengan curva.
            Con hierarchy=True conviene dejarlo en True.

    Returns:
        list: nodos sin repetir, en orden
    """
    if nodes is None:
        nodes = cmds.ls(selection=True, long=True, type="transform") or []

    collected = []
    for node in nodes:
        collected.append(node)
        if hierarchy:
            collected.extend(cmds.listRelatives(node, allDescendents=True,
                                                type="transform",
                                                fullPath=True) or [])

    targets = []
    seen = set()
    for node in collected:
        if node in seen:
            continue
        seen.add(node)

        if only_controls and not is_control(node):
            continue

        targets.append(node)

    return targets


# ---------------------------------------------------------------------------
# COLOR
# ---------------------------------------------------------------------------
def _color_nodes(transform):
    """
    Donde se escribe el override: en las SHAPES, no en el transform.

    En la shape, el color se ve en el viewport y ademas el outliner mantiene su
    texto normal. Si el transform no tiene shapes (no deberia pasar con
    only_controls), se cae al propio transform para no dejar la operacion a
    medias sin decir nada.
    """
    shapes = cmds.listRelatives(transform, shapes=True, noIntermediate=True,
                                fullPath=True) or []

    return shapes or [transform]


def set_color(index, nodes=None, hierarchy=False):
    """
    Pone el color de override en los controles.

    Args:
        index (int): indice de color de Maya (1-31), o 0 para quitar el
            override y devolver el control a su color por defecto.

    Returns:
        list: transforms que se han coloreado
    """
    targets = collect_targets(nodes, hierarchy=hierarchy)

    if not targets:
        cmds.warning("[Tools] Selecciona algun control.")
        return []

    done = []
    for transform in targets:
        for node in _color_nodes(transform):
            try:
                if index <= 0:
                    cmds.setAttr(f"{node}.overrideEnabled", 0)
                    continue

                cmds.setAttr(f"{node}.overrideEnabled", 1)

                # Si el nodo esta en modo RGB, el indice no se mira siquiera.
                if cmds.attributeQuery("overrideRGBColors", node=node,
                                       exists=True):
                    cmds.setAttr(f"{node}.overrideRGBColors", 0)

                cmds.setAttr(f"{node}.overrideColor", index)
            except Exception as error:
                # Pasa cuando el override esta conectado (una capa de display)
                # o el atributo esta bloqueado. Se avisa y se sigue con el resto.
                cmds.warning(f"[Tools] No puedo colorear {node}: {error}")

        done.append(transform)

    action = "sin color" if index <= 0 else f"color {index}"
    print(f"[Tools] {len(done)} controles a {action}.")

    return done


# ---------------------------------------------------------------------------
# BLOQUEO DE ATRIBUTOS
# ---------------------------------------------------------------------------
def set_attributes(attributes, lock=True, hide=None, nodes=None,
                   hierarchy=False):
    """
    Bloquea o desbloquea los canales indicados.

    Args:
        attributes (list): nombres largos, de CHANNEL_NAMES.
        lock (bool): True bloquea, False desbloquea.
        hide (bool): ocultar del channel box. None = lo mismo que lock, que es
            lo habitual: lo que se bloquea se esconde y lo que se desbloquea
            reaparece. Pasa False para bloquear dejandolo a la vista.
        hierarchy (bool): aplicar tambien a los controles de debajo.

    Returns:
        list: transforms tocados
    """
    if hide is None:
        hide = lock

    if not attributes:
        cmds.warning("[Tools] No has marcado ningun canal.")
        return []

    targets = collect_targets(nodes, hierarchy=hierarchy)

    if not targets:
        cmds.warning("[Tools] Selecciona algun control.")
        return []

    done = []
    for node in targets:
        for attribute in attributes:
            plug = f"{node}.{attribute}"

            if not cmds.attributeQuery(attribute, node=node, exists=True):
                continue

            try:
                # El orden importa: para desbloquear hay que quitar el lock
                # ANTES de tocar keyable, o Maya rechaza el cambio.
                if not lock:
                    cmds.setAttr(plug, lock=False)

                cmds.setAttr(plug, keyable=not hide, channelBox=False)

                # Un canal no keyable pero visible en el channel box necesita
                # channelBox=True; si no, desaparece aunque no lo bloquees.
                if not hide and not cmds.getAttr(plug, keyable=True):
                    cmds.setAttr(plug, channelBox=True)

                if lock:
                    cmds.setAttr(plug, lock=True)
            except Exception as error:
                cmds.warning(f"[Tools] No puedo tocar {plug}: {error}")

        done.append(node)

    verb = "bloqueados" if lock else "desbloqueados"
    print(f"[Tools] {len(attributes)} canales {verb} en {len(done)} controles.")

    return done