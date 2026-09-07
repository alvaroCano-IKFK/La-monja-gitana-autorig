"""
guides_io_module.py

Exporta e importa el rig de guias (guides_GRP) en formato JSON.

La idea es no hardcodear ninguna guia concreta: se recorre la jerarquia del
DAG a partir de guides_GRP y se guarda lo que haya. Asi, si maniana aniades
guias nuevas al CharacterGuides, el export/import las coge solas sin tocar
este fichero.

Se guarda por cada nodo:
    - su ruta relativa dentro de guides_GRP (para reconstruir la jerarquia)
    - el tipo (joint, transform, nurbsSurface, nurbsCurve, locator)
    - transform completo: rotateOrder, translate, rotate, scale, rotateAxis
    - lo especifico de joints: jointOrient, preferredAngle, radius, ssc, side...
    - lo especifico de shapes: CVs en espacio objeto + topologia
    - atributos custom (user defined) que hayas podido aniadir a mano

Uso:
    import guides_io_module
    guides_io_module.export_guides()          # abre file dialog
    guides_io_module.export_guides("C:/x.json")
    guides_io_module.import_guides()          # abre file dialog
"""

import os
import json
import datetime

import maya.cmds as cmds


FILE_VERSION = 1
GUIDES_ROOT = "guides_GRP"

# Atributos de transform que se guardan para todos los nodos.
# El rotateOrder va aparte porque hay que ponerlo ANTES que las rotaciones.
TRANSFORM_ATTRS = [
    "translateX", "translateY", "translateZ",
    "rotateX", "rotateY", "rotateZ",
    "scaleX", "scaleY", "scaleZ",
    "rotateAxisX", "rotateAxisY", "rotateAxisZ",
    "visibility",
]

# Atributos que solo tienen sentido en joints.
JOINT_ATTRS = [
    "jointOrientX", "jointOrientY", "jointOrientZ",
    "preferredAngleX", "preferredAngleY", "preferredAngleZ",
    "radius",
    "segmentScaleCompensate",
    "drawStyle",
    "side",
    "type",
]

# Tipos de atributo custom que sabemos reconstruir.
SUPPORTED_UD_TYPES = (
    "double", "float", "long", "short", "byte", "bool", "enum", "string",
)


# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------
def _long_name(node):
    """Ruta larga (|a|b|c) de un nodo, o None si no existe."""
    found = cmds.ls(node, l=True)

    return found[0] if found else None


def _short_name(long_name):
    """Ultimo tramo de una ruta larga."""

    return long_name.rsplit("|", 1)[-1]


def _node_kind(node):
    """
    Que clase de nodo es, a efectos de reconstruirlo luego.
    Se mira primero si es joint y despues el tipo de su shape.
    """
    if cmds.nodeType(node) == "joint":
        return "joint"

    shapes = cmds.listRelatives(node, s=True, ni=True, f=True) or []
    if not shapes:
        return "transform"

    shape_type = cmds.nodeType(shapes[0])
    if shape_type in ("nurbsSurface", "nurbsCurve", "locator"):
        return shape_type

    # Cualquier otra cosa (mesh, etc) se guarda como grupo vacio: no vamos a
    # reconstruir geometria, pero al menos no se rompe la jerarquia.
    return "transform"


def _first_shape(node):
    shapes = cmds.listRelatives(node, s=True, ni=True, f=True) or []

    return shapes[0] if shapes else None


def _safe_set(attr, value):
    """
    setAttr tolerante: si el atributo esta bloqueado o conectado no revienta
    la importacion entera, solo avisa.
    """
    try:
        if cmds.getAttr(attr, lock=True):
            return False
        if cmds.listConnections(attr, s=True, d=False, p=True):
            return False
        cmds.setAttr(attr, value)

        return True
    except Exception as e:
        cmds.warning("No he podido poner {0}: {1}".format(attr, e))

        return False


def _default_directory():
    """
    Carpeta que se propone en el file dialog: la data del proyecto si existe,
    si no la de la escena abierta, si no el home.
    """
    try:
        workspace_root = cmds.workspace(q=True, rootDirectory=True)
        data_dir = os.path.join(workspace_root, "data")
        if os.path.isdir(data_dir):
            return data_dir
    except Exception:
        pass

    scene = cmds.file(q=True, sn=True)
    if scene:
        return os.path.dirname(scene)

    return os.path.expanduser("~")


def _ask_for_file(save=True):
    """Abre el file dialog de Maya y devuelve la ruta, o None si se cancela."""
    caption = "Exportar guias" if save else "Importar guias"
    file_mode = 0 if save else 1

    result = cmds.fileDialog2(
        fileMode=file_mode,
        caption=caption,
        fileFilter="JSON (*.json);;Todos los archivos (*.*)",
        dialogStyle=2,
        startingDirectory=_default_directory(),
    )

    if not result:
        return None

    path = result[0]
    if save and not path.lower().endswith(".json"):
        path += ".json"

    return path


# ----------------------------------------------------------------------
# EXPORT
# ----------------------------------------------------------------------
def _export_user_attrs(node):
    """
    Atributos custom del nodo. Se ignoran los tipos raros (matrices, multis)
    porque no los vamos a poder reconstruir de forma fiable.
    """
    data = []

    for attr_name in cmds.listAttr(node, ud=True) or []:
        full_attr = "{0}.{1}".format(node, attr_name)

        if not cmds.objExists(full_attr):
            continue

        try:
            attr_type = cmds.getAttr(full_attr, type=True)
        except Exception:
            continue

        if attr_type not in SUPPORTED_UD_TYPES:
            continue

        try:
            entry = {
                "name": attr_name,
                "type": attr_type,
                "value": cmds.getAttr(full_attr),
                "keyable": cmds.getAttr(full_attr, k=True),
            }
            if attr_type == "enum":
                entry["enumName"] = cmds.addAttr(full_attr, q=True, en=True)
            data.append(entry)
        except Exception:
            continue

    return data


def _export_nurbs_surface(node, shape):
    """
    Topologia + CVs en espacio objeto. Se guardan los CVs en object space para
    que la forma sea independiente del transform del nodo (que ya se guarda
    aparte). Asi mover la boca entera no ensucia la forma.
    """
    degree_u = cmds.getAttr(shape + ".degreeU")
    degree_v = cmds.getAttr(shape + ".degreeV")
    spans_u = cmds.getAttr(shape + ".spansU")
    spans_v = cmds.getAttr(shape + ".spansV")
    form_u = cmds.getAttr(shape + ".formU")
    form_v = cmds.getAttr(shape + ".formV")

    # En forma abierta el numero de CVs es spans + degree
    num_u = spans_u + degree_u
    num_v = spans_v + degree_v

    cvs = []
    for i in range(num_u):
        row = []
        for j in range(num_v):
            cv = "{0}.cv[{1}][{2}]".format(node, i, j)
            row.append(cmds.xform(cv, q=True, os=True, t=True))
        cvs.append(row)

    return {
        "degreeU": degree_u,
        "degreeV": degree_v,
        "spansU": spans_u,
        "spansV": spans_v,
        "formU": form_u,
        "formV": form_v,
        "cvs": cvs,
    }


def _export_nurbs_curve(node, shape):
    degree = cmds.getAttr(shape + ".degree")
    spans = cmds.getAttr(shape + ".spans")
    form = cmds.getAttr(shape + ".form")

    num_cvs = spans + degree if form == 0 else spans

    cvs = []
    for i in range(num_cvs):
        cv = "{0}.cv[{1}]".format(node, i)
        cvs.append(cmds.xform(cv, q=True, os=True, t=True))

    return {
        "degree": degree,
        "spans": spans,
        "form": form,
        "cvs": cvs,
    }


def _export_locator(shape):
    return {
        "localPosition": list(cmds.getAttr(shape + ".localPosition")[0]),
        "localScale": list(cmds.getAttr(shape + ".localScale")[0]),
    }


def _export_node(node, relative_path, relative_parent):
    """Diccionario con todo lo que hace falta para recrear este nodo."""
    kind = _node_kind(node)

    entry = {
        "name": _short_name(node),
        "path": relative_path,
        "parent": relative_parent,
        "kind": kind,
        "rotateOrder": cmds.getAttr(node + ".rotateOrder"),
        "attrs": {},
    }

    for attr_name in TRANSFORM_ATTRS:
        full_attr = "{0}.{1}".format(node, attr_name)
        if cmds.objExists(full_attr):
            entry["attrs"][attr_name] = cmds.getAttr(full_attr)

    if kind == "joint":
        for attr_name in JOINT_ATTRS:
            full_attr = "{0}.{1}".format(node, attr_name)
            if cmds.objExists(full_attr):
                entry["attrs"][attr_name] = cmds.getAttr(full_attr)

        # otherType es string, va aparte del bloque numerico
        if cmds.objExists(node + ".otherType"):
            entry["otherType"] = cmds.getAttr(node + ".otherType")

    shape = _first_shape(node)
    if shape:
        if kind == "nurbsSurface":
            entry["shape"] = _export_nurbs_surface(node, shape)
        elif kind == "nurbsCurve":
            entry["shape"] = _export_nurbs_curve(node, shape)
        elif kind == "locator":
            entry["shape"] = _export_locator(shape)

    user_attrs = _export_user_attrs(node)
    if user_attrs:
        entry["userAttrs"] = user_attrs

    return entry


def export_guides(filepath=None, root=GUIDES_ROOT):
    """
    Guarda toda la jerarquia de guides_GRP en un JSON.

    filepath: ruta destino. Si es None se abre el file dialog.
    root: nodo raiz a exportar, por defecto guides_GRP.

    Devuelve la ruta escrita, o None si algo ha fallado o se ha cancelado.
    """
    if not cmds.objExists(root):
        cmds.warning(
            "No existe '{0}' en la escena. Crea las guias antes de "
            "exportarlas.".format(root)
        )

        return None

    root_long = _long_name(root)

    # El prefijo es lo que hay por encima de la raiz: se recorta de todas las
    # rutas para que el JSON sea independiente de donde este colgado el grupo.
    prefix = root_long.rsplit("|", 1)[0]

    def relative(long_name):
        if prefix and long_name.startswith(prefix + "|"):
            return long_name[len(prefix) + 1:]

        return long_name.lstrip("|")

    # Se ordena por profundidad de ruta (numero de "|") para garantizar que
    # los padres van siempre antes que los hijos: el import los crea en este
    # mismo orden y necesita que el padre ya exista.
    descendants = cmds.listRelatives(
        root_long, ad=True, f=True, type="transform") or []
    descendants.sort(key=lambda n: n.count("|"))

    all_nodes = [root_long] + descendants

    nodes_data = []
    for node in all_nodes:
        node_relative = relative(node)
        parent_list = cmds.listRelatives(node, p=True, f=True)
        parent_relative = relative(parent_list[0]) if parent_list else None

        # El padre de la raiz queda a None aunque la raiz cuelgue de algo
        if node == root_long:
            parent_relative = None

        nodes_data.append(_export_node(node, node_relative, parent_relative))

    if filepath is None:
        filepath = _ask_for_file(save=True)
        if not filepath:
            return None

    data = {
        "fileVersion": FILE_VERSION,
        "root": _short_name(root_long),
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mayaVersion": cmds.about(q=True, version=True),
        "scene": cmds.file(q=True, sn=True),
        "nodes": nodes_data,
    }

    directory = os.path.dirname(filepath)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)

    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)

    print("Guias exportadas ({0} nodos): {1}".format(len(nodes_data), filepath))

    return filepath


# ----------------------------------------------------------------------
# IMPORT
# ----------------------------------------------------------------------
def _create_nurbs_surface(entry):
    """
    Recrea el plano NURBS. Como despues se colocan TODOS los CVs uno a uno,
    lo unico que tiene que coincidir es la topologia (grado y spans): la forma
    de partida da igual.
    """
    shape_data = entry["shape"]

    degree_u = shape_data["degreeU"]
    degree_v = shape_data["degreeV"]

    if degree_u != degree_v:
        cmds.warning(
            "La superficie '{0}' tiene grados distintos en U y V ({1}/{2}). "
            "Se reconstruye con grado {1} en ambos.".format(
                entry["name"], degree_u, degree_v)
        )

    node = cmds.nurbsPlane(
        ax=(0, 1, 0),
        w=1,
        lr=1,
        d=degree_u,
        u=shape_data["spansU"],
        v=shape_data["spansV"],
        ch=False,
    )[0]

    return node


def _apply_nurbs_surface_cvs(node, entry):
    for i, row in enumerate(entry["shape"]["cvs"]):
        for j, position in enumerate(row):
            cv = "{0}.cv[{1}][{2}]".format(node, i, j)
            cmds.xform(cv, os=True, t=position)


def _create_nurbs_curve(entry):
    shape_data = entry["shape"]
    points = [tuple(p) for p in shape_data["cvs"]]

    if shape_data["form"] == 2:  # periodica: hay que cerrar el bucle
        degree = shape_data["degree"]
        node = cmds.curve(d=degree, p=points + points[:degree], per=True)
    else:
        node = cmds.curve(d=shape_data["degree"], p=points)

    return node


def _create_locator(entry):
    node = cmds.spaceLocator()[0]
    shape = _first_shape(node)
    shape_data = entry.get("shape", {})

    if shape and shape_data:
        cmds.setAttr(shape + ".localPosition",
                     *shape_data.get("localPosition", [0, 0, 0]))
        cmds.setAttr(shape + ".localScale",
                     *shape_data.get("localScale", [1, 1, 1]))

    return node


def _apply_user_attrs(node, entry):
    for attr_data in entry.get("userAttrs", []):
        attr_name = attr_data["name"]
        attr_type = attr_data["type"]
        full_attr = "{0}.{1}".format(node, attr_name)

        if not cmds.objExists(full_attr):
            try:
                if attr_type == "string":
                    cmds.addAttr(node, ln=attr_name, dt="string")
                elif attr_type == "enum":
                    cmds.addAttr(node, ln=attr_name, at="enum",
                                 en=attr_data.get("enumName", "off:on"))
                else:
                    cmds.addAttr(node, ln=attr_name, at=attr_type)

                cmds.setAttr(full_attr, k=attr_data.get("keyable", True))
            except Exception as e:
                cmds.warning("No he podido crear {0}: {1}".format(full_attr, e))
                continue

        value = attr_data.get("value")
        if value is None:
            continue

        try:
            if attr_type == "string":
                cmds.setAttr(full_attr, value, type="string")
            else:
                cmds.setAttr(full_attr, value)
        except Exception as e:
            cmds.warning("No he podido poner {0}: {1}".format(full_attr, e))


def _apply_transform(node, entry):
    """
    Orden importante: primero rotateOrder, luego jointOrient y rotateAxis, y
    al final las rotaciones. Si se hace al reves Maya reinterpreta los angulos
    y la guia acaba girada.
    """
    _safe_set(node + ".rotateOrder", entry.get("rotateOrder", 0))

    attrs = entry.get("attrs", {})

    ordered_first = [
        "jointOrientX", "jointOrientY", "jointOrientZ",
        "rotateAxisX", "rotateAxisY", "rotateAxisZ",
        "segmentScaleCompensate",
    ]

    for attr_name in ordered_first:
        if attr_name in attrs:
            _safe_set("{0}.{1}".format(node, attr_name), attrs[attr_name])

    for attr_name, value in attrs.items():
        if attr_name in ordered_first:
            continue
        _safe_set("{0}.{1}".format(node, attr_name), value)

    if "otherType" in entry and cmds.objExists(node + ".otherType"):
        try:
            cmds.setAttr(node + ".otherType", entry["otherType"], type="string")
        except Exception:
            pass


def import_guides(filepath=None, force=False, root=GUIDES_ROOT):
    """
    Reconstruye las guias desde un JSON exportado con export_guides.

    filepath: ruta del JSON. Si es None se abre el file dialog.
    force: si ya hay guides_GRP en la escena, True lo borra sin preguntar.
           Con False se pregunta por dialogo.

    Devuelve el nombre del grupo raiz creado, o None si se cancela o falla.
    """
    if filepath is None:
        filepath = _ask_for_file(save=False)
        if not filepath:
            return None

    if not os.path.isfile(filepath):
        cmds.warning("No encuentro el archivo: {0}".format(filepath))

        return None

    with open(filepath, "r") as f:
        data = json.load(f)

    if data.get("fileVersion") != FILE_VERSION:
        cmds.warning(
            "El archivo es de la version {0} y este modulo lee la {1}. "
            "Puede que algo no cuadre.".format(
                data.get("fileVersion"), FILE_VERSION)
        )

    file_root = data.get("root", root)

    # Si ya hay guias en la escena hay que quitarlas: si no, Maya renombra los
    # nodos con sufijos y luego los modulos de build no encuentran nada.
    if cmds.objExists(file_root):
        if not force:
            answer = cmds.confirmDialog(
                title="Importar guias",
                message="Ya existe '{0}' en la escena.\n"
                        "Hay que borrarlo para importar. Continuo?".format(file_root),
                button=["Borrar e importar", "Cancelar"],
                defaultButton="Cancelar",
                cancelButton="Cancelar",
                dismissString="Cancelar",
            )
            if answer != "Borrar e importar":
                print("Importacion cancelada.")

                return None

        cmds.delete(file_root)

    cmds.select(clear=True)

    # Aviso si algun nombre de guia ya lo esta usando otro nodo de la escena.
    # Maya lo permite (los nombres del DAG solo son unicos entre hermanos),
    # pero los modulos de build buscan por nombre corto y cogerian el que no es.
    clashes = []
    for entry in data.get("nodes", []):
        if cmds.objExists(entry["name"]):
            clashes.append(entry["name"])

    if clashes:
        cmds.warning(
            "Estos nombres ya existen en la escena y pueden confundir al "
            "build: {0}".format(", ".join(clashes[:10]))
        )

    # Mapa ruta_del_json -> nodo real creado, para poder emparentar los hijos
    created = {}

    for entry in data.get("nodes", []):
        kind = entry.get("kind", "transform")
        parent_path = entry.get("parent")
        parent_node = created.get(parent_path) if parent_path else None

        if parent_path and parent_node is None:
            cmds.warning(
                "No encuentro el padre '{0}' de '{1}': lo dejo en el "
                "mundo.".format(parent_path, entry["name"])
            )

        # --- creacion segun el tipo ---
        if kind == "joint":
            # createNode en vez de cmds.joint: joint hereda la seleccion y
            # encadena joints sin querer.
            if parent_node:
                node = cmds.createNode("joint", n=entry["name"], p=parent_node)
            else:
                node = cmds.createNode("joint", n=entry["name"])

        elif kind in ("nurbsSurface", "nurbsCurve", "locator"):
            if kind == "nurbsSurface":
                node = _create_nurbs_surface(entry)
            elif kind == "nurbsCurve":
                node = _create_nurbs_curve(entry)
            else:
                node = _create_locator(entry)

            if parent_node:
                # r=True para que no compense el transform del padre: los
                # valores buenos se ponen justo despues.
                node = cmds.parent(node, parent_node, r=True)[0]

            node = cmds.rename(node, entry["name"])

        else:
            if parent_node:
                node = cmds.createNode("transform", n=entry["name"], p=parent_node)
            else:
                node = cmds.createNode("transform", n=entry["name"])

        node = _long_name(node)

        # --- transform y atributos ---
        _apply_transform(node, entry)
        _apply_user_attrs(node, entry)

        if kind == "nurbsSurface":
            _apply_nurbs_surface_cvs(node, entry)

        created[entry["path"]] = node

    cmds.select(clear=True)

    print("Guias importadas ({0} nodos): {1}".format(len(created), filepath))

    return file_root