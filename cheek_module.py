import maya.cmds as cmds

import controlsLibrary
from groups_module import ControlsGroups
import skinning_module


class CheekModule(object):
    """
    Mejillas: tres controles por lado (inner, mid, outer), cada uno con su
    joint, su setup local y su rivet sobre la cara.

    Por cada mejilla:

        GUIA ---------> JOINT  (posicion y orientacion)
                 +----> CONTROL + jerarquia (GRP > SPC > OFF > SDK > NEG > ANIM)

        SETUP LOCAL
            ctrl.matrix  -> MMX.matrixIn[0]
            ANIM.matrix  -> MMX.matrixIn[1]
            MMX.matrixSum -> Local_TRN.offsetParentMatrix   (Local_OFF > Local_TRN)
            Local_TRN.worldMatrix[0] -> JNT.offsetParentMatrix   (JNT a ceros)

        RIVET
            ctrl.worldMatrix[0] -> DCM.inputMatrix
            DCM.outputTranslate -> CPOM.inPosition
            Rivet_GEO.outMesh   -> CPOM.inMesh
            CPOM.parameterU/V   == copiados (sin conexion) ==> UVP.coordinate[0]
            Rivet_GEO.outMesh   -> UVP.deformedGeometry
            UVP.outputMatrix[0] -> LOC.offsetParentMatrix
            UVP.outputMatrix[0] -> DCM.inputMatrix ; DCM.outputTranslate -> GRP.translate

        NEGACION
            MMX.matrixSum -> INV.inputMatrix
            INV.outputMatrix -> NEG.offsetParentMatrix    (NEG justo encima del ANIM)

    El NEG cancela el movimiento propio del control (ctrl + ANIM), asi que el
    control no se mueve por si solo: lo que lo mueve es el GRP, que va pegado
    al rivet. En cuanto el rivet se deforme como la cara (skinneado igual),
    mover el control mueve el joint, el joint deforma el rivet y el rivet
    arrastra al control. Sin doble transformacion.

    El rivet (las caras duplicadas) es un paso a mano ANTES del build, desde
    Tools > Cheek rivets. Si falta, la mejilla se construye igual pero sin la
    parte del rivet ni el NEG: el control mueve el joint en local y ya.
    """

    MODULE_TYPE = "cheek"

    # De dentro afuera. El orden es el de los botones de la UI.
    KEYS = ("inner", "mid", "outer")

    # Grupo de la jerarquia del control que entra en el matrixIn[1] del
    # multMatrix y encima del cual se mete el NEG.
    #
    # ANIM y no SPC: es el padre directo del control. Asi la cancelacion es
    # exacta pase lo que pase en los grupos de arriba (un set driven key en el
    # SDK, por ejemplo). Con SPC u OFF la cuenta solo cuadra mientras todos
    # los grupos de entre medias esten a cero.
    LOCAL_GROUP = "ANIM"

    # Shape del control. Va en la SHAPE, nunca en el transform (mismo criterio
    # que el ojo): 90 en X porque la libreria los dibuja tumbados.
    CONTROL_STYLE = "circleControl"
    CV_ROTATION = (90.0, 0.0, 0.0)
    CV_SCALE = 0.25

    # Los joints de mejilla solo deforman la malla facial, igual que los
    # AimEnd del ojo: van al espacio "face" del SkinningModule. A False se
    # quedan en el espacio body.
    MARK_FACE_SKIN_SPACE = True

    def __init__(self, rig_name="Character", side="L", root_instance=None,
                 features=None):
        self.rig_name = rig_name
        self.side = side
        self.prefix = f"{side}_{rig_name}"
        self.root_instance = root_instance
        self.features = set(features or [])

        self.group_maker = ControlsGroups()

        # key -> diccionario con todos los nodos de esa mejilla
        self.cheeks = {}

        self.systems_group = None
        self.controls_group = None
        self.joints_group = None

    # ------------------------------------------------------------------
    # CONVENCION DE NOMBRES (la usan la UI y el build)
    # ------------------------------------------------------------------
    @staticmethod
    def guide_name(side, key):
        """Guia de una mejilla. Sin sufijo _JNT: el skinning duplicaria la guia."""
        return f"{side}_cheek_{key}"

    @staticmethod
    def base_name(key):
        """cheekInner / cheekMid / cheekOuter"""
        return f"cheek{key[0].upper()}{key[1:]}"

    @staticmethod
    def rivet_name(side, rig_name, key):
        """Malla del rivet: las caras duplicadas de esa mejilla."""
        return f"{side}_{rig_name}_{CheekModule.base_name(key)}Rivet_GEO"

    # ------------------------------------------------------------------
    # RIVET DESDE LA SELECCION (paso a mano, antes del build)
    # ------------------------------------------------------------------
    @staticmethod
    def _component_transform(component):
        """Transform (ruta larga) de la malla a la que pertenece un componente."""
        node = component.split(".", 1)[0]

        if cmds.nodeType(node) == "mesh":
            parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
            node = parents[0] if parents else node

        found = cmds.ls(node, long=True) or []
        return found[0] if found else None

    @staticmethod
    def _index_ranges(indices):
        """[1, 2, 3, 7, 8] -> [(1, 3), (7, 8)]. Para borrar caras en bloque."""
        ranges = []
        for index in sorted(indices):
            if ranges and index == ranges[-1][1] + 1:
                ranges[-1][1] = index
            else:
                ranges.append([index, index])
        return [tuple(r) for r in ranges]

    @staticmethod
    def build_rivet_from_selection(side, rig_name, key, components=None):
        """
        Duplica las caras seleccionadas en una malla aparte: el rivet de esa
        mejilla.

        Acepta caras, edges o vertices: todo se convierte a caras. Se duplica
        la malla entera y se borran las caras que no estaban seleccionadas,
        asi los indices de lo que queda no dependen de nada raro.

        La copia sale limpia para que outMesh y el mundo coincidan:
        - sin la shape Orig (si la malla venia skinneada),
        - en la raiz del mundo,
        - con las transformaciones congeladas,
        - sin history.
        Esto importa porque el CPOM y el uvPin leen outMesh, que esta en el
        espacio del objeto. Con el transform a identidad, ese espacio es el
        mundo.

        Devuelve (nombre_del_rivet, numero_de_caras) o None.
        """
        if components is None:
            components = cmds.ls(selection=True, flatten=True) or []

        components = [item for item in components if "." in item]
        if not components:
            cmds.warning("[CheekModule] Selecciona las caras de la mejilla, no "
                         "el objeto entero.")
            return None

        faces = cmds.ls(cmds.polyListComponentConversion(components, toFace=True) or [],
                        flatten=True)
        if not faces:
            cmds.warning("[CheekModule] La seleccion no da ninguna cara.")
            return None

        meshes = {CheekModule._component_transform(face) for face in faces}
        meshes.discard(None)
        if len(meshes) != 1:
            cmds.warning("[CheekModule] Las caras tienen que ser de UNA sola "
                         f"malla (hay {len(meshes)}).")
            return None

        source = meshes.pop()
        keep = {int(face.rsplit("[", 1)[1].rstrip("]")) for face in faces}

        name = CheekModule.rivet_name(side, rig_name, key)
        if cmds.objExists(name):
            cmds.delete(name)

        rivet = cmds.duplicate(source, name=name, returnRootsOnly=True)[0]

        # Fuera lo que no sea la shape visible: la Orig del skinCluster y
        # cualquier transform hijo que colgase de la malla.
        for child in cmds.listRelatives(rivet, children=True, fullPath=True) or []:
            if cmds.nodeType(child) != "mesh" or cmds.getAttr(f"{child}.intermediateObject"):
                cmds.delete(child)

        shapes = cmds.listRelatives(rivet, shapes=True, fullPath=True) or []
        if not shapes:
            cmds.delete(rivet)
            cmds.warning(f"[CheekModule] {source} no tiene shape de malla.")
            return None

        cmds.rename(shapes[0], f"{name}Shape")

        for attribute in ("translate", "rotate", "scale"):
            for axis in "XYZ":
                cmds.setAttr(f"{rivet}.{attribute}{axis}", lock=False)

        if cmds.listRelatives(rivet, parent=True):
            rivet = cmds.parent(rivet, world=True)[0]

        cmds.makeIdentity(rivet, apply=True, translate=True, rotate=True, scale=True)

        total = cmds.polyEvaluate(rivet, face=True)
        discard = [index for index in range(total) if index not in keep]
        if discard:
            cmds.delete([f"{rivet}.f[{a}:{b}]"
                         for a, b in CheekModule._index_ranges(discard)])

        cmds.delete(rivet, constructionHistory=True)
        cmds.select(clear=True)

        face_count = cmds.polyEvaluate(rivet, face=True)
        print(f"[CheekModule] {name}: {face_count} caras desde {source}.")

        return rivet, face_count

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_matrix_nodes():
        """decomposeMatrix e inverseMatrix viven en el plugin matrixNodes."""
        try:
            if not cmds.pluginInfo("matrixNodes", query=True, loaded=True):
                cmds.loadPlugin("matrixNodes", quiet=True)
        except Exception:
            pass

    def _resolve_guide(self, key):
        name = self.guide_name(self.side, key)
        return name if cmds.objExists(name) else None

    def _visible_shape(self, transform):
        shapes = cmds.listRelatives(transform, shapes=True, noIntermediate=True,
                                    fullPath=True) or []
        return shapes[0] if shapes else None

    def _ensure_group(self, group_name, parent_group=None):
        """Mismo helper que el ojo: lo crea si no existe y lo cuelga donde toca."""
        if cmds.objExists(group_name):
            group_node = group_name
        else:
            group_node = cmds.group(em=True, world=True, n=group_name)

        if parent_group and cmds.objExists(parent_group):
            current_parent = cmds.listRelatives(group_node, parent=True) or []
            if not current_parent or current_parent[0] != parent_group:
                cmds.parent(group_node, parent_group, relative=True)

        return group_node

    def _face_systems_root(self):
        """C_<rig>_face_GRP, bajo el rig_GRP. Compartido con ojo, boca y jaw."""
        rig_grp = f"{self.rig_name}_rig_GRP"
        if self.root_instance is not None and hasattr(self.root_instance, "get_rig_grp"):
            rig_grp = self.root_instance.get_rig_grp()

        parent = rig_grp if cmds.objExists(rig_grp) else None
        return self._ensure_group(f"C_{self.rig_name}_face_GRP", parent)

    def _face_controls_root(self):
        """C_<rig>_faceControls_GRP, bajo el local_CTL. Sigue a la cabeza."""
        local_ctl = f"{self.rig_name}_local_CTL"
        if self.root_instance is not None:
            local_ctl = getattr(self.root_instance, "localCtl", None) or local_ctl

        parent = local_ctl if cmds.objExists(local_ctl) else None
        return self._ensure_group(f"C_{self.rig_name}_faceControls_GRP", parent)

    def _build_containers(self):
        """
        Grupos del modulo. Se crean ANTES que nada para que cada pieza entre en
        su sitio al crearse: el GRP del control tiene que estar ya en su padre
        definitivo cuando se le conecta el translate, porque un translate
        conectado ya no se puede compensar al reparentar.

        Mismo reparto que el ojo:
          - el SISTEMA (joints, setup local, rivets) cuelga de un grupo que no
            hereda nada: se queda en bind para que la malla facial solo pase
            el delta de expresion.
          - los CONTROLES cuelgan del faceControls_GRP, que sigue a la cabeza.
        """
        center = f"C_{self.rig_name}"

        cheeks_grp = self._ensure_group(f"{center}_cheeks_GRP", self._face_systems_root())
        cmds.setAttr(f"{cheeks_grp}.inheritsTransform", 0)

        self.systems_group = self._ensure_group(f"{self.prefix}_cheeks_GRP", cheeks_grp)
        self.joints_group = self._ensure_group(f"{self.prefix}_cheekJoints_GRP",
                                               self.systems_group)

        controls_grp = self._ensure_group(f"{center}_cheeksControls_GRP",
                                          self._face_controls_root())
        self.controls_group = self._ensure_group(f"{self.prefix}_cheeksControls_GRP",
                                                 controls_grp)

    def _clean(self, key):
        """
        Borra lo que dejo una build anterior de esa mejilla. Aqui no se
        reutiliza nada: con el NEG metido en medio de la jerarquia y las
        conexiones ya hechas, recolocar lo viejo da mas problemas que rehacerlo.
        El rivet NO se toca: es el paso a mano.
        """
        name = f"{self.prefix}_{self.base_name(key)}"

        nodes = [
            f"{name}_GRP", f"{name}_JNT", f"{name}Local_OFF", f"{name}Rivet_LOC",
            f"{name}Local_MMX", f"{name}Neg_INV",
            f"{name}Rivet_DCM", f"{name}Rivet_CPOM", f"{name}Rivet_UVP",
            f"{name}RivetPos_DCM",
        ]
        existing = [node for node in nodes if cmds.objExists(node)]
        if existing:
            cmds.delete(existing)

    # ------------------------------------------------------------------
    # UNA MEJILLA
    # ------------------------------------------------------------------
    def _build_joint(self, name, guide):
        """Joint en la posicion y orientacion de la guia."""
        cmds.select(clear=True)
        joint = cmds.joint(name=f"{name}_JNT")
        cmds.matchTransform(joint, guide, position=True, rotation=True)
        cmds.parent(joint, self.joints_group)
        cmds.select(clear=True)
        return joint

    def _build_control(self, name, joint):
        """Control con su jerarquia de grupos, colocado sobre el joint."""
        ctrl = controlsLibrary.create_control_from_lib(
            lib_name=self.CONTROL_STYLE, final_name=f"{name}_CTRL")
        controlsLibrary.transform_shape(ctrl, rotate=self.CV_ROTATION,
                                        scale=self.CV_SCALE)

        ctrl_grp = self.group_maker.create_rig_hierarchy(
            ctrl, joint, match_rotation=True, world_space=True)

        # Al grupo de controles conservando el mundo. Antes de conectar nada.
        cmds.parent(ctrl_grp, self.controls_group)

        return ctrl, ctrl_grp

    def _build_local(self, name, guide, ctrl, local_group, joint):
        """
        Setup local: el joint solo se entera de lo que el animador mueve el
        control (y su ANIM), no de donde este colgado el control.
        """
        mult = cmds.createNode("multMatrix", name=f"{name}Local_MMX")
        cmds.connectAttr(f"{ctrl}.matrix", f"{mult}.matrixIn[0]")
        cmds.connectAttr(f"{local_group}.matrix", f"{mult}.matrixIn[1]")

        local_off = cmds.group(em=True, name=f"{name}Local_OFF")
        cmds.matchTransform(local_off, guide, position=True, rotation=True)
        local_off = cmds.parent(local_off, self.systems_group)[0]

        # Hijo del OFF a ceros: es el que recibe la matriz.
        local_trn = cmds.group(em=True, name=f"{name}Local_TRN", parent=local_off)
        cmds.connectAttr(f"{mult}.matrixSum", f"{local_trn}.offsetParentMatrix")

        # El joint sale de la matriz del TRN. Sus canales a cero, o la
        # transformacion se aplicaria dos veces.
        cmds.connectAttr(f"{local_trn}.worldMatrix[0]", f"{joint}.offsetParentMatrix")
        for attribute in ("translate", "rotate", "jointOrient"):
            cmds.setAttr(f"{joint}.{attribute}", 0, 0, 0)

        return mult, local_off, local_trn

    def _build_rivet(self, name, key, ctrl, ctrl_grp, local_group, mult):
        """
        Rivet + NEG. Devuelve el diccionario de nodos, o {} si no hay rivet.
        """
        rivet = self.rivet_name(self.side, self.rig_name, key)
        if not cmds.objExists(rivet):
            cmds.warning(f"[CheekModule] No existe {rivet}. Selecciona las caras "
                         f"en Tools > Cheek rivets. {name} se construye sin rivet: "
                         f"el control mueve el joint pero no sigue a la cara.")
            return {}

        # El rivet al grupo del sistema, que esta en bind igual que el.
        #
        # ANTES de buscar la shape: _visible_shape devuelve la ruta larga, y
        # reparentar la cambia. Con la ruta de antes del parent, el connectAttr
        # no encuentra el nodo.
        if not cmds.listRelatives(rivet, parent=True):
            rivet = cmds.parent(rivet, self.systems_group)[0]

        rivet_shape = self._visible_shape(rivet)
        if not rivet_shape:
            cmds.warning(f"[CheekModule] {rivet} no tiene shape visible.")
            return {}

        # 1. Donde esta el control -> punto mas cercano de la malla
        ctrl_position = cmds.createNode("decomposeMatrix", name=f"{name}Rivet_DCM")
        cmds.connectAttr(f"{ctrl}.worldMatrix[0]", f"{ctrl_position}.inputMatrix")

        closest = cmds.createNode("closestPointOnMesh", name=f"{name}Rivet_CPOM")
        cmds.connectAttr(f"{rivet_shape}.outMesh", f"{closest}.inMesh")
        cmds.connectAttr(f"{ctrl_position}.outputTranslate", f"{closest}.inPosition")

        # Se lee AHORA, con el control todavia sobre la guia: despues el GRP
        # pasa a ir conducido por el propio uvPin.
        u_value = cmds.getAttr(f"{closest}.parameterU")
        v_value = cmds.getAttr(f"{closest}.parameterV")

        # 2. uvPin con las UV COPIADAS, sin conexion
        uv_pin = cmds.createNode("uvPin", name=f"{name}Rivet_UVP")
        cmds.setAttr(f"{uv_pin}.coordinate[0].coordinateU", u_value)
        cmds.setAttr(f"{uv_pin}.coordinate[0].coordinateV", v_value)
        cmds.connectAttr(f"{rivet_shape}.outMesh", f"{uv_pin}.deformedGeometry")
        # originalGeometry se deja libre: se conecta a mano con el skinning
        # hecho (la shape Orig del PROPIO rivet, misma topologia).

        # 3. Locator para verlo en el viewport
        locator = cmds.spaceLocator(name=f"{name}Rivet_LOC")[0]
        cmds.connectAttr(f"{uv_pin}.outputMatrix[0]", f"{locator}.offsetParentMatrix")
        locator = cmds.parent(locator, self.systems_group, relative=True)[0]

        # 4. NEG justo encima del grupo local (ANIM). Nace a ceros dentro de su
        # padre, y el ANIM entra en relative para conservar sus ceros.
        local_parent = cmds.listRelatives(local_group, parent=True)[0]
        neg = cmds.group(em=True, name=f"{name}_NEG", parent=local_parent)
        cmds.parent(local_group, neg, relative=True)

        inverse = cmds.createNode("inverseMatrix", name=f"{name}Neg_INV")
        cmds.connectAttr(f"{mult}.matrixSum", f"{inverse}.inputMatrix")
        cmds.connectAttr(f"{inverse}.outputMatrix", f"{neg}.offsetParentMatrix")

        # 5. El GRP del control va al punto del rivet
        rivet_position = cmds.createNode("decomposeMatrix", name=f"{name}RivetPos_DCM")
        cmds.connectAttr(f"{uv_pin}.outputMatrix[0]", f"{rivet_position}.inputMatrix")
        cmds.connectAttr(f"{rivet_position}.outputTranslate", f"{ctrl_grp}.translate")

        return {
            "rivet": rivet, "ctrl_position": ctrl_position, "closest": closest,
            "uv": (u_value, v_value), "uv_pin": uv_pin, "locator": locator,
            "neg": neg, "inverse": inverse, "rivet_position": rivet_position,
        }

    def _build_cheek(self, key):
        guide = self._resolve_guide(key)
        if not guide:
            cmds.warning(f"[CheekModule] Falta la guia "
                         f"{self.guide_name(self.side, key)}. Se salta.")
            return None

        self._clean(key)

        name = f"{self.prefix}_{self.base_name(key)}"

        joint = self._build_joint(name, guide)
        ctrl, ctrl_grp = self._build_control(name, joint)

        local_group = f"{name}_{self.LOCAL_GROUP}"
        if not cmds.objExists(local_group):
            cmds.warning(f"[CheekModule] No existe {local_group}. Revisa "
                         f"LOCAL_GROUP contra los sufijos de groups_module.")
            return None

        mult, local_off, local_trn = self._build_local(name, guide, ctrl,
                                                       local_group, joint)

        data = {
            "guide": guide, "joint": joint, "ctrl": ctrl, "ctrl_grp": ctrl_grp,
            "local_group": local_group, "mult": mult,
            "local_off": local_off, "local_trn": local_trn,
        }
        data.update(self._build_rivet(name, key, ctrl, ctrl_grp, local_group, mult))

        self.cheeks[key] = data
        return data

    # ------------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------------
    def build(self):
        missing = [self.guide_name(self.side, key) for key in self.KEYS
                   if not self._resolve_guide(key)]
        if len(missing) == len(self.KEYS):
            cmds.warning(f"[CheekModule] {self.side}: no hay guias de mejilla "
                         f"({', '.join(missing)}). Se salta.")
            return None

        self._ensure_matrix_nodes()
        self._build_containers()

        self.cheeks = {}
        for key in self.KEYS:
            self._build_cheek(key)

        if not self.cheeks:
            return None

        if self.MARK_FACE_SKIN_SPACE and hasattr(skinning_module, "mark_skin_space"):
            skinning_module.mark_skin_space(
                [data["joint"] for data in self.cheeks.values()],
                skinning_module.FACE_SPACE)

        cmds.select(clear=True)

        without_rivet = [key for key, data in self.cheeks.items() if "uv_pin" not in data]
        print(f"[CheekModule] {self.prefix}: {len(self.cheeks)} mejillas"
              + (f" (sin rivet: {', '.join(without_rivet)})" if without_rivet else "")
              + ".")

        return self.systems_group