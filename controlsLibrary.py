import maya.cmds as cmds
import maya.api.OpenMaya as om
from functools import partial
import os
import json

# --- CONFIGURACIÓN DE PATHS ---
BASE_PATH = r"C:\Users\Usuario\Documents\GitHub\La-monja-gitana-autorig02"
CONTROLS_DIR = os.path.join(BASE_PATH, "control_library")

# Asegurar que la carpeta existe
if not os.path.exists(CONTROLS_DIR):
    os.makedirs(CONTROLS_DIR)

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

def build_curve(data, name):
    return cmds.curve(n=name, d=data["degree"], p=data["cvs"], k=data["knots"])

# --- LÓGICA DE GUARDADO ---

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
        cmds.warning("La selección no tiene shapes de curva")
        return

    shapes_data = [get_curve_data(s) for s in shapes]
    
    control_data = {
        "name": file_name,
        "shapes": shapes_data
    }

    # Escritura explícita en UTF-8
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(control_data, f, indent=4, ensure_ascii=False)
    
    print(f"ÉXITO: Control guardado en {file_path}")

# --- LÓGICA DE IMPORTACIÓN ---

def load_json_file(list_ui, *args):
    selected_items = cmds.textScrollList(list_ui, q=True, si=True)
    if not selected_items:
        cmds.warning("Selecciona un archivo de la lista")
        return

    full_path = os.path.join(CONTROLS_DIR, selected_items[0])
    
    # Lectura explícita en UTF-8
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
        
    print(f"ÉXITO: Control '{final_name}' importado.")

def show_import_selector(*args):
    if not os.path.exists(CONTROLS_DIR):
        os.makedirs(CONTROLS_DIR)
    
    all_files = [f for f in os.listdir(CONTROLS_DIR) if f.endswith('.json')]
    
    if not all_files:
        cmds.warning("No se encontraron archivos JSON en la librería.")
        return

    win = "ImportSelectorWin"
    if cmds.window(win, exists=True):
        cmds.deleteUI(win)

    cmds.window(win, title="Librería de Controles", w=250, h=350, s=True)
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
    cmds.button(l="ABRIR LIBRERÍA", h=40, bgc=(0.35, 0.45, 0.55), c=show_import_selector)
    
    cmds.separator(h=5, style="none")
    cmds.showWindow(win)

if __name__ == "__main__":
    ControladorUI()
    
def create_control_from_lib(lib_name, final_name):
    """
    Crea un controlador desde la librería sin usar la UI.
    :param lib_name: Nombre del archivo JSON (sin .json)
    :param final_name: Nombre que tendrá el control en Maya
    :return: str con el nombre del transform creado
    """
    file_path = os.path.join(CONTROLS_DIR, f"{lib_name}.json")
    
    if not os.path.exists(file_path):
        cmds.warning(f"No se encontró el control {lib_name} en la librería. Usando círculo por defecto.")
        return cmds.circle(n=final_name, nr=(0, 1, 0))[0]

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    created_shapes = []
    for i, shape_data in enumerate(data["shapes"]):
        crv = build_curve(shape_data, f"{final_name}_temp_{i}")
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
    