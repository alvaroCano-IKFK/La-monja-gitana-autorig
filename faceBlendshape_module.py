# -*- coding: utf-8 -*-
"""
faceBlendshape_module.py
========================

Tool de postproceso para el montaje de dos mallas:

    malla facial  -- skin a los _ENV del espacio "face" (no escala)
         |
     blendShape (front of chain)
         v
    malla body    -- skin a los _ENV del espacio "body" (escala con el global)

Va despues del build y del skinning, que es cuando existen las mallas y sus
skinCluster. Por eso es una tool de la UI y no un paso del build.

    create_face_blendshape(face, body)   monta la blendShape
    validate(face, body)                 comprueba que el montaje aguanta el
                                         global scale (lo que nos rompio el rig)
"""

import maya.cmds as cmds

import skinning_module


# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------
def _world_scale(node):
    m = cmds.getAttr(f"{node}.worldMatrix[0]")
    return [sum(v * v for v in m[i:i + 3]) ** 0.5 for i in (0, 4, 8)]


def _mesh_transform(node):
    """Acepta el transform o la shape. Devuelve el transform si es una malla."""
    if not node or not cmds.objExists(node):
        return None

    if cmds.nodeType(node) == "mesh":
        node = cmds.listRelatives(node, parent=True)[0]

    shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True,
                                type="mesh") or []
    return node if shapes else None


def _long_shapes(mesh):
    shapes = cmds.listRelatives(mesh, shapes=True, noIntermediate=True,
                                fullPath=True) or []
    return set(shapes)


def find_skin_cluster(mesh):
    """
    El skinCluster que deforma ESTA malla.

    No vale coger el primero del history: el history del body sube por la
    blendShape hasta la malla facial y se trae tambien su skinCluster.
    """
    mine = _long_shapes(mesh)
    for skin in cmds.ls(cmds.listHistory(mesh, pruneDagObjects=True) or [],
                        type="skinCluster"):
        geometry = cmds.skinCluster(skin, q=True, geometry=True) or []
        if mine & set(cmds.ls(geometry, long=True)):
            return skin
    return None


def find_face_blendshape(face_mesh, body_mesh):
    """La blendShape del body que tiene la facial como target, o None."""
    mine = _long_shapes(body_mesh)
    face_names = {face_mesh} | {s.split("|")[-1] for s in _long_shapes(face_mesh)}

    for bls in cmds.ls(cmds.listHistory(body_mesh, pruneDagObjects=True) or [],
                       type="blendShape"):
        geometry = cmds.blendShape(bls, q=True, geometry=True) or []
        if not mine & set(cmds.ls(geometry, long=True)):
            continue
        targets = cmds.blendShape(bls, q=True, target=True) or []
        if face_names & {t.split("|")[-1] for t in targets}:
            return bls
    return None


# ----------------------------------------------------------------------
# CREAR
# ----------------------------------------------------------------------
def create_face_blendshape(face_mesh, body_mesh, name=None):
    """
    BlendShape de la facial al body, SIEMPRE delante del skin.

    frontOfChain es lo que hace que el delta de expresion entre antes del
    skinCluster del body, y por tanto siga a la cabeza, al cuerpo y al global
    scale. Detras del skin, la expresion se quedaria clavada en el sitio.

    Si ya existe, no se duplica: se devuelve la que hay.
    """
    face = _mesh_transform(face_mesh)
    body = _mesh_transform(body_mesh)

    if not face or not body:
        cmds.warning("[FaceBLS] Hacen falta dos mallas: la facial y la de body.")
        return None
    if face == body:
        cmds.warning("[FaceBLS] La facial y el body son la misma malla.")
        return None

    face_vtx = cmds.polyEvaluate(face, vertex=True)
    body_vtx = cmds.polyEvaluate(body, vertex=True)
    if face_vtx != body_vtx:
        cmds.warning(f"[FaceBLS] Topologias distintas: {face} tiene {face_vtx} "
                     f"vertices y {body} {body_vtx}. La blendShape necesita la "
                     "misma malla.")
        return None

    existing = find_face_blendshape(face, body)
    if existing:
        print(f"[FaceBLS] Ya existe '{existing}' ({face} -> {body}). No se toca.")
        return existing

    bls = cmds.blendShape(face, body, frontOfChain=True,
                          name=name or f"{body}_face_BLS")[0]
    cmds.setAttr(f"{bls}.weight[0]", 1.0)

    print(f"[FaceBLS] '{bls}' creada: {face} -> {body}, delante del skin.")
    return bls


# ----------------------------------------------------------------------
# VALIDAR
# ----------------------------------------------------------------------
def validate(face_mesh, body_mesh, rig_name="Character", scale_factor=2.0):
    """
    Comprueba el montaje de dos mallas. No cambia nada de la escena: la prueba
    de escala devuelve el Global_Scale a su valor aunque algo falle.

    1. La blendShape va delante del skin del body.
    2. Ningun joint pesa en las dos mallas (esa zona se deformaria dos veces).
    3. Las influencias de la facial estan en faceSKN_GRP y las del body no.
    4. Prueba de escala: con el global multiplicado, la facial no se mueve,
       las influencias del body escalan y las de la facial no.

    Returns:
        bool: True si todo esta bien.
    """
    face = _mesh_transform(face_mesh)
    body = _mesh_transform(body_mesh)
    if not face or not body:
        cmds.warning("[FaceBLS] Hacen falta dos mallas: la facial y la de body.")
        return False

    report = []
    problems = []

    def ok(text):
        report.append(f"   OK   {text}")

    def bad(text):
        problems.append(text)
        report.append(f"   MAL  {text}")

    body_skin = find_skin_cluster(body)
    face_skin = find_skin_cluster(face)
    bls = find_face_blendshape(face, body)

    if not body_skin:
        bad(f"{body} no tiene skinCluster.")
    if not face_skin:
        bad(f"{face} no tiene skinCluster.")
    if not bls:
        bad(f"No hay blendShape de {face} a {body}. Usa CREATE BLENDSHAPE.")

    # 1. Orden de deformers. listHistory va del ultimo aplicado al primero, asi
    #    que el skin tiene que salir ANTES que la blendShape en la lista.
    if bls and body_skin:
        history = cmds.listHistory(body, pruneDagObjects=True) or []
        if history.index(body_skin) < history.index(bls):
            ok(f"'{bls}' va delante de '{body_skin}'.")
        else:
            bad(f"'{bls}' va DETRAS del skin. Arreglo: "
                f"cmds.reorderDeformers('{body_skin}', '{bls}', '{body}')")

    if not (body_skin and face_skin):
        _print_report(face, body, report, problems)
        return not problems

    body_inf = set(cmds.skinCluster(body_skin, q=True, weightedInfluence=True) or [])
    face_inf = set(cmds.skinCluster(face_skin, q=True, weightedInfluence=True) or [])

    # 2. Joints con peso en las dos mallas
    both = sorted(body_inf & face_inf)
    if both:
        bad(f"{len(both)} joints pesan en las dos mallas: {both}")
    else:
        ok("Ningun joint pesa en las dos mallas.")

    # 3. Espacios de skin
    face_grp = f"|{rig_name}_faceSKN_GRP|"

    def in_face_space(joint):
        return face_grp in cmds.ls(joint, long=True)[0]

    misplaced_face = sorted(j for j in face_inf if not in_face_space(j))
    misplaced_body = sorted(j for j in body_inf if in_face_space(j))

    if misplaced_face:
        bad(f"Influencias de la facial fuera de {rig_name}_faceSKN_GRP: "
            f"{misplaced_face}. Marca sus _JNT con "
            "skinning_module.mark_skin_space(..., 'face') en su modulo.")
    else:
        ok(f"Todas las influencias de la facial en {rig_name}_faceSKN_GRP.")

    if misplaced_body:
        bad(f"Influencias del body dentro de {rig_name}_faceSKN_GRP: "
            f"{misplaced_body}. No escalaran con el personaje.")
    else:
        ok("Ninguna influencia del body en el espacio face.")

    # 4. Prueba de escala
    _scale_test(face, body_inf, face_inf, rig_name, scale_factor, ok, bad)

    _print_report(face, body, report, problems)
    return not problems


def _scale_test(face, body_inf, face_inf, rig_name, factor, ok, bad):
    plug = f"{rig_name}_global_CTL.Global_Scale"

    if not cmds.objExists(plug):
        bad(f"No existe {plug}: no se puede hacer la prueba de escala.")
        return
    if not cmds.getAttr(plug, settable=True):
        bad(f"{plug} esta conectado o tiene keys: no se puede hacer la prueba "
            "de escala. Quitalos o pruebalo en una escena limpia.")
        return

    old_value = cmds.getAttr(plug)
    joints = sorted(body_inf | face_inf)

    bbox_before = cmds.exactWorldBoundingBox(face)
    scale_before = {j: _world_scale(j) for j in joints}

    try:
        cmds.setAttr(plug, old_value * factor)

        bbox_after = cmds.exactWorldBoundingBox(face)
        scale_after = {j: _world_scale(j) for j in joints}
    finally:
        cmds.setAttr(plug, old_value)

    tolerance = 1e-3

    # La facial tiene que quedarse exactamente igual
    drift = max(abs(a - b) for a, b in zip(bbox_before, bbox_after))
    if drift > tolerance:
        bad(f"La facial se mueve al escalar el global (desviacion {drift:.3f}). "
            "La blendShape le pasara esa escala al body.")
    else:
        ok("La facial no se mueve al escalar el global.")

    def ratio_wrong(joint, expected):
        return any(abs(after / before - expected) > tolerance
                   for before, after in zip(scale_before[joint], scale_after[joint])
                   if before > 1e-6)

    body_wrong = [j for j in sorted(body_inf) if ratio_wrong(j, factor)]
    face_wrong = [j for j in sorted(face_inf) if ratio_wrong(j, 1.0)]

    if body_wrong:
        bad(f"{len(body_wrong)} influencias del body no escalan con el global: "
            f"{body_wrong}")
    else:
        ok("Todas las influencias del body escalan con el global.")

    if face_wrong:
        bad(f"{len(face_wrong)} influencias de la facial escalan con el global: "
            f"{face_wrong}")
    else:
        ok("Ninguna influencia de la facial escala con el global.")


def _print_report(face, body, report, problems):
    print(f"\n[FaceBLS] Validacion {face} -> {body}")
    print("\n".join(report))
    if problems:
        cmds.warning(f"[FaceBLS] {len(problems)} problema(s). Mira el script editor.")
    else:
        print("[FaceBLS] Todo correcto.")