import maya.cmds as cmds
import maya.api.OpenMaya as om
from functools import partial
import os
import json

# --- CONFIGURACION DE PATHS ---
BASE_PATH = r"C:\Users\a.cano\Documents\GitHub\La-monja-gitana-autorig"
CONTROLS_DIR = os.path.join(BASE_PATH, "control_library")

# Asegurar que la carpeta existe
if not os.path.exists(CONTROLS_DIR):
    os.makedirs(CONTROLS_DIR)

# --- ESCALA DEL RIG ---
#
# Los CVs del JSON estan guardados en unidades absolutas: una shape de 10 cm es
# de 10 cm da igual el personaje. Si las guias se escalan, los controles siguen
# midiendo lo mismo y se ven diminutos.
#
# La solucion es escalar los CVs AL CREAR la curva, no el transform del control.
# Escalar el transform funcionaria visualmente, pero dejaria a los controles con
# un scale distinto de 1 en el channel box: el animador no sabria si ese valor
# es suyo o del rig, y cualquier freeze transform lo perderia.

#: Altura de guides_GRP con la que se dibujaron los controles de la libreria.
#: 0 = sin calibrar, y entonces no se escala nada (comportamiento de siempre).
#: Para calibrar: abre la escena en la que los controles salian del tamano
#: correcto, ejecuta controlsLibrary.print_guide_calibration() y pega aqui el
#: numero que imprime. Se hace una vez y ya.
REFERENCE_GUIDE_HEIGHT = 71.5072

_RIG_SCALE = 1.0
_SCALE_WARNED = False


def get_rig_scale():
    """Factor por el que se multiplican los CVs de todos los controles."""
    return _RIG_SCALE


def set_rig_scale(scale):
    """
    Fija el factor a mano, por si se quiere forzar sin medir las guias.
    """
    global _RIG_SCALE

    try:
        scale = float(scale)
    except (TypeError, ValueError):
        cmds.warning(f"[controlsLibrary] Escala invalida: {scale}. Se deja en 1.")
        _RIG_SCALE = 1.0

        return _RIG_SCALE

    # Una escala de 0 o negativa colapsaria las shapes a un punto y no habria
    # forma de darse cuenta mirando el viewport.
    if scale <= 0.0:
        cmds.warning(f"[controlsLibrary] Escala {scale} no valida. Se deja en 1.")
        scale = 1.0

    _RIG_SCALE = scale

    return _RIG_SCALE


def measure_guides_height(root="guides_GRP"):
    """
    Altura de la caja contenedora de las guias, en mundo.

    Se usa la altura y no la anchura porque es la medida que menos cambia con la
    pose de las guias: un personaje con los brazos en cruz y el mismo con los
    brazos pegados al cuerpo tienen anchuras muy distintas pero la misma altura.

    Devuelve None si no hay guias en la escena.
    """
    if not cmds.objExists(root):
        return None

    bbox = cmds.xform(root, q=True, bb=True, ws=True)
    height = abs(bbox[4] - bbox[1])

    if height < 1e-6:
        return None

    return height


def update_rig_scale_from_guides(root="guides_GRP"):
    """
    Mide las guias de la escena y ajusta la escala de los controles.

    Esto lo llama build_module al empezar, antes de crear ningun control. Si no
    hay calibracion o no hay guias, se queda en 1 y todo funciona como siempre.
    """
    global _SCALE_WARNED

    if not REFERENCE_GUIDE_HEIGHT:
        if not _SCALE_WARNED:
            print("[controlsLibrary] REFERENCE_GUIDE_HEIGHT esta a 0: los "
                  "controles se crean a tamano fijo. Ejecuta "
                  "controlsLibrary.print_guide_calibration() para calibrar.")
            _SCALE_WARNED = True

        return set_rig_scale(1.0)

    height = measure_guides_height(root)

    if height is None:
        cmds.warning(f"[controlsLibrary] No puedo medir '{root}'. "
                     f"Los controles se crean a tamano fijo.")

        return set_rig_scale(1.0)

    scale = height / float(REFERENCE_GUIDE_HEIGHT)
    set_rig_scale(scale)

    print(f"[controlsLibrary] Altura de guias {height:.3f} / referencia "
          f"{REFERENCE_GUIDE_HEIGHT:.3f} -> escala de controles x{scale:.3f}")

    return scale


def print_guide_calibration(root="guides_GRP"):
    """
    Imprime la altura actual de las guias, para pegarla en
    REFERENCE_GUIDE_HEIGHT.

    Ejecutalo con las guias al tamano en el que los controles salen bien.
    """
    height = measure_guides_height(root)

    if height is None:
        cmds.warning(f"[controlsLibrary] No hay '{root}' en la escena o mide 0.")

        return None

    print(f"[controlsLibrary] Pega esto en controlsLibrary.py:\n"
          f"    REFERENCE_GUIDE_HEIGHT = {height:.4f}")

    return height


# --- CURVE DATA ---

def get_curve_data(shape):
    sel = om.MSelectionList()
    sel.add(shape)
    dag = sel.getDagPath(0)
    fn = om.MFnNurbsCurve(dag)

    cvs = []
    for i in range(fn.numCVs):
        p = fn.cvPosition(i, om.MSpace.kObject)
        cvs.append([p.x, p.y, p.z])

    return {
        "degree": fn.degree,
        "form": fn.form,
        "knots": list(fn.knots()),
        "cvs": cvs
    }

def build_curve(data, name, scale=1.0):
    """
    Reconstruye una shape del JSON.

    scale multiplica los CVs, que estan en espacio objeto. Los knots NO se
    tocan: describen la parametrizacion de la curva, no su tamano. Escalarlos
    deformaria la distribucion de los CVs a lo largo del span en vez de
    agrandar la shape.
    """
    cvs = data["cvs"]

    if scale != 1.0:
        cvs = [[axis * scale for axis in point] for point in cvs]

    return cmds.curve(n=name, d=data["degree"], p=cvs, k=data["knots"])

# --- LOGICA DE GUARDADO ---

def save_control(*args):
    sel = cmds.ls(sl=True, type="transform")
    if not sel:
        cmds.warning("Selecciona un transform (curva) en el viewport")
        return

    result = cmds.promptDialog(
        title='Guardar Nuevo Control',
        message='Nombre del archivo JSON:',
        button=['Guardar', 'Cancelar'],
        defaultButton='Guardar',
        cancelButton='Cancelar',
        dismissString='Cancelar',
        text=sel[0]
    )

    if result != 'Guardar':
        return

    file_name = cmds.promptDialog(query=True, text=True)
    if not file_name:
        return

    file_path = os.path.join(CONTROLS_DIR, f"{file_name}.json")

    shapes = cmds.listRelatives(sel[0], s=True, type="nurbsCurve", fullPath=True)
    if not shapes:
        cmds.warning("La seleccion no tiene shapes de curva")
        return

    shapes_data = [get_curve_data(s) for s in shapes]
    
    control_data = {
        "name": file_name,
        "shapes": shapes_data
    }

    # Escritura explicita en UTF-8
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(control_data, f, indent=4, ensure_ascii=False)
    
    print(f"EXITO: Control guardado en {file_path}")

# --- LOGICA DE IMPORTACION ---

def load_json_file(list_ui, *args):
    selected_items = cmds.textScrollList(list_ui, q=True, si=True)
    if not selected_items:
        cmds.warning("Selecciona un archivo de la lista")
        return

    full_path = os.path.join(CONTROLS_DIR, selected_items[0])
    
    # Lectura explicita en UTF-8
    with open(full_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ctrl_name = data["name"]
    created_shapes = []

    for i, shape_data in enumerate(data["shapes"]):
        crv = build_curve(shape_data, f"{ctrl_name}_temp_{i}")
        created_shapes.append(crv)

    main_ctrl = created_shapes[0]
    if len(created_shapes) > 1:
        for extra_shape in created_shapes[1:]:
            shape_nodes = cmds.listRelatives(extra_shape, s=True)
            if shape_nodes:
                cmds.parent(shape_nodes[0], main_ctrl, r=True, s=True)
            cmds.delete(extra_shape)
    
    # Evitar error si el nombre ya existe en escena al renombrar
    final_name = cmds.rename(main_ctrl, ctrl_name)
    
    if cmds.window("ImportSelectorWin", exists=True):
        cmds.deleteUI("ImportSelectorWin")
        
    print(f"EXITO: Control '{final_name}' importado.")

def show_import_selector(*args):
    if not os.path.exists(CONTROLS_DIR):
        os.makedirs(CONTROLS_DIR)
    
    all_files = [f for f in os.listdir(CONTROLS_DIR) if f.endswith('.json')]
    
    if not all_files:
        cmds.warning("No se encontraron archivos JSON en la libreria.")
        return

    win = "ImportSelectorWin"
    if cmds.window(win, exists=True):
        cmds.deleteUI(win)

    cmds.window(win, title="Libreria de Controles", w=250, h=350, s=True)
    cmds.columnLayout(adj=True, m=10)
    
    cmds.text(l="Archivos disponibles:", al="left", h=25)
    list_ui = cmds.textScrollList(numberOfRows=12, allowMultiSelection=False, append=sorted(all_files))
    
    cmds.separator(h=10, style="none")
    cmds.button(l="IMPORTAR SELECCIONADO", c=partial(load_json_file, list_ui), h=40, bgc=(0.32, 0.52, 0.32))
    
    cmds.showWindow(win)

# --- UI PRINCIPAL ---

def ControladorUI():
    win = "ControladorUI"
    if cmds.window(win, exists=True):
        cmds.deleteUI(win)

    cmds.window(win, title="Rig Control Manager", widthHeight=(300, 160), s=False)
    cmds.columnLayout(adj=True, rowSpacing=10, columnOffset=("both", 15))

    cmds.separator(h=5, style="none")
    cmds.text(l="LIBRARY MANAGER", fn="boldLabelFont", h=20)
    
    cmds.button(l="GUARDAR CONTROL (JSON)", h=40, bgc=(0.5, 0.35, 0.35), c=save_control)
    cmds.button(l="ABRIR LIBRERIA", h=40, bgc=(0.35, 0.45, 0.55), c=show_import_selector)
    
    cmds.separator(h=5, style="none")
    cmds.showWindow(win)

if __name__ == "__main__":
    ControladorUI()
    
def create_control_from_lib(lib_name, final_name, scale=1.0):
    """
    Crea un controlador desde la libreria sin usar la UI.

    :param lib_name: Nombre del archivo JSON (sin .json)
    :param final_name: Nombre que tendra el control en Maya
    :param scale: multiplicador EXTRA para este control concreto, encima de la
        escala global del rig. Sirve para el control global, que interesa que
        sea mas grande que el resto, o para los dedos, que interesa que sean
        mas pequenos. 1.0 = solo la escala del rig.
    :return: str con el nombre del transform creado
    """
    file_path = os.path.join(CONTROLS_DIR, f"{lib_name}.json")

    # El tamano final sale de multiplicar las dos: la escala del personaje y el
    # ajuste de este control. Asi los modulos no tienen que saber nada de lo
    # grande que es el personaje.
    final_scale = get_rig_scale() * scale

    if not os.path.exists(file_path):
        cmds.warning(f"No se encontro el control {lib_name} en la libreria. Usando circulo por defecto.")
        # El circulo de emergencia tambien tiene que escalar: si no, en un
        # personaje grande aparece un punto en medio del rig y parece un bug.
        return cmds.circle(n=final_name, nr=(0, 1, 0), r=final_scale)[0]

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    created_shapes = []
    for i, shape_data in enumerate(data["shapes"]):
        crv = build_curve(shape_data, f"{final_name}_temp_{i}", scale=final_scale)
        created_shapes.append(crv)

    main_ctrl = created_shapes[0]
    if len(created_shapes) > 1:
        for extra_shape in created_shapes[1:]:
            shape_nodes = cmds.listRelatives(extra_shape, s=True)
            if shape_nodes:
                cmds.parent(shape_nodes[0], main_ctrl, r=True, s=True)
            cmds.delete(extra_shape)
    
    return cmds.rename(main_ctrl, final_name)
    #xd